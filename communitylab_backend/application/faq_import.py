"""Lectura y validación de FAQs nuevas para agregarlas a la base.

Pertenece a la capa de aplicación. Convierte un archivo CSV (columnas
``pregunta``, ``respuesta``, ``curso``) o JSON (una lista de objetos, o un
objeto con la lista en ``faqs``) en filas limpias y validadas. Acepta los
nombres en español y en inglés (``question``, ``answer``, ``course``).

No escribe nada: la escritura, con copia de seguridad previa, la hace
``application.knowledge.KnowledgeService`` a través del puerto
``KnowledgeBasePort``. La API HTTP y la herramienta de terminal
(``tools/import_faqs.py``) usan ese mismo servicio.
"""

import csv
import io
import json
import re

from communitylab_backend.domain.errors import InvalidInteractionError

MAX_FAQS = 200
MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 5000
MAX_COURSE_CHARS = 120
FIELDS = {"question": ("question", "pregunta"), "answer": ("answer", "respuesta"), "course": ("course", "curso", "course_id")}


def read_faq_file(name: str, content: bytes) -> list[dict]:
    """Lee el archivo ``name`` (``.csv`` o ``.json``) y devuelve sus filas sin validar.

    ``content`` son los bytes del archivo en UTF-8. Produce
    ``InvalidInteractionError`` si no se puede leer o no tiene una lista de FAQs.
    """
    try:
        text = content.decode("utf-8-sig")
        if name.lower().endswith(".csv"):
            return list(csv.DictReader(io.StringIO(text)))
        data = json.loads(text)
    except (UnicodeDecodeError, ValueError, csv.Error) as exc:
        raise InvalidInteractionError("El archivo de FAQs debe ser un CSV o JSON válido en UTF-8") from exc
    rows = data.get("faqs") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise InvalidInteractionError("El JSON debe ser una lista de FAQs o un objeto con la lista en «faqs»")
    return rows


def _pick(row: dict, names: tuple[str, ...]) -> str:
    """Devuelve el primer valor no vacío de ``row`` entre ``names``, sin espacios sobrantes."""
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return re.sub(r"\s+", " ", str(value)).strip()
    return ""


def clean_faq_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Valida las filas y las separa en válidas e inválidas.

    Cada FAQ válida queda como ``{"question", "answer", "course"}``; si falta
    el curso se usa ``general``. Cada inválida trae ``row`` (número de fila,
    desde 1) y ``reason``. Produce ``InvalidInteractionError`` si no hay
    filas o hay más de ``MAX_FAQS``.
    """
    if not rows:
        raise InvalidInteractionError("El archivo no tiene FAQs")
    if len(rows) > MAX_FAQS:
        raise InvalidInteractionError(f"El archivo tiene {len(rows)} FAQs; el máximo por carga es {MAX_FAQS}")
    valid, invalid = [], []
    for number, row in enumerate(rows, 1):
        question, answer = _pick(row, FIELDS["question"]), _pick(row, FIELDS["answer"])
        course = _pick(row, FIELDS["course"]) or "general"
        if not question or not answer:
            invalid.append({"row": number, "reason": "Falta la pregunta o la respuesta"})
        elif len(question) > MAX_QUESTION_CHARS or len(answer) > MAX_ANSWER_CHARS or len(course) > MAX_COURSE_CHARS:
            invalid.append({"row": number, "reason": f"Texto demasiado largo (pregunta hasta {MAX_QUESTION_CHARS}, respuesta hasta {MAX_ANSWER_CHARS} caracteres)"})
        else:
            valid.append({"question": question, "answer": answer, "course": course})
    return valid, invalid
