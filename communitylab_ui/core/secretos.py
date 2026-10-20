"""
Gestion de secretos de CommunityLab.

IDEA CENTRAL
------------
El resto del equipo NUNCA lee variables de entorno ni habla con OCI Vault
directamente. Todos usan una sola funcion:

    from core.secretos import obtener_secreto
    clave = obtener_secreto("GEMINI_API_KEY")

De donde sale ese valor es problema de este archivo, no del que lo usa.
Hoy sale de un archivo .env local. Con OCI Vault configurado sale de ahi y
nadie mas tiene que cambiar una sola linea de su codigo.

COMO ELIGE LA FUENTE
--------------------
Se controla con la variable de entorno FUENTE_SECRETOS:

    FUENTE_SECRETOS=env    -> lee del archivo .env          (por defecto)
    FUENTE_SECRETOS=vault  -> lee de OCI Vault
    FUENTE_SECRETOS=auto   -> intenta Vault, si falla usa .env  (recomendado)

QUE NECESITA EL MODO vault / auto
---------------------------------
    1. OCI_VAULT_OCID en el .env (es un identificador, no un secreto).
    2. Un archivo ~/.oci/config con las credenciales de tu usuario de OCI
       (se genera con `oci setup config` o desde la consola de OCI).
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
# Fuente 1: archivo .env local
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
    _cargar_dotenv_una_vez()
    clave_env = CATALOGO_SECRETOS.get(nombre_logico, {}).get("env", nombre_logico)
    return os.environ.get(clave_env)


# ---------------------------------------------------------------------------
# Fuente 2: OCI Vault
#
# Nota de costo: usar el Vault virtual (el tipo por defecto) con clave de
# software. El Private Vault y las claves HSM dedicadas si tienen costo.
# Verificar los limites vigentes de Always Free antes de crear nada.
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _cliente_vault():
    """Crea una sola vez el cliente de OCI Secrets (import perezoso)."""
    import oci  # solo se necesita si se usa Vault

    perfil = os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT")
    cfg = oci.config.from_file(profile_name=perfil)
    return oci.secrets.SecretsClient(cfg)


def _leer_de_vault(nombre_logico: str) -> str | None:
    """
    Lee un secreto de OCI Vault por su nombre y devuelve su version vigente.

    Nunca lanza excepciones: si algo falla (sin ~/.oci/config, sin permisos,
    secreto inexistente, sin paquete oci) registra el motivo en el log y
    devuelve None. Asi el modo 'auto' puede caer a .env sin romperse.
    En el log se escribe el tipo de error, JAMAS el valor del secreto.
    """
    _cargar_dotenv_una_vez()
    vault_id = os.environ.get("OCI_VAULT_OCID")
    nombre_en_vault = CATALOGO_SECRETOS.get(nombre_logico, {}).get("vault")

    if not vault_id:
        logger.warning("OCI_VAULT_OCID no esta definido; no se puede leer '%s' de Vault.", nombre_logico)
        return None
    if not nombre_en_vault:
        logger.warning("'%s' no esta en el catalogo; no se puede buscar en Vault.", nombre_logico)
        return None

    try:
        respuesta = _cliente_vault().get_secret_bundle_by_name(
            secret_name=nombre_en_vault,
            vault_id=vault_id,
        )
        contenido = respuesta.data.secret_bundle_content.content  # viene en base64
        return base64.b64decode(contenido).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - queremos capturar todo a proposito
        logger.warning(
            "No se pudo leer '%s' (%s) de OCI Vault: %s: %s",
            nombre_logico, nombre_en_vault, type(exc).__name__, exc,
        )
        return None


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
        raise SecretoNoEncontrado(
            f"Falta el secreto '{nombre_logico}' (fuente activa: {fuente}). "
            f"{desc} "
            f"Revisa .env, o que exista en OCI Vault con el nombre "
            f"'{CATALOGO_SECRETOS.get(nombre_logico, {}).get('vault', '?')}'."
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
        hay_ocid = "definido" if os.environ.get("OCI_VAULT_OCID") else "NO definido"
        print(f"OCI_VAULT_OCID: {hay_ocid}")
    print()
    for fila in diagnostico():
        marca = "OK  " if fila["estado"] == "configurado" else "FALTA"
        print(f"[{marca}] {fila['secreto']:<20} {fila['descripcion']}")
