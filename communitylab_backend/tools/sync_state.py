"""Sube o baja la memoria del motor (historial de dudas y base de FAQs) a OCI Object Storage.

Sirve para preparar un despliegue con ``STATE_PROVIDER=oci``: ``subir`` copia
al bucket los archivos locales, para que el servidor arranque con el ranking
y las FAQs que ya existen. ``bajar`` trae al equipo la memoria del servidor.
Usa el bucket, la autenticación y el prefijo del ``.env`` (``OCI_NAMESPACE``,
``OCI_BUCKET``, ``OCI_AUTH``, ``OCI_STATE_PREFIX``). Cada archivo es una sola
solicitud a OCI.

Uso:
    python -m communitylab_backend.tools.sync_state subir
    python -m communitylab_backend.tools.sync_state bajar
"""

import argparse
import sys

from communitylab_backend.domain.errors import BackendError


def main(argv: list[str] | None = None) -> int:
    """Sube o baja los dos archivos de memoria y muestra dónde quedaron.

    ``subir`` reemplaza la copia del bucket; ``bajar`` reemplaza la copia
    local. Retorna 0 si terminó bien y 1 si OCI o los archivos dieron un
    error, que se muestra con su mensaje seguro.
    """
    from communitylab_backend.config.settings import Settings
    from communitylab_backend.infrastructure.oci_state import OCIFileMirror

    parser = argparse.ArgumentParser(description="Sube o baja la memoria del motor a OCI Object Storage.")
    parser.add_argument("accion", choices=["subir", "bajar"], help="subir: equipo → OCI · bajar: OCI → equipo")
    args = parser.parse_args(argv)
    settings = Settings()
    try:
        mirror = OCIFileMirror(settings.oci_namespace, settings.oci_bucket, settings.oci_region, settings.oci_state_prefix, settings.oci_auth, settings.oci_config_file, settings.oci_config_profile, settings.provider_timeout_seconds)
        for path in (settings.history_db_path, settings.faq_db_path):
            if args.accion == "subir":
                if not path.is_file():
                    print(f"  sin archivo local, se omite: {path}")
                    continue
                print(f"[OK] {path} -> {mirror.save(path)}")
            else:
                found = mirror.restore(path)
                print(f"[OK] {mirror.object_name(path)} -> {path}" if found else f"  el bucket todavía no tiene {mirror.object_name(path)}")
    except BackendError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
