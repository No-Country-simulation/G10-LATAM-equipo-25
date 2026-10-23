"""Pruebas del adaptador de OCI Object Storage, sin red ni cuenta de OCI."""

import json

import pytest

from communitylab_backend.domain.errors import ProviderUnavailableError, StorageError
from communitylab_backend.infrastructure.oci_storage import OCIObjectStorageAdapter


class FakeServiceError(Exception):
    """Error falso con ``status`` como el de ``oci.exceptions.ServiceError``."""

    def __init__(self, status):
        """Guarda el código HTTP simulado y un mensaje con datos sensibles."""
        super().__init__("ocid1.tenancy.secreto")
        self.status = status


class FakeClient:
    """Cliente falso que registra las escrituras o lanza un error."""

    def __init__(self, error=None):
        """Configura el error a lanzar y la lista de llamadas."""
        self.calls, self.error = [], error

    def put_object(self, namespace_name, bucket_name, object_name, put_object_body, **kwargs):
        """Registra la escritura o lanza el error configurado."""
        if self.error:
            raise self.error
        self.calls.append((namespace_name, bucket_name, object_name, put_object_body, kwargs))


def adapter(client, **values):
    """Crea el adaptador de prueba con valores por defecto."""
    return OCIObjectStorageAdapter(values.pop("namespace", "ns"), values.pop("bucket", "bk"), client=client, **values)


def test_save_uploads_json_and_returns_location():
    """Sube el paquete como JSON UTF-8 y devuelve la ubicación del objeto."""
    client = FakeClient()
    location = adapter(client).save("abc-123", {"texto": "¿Cómo instalo Python?"})
    namespace, bucket, name, body, options = client.calls[0]
    assert (namespace, bucket, name) == ("ns", "bk", "activos/abc-123.json")
    assert json.loads(body.decode("utf-8")) == {"texto": "¿Cómo instalo Python?"}
    assert "¿Cómo" in body.decode("utf-8") and options["content_type"] == "application/json"
    assert location == "oci://ns/bk/activos/abc-123.json"


def test_provider_name_matches_the_port_contract():
    """El proveedor se identifica como ``oci``."""
    assert adapter(FakeClient()).provider == "oci"


@pytest.mark.parametrize("request_id", ["", "../secreto", "a/b", "con espacio", "x" * 200])
def test_unsafe_request_ids_are_rejected_before_any_call(request_id):
    """Identificadores raros no llegan a OCI."""
    client = FakeClient()
    with pytest.raises(StorageError):
        adapter(client).save(request_id, {})
    assert client.calls == []


def test_unserializable_package_is_a_storage_error():
    """Un paquete que no es JSON se informa sin llamar a OCI."""
    client = FakeClient()
    with pytest.raises(StorageError):
        adapter(client).save("abc", {"valor": object()})
    assert client.calls == []


@pytest.mark.parametrize("status,fragment", [(403, "permiso"), (401, "credenciales"), (404, "OCI_BUCKET"), (429, "límite"), (500, "No se pudo guardar")])
def test_oci_errors_are_translated_without_leaking(status, fragment):
    """Cada error de OCI produce un mensaje útil y sin identificadores de la cuenta."""
    with pytest.raises(StorageError) as raised:
        adapter(FakeClient(FakeServiceError(status))).save("abc", {})
    assert fragment in str(raised.value) and "ocid1" not in str(raised.value)


def test_non_service_errors_are_also_storage_errors():
    """Un corte de red u otro fallo también se traduce."""
    with pytest.raises(StorageError):
        adapter(FakeClient(ConnectionError("sin red"))).save("abc", {})


@pytest.mark.parametrize("values", [{"namespace": None}, {"bucket": ""}, {"prefix": "../x"}])
def test_incomplete_or_unsafe_configuration_is_unavailable(values):
    """Sin namespace, sin bucket o con prefijo inseguro falla al construirse."""
    with pytest.raises(ProviderUnavailableError):
        adapter(FakeClient(), **values)


def test_missing_config_file_is_unavailable(tmp_path):
    """Si no existe ``~/.oci/config`` la composición falla con un mensaje claro."""
    pytest.importorskip("oci")
    with pytest.raises(ProviderUnavailableError, match="OCI"):
        OCIObjectStorageAdapter("ns", "bk", auth="config", config_file=tmp_path / "no-existe")


def test_real_sdk_client_accepts_our_call(tmp_path):
    """Contrato: el cliente real del SDK acepta los argumentos que enviamos.

    Se reemplaza solo la llamada HTTP final, de modo que la validación de
    argumentos del propio SDK sí se ejecuta, sin red ni credenciales.
    """
    oci = pytest.importorskip("oci")
    from requests.auth import AuthBase

    class NoSigner(AuthBase):
        """Firmante vacío para construir el cliente sin credenciales."""

        def __call__(self, request):
            """Devuelve la petición sin firmar."""
            return request

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = tmp_path / "key.pem"
    key.write_bytes(rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    config = {"user": "ocid1.user.oc1..aaaa", "fingerprint": "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99", "key_file": str(key), "tenancy": "ocid1.tenancy.oc1..aaaa", "region": "sa-saopaulo-1"}
    sdk = oci.object_storage.ObjectStorageClient(config, signer=NoSigner())
    captured = {}

    def fake_call_api(**kwargs):
        """Captura lo que el SDK enviaría y simula una respuesta vacía."""
        captured.update(kwargs)
        return oci.response.Response(200, {}, None, None)

    sdk.base_client.call_api = fake_call_api
    adapter(sdk).save("abc-123", {"ok": True})
    assert captured["path_params"] == {"namespaceName": "ns", "bucketName": "bk", "objectName": "activos/abc-123.json"}
    assert captured["header_params"]["Content-Type"] == "application/json"
