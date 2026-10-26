"""Pruebas de la memoria del motor en OCI Object Storage, sin red ni cuenta de OCI."""

import pytest

from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import StorageError
from communitylab_backend.infrastructure.oci_state import MirroredDoubtHistory, MirroredKnowledgeBase, OCIFileMirror


class FakeServiceError(Exception):
    """Error falso con ``status`` como el de ``oci.exceptions.ServiceError``."""

    def __init__(self, status):
        """Guarda el código HTTP simulado y un mensaje con datos sensibles."""
        super().__init__("ocid1.tenancy.oc1..secreto-de-la-cuenta")
        self.status = status


class FakeRaw:
    """Imita ``response.data.raw`` del SDK: entrega el contenido por partes."""

    def __init__(self, content):
        """Guarda el contenido del objeto."""
        self.content = content

    def stream(self, size, decode_content=False):
        """Entrega el contenido en partes de ``size`` bytes."""
        for start in range(0, len(self.content), size):
            yield self.content[start:start + size]


class FakeResponse:
    """Respuesta falsa de ``get_object``."""

    def __init__(self, content):
        """Arma ``data.raw`` con el contenido."""
        self.data = type("Data", (), {"raw": FakeRaw(content)})()


class FakeBucket:
    """Bucket en memoria: guarda objetos por nombre o lanza el error configurado."""

    def __init__(self, objects=None, error=None):
        """Recibe los objetos iniciales y el error a lanzar."""
        self.objects, self.error, self.puts = dict(objects or {}), error, []

    def get_object(self, namespace_name, bucket_name, object_name):
        """Devuelve el objeto, un 404 si no existe o el error configurado."""
        if self.error:
            raise self.error
        if object_name not in self.objects:
            raise FakeServiceError(404)
        return FakeResponse(self.objects[object_name])

    def put_object(self, namespace_name, bucket_name, object_name, body, **kwargs):
        """Guarda el objeto o lanza el error configurado."""
        if self.error:
            raise self.error
        self.objects[object_name] = body
        self.puts.append(object_name)


def mirror(bucket):
    """Espejo de prueba sobre el bucket falso."""
    return OCIFileMirror("ns", "bk", client=bucket)


def test_restore_replaces_local_file_with_bucket_copy(tmp_path):
    """Al arrancar, la copia del bucket reemplaza a la local."""
    local = tmp_path / "historial_dudas.db"
    local.write_bytes(b"vieja")
    assert mirror(FakeBucket({"estado/historial_dudas.db": b"x" * 3_000_000})).restore(local) is True
    assert local.read_bytes() == b"x" * 3_000_000 and not (tmp_path / "historial_dudas.db.tmp").exists()


def test_first_start_keeps_local_file(tmp_path):
    """Si el bucket todavía no tiene el archivo, se usa la copia local sin error."""
    local = tmp_path / "motor_educativo.db"
    local.write_bytes(b"base del repositorio")
    assert mirror(FakeBucket()).restore(local) is False
    assert local.read_bytes() == b"base del repositorio"


def test_restore_errors_stop_without_leaking(tmp_path):
    """Sin permiso, no se sigue con una memoria vacía y el mensaje no trae identificadores."""
    with pytest.raises(StorageError, match="permiso") as error:
        mirror(FakeBucket(error=FakeServiceError(403))).restore(tmp_path / "historial_dudas.db")
    assert "ocid1" not in str(error.value)


def test_save_uploads_under_prefix(tmp_path):
    """Sube el archivo completo con el nombre ``<prefijo>/<archivo>``."""
    local = tmp_path / "motor_educativo.db"
    local.write_bytes(b"contenido")
    bucket = FakeBucket()
    assert mirror(bucket).save(local) == "oci://ns/bk/estado/motor_educativo.db"
    assert bucket.objects["estado/motor_educativo.db"] == b"contenido"


class FakeHistory:
    """Historial local falso que dice cuántas dudas guardó."""

    def __init__(self, saved):
        """Fija cuántas filas dirá que guardó o actualizó."""
        self.saved = saved

    def record(self, request_id, community, doubts):
        """Simula guardar dudas."""
        return self.saved

    def attach_faqs(self, topic_key, faq_ids):
        """Simula marcar un tema."""
        return self.saved

    def ranking(self, days=None, limit=20):
        """Ranking vacío."""
        return {"total_doubts": 0, "topics": []}


def test_history_uploads_only_when_something_changed(tmp_path):
    """Guardar dudas sube el historial; las lecturas y los lotes sin dudas no tocan OCI."""
    local = tmp_path / "historial_dudas.db"
    local.write_bytes(b"historial")
    bucket = FakeBucket()
    MirroredDoubtHistory(FakeHistory(0), mirror(bucket), local).record("r1", "c", [])
    history = MirroredDoubtHistory(FakeHistory(2), mirror(bucket), local)
    history.ranking()
    assert bucket.puts == []
    history.record("r2", "c", [{"topic": "x"}])
    history.attach_faqs("x", ["faq-1"])
    assert bucket.puts == ["estado/historial_dudas.db", "estado/historial_dudas.db"]


class FakeBase:
    """Base local falsa: agrega FAQs salvo en vista previa."""

    def add_faqs(self, rows, dry_run):
        """Simula la carga."""
        return {"new_ids": [] if dry_run else ["faq-1"], "warnings": []}


def test_knowledge_base_uploads_after_adding_and_warns_on_failure(tmp_path):
    """Agregar FAQs sube la base; si OCI falla, las FAQs quedan y la respuesta avisa."""
    local = tmp_path / "motor_educativo.db"
    local.write_bytes(b"base")
    bucket = FakeBucket()
    base = MirroredKnowledgeBase(FakeBase(), mirror(bucket), local)
    base.add_faqs([{}], dry_run=True)
    assert bucket.puts == []
    base.add_faqs([{}], dry_run=False)
    assert bucket.puts == ["estado/motor_educativo.db"]
    broken = MirroredKnowledgeBase(FakeBase(), mirror(FakeBucket(error=FakeServiceError(500))), local)
    result = broken.add_faqs([{}], dry_run=False)
    assert result["new_ids"] == ["faq-1"] and "no se pudo respaldar la base en OCI" in result["warnings"][0]


def test_state_provider_oci_restores_once_and_wraps_history(tmp_path, monkeypatch):
    """Con ``STATE_PROVIDER=oci`` la memoria se restaura una sola vez y el historial queda respaldado."""
    from communitylab_backend.api import dependencies

    restored = []

    class FakeMirror:
        """Espejo falso que registra las restauraciones."""

        def __init__(self, *args, **kwargs):
            """No abre ninguna sesión."""

        def restore(self, path):
            """Registra el archivo restaurado."""
            restored.append(path.name)
            return True

    monkeypatch.setattr(dependencies, "OCIFileMirror", FakeMirror)
    dependencies._state_mirror.cache_clear()
    values = {"state_provider": "oci", "oci_namespace": "ns", "oci_bucket": "bk", "history_db_path": tmp_path / "h.db", "faq_db_path": tmp_path / "f.db"}
    try:
        history = dependencies.build_history(Settings(_env_file=None, **values))
        dependencies.build_knowledge(Settings(_env_file=None, **values))
        assert type(history).__name__ == "MirroredDoubtHistory"
        assert restored == ["h.db", "f.db"]
        assert type(dependencies.build_history(Settings(_env_file=None))).__name__ == "DoubtHistory"
    finally:
        dependencies._state_mirror.cache_clear()
