"""
Gestion de secretos de CommunityLab.

IDEA CENTRAL
------------
El resto del equipo NUNCA lee variables de entorno ni habla con OCI Vault
directamente. Todos usan una sola funcion:

    from core.secretos import obtener_secreto
    clave = obtener_secreto("GEMINI_API_KEY")

De donde sale ese valor es problema de este archivo, no del que lo usa.
Hoy sale de un archivo .env local. Manana saldra de OCI Vault y nadie mas
tendra que cambiar una sola linea de su codigo.

COMO ELIGE LA FUENTE
--------------------
Se controla con la variable de entorno FUENTE_SECRETOS:

    FUENTE_SECRETOS=env    -> lee del archivo .env          (por defecto, Sprint 1)
    FUENTE_SECRETOS=vault  -> lee de OCI Vault              (Sprint 2)
    FUENTE_SECRETOS=auto   -> intenta Vault, si falla usa .env

REGLA INNEGOCIABLE DEL EQUIPO
-----------------------------
El archivo .env NUNCA se sube al repositorio. Debe estar en .gitignore
desde el primer commit. Lo que si se sube es .env.example, que tiene los
nombres de las variables pero ningun valor real.
"""

from __future__ import annotations

import os
import functools
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Catalogo de secretos del proyecto.
#
# Cada entrada dice: nombre logico -> (nombre en .env, nombre en OCI Vault).
# Tener el catalogo en un solo lugar evita que cada quien invente su propio
# nombre de variable y que despues nadie sepa cual es la buena.
# ---------------------------------------------------------------------------
CATALOGO_SECRETOS: dict[str, dict[str, str]] = {
    "GEMINI_API_KEY": {
        "env": "GEMINI_API_KEY",
        "vault": "communitylab-gemini-api-key",
        "descripcion": "Clave del modelo Gemini que analiza y redacta.",
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
# Fuente 1: archivo .env local  (Sprint 1 - lo que usamos hoy)
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


def _leer_de_env(nombre_logico: str) -> str | None:
    _cargar_dotenv_una_vez()
    clave_env = CATALOGO_SECRETOS.get(nombre_logico, {}).get("env", nombre_logico)
    return os.environ.get(clave_env)


# ---------------------------------------------------------------------------
# Fuente 2: OCI Vault  (Sprint 2 - todavia NO conectado)
#
# Nota de costo: usar el Vault virtual (el tipo por defecto) con clave de
# software. El Private Vault y las claves HSM dedicadas si tienen costo.
# Verificar los limites vigentes de Always Free antes de crear nada.
# ---------------------------------------------------------------------------
def _leer_de_vault(nombre_logico: str) -> str | None:
    """
    Lee un secreto de OCI Vault.

    Pendiente de Sprint 2. Cuando se implemente, el resto del proyecto
    no se entera: sigue llamando obtener_secreto() igual que hoy.

    El esqueleto de la implementacion es aproximadamente:

        import base64, oci
        cfg = oci.config.from_file()
        cliente = oci.secrets.SecretsClient(cfg)
        respuesta = cliente.get_secret_bundle_by_name(
            secret_name=CATALOGO_SECRETOS[nombre_logico]["vault"],
            vault_id=os.environ["OCI_VAULT_OCID"],
        )
        contenido = respuesta.data.secret_bundle_content.content
        return base64.b64decode(contenido).decode("utf-8")
    """
    logger.debug("Vault todavia no implementado; se omite %s", nombre_logico)
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
    fuente = os.environ.get("FUENTE_SECRETOS", "env").lower()

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
            f"Copia .env.example a .env y llena ese valor."
        )
    return valor


def diagnostico() -> list[dict[str, str]]:
    """
    Revisa que secretos estan configurados y cuales faltan, SIN mostrar
    ningun valor. Sirve para el panel de Streamlit y para que cada
    integrante verifique su entorno sin pedir ayuda.
    """
    fuente = os.environ.get("FUENTE_SECRETOS", "env").lower()
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
    print(f"Fuente activa: {os.environ.get('FUENTE_SECRETOS', 'env')}\n")
    for fila in diagnostico():
        marca = "OK  " if fila["estado"] == "configurado" else "FALTA"
        print(f"[{marca}] {fila['secreto']:<20} {fila['descripcion']}")
