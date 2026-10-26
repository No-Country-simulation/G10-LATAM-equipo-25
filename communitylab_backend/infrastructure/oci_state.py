"""Memoria del motor en OCI Object Storage, para desplegar en cualquier servidor.

Pertenece a infraestructura. El motor guarda su memoria en dos archivos
SQLite: el historial de dudas (``data/historial_dudas.db``) y la base de
conocimiento (``data/motor_educativo.db``, que crece al agregar FAQs). En un
servidor cuyo disco se borra al reiniciar (por ejemplo, Hugging Face Spaces)
esa memoria se perdería. Con ``STATE_PROVIDER=oci``:

- al arrancar, ``OCIFileMirror.restore`` baja la última copia de cada archivo
  desde el bucket (si todavía no existe, se usa la copia local del repositorio);
- después de cada escritura, ``MirroredDoubtHistory`` y
  ``MirroredKnowledgeBase`` vuelven a subir el archivo.

Las dos clases envuelven a los adaptadores locales y cumplen los mismos
contratos (``DoubtHistoryPort`` y ``KnowledgeBasePort``): ni el grafo ni la
API se enteran de dónde vive la memoria. Usa la misma autenticación y el mismo
bucket que ``OCIObjectStorageAdapter``. Los errores se traducen a
``StorageError`` con mensajes seguros, sin credenciales ni rutas.
"""

import logging
import os
import re
from pathlib import Path

from communitylab_backend.domain.errors import ProviderUnavailableError, StorageError
from communitylab_backend.infrastructure.oci_storage import AUTH_CONFIG_FILE, _build_client, _no_retry

logger = logging.getLogger(__name__)
_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class OCIFileMirror:
    """Copia archivos locales a un bucket de OCI y los recupera al arrancar.

    Cada archivo se guarda como ``<prefijo>/<nombre del archivo>``; por
    ejemplo ``estado/historial_dudas.db``. ``client`` permite usar un cliente
    falso en pruebas.
    """

    def __init__(self, namespace: str | None, bucket: str | None, region: str | None = None, prefix: str = "estado", auth: str = AUTH_CONFIG_FILE, config_file: Path = Path("~/.oci/config"), profile: str = "DEFAULT", timeout_seconds: float = 30.0, client=None):
        """Configura el bucket, el prefijo y la sesión con OCI.

        Produce ``ProviderUnavailableError`` si falta el namespace o el
        bucket, si el prefijo no es seguro o si no se puede iniciar sesión.
        """
        if not namespace or not bucket:
            raise ProviderUnavailableError("Falta configurar OCI_NAMESPACE y OCI_BUCKET para guardar la memoria del motor")
        if not _SAFE_PART.match(prefix):
            raise ProviderUnavailableError("El prefijo de la memoria en OCI solo admite letras, números, punto, guion y guion bajo")
        self.namespace, self.bucket, self.prefix = namespace, bucket, prefix
        self._client = client if client is not None else _build_client(auth, region, config_file, profile, timeout_seconds)

    def object_name(self, path: Path) -> str:
        """Nombre del objeto en el bucket para el archivo local ``path``."""
        return f"{self.prefix}/{Path(path).name}"

    def restore(self, path: Path) -> bool:
        """Baja la copia del bucket a ``path`` y retorna ``True`` si existía.

        Si el bucket todavía no tiene ese archivo (primer arranque), deja el
        archivo local como está y retorna ``False``. Escribe primero en un
        archivo temporal y lo reemplaza de una vez, para no dejar una base a
        medias. Produce ``StorageError`` si OCI no responde o rechaza el
        acceso: en ese caso el motor no debe seguir, porque escribiría sobre
        una memoria vacía y la subiría encima de la buena.
        """
        path = Path(path)
        try:
            response = self._client.get_object(self.namespace, self.bucket, self.object_name(path))
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                logger.info("state_not_found", extra={"provider": "oci"})
                return False
            raise _translate_error(exc, "bajar") from exc
        temporary = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(temporary, "wb") as file:
                for chunk in response.data.raw.stream(1024 * 1024, decode_content=False):
                    file.write(chunk)
            os.replace(temporary, path)
        except Exception as exc:
            raise StorageError("No se pudo escribir en disco la memoria bajada de OCI") from exc
        return True

    def save(self, path: Path) -> str:
        """Sube el archivo ``path`` al bucket y retorna su ubicación ``oci://``.

        Reemplaza la copia anterior. Sin reintentos automáticos. Produce
        ``StorageError`` si el archivo no se puede leer o si OCI rechaza o no
        completa la escritura.
        """
        path = Path(path)
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise StorageError("No se pudo leer el archivo de memoria para subirlo a OCI") from exc
        name = self.object_name(path)
        try:
            self._client.put_object(self.namespace, self.bucket, name, body, content_type="application/octet-stream", retry_strategy=_no_retry())
        except Exception as exc:
            raise _translate_error(exc, "subir") from exc
        return f"oci://{self.namespace}/{self.bucket}/{name}"


def _translate_error(exc: Exception, action: str) -> StorageError:
    """Convierte un error del SDK en un ``StorageError`` con mensaje seguro.

    ``action`` es "bajar" o "subir". No copia el texto de ``exc``: podría
    incluir identificadores de la cuenta.
    """
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return StorageError(f"OCI rechazó las credenciales o falta el permiso para {action} la memoria del motor")
    if status == 404:
        return StorageError("OCI no encontró el bucket o el namespace de la memoria (revisar OCI_BUCKET y OCI_NAMESPACE)")
    if status == 429:
        return StorageError("OCI alcanzó su límite de uso; reintentar más tarde")
    return StorageError(f"No se pudo {action} la memoria del motor en OCI Object Storage")


class MirroredDoubtHistory:
    """Historial de dudas que se sube a OCI después de cada cambio.

    Implementa ``DoubtHistoryPort`` envolviendo al historial local
    (``inner``). Las lecturas no tocan OCI; ``record`` y ``attach_faqs``
    suben el archivo ``path`` cuando cambiaron algo. Si la subida falla,
    produce ``StorageError``: el lote se procesa igual y queda un aviso.
    """

    def __init__(self, inner, mirror: OCIFileMirror, path: Path):
        """Recibe el historial local, el espejo de OCI y la ruta del archivo."""
        self.inner, self.mirror, self.path = inner, mirror, Path(path)

    def record(self, request_id: str, community: str, doubts: list[dict]) -> int:
        """Guarda las dudas en el historial local y sube el archivo a OCI."""
        saved = self.inner.record(request_id, community, doubts)
        if saved:
            self.mirror.save(self.path)
        return saved

    def attach_faqs(self, topic_key: str, faq_ids: list[str]) -> int:
        """Marca el tema como resuelto en el historial local y sube el archivo a OCI."""
        updated = self.inner.attach_faqs(topic_key, faq_ids)
        if updated:
            self.mirror.save(self.path)
        return updated

    def known_topics(self, limit: int = 15) -> list[str]:
        """Temas conocidos, leídos del archivo local (ya restaurado al arrancar)."""
        return self.inner.known_topics(limit)

    def ranking(self, days: int | None = None, limit: int = 20) -> dict:
        """Ranking de dudas, leído del archivo local (ya restaurado al arrancar)."""
        return self.inner.ranking(days, limit)


class MirroredKnowledgeBase:
    """Base de conocimiento que se sube a OCI después de agregar FAQs.

    Implementa ``KnowledgeBasePort`` envolviendo a la base local (``inner``).
    Solo ``add_faqs`` escribe; cuando agrega FAQs, sube ``path`` a OCI. Si la
    subida falla, las FAQs quedan en la base local y la respuesta trae un
    aviso en ``warnings`` (se perderían al reiniciar el servidor).
    """

    def __init__(self, inner, mirror: OCIFileMirror, path: Path):
        """Recibe la base local, el espejo de OCI y la ruta de la base."""
        self.inner, self.mirror, self.path = inner, mirror, Path(path)

    def summary(self) -> dict:
        """Totales de la base local."""
        return self.inner.summary()

    def faqs(self, limit: int) -> list[dict]:
        """FAQs oficiales de la base local."""
        return self.inner.faqs(limit)

    def reviews(self, course: str | None, sentiment: str | None, limit: int) -> list[dict]:
        """Reseñas reales de la base local."""
        return self.inner.reviews(course, sentiment, limit)

    def courses(self) -> list[str]:
        """Cursos con reseñas de la base local."""
        return self.inner.courses()

    def add_faqs(self, rows: list[dict], dry_run: bool) -> dict:
        """Agrega las FAQs en la base local y, si agregó alguna, la sube a OCI."""
        result = self.inner.add_faqs(rows, dry_run)
        if result.get("new_ids"):
            try:
                self.mirror.save(self.path)
            except StorageError as exc:
                result = {**result, "warnings": [*result.get("warnings", []), f"Las FAQs se agregaron, pero no se pudo respaldar la base en OCI: {exc}"]}
        return result
