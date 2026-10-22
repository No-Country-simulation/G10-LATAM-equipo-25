"""
Gestion de secretos de CommunityLab.

IDEA CENTRAL
------------
El resto del equipo NUNCA lee variables de entorno ni habla con OCI Vault
directamente. Todos usan una sola funcion:

    from core.secretos import obtener_secreto
    clave = obtener_secreto("GEMINI_API_KEY")

De donde sale ese valor es problema de este archivo, no del que lo usa.
En una computadora sale de un archivo .env local; en produccion sale de
OCI Vault, y nadie mas tiene que cambiar una sola linea de su codigo.

COMO ELIGE LA FUENTE
--------------------
Se controla con la variable de entorno FUENTE_SECRETOS:

    FUENTE_SECRETOS=env    -> lee del archivo .env          (si no se define)
    FUENTE_SECRETOS=vault  -> lee de OCI Vault              (produccion)
    FUENTE_SECRETOS=auto   -> intenta Vault, si falla usa .env  (recomendado)

QUE NECESITA EL MODO vault / auto
---------------------------------
    1. OCI_VAULT_ID en el .env (es un identificador, no un secreto). Tambien
       se acepta el nombre OCI_VAULT_OCID.
    2. Con OCI_AUTH=config: un archivo ~/.oci/config con las credenciales de
       tu usuario de OCI (se genera con `oci setup config` o desde la consola).
       Con OCI_AUTH=instance_principal (servidor de OCI Compute) no hace falta.
    3. Una politica IAM que permita leer los secretos (ver README).
    4. Opcional: OCI_CONFIG_PROFILE si usas un perfil distinto de DEFAULT.

REGLA INNEGOCIABLE DEL EQUIPO
-----------------------------
El archivo .env NUNCA se sube al repositorio. Debe estar en .gitignore
desde el primer commit. Lo que si se sube es .env.example, que tiene los
nombres de las variables pero ningun valor real.
"""

from __future__ import annotations

import base64
import functools
import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Catalogo de secretos del proyecto.
#
# Cada entrada dice: nombre logico -> (nombre en .env, nombre en OCI Vault).
# Tener el catalogo en un solo lugar evita que cada quien invente su propio
# nombre de variable y que despues nadie sepa cual es la buena.
#
# IMPORTANTE: el valor de "vault" debe coincidir EXACTAMENTE con el nombre que
# se le puso al secreto en la consola de OCI.
# ---------------------------------------------------------------------------
CATALOGO_SECRETOS: dict[str, dict[str, str]] = {
    "BACKEND_URL": {
        "env": "BACKEND_URL",
        "vault": "communitylab-backend-url",
        "descripcion": "Direccion del backend (por defecto http://localhost:8000).",
        "obligatorio": "no",
    },
    "GEMINI_API_KEY": {
        "env": "GEMINI_API_KEY",
        "vault": "communitylab-gemini-api-key",
        "descripcion": "Clave de Google Gemini: analiza la consulta y redacta los activos (FAQ y newsletter).",
        "obligatorio": "si",
    },
    "COHERE_API_KEY": {
        "env": "COHERE_API_KEY",
        "vault": "communitylab-cohere-api-key",
        "descripcion": "Clave de Cohere: Embed (vectores) y Rerank (ordenar por relevancia) para encontrar la FAQ correcta.",
        "obligatorio": "si",
    },
    "OCI_NAMESPACE": {
        "env": "OCI_NAMESPACE",
        "vault": "communitylab-oci-namespace",
        "descripcion": "Namespace de Object Storage donde vive el bucket.",
        "obligatorio": "si",
    },
    "OCI_BUCKET": {
        "env": "OCI_BUCKET",
        "vault": "communitylab-oci-bucket",
        "descripcion": "Nombre del bucket de destino.",
        "obligatorio": "si",
    },
    "OCI_REGION": {
        "env": "OCI_REGION",
        "vault": "communitylab-oci-region",
        "descripcion": "Region de OCI. Debe coincidir con la del bucket.",
        "obligatorio": "si",
    },
}


class SecretoNoEncontrado(Exception):
    """Se lanza cuando un secreto obligatorio no existe en ninguna fuente."""


# ---------------------------------------------------------------------------
# Fuente 1: archivo .env local  (por defecto, para trabajar en una computadora)
# ---------------------------------------------------------------------------
def _cargar_dotenv_una_vez() -> None:
    """Lee el archivo .env y mete sus valores en las variables de entorno."""
    if getattr(_cargar_dotenv_una_vez, "_hecho", False):
        return
    try:
        from dotenv import load_dotenv  # paquete python-dotenv
        load_dotenv()
    except ImportError:
        # Si python-dotenv no esta instalado, leemos el .env a mano.
        # Asi el proyecto arranca aunque falte la dependencia.
        ruta = os.path.join(os.getcwd(), ".env")
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if not linea or linea.startswith("#") or "=" not in linea:
                        continue
                    nombre, valor = linea.split("=", 1)
                    os.environ.setdefault(nombre.strip(), valor.strip().strip('"\''))
    _cargar_dotenv_una_vez._hecho = True  # type: ignore[attr-defined]


def _fuente_activa() -> str:
    """
    Devuelve 'env', 'vault' o 'auto'.

    Carga el .env ANTES de leer FUENTE_SECRETOS; si no, un FUENTE_SECRETOS
    definido dentro del .env se ignoraria en la primera llamada.
    """
    _cargar_dotenv_una_vez()
    return os.environ.get("FUENTE_SECRETOS", "env").lower()


def _leer_de_env(nombre_logico: str) -> str | None:
    """Lee un secreto del entorno (o del .env) usando su nombre en el catalogo."""
    _cargar_dotenv_una_vez()
    clave_env = CATALOGO_SECRETOS.get(nombre_logico, {}).get("env", nombre_logico)
    return os.environ.get(clave_env)


# ---------------------------------------------------------------------------
# Fuente 2: OCI Vault  (produccion en OCI Compute)
#
# Variables que usa (se leen siempre del entorno o del .env, nunca del Vault):
#   OCI_VAULT_ID        OCID del Vault (se acepta tambien OCI_VAULT_OCID)
#   OCI_AUTH            config (archivo ~/.oci/config) | instance_principal
#   OCI_REGION          region del Vault (opcional con instance_principal)
#   OCI_CONFIG_FILE     ruta del archivo de configuracion (solo con config)
#   OCI_CONFIG_PROFILE  perfil del archivo (solo con config)
# Son los mismos nombres que usa el backend (ver su docs/secretos.md).
#
# Nota de costo: usar el Vault virtual (el tipo por defecto) con clave de
# software. El Private Vault y las claves HSM dedicadas si tienen costo.
# Verificar los limites vigentes de Always Free antes de crear nada.
# ---------------------------------------------------------------------------
def _id_vault() -> str | None:
    """OCID del Vault, leido del entorno o del .env."""
    _cargar_dotenv_una_vez()
    return os.environ.get("OCI_VAULT_ID") or os.environ.get("OCI_VAULT_OCID")


@functools.lru_cache(maxsize=1)
def _cliente_vault():
    """
    Crea una sola vez el cliente oficial de OCI para leer secretos.

    Con OCI_AUTH=config usa el archivo de configuracion de OCI (para probar
    desde una computadora); con OCI_AUTH=instance_principal usa la identidad
    del servidor de OCI Compute, sin claves guardadas. El SDK (paquete oci)
    se importa aqui para que el panel arranque aunque no este instalado.
    Si falla, lanza la excepcion original y no se guarda en cache.
    """
    import oci  # se importa solo si de verdad se usa el Vault

    _cargar_dotenv_una_vez()
    autenticacion = os.environ.get("OCI_AUTH", "config").lower()
    region = os.environ.get("OCI_REGION") or None
    if autenticacion == "instance_principal":
        firmante = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        return oci.secrets.SecretsClient({"region": region} if region else {}, signer=firmante)
    ruta = os.path.expanduser(os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"))
    config = oci.config.from_file(ruta, os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT"))
    if region:
        config["region"] = region
    return oci.secrets.SecretsClient(config)


def _leer_de_vault(nombre_logico: str, cliente=None) -> str | None:
    """
    Lee un secreto de OCI Vault y devuelve su texto, o None si no se pudo.

    Busca el nombre del Vault en CATALOGO_SECRETOS (columna "vault"); un
    nombre fuera del catalogo devuelve None. Nunca lanza excepciones: si
    falta el SDK, OCI_VAULT_ID, el permiso o el propio secreto, registra un
    aviso SIN el valor y devuelve None, para que FUENTE_SECRETOS=auto pueda
    seguir con el .env. ``cliente`` permite usar un cliente falso en pruebas.
    """
    nombre_vault = CATALOGO_SECRETOS.get(nombre_logico, {}).get("vault")
    id_vault = _id_vault()
    if not nombre_vault:
        return None
    if not id_vault:
        # En modo auto es lo normal en una computadora: se sigue con el .env sin avisar.
        registrar = logger.info if _fuente_activa() == "auto" else logger.warning
        registrar("Falta OCI_VAULT_ID; no se puede leer %s de OCI Vault", nombre_logico)
        return None
    try:
        cliente = cliente if cliente is not None else _cliente_vault()
    except ImportError:
        logger.warning("El SDK de OCI (paquete oci) no esta instalado; no se puede leer OCI Vault")
        return None
    except Exception:
        logger.warning("No se pudo iniciar la sesion con OCI para leer el Vault (revisar OCI_AUTH y la configuracion de OCI)")
        return None
    try:
        respuesta = cliente.get_secret_bundle_by_name(secret_name=nombre_vault, vault_id=id_vault)
    except Exception as exc:
        # No se copia el texto del error: puede traer identificadores de la cuenta.
        estado = getattr(exc, "status", None)
        if estado == 404:
            logger.warning("OCI Vault no tiene el secreto '%s'", nombre_vault)
        elif estado in (401, 403):
            logger.warning("OCI rechazo el acceso al secreto '%s' (revisar grupo dinamico y politica 'read secret-family')", nombre_vault)
        else:
            logger.warning("No se pudo leer el secreto '%s' de OCI Vault (estado %s)", nombre_vault, estado or "sin respuesta")
        return None
    try:
        contenido = respuesta.data.secret_bundle_content.content
        valor = base64.b64decode(contenido, validate=True).decode("utf-8").strip()
    except Exception:
        logger.warning("El secreto '%s' de OCI Vault no tiene un texto valido", nombre_vault)
        return None
    return valor or None


# ---------------------------------------------------------------------------
# API publica: lo unico que el resto del equipo necesita conocer
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def obtener_secreto(nombre_logico: str, obligatorio: bool = True) -> str | None:
    """
    Devuelve el valor de un secreto, venga de donde venga.

    Ejemplo de uso:
        from core.secretos import obtener_secreto
        clave = obtener_secreto("GEMINI_API_KEY")

    El resultado se guarda en memoria (lru_cache), asi que llamarla muchas
    veces no vuelve a leer el archivo ni a consultar el Vault.
    """
    fuente = _fuente_activa()

    valor: str | None = None
    if fuente == "vault":
        valor = _leer_de_vault(nombre_logico)
    elif fuente == "auto":
        valor = _leer_de_vault(nombre_logico) or _leer_de_env(nombre_logico)
    else:  # "env" y cualquier valor desconocido
        valor = _leer_de_env(nombre_logico)

    if not valor and obligatorio:
        desc = CATALOGO_SECRETOS.get(nombre_logico, {}).get("descripcion", "")
        nombre_vault = CATALOGO_SECRETOS.get(nombre_logico, {}).get("vault", nombre_logico)
        ayuda = {
            "vault": f"Revisa OCI_VAULT_ID, OCI_AUTH y que el secreto '{nombre_vault}' exista en el Vault.",
            "auto": f"No esta en OCI Vault ('{nombre_vault}') ni en el .env.",
        }.get(fuente, "Copia .env.example a .env y llena ese valor.")
        raise SecretoNoEncontrado(
            f"Falta el secreto '{nombre_logico}' (fuente activa: {fuente}). "
            f"{desc} {ayuda}"
        )
    return valor


def diagnostico() -> list[dict[str, str]]:
    """
    Revisa que secretos estan configurados y cuales faltan, SIN mostrar
    ningun valor. Sirve para el panel de Streamlit y para que cada
    integrante verifique su entorno sin pedir ayuda.
    """
    fuente = _fuente_activa()
    reporte = []
    for nombre, meta in CATALOGO_SECRETOS.items():
        try:
            valor = obtener_secreto(nombre, obligatorio=False)
        except Exception:
            valor = None
        reporte.append({
            "secreto": nombre,
            "fuente": fuente,
            "estado": "configurado" if valor else "FALTA",
            "descripcion": meta["descripcion"],
        })
    return reporte


if __name__ == "__main__":
    # Ejecutar con:  python core/secretos.py
    # Para ver el motivo de un fallo de Vault, agrega logs:
    logging.basicConfig(level=logging.WARNING, format="  (log) %(message)s")

    print(f"Fuente activa: {_fuente_activa()}")
    if _fuente_activa() in ("vault", "auto"):
        print(f"OCI_VAULT_ID: {'definido' if _id_vault() else 'NO definido'}")
    print()
    for fila in diagnostico():
        marca = "OK  " if fila["estado"] == "configurado" else "FALTA"
        print(f"[{marca}] {fila['secreto']:<20} {fila['descripcion']}")
