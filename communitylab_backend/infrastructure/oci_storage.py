"""Adaptador de OCI Object Storage para el puerto ``ObjectStoragePort``.

Guarda cada paquete de borradores como un objeto JSON en un bucket de la capa
Always Free de OCI. Se autentica de dos formas: con el archivo de
configuración de OCI (``~/.oci/config``), pensado para trabajar en una
computadora, o con *instance principal*, pensado para un servidor de OCI
Compute, donde no hay claves guardadas.

Dependencia externa: ``oci`` (SDK oficial). Se importa de forma diferida para
que el backend arranque con almacenamiento local aunque el SDK no esté
instalado. Los errores del SDK se traducen a errores de dominio con mensajes
seguros, sin credenciales ni rutas.
"""

import json
import re
from pathlib import Path

from communitylab_backend.domain.errors import ProviderUnavailableError, StorageError

AUTH_CONFIG_FILE = "config"
AUTH_INSTANCE_PRINCIPAL = "instance_principal"
_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _build_client(auth: str, region: str | None, config_file: Path, profile: str, timeout_seconds: float):
    """Crea el cliente oficial de Object Storage según el modo de autenticación.

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
            return oci.object_storage.ObjectStorageClient(config, timeout=timeout_seconds)
        if auth == AUTH_INSTANCE_PRINCIPAL:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            return oci.object_storage.ObjectStorageClient({"region": region} if region else {}, signer=signer, timeout=timeout_seconds)
    except Exception as exc:
        raise ProviderUnavailableError("No se pudo iniciar la sesión con OCI (revisar la configuración de OCI)") from exc
    raise ProviderUnavailableError("Modo de autenticación de OCI desconocido")


def _translate_error(exc: Exception) -> StorageError:
    """Convierte un error del SDK en un error de dominio con mensaje seguro.

    Distingue lo que el equipo puede corregir: credenciales o permisos
    (401 y 403), bucket o namespace inexistente (404) y límite de uso (429).
    No copia el texto de ``exc``: podría incluir identificadores de la cuenta.
    """
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return StorageError("OCI rechazó las credenciales o falta el permiso para escribir en el bucket")
    if status == 404:
        return StorageError("OCI no encontró el bucket o el namespace (revisar OCI_BUCKET y OCI_NAMESPACE)")
    if status == 429:
        return StorageError("OCI alcanzó su límite de uso; reintentar más tarde")
    return StorageError("No se pudo guardar el paquete en OCI Object Storage")


class OCIObjectStorageAdapter:
    """Guarda paquetes JSON sanitizados en un bucket de OCI Object Storage.

    Implementa ``ObjectStoragePort`` en infraestructura. Escribe un objeto por
    solicitud con el nombre ``<prefijo>/<request_id>.json``; si el nombre ya
    existe, OCI lo reemplaza. No publica assets ni lee objetos.
    """

    provider = "oci"

    def __init__(self, namespace: str | None, bucket: str | None, region: str | None = None, prefix: str = "activos", auth: str = AUTH_CONFIG_FILE, config_file: Path = Path("~/.oci/config"), profile: str = "DEFAULT", timeout_seconds: float = 30.0, client=None):
        """Configura destino, autenticación y tiempo de espera.

        ``client`` permite inyectar un cliente falso en pruebas. Produce
        ``ProviderUnavailableError`` si falta el namespace o el bucket, si el
        prefijo no es seguro, o si no se puede iniciar sesión con OCI.
        """
        if not namespace or not bucket:
            raise ProviderUnavailableError("Falta configurar OCI_NAMESPACE y OCI_BUCKET")
        if not _SAFE_PART.match(prefix):
            raise ProviderUnavailableError("El prefijo de OCI solo admite letras, números, punto, guion y guion bajo")
        self.namespace, self.bucket, self.prefix = namespace, bucket, prefix
        self._client = client if client is not None else _build_client(auth, region, config_file, profile, timeout_seconds)

    def object_name(self, request_id: str) -> str:
        """Devuelve el nombre del objeto para ``request_id``.

        Produce ``StorageError`` si el identificador trae caracteres que no
        sean letras, números, punto, guion o guion bajo.
        """
        if not _SAFE_PART.match(request_id or ""):
            raise StorageError("El identificador de la solicitud no es válido para nombrar el objeto")
        return f"{self.prefix}/{request_id}.json"

    def save(self, request_id: str, package: dict) -> str:
        """Guarda ``package`` como JSON y retorna ``oci://namespace/bucket/objeto``.

        Tiene el efecto secundario de escribir en el bucket. Sin reintentos
        automáticos. Produce ``StorageError`` si el paquete no se puede
        convertir a JSON o si OCI rechaza o no completa la escritura.
        """
        name = self.object_name(request_id)
        try:
            body = json.dumps(package, ensure_ascii=False, indent=2).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise StorageError("El paquete de borradores no se pudo convertir a JSON") from exc
        try:
            self._client.put_object(self.namespace, self.bucket, name, body, content_type="application/json", retry_strategy=_no_retry())
        except Exception as exc:
            raise _translate_error(exc) from exc
        return f"oci://{self.namespace}/{self.bucket}/{name}"


def _no_retry():
    """Devuelve la estrategia del SDK que no reintenta, o ``None`` sin el SDK.

    Un reintento repite una escritura y consume solicitudes de la cuota
    gratuita, así que cada guardado se intenta una sola vez.
    """
    try:
        import oci
    except ImportError:
        return None
    return oci.retry.NoneRetryStrategy()
