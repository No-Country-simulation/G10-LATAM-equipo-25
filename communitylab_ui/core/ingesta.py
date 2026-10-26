"""
Ingesta de lotes en el panel: archivos JSON o CSV y lotes de ejemplo.

QUE ES ESTO
-----------
Convierte lo que sube el equipo (un export de Discord, un CSV de un
formulario, etc.) al formato de entrada del briefing, que es el que recibe
el backend:

    {
      "origen_comunidad": "...",
      "periodo_referencia": "...",
      "interacciones": [{"autor": ..., "canal": ..., "tipo": ..., "texto": ...}]
    }

El CSV necesita al menos la columna "texto". Las columnas "autor", "canal"
y "tipo" son opcionales.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

CARPETA_EJEMPLOS = Path(__file__).resolve().parent.parent / "data" / "lotes_ejemplo"
MAX_INTERACCIONES = 100


class LoteInvalido(Exception):
    """El archivo no tiene el formato esperado. El mensaje es apto para mostrarse."""


def _limpiar(filas: list[dict]) -> list[dict]:
    """Deja solo autor, canal, tipo y texto; descarta filas sin texto."""
    interacciones = []
    for i, fila in enumerate(filas, 1):
        texto = str(fila.get("texto") or fila.get("text") or "").strip()
        if not texto:
            continue
        interacciones.append({
            "id": str(fila.get("id") or f"msg_{i:04d}"),
            "autor": str(fila.get("autor") or fila.get("author") or "Anónimo").strip(),
            "canal": str(fila.get("canal") or fila.get("channel") or "sin canal").strip(),
            "tipo": str(fila.get("tipo") or fila.get("type") or "comentario").strip(),
            "texto": texto,
        })
    if not interacciones:
        raise LoteInvalido("El archivo no tiene ninguna interacción con texto.")
    if len(interacciones) > MAX_INTERACCIONES:
        raise LoteInvalido(f"El lote tiene {len(interacciones)} interacciones; el máximo es {MAX_INTERACCIONES}.")
    return interacciones


def leer_archivo(nombre: str, contenido: bytes, origen: str = "", periodo: str = "") -> dict:
    """Convierte un archivo subido (JSON o CSV) en un lote listo para el backend."""
    try:
        texto = contenido.decode("utf-8-sig")
        if nombre.lower().endswith(".csv"):
            filas = list(csv.DictReader(io.StringIO(texto)))
            datos = {}
        else:
            datos = json.loads(texto)
            filas = datos.get("interacciones") or datos.get("interactions") or []
    except (UnicodeDecodeError, ValueError, AttributeError) as exc:
        raise LoteInvalido("El archivo debe ser un JSON o CSV en UTF-8.") from exc
    return {
        "origen_comunidad": origen or datos.get("origen_comunidad") or datos.get("community_source") or "Comunidad",
        "periodo_referencia": periodo or datos.get("periodo_referencia") or datos.get("reference_period") or Path(nombre).stem,
        "interacciones": _limpiar(filas),
    }


def lotes_ejemplo() -> dict[str, Path]:
    """Lotes de demostracion disponibles: {nombre visible: ruta}."""
    if not CARPETA_EJEMPLOS.exists():
        return {}
    return {
        ruta.stem.replace("_", " "): ruta
        for ruta in sorted(CARPETA_EJEMPLOS.iterdir())
        if ruta.suffix.lower() in {".json", ".csv"}
    }


def leer_ejemplo(ruta: Path) -> dict:
    """Carga uno de los lotes de ejemplo."""
    return leer_archivo(ruta.name, ruta.read_bytes())


def lote_desde_dict(datos: dict, nombre: str = "lote") -> dict:
    """Normaliza un lote que ya viene como diccionario (en espanol o en ingles)."""
    return {
        "origen_comunidad": datos.get("origen_comunidad") or datos.get("community_source") or "Comunidad",
        "periodo_referencia": datos.get("periodo_referencia") or datos.get("reference_period") or nombre,
        "interacciones": _limpiar(datos.get("interacciones") or datos.get("interactions") or []),
    }


def leer_respuesta_guardada(nombre: str, contenido: bytes) -> tuple[dict, dict]:
    """
    Lee un archivo de salidas/respuestas del backend ({"entrada", "respuesta"}).

    Sirve para mostrar el panel sin backend encendido, con resultados reales
    generados antes con: python -m communitylab_backend.tools.process_batch ejemplos
    """
    try:
        datos = json.loads(contenido.decode("utf-8-sig"))
        return lote_desde_dict(datos["entrada"], Path(nombre).stem), datos["respuesta"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise LoteInvalido("El archivo no es una respuesta guardada de salidas/respuestas.") from exc


PLANTILLA_FAQS = (
    "pregunta,respuesta,curso\n"
    "\"¿Cómo estructuro un router en LangGraph?\",\"Usa add_conditional_edges hacia una función router "
    "que decide el siguiente nodo.\",langgraph\n"
)


def leer_faqs(nombre: str, contenido: bytes) -> list[dict]:
    """
    Lee un CSV (pregunta, respuesta, curso) o un JSON con FAQs nuevas.

    Devuelve las filas tal cual: la validacion la hace el backend, que es
    quien decide que se agrega a la base. El JSON puede ser una lista o un
    objeto con la lista en "faqs".
    """
    try:
        texto = contenido.decode("utf-8-sig")
        if nombre.lower().endswith(".csv"):
            return list(csv.DictReader(io.StringIO(texto)))
        datos = json.loads(texto)
    except (UnicodeDecodeError, ValueError, csv.Error) as exc:
        raise LoteInvalido("El archivo de FAQs debe ser un CSV o JSON en UTF-8.") from exc
    filas = datos.get("faqs") if isinstance(datos, dict) else datos
    if not isinstance(filas, list) or not filas or not all(isinstance(f, dict) for f in filas):
        raise LoteInvalido("El JSON debe ser una lista de FAQs (o un objeto con la lista en \"faqs\").")
    return filas
