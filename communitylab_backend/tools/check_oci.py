"""Prueba real de la conexión con OCI Object Storage.

Construye el mismo almacenamiento que usa la API, sube un paquete mínimo de
prueba y muestra su ubicación. Sirve para comprobar, una sola vez, que el
bucket, el namespace y las credenciales están bien. Hace 1 solicitud a OCI.

Uso: ``python -m communitylab_backend.tools.check_oci``
"""

import uuid

from communitylab_backend.config.settings import Settings
from communitylab_backend.infrastructure.oci_storage import OCIObjectStorageAdapter


def main() -> int:
    """Sube un paquete de prueba e imprime su ubicación; retorna el código de salida.

    Usa ``Settings`` (variables de entorno o ``.env``). Propaga los errores de
    dominio con su mensaje seguro. Nunca imprime credenciales.
    """
    settings = Settings()
    storage = OCIObjectStorageAdapter(settings.oci_namespace, settings.oci_bucket, settings.oci_region, settings.oci_object_prefix, settings.oci_auth, settings.oci_config_file, settings.oci_config_profile, settings.provider_timeout_seconds)
    location = storage.save(f"prueba-conexion-{uuid.uuid4().hex[:8]}", {"mensaje": "Prueba de conexión de CommunityLab", "human_review": {"required": True, "status": "pending"}})
    print(f"Guardado en: {location}")
    print("Revisa el bucket en la consola de OCI: debe aparecer ese objeto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
