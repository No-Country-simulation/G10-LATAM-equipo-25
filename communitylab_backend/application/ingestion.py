"""Ingesta de lotes de interacciones desde archivos JSON o CSV.

Pertenece a la capa de aplicación. Convierte lo que exporta una comunidad
(Discord, Slack, foros, formularios) al formato que entiende el flujo. Acepta
los nombres del briefing en español (``origen_comunidad``, ``interacciones``,
``autor``, ``canal``, ``tipo``, ``texto``) y los del backend en inglés.

Limpieza que aplica: quita espacios sobrantes, descarta filas sin texto y
recorta textos demasiado largos. Los datos personales se ocultan después, en
el nodo ``sanitize`` del grafo.
"""

import csv
import json
import re
from pathlib import Path

from communitylab_backend.domain.errors import InvalidInteractionError

MAX_TEXT_CHARS = 10000
MAX_INTERACTIONS = 100
FIELDS = {"id": ("id",), "author": ("author", "autor"), "channel": ("channel", "canal"), "type": ("type", "tipo"), "text": ("text", "texto", "mensaje", "message")}


def _pick(row: dict, names: tuple[str, ...]) -> str | None:
    """Devuelve el primer valor no vacío de ``row`` entre los ``names`` aceptados."""
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return re.sub(r"\s+", " ", str(value)).strip()
    return None


def clean_interactions(rows: list[dict]) -> list[dict]:
    """Normaliza filas con nombres en español o inglés al formato del flujo.

    Retorna diccionarios con ``id``, ``author``, ``channel``, ``type`` y
    ``text``. Descarta filas sin texto y recorta el texto a
    ``MAX_TEXT_CHARS``. Produce ``InvalidInteractionError`` si no queda
    ninguna interacción o si hay más de ``MAX_INTERACTIONS``.
    """
    cleaned = []
    for row in rows:
        item = {field: _pick(row, names) for field, names in FIELDS.items()}
        if item["text"]:
            item["text"] = item["text"][:MAX_TEXT_CHARS]
            cleaned.append(item)
    if not cleaned:
        raise InvalidInteractionError("El archivo no contiene interacciones con texto")
    if len(cleaned) > MAX_INTERACTIONS:
        raise InvalidInteractionError(f"El lote tiene {len(cleaned)} interacciones; el máximo es {MAX_INTERACTIONS}")
    return cleaned


def load_batch_file(path: Path, community_source: str | None = None, reference_period: str | None = None) -> dict:
    """Lee un lote desde ``path`` (``.json`` o ``.csv``) y lo deja listo para el flujo.

    Un JSON trae la comunidad, el período y la lista de interacciones. Un CSV
    trae una interacción por fila (columnas ``autor``, ``canal``, ``tipo``,
    ``texto``); la comunidad y el período se toman de los argumentos o del
    nombre del archivo. Retorna ``community_source``, ``reference_period`` e
    ``interactions``. Produce ``InvalidInteractionError`` si el archivo no se
    puede leer o no tiene el formato esperado.
    """
    path = Path(path)
    try:
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            data = {}
        else:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            rows = data.get("interacciones") or data.get("interactions") or []
    except (OSError, ValueError, AttributeError) as exc:
        raise InvalidInteractionError(f"No se pudo leer el lote {path.name}: debe ser un JSON o CSV válido") from exc
    return {
        "community_source": community_source or data.get("origen_comunidad") or data.get("community_source") or "comunidad",
        "reference_period": reference_period or data.get("periodo_referencia") or data.get("reference_period") or path.stem,
        "interactions": clean_interactions(rows),
    }
