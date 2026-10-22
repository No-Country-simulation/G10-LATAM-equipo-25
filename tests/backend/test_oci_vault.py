"""Pruebas de la lectura de secretos desde OCI Vault, sin red ni cuenta de OCI."""

import base64
from types import SimpleNamespace

import pytest

from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import ProviderUnavailableError
from communitylab_backend.infrastructure.oci_vault import OCIVaultSecretProvider

VALOR = "clave-super-secreta-123"


class FakeServiceError(Exception):
    """Error falso con ``status`` como el de ``oci.exceptions.ServiceError``."""

    def __init__(self, status):
        """Guarda el código HTTP simulado y un mensaje con datos sensibles."""
        super().__init__("ocid1.vault.secreto")
        self.status = status


def bundle(content):
    """Arma una respuesta con la forma de ``SecretBundle`` del SDK."""
    return SimpleNamespace(data=SimpleNamespace(secret_bundle_content=SimpleNamespace(content_type="BASE64", content=content)))


def encoded(text):
    """Codifica ``text`` en base64, como lo entrega OCI Vault."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class FakeSecretsClient:
    """Cliente falso que entrega secretos por nombre o lanza un error."""

    def __init__(self, secrets=None, error=None):
        """Configura los secretos disponibles, el error a lanzar y las llamadas."""
        self.secrets, self.error, self.calls = secrets or {}, error, []

    def get_secret_bundle_by_name(self, secret_name, vault_id, **kwargs):
        """Registra la llamada y devuelve el secreto, un 404 o el error configurado."""
        self.calls.append((secret_name, vault_id))
        if self.error:
            raise self.error
        if secret_name not in self.secrets:
            raise FakeServiceError(404)
        return bundle(self.secrets[secret_name])


def provider(client, **values):
    """Crea el lector de prueba con un Vault ficticio."""
    return OCIVaultSecretProvider(values.pop("vault_id", "ocid1.vault.prueba"), client=client, **values)


def test_reads_and_decodes_the_secret_by_its_vault_name():
    """Traduce el nombre lógico al del Vault y decodifica el base64."""
    client = FakeSecretsClient({"communitylab-gemini-api-key": encoded(VALOR + "\n")})
    assert provider(client).get("GEMINI_API_KEY") == VALOR
    assert client.calls == [("communitylab-gemini-api-key", "ocid1.vault.prueba")]


def test_custom_secret_names_are_respected():
    """Los nombres del Vault se pueden cambiar con ``secret_names``."""
    client = FakeSecretsClient({"otra-clave": encoded(VALOR)})
    assert provider(client, secret_names={"COHERE_API_KEY": "otra-clave"}).get("COHERE_API_KEY") == VALOR


def test_values_are_cached_in_memory():
    """Cada secreto se pide a OCI una sola vez por proceso."""
    client = FakeSecretsClient({"communitylab-cohere-api-key": encoded(VALOR)})
    lector = provider(client)
    assert lector.get("COHERE_API_KEY") == lector.get("COHERE_API_KEY") == VALOR
    assert len(client.calls) == 1


def test_missing_or_unknown_secrets_return_none():
    """Un secreto inexistente (404), vacío o fuera del catálogo devuelve ``None``."""
    client = FakeSecretsClient({"communitylab-cohere-api-key": encoded("  ")})
    lector = provider(client)
    assert lector.get("GEMINI_API_KEY") is None
    assert lector.get("COHERE_API_KEY") is None
    assert lector.get("OTRA_VARIABLE") is None
    assert [name for name, _ in client.calls] == ["communitylab-gemini-api-key", "communitylab-cohere-api-key"]


def test_vault_id_is_required():
    """Sin ``OCI_VAULT_ID`` falla con un mensaje claro antes de llamar a OCI."""
    with pytest.raises(ProviderUnavailableError, match="OCI_VAULT_ID"):
        provider(FakeSecretsClient(), vault_id=None)


@pytest.mark.parametrize("status,fragment", [(401, "credenciales"), (403, "read secret-family"), (429, "límite"), (500, "No se pudo leer")])
def test_oci_errors_are_translated_without_leaking(status, fragment):
    """Cada error de OCI produce un mensaje útil y sin identificadores de la cuenta."""
    with pytest.raises(ProviderUnavailableError) as raised:
        provider(FakeSecretsClient(error=FakeServiceError(status))).get("GEMINI_API_KEY")
    assert fragment in str(raised.value) and "ocid1" not in str(raised.value)


def test_network_errors_are_provider_errors():
    """Un fallo sin código HTTP (por ejemplo, de red) también se traduce."""
    with pytest.raises(ProviderUnavailableError, match="No se pudo leer"):
        provider(FakeSecretsClient(error=TimeoutError("ocid1.vault"))).get("GEMINI_API_KEY")


@pytest.mark.parametrize("content", ["no es base64!", base64.b64encode(b"\xff\xfe").decode("ascii"), None])
def test_invalid_content_is_reported_without_the_value(content):
    """Un contenido que no es base64 de texto UTF-8 falla sin mostrar el contenido."""
    with pytest.raises(ProviderUnavailableError, match="texto válido") as raised:
        provider(FakeSecretsClient({"communitylab-gemini-api-key": content})).get("GEMINI_API_KEY")
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_repr_never_shows_values():
    """La representación del lector no incluye valores en memoria."""
    lector = provider(FakeSecretsClient({"communitylab-gemini-api-key": encoded(VALOR)}))
    lector.get("GEMINI_API_KEY")
    assert VALOR not in repr(lector) and "GEMINI_API_KEY" in repr(lector)


def test_unknown_auth_mode_fails_clearly():
    """Un modo de autenticación desconocido no intenta conectarse."""
    pytest.importorskip("oci")
    with pytest.raises(ProviderUnavailableError, match="desconocido"):
        OCIVaultSecretProvider("ocid1.vault.prueba", auth="otro")


def test_config_file_builds_the_real_sdk_client(tmp_path):
    """Con un archivo de configuración válido se crea el cliente oficial, sin llamar a OCI."""
    oci = pytest.importorskip("oci")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = tmp_path / "key.pem"
    key.write_bytes(rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    config = tmp_path / "config"
    config.write_text(f"[DEFAULT]\nuser=ocid1.user.oc1..aaaa\nfingerprint=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99\nkey_file={key}\ntenancy=ocid1.tenancy.oc1..aaaa\nregion=sa-saopaulo-1\n", encoding="utf-8")
    lector = OCIVaultSecretProvider("ocid1.vault.prueba", config_file=config)
    assert isinstance(lector._client, oci.secrets.SecretsClient)


@pytest.fixture
def dependencies():
    """Importa la composición de la API y limpia la caché del lector de Vault."""
    from communitylab_backend.api import dependencies as module
    module._vault_provider.cache_clear()
    yield module
    module._vault_provider.cache_clear()


def settings(**values):
    """Crea ``Settings`` aislados del archivo ``.env`` local."""
    return Settings(_env_file=None, **values)


@pytest.fixture
def fake_vault(dependencies, monkeypatch):
    """Reemplaza el lector real por uno con cliente falso y cuenta cuántos se crean."""
    client = FakeSecretsClient({"communitylab-gemini-api-key": encoded("clave-gemini"), "clave-cohere-prod": encoded("clave-cohere")})
    created = []

    def build(vault_id, secret_names, *args, **kwargs):
        """Crea el lector con el cliente falso y registra los nombres recibidos."""
        created.append((vault_id, secret_names))
        return OCIVaultSecretProvider(vault_id, secret_names, client=client)

    monkeypatch.setattr(dependencies, "OCIVaultSecretProvider", build)
    return client, created


def test_environment_mode_keeps_reading_settings(dependencies, fake_vault):
    """Con ``environment`` (por defecto) la clave sale de ``Settings`` y no se toca el Vault."""
    client, created = fake_vault
    assert dependencies.get_api_key(settings(gemini_api_key="local"), "GEMINI_API_KEY") == "local"
    assert dependencies.get_api_key(settings(), "COHERE_API_KEY") is None
    assert client.calls == [] and created == []


def test_oci_mode_reads_keys_from_the_vault(dependencies, fake_vault):
    """Con ``oci`` las claves salen del Vault aunque el ``.env`` tenga otras."""
    client, created = fake_vault
    config = settings(secret_provider="oci", oci_vault_id="ocid1.vault.prod", oci_secret_cohere="clave-cohere-prod", gemini_api_key="ignorada")
    assert dependencies.get_api_key(config, "GEMINI_API_KEY") == "clave-gemini"
    assert dependencies.get_api_key(config, "COHERE_API_KEY") == "clave-cohere"
    assert dependencies.get_api_key(config, "GEMINI_API_KEY") == "clave-gemini"
    assert len(created) == 1 and created[0][0] == "ocid1.vault.prod"
    assert [name for name, _ in client.calls] == ["communitylab-gemini-api-key", "clave-cohere-prod"]


def test_oci_mode_reports_a_missing_secret_by_name(dependencies, fake_vault):
    """Si el Vault no tiene el secreto, el error dice cuál y qué variable revisar."""
    config = settings(secret_provider="oci", oci_vault_id="ocid1.vault.prod")
    with pytest.raises(ProviderUnavailableError, match="communitylab-cohere-api-key.*OCI_SECRET_COHERE"):
        dependencies.get_api_key(config, "COHERE_API_KEY")


def test_oci_mode_requires_the_vault_id(dependencies):
    """Con ``oci`` y sin ``OCI_VAULT_ID`` la composición falla con un mensaje claro."""
    with pytest.raises(ProviderUnavailableError, match="OCI_VAULT_ID"):
        dependencies.get_api_key(settings(secret_provider="oci"), "GEMINI_API_KEY")


def test_gemini_workflow_uses_the_vault_key(dependencies, fake_vault, monkeypatch):
    """``build_workflow`` entrega a Gemini la clave leída del Vault."""
    received = []
    monkeypatch.setattr(dependencies, "GeminiLLMAdapter", lambda key, *args: received.append(key) or dependencies.MockLLMProvider())
    dependencies.build_workflow(settings(secret_provider="oci", oci_vault_id="ocid1.vault.prod", llm_provider="gemini"))
    assert received == ["clave-gemini"]


def test_mock_workflow_never_asks_the_vault(dependencies, fake_vault):
    """Con proveedores locales no se necesita ninguna clave, aunque el modo sea ``oci``."""
    client, created = fake_vault
    dependencies.build_workflow(settings(secret_provider="oci"))
    assert client.calls == [] and created == []
