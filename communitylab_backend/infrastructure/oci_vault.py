"""Adaptador de OCI Vault para el puerto ``SecretProvider``.

Lee las claves de Gemini y Cohere desde un Vault de OCI en lugar de un archivo
``.env``. Pensado para producción en OCI Compute con *instance principal*: el
servidor se identifica ante OCI sin guardar claves en disco. También admite el
archivo de configuración de OCI (``~/.oci/config``) para probar desde una
computadora.

Dependencia externa: ``oci`` (SDK oficial). Se importa de forma diferida para
que el backend arranque en modo local aunque el SDK no esté instalado. Los
valores se guardan sólo en memoria y nunca se registran ni aparecen en los
mensajes de error; los errores del SDK se traducen a ``ProviderUnavailableError``.
"""

import base64
import binascii
from pathlib import Path

from communitylab_backend.domain.errors import ProviderUnavailableError
from communitylab_backend.infrastructure.oci_storage import AUTH_CONFIG_FILE, AUTH_INSTANCE_PRINCIPAL

DEFAULT_SECRET_NAMES = {"GEMINI_API_KEY": "communitylab-gemini-api-key", "COHERE_API_KEY": "communitylab-cohere-api-key"}


def _build_client(auth: str, region: str | None, config_file: Path, profile: str, timeout_seconds: float):
    """Crea el cliente oficial de lectura de secretos según la autenticación.

    Con ``config`` lee ``config_file`` y su ``profile``; con
    ``instance_principal`` usa la identidad del servidor. ``region`` reemplaza
    la del archivo si se indica. Produce ``ProviderUnavailableError`` si falta
    el SDK, no se puede leer la configuración o el modo es desconocido.
    """
    try:
        import oci
    except ImportError as exc:
        raise ProviderUnavailableError("El SDK de OCI (oci) no está instalado") from exc
    try:
        if auth == AUTH_CONFIG_FILE:
            config = oci.config.from_file(str(Path(config_file).expanduser()), profile)
            if region:
                config["region"] = region
            oci.config.validate_config(config)
            return oci.secrets.SecretsClient(config, timeout=timeout_seconds)
        if auth == AUTH_INSTANCE_PRINCIPAL:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            return oci.secrets.SecretsClient({"region": region} if region else {}, signer=signer, timeout=timeout_seconds)
    except Exception as exc:
        raise ProviderUnavailableError("No se pudo iniciar la sesión con OCI para leer el Vault (revisar la configuración de OCI)") from exc
    raise ProviderUnavailableError("Modo de autenticación de OCI desconocido")


def _translate_error(exc: Exception, secret_name: str) -> ProviderUnavailableError:
    """Convierte un error del SDK en un error de dominio con mensaje seguro.

    Distingue credenciales o permisos (401 y 403) y límite de uso (429). Sólo
    menciona ``secret_name``, que no es sensible; no copia el texto de ``exc``
    porque podría incluir identificadores de la cuenta.
    """
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return ProviderUnavailableError(f"OCI rechazó las credenciales o falta el permiso para leer el secreto '{secret_name}' (revisar el grupo dinámico y la política 'read secret-family')")
    if status == 429:
        return ProviderUnavailableError("OCI Vault alcanzó su límite de uso; reintentar más tarde")
    return ProviderUnavailableError(f"No se pudo leer el secreto '{secret_name}' de OCI Vault")


class OCIVaultSecretProvider:
    """Obtiene secretos de un Vault de OCI y los guarda en memoria.

    Implementa ``SecretProvider`` en infraestructura. ``get`` recibe el nombre
    lógico de la variable (por ejemplo ``GEMINI_API_KEY``) y lo traduce al
    nombre del secreto en el Vault. Cada secreto se pide a OCI una sola vez por
    proceso: para usar una versión nueva hay que reiniciar el backend.
    """

    def __init__(self, vault_id: str | None, secret_names: dict[str, str] | None = None, region: str | None = None, auth: str = AUTH_CONFIG_FILE, config_file: Path = Path("~/.oci/config"), profile: str = "DEFAULT", timeout_seconds: float = 30.0, client=None):
        """Configura el Vault, los nombres de secretos y la autenticación.

        ``secret_names`` relaciona nombre lógico con nombre en el Vault; por
        defecto usa ``DEFAULT_SECRET_NAMES``. ``client`` permite inyectar un
        cliente falso en pruebas. Produce ``ProviderUnavailableError`` si falta
        ``vault_id`` o no se puede iniciar sesión con OCI.
        """
        if not vault_id:
            raise ProviderUnavailableError("Falta configurar OCI_VAULT_ID para leer secretos de OCI Vault")
        self.vault_id = vault_id
        self.secret_names = dict(secret_names or DEFAULT_SECRET_NAMES)
        self._cache: dict[str, str] = {}
        self._client = client if client is not None else _build_client(auth, region, config_file, profile, timeout_seconds)

    def __repr__(self) -> str:
        """Muestra los nombres configurados, nunca los valores en memoria."""
        return f"OCIVaultSecretProvider(secret_names={sorted(self.secret_names)})"

    def get(self, name: str) -> str | None:
        """Busca el secreto ``name`` en el Vault y retorna su valor o ``None``.

        Retorna ``None`` si ``name`` no está en ``secret_names``, si el Vault no
        tiene ese secreto (404) o si su contenido está vacío. Guarda en memoria
        los valores encontrados. Produce ``ProviderUnavailableError`` ante
        permisos, límites o fallos de OCI, o si el contenido no es texto.
        """
        if name in self._cache:
            return self._cache[name]
        secret_name = self.secret_names.get(name)
        if not secret_name:
            return None
        try:
            response = self._client.get_secret_bundle_by_name(secret_name, self.vault_id)
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise _translate_error(exc, secret_name) from exc
        value = _decode(response, secret_name)
        if value:
            self._cache[name] = value
        return value or None


def _decode(response, secret_name: str) -> str:
    """Extrae y decodifica el contenido base64 de la respuesta del Vault.

    Retorna el texto sin espacios ni saltos de línea en los extremos. Produce
    ``ProviderUnavailableError`` si la respuesta no trae contenido base64 o
    éste no es texto UTF-8. No encadena el error original: podría arrastrar
    los bytes del secreto a un registro.
    """
    try:
        content = response.data.secret_bundle_content.content
        return base64.b64decode(content, validate=True).decode("utf-8").strip()
    except (AttributeError, TypeError, binascii.Error, UnicodeDecodeError):
        raise ProviderUnavailableError(f"El secreto '{secret_name}' de OCI Vault no tiene un texto válido") from None
