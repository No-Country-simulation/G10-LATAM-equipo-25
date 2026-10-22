# Almacenamiento de paquetes en OCI Object Storage

Cada vez que el backend procesa un lote (`POST /api/v1/activity/process`), guarda un paquete JSON con el análisis, la evidencia y los borradores generados. Este adaptador lo guarda en un bucket de **OCI Object Storage** de la capa Always Free, que es un requisito obligatorio del MVP.

## Qué hace

- Implementa `ObjectStoragePort` (`infrastructure/oci_storage.py`).
- Sube un objeto por solicitud: `activos/<request_id>.json`. El `request_id` es un UUID que genera la API.
- Devuelve la ubicación como `oci://<namespace>/<bucket>/activos/<request_id>.json`.
- Los paquetes ya vienen sanitizados y siempre con `human_review: pending`.
- Cuando el equipo aprueba o rechaza los borradores en el panel (`POST /api/v1/assets/review`), se guarda un segundo objeto, `activos/<request_id>-curaduria.json`, con la versión revisada y `human_review: completed`.
- Sin reintentos automáticos: cada reintento gastaría solicitudes de la cuota gratuita (50.000 al mes en Always Free).

## Configuración

```env
STORAGE_PROVIDER=oci                     # local | oci (por defecto local)
OCI_NAMESPACE=tu_namespace
OCI_BUCKET=communitylab-activos
OCI_REGION=sa-saopaulo-1
OCI_AUTH=config                          # config | instance_principal
OCI_CONFIG_FILE=~/.oci/config            # solo con OCI_AUTH=config
OCI_CONFIG_PROFILE=DEFAULT
OCI_OBJECT_PREFIX=activos
```

Con `local` (el valor por defecto) los paquetes se guardan en la carpeta `salidas/paquetes/` (`LOCAL_STORAGE_DIR`).

## Autenticación

| Dónde corre | `OCI_AUTH` | Qué hace falta |
|---|---|---|
| Computadora de desarrollo | `config` | Archivo `~/.oci/config` con una clave de API de tu usuario |
| Servidor en OCI Compute | `instance_principal` | Un grupo dinámico y una política de IAM que permitan escribir en el bucket. No hay claves guardadas |

**Nunca subas `~/.oci/config`, la clave `.pem` ni el `.env` al repositorio.**

## Preparar OCI (una vez)

1. Crear una cuenta de Oracle Cloud Free Tier (pide una tarjeta solo para verificar identidad).
2. Crear un bucket **privado**, capa **Standard**, ámbito **Espacio de nombres**. Anotar el namespace (en los detalles del bucket).
3. Crear una clave de API en *Mi perfil → Claves de API*, guardar la clave privada y la configuración en `~/.oci/`.

## Probar la conexión

Con el entorno virtual activo y las variables en el `.env`:

```bash
pip install oci
python -m communitylab_backend.tools.check_oci
```

Sube un paquete de prueba y muestra su ubicación. Debe aparecer en el bucket, dentro de la carpeta `activos`.

## Errores

| Situación | Resultado |
|---|---|
| Falta namespace, bucket o la configuración de OCI | 503 (`ProviderUnavailableError`), indica qué variable revisar |
| OCI rechaza las credenciales o falta permiso (401, 403) | 502 (`StorageError`) |
| Bucket o namespace inexistente (404) | 502, indica revisar `OCI_BUCKET` y `OCI_NAMESPACE` |
| Límite de uso (429) o cualquier otro fallo | 502 |

Los mensajes nunca incluyen credenciales ni identificadores de la cuenta.

## Pruebas

Las pruebas usan un cliente falso y no necesitan una cuenta de OCI. Una de ellas usa el cliente real del SDK con la llamada HTTP reemplazada, para comprobar que los argumentos que enviamos son válidos.

```bash
python -m pytest tests/backend -q
```

## Pendiente

- Probar contra el bucket real (`check_oci`): requiere las credenciales de quien creó la cuenta.
- Para el despliegue en OCI Compute: configurar `instance_principal` y la política de IAM.
- Decidir si el índice de FAQs también vive en el bucket (hoy es un archivo local).
