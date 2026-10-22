"""Almacén vectorial local basado en un archivo JSON.

Implementa ``VectorStorePort`` para el Motor FAQ: carga un índice de FAQs ya
convertidas en vectores y busca por similitud coseno. Con unas pocas cientos
de FAQs no se necesita una base de datos vectorial; el mismo archivo puede
vivir luego en OCI Object Storage sin cambiar el contrato.

Formato del archivo (``version`` 1): ``embedding_model``, ``dimension`` y una
lista ``records`` con ``record_id``, ``snippet``, ``source`` y ``vector``.
"""

import json
import math
import os
from functools import lru_cache
from pathlib import Path

from communitylab_backend.domain.errors import RetrievalError
from communitylab_backend.domain.models import Evidence

INDEX_VERSION = 1
_VECTOR_DECIMALS = 6


def _normalize(vector: list[float]) -> list[float]:
    """Devuelve ``vector`` con norma 1, para que el coseno sea un producto punto.

    Produce ``RetrievalError`` si el vector es nulo, porque no tiene dirección.
    """
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise RetrievalError("El índice contiene un vector nulo")
    return [value / norm for value in vector]


@lru_cache(maxsize=4)
def _load_index(path: str, modified_ns: int) -> tuple[int, tuple[tuple[str, str, str, tuple[float, ...]], ...]]:
    """Lee y valida el índice; el resultado se cachea por ruta y fecha de cambio.

    Retorna la dimensión y los registros con el vector normalizado. Se
    recalcula sólo si el archivo cambia. Produce ``RetrievalError`` si falta,
    no es JSON o tiene un formato incompatible.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data["version"] != INDEX_VERSION:
            raise ValueError("versión de índice no soportada")
        dimension = int(data["dimension"])
        records = []
        for item in data["records"]:
            vector = item["vector"]
            if len(vector) != dimension:
                raise ValueError("dimensión de vector inconsistente")
            records.append((str(item["record_id"]), str(item["snippet"]), str(item["source"]), tuple(_normalize([float(value) for value in vector]))))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, RetrievalError):
            raise
        raise RetrievalError("El índice de FAQs no está disponible o tiene un formato incompatible") from exc
    if not records:
        raise RetrievalError("El índice de FAQs está vacío")
    return dimension, tuple(records)


class LocalVectorStore:
    """Busca vectores en un índice JSON local mediante similitud coseno.

    Pertenece a infraestructura. No llama a servicios externos ni calcula
    embeddings: recibe el vector de la consulta ya calculado.
    """

    def __init__(self, path: Path):
        """Recibe la ruta ``path`` del índice; la lectura se difiere a ``search``."""
        self.path = Path(path)

    def search(self, vector: list[float], limit: int) -> list[Evidence]:
        """Devuelve hasta ``limit`` citas ordenadas por similitud con ``vector``.

        El ``score`` de cada cita es el coseno (entre -1 y 1). Produce
        ``RetrievalError`` si el índice no existe, está dañado o su dimensión
        no coincide con la del vector (por ejemplo, otro modelo de embeddings).
        """
        try:
            modified = os.stat(self.path).st_mtime_ns
        except OSError as exc:
            raise RetrievalError("El índice de FAQs no está disponible o tiene un formato incompatible") from exc
        dimension, records = _load_index(str(self.path), modified)
        if len(vector) != dimension:
            raise RetrievalError(f"La consulta tiene {len(vector)} dimensiones pero el índice usa {dimension}; reconstruir el índice con el mismo modelo")
        query = _normalize(vector)
        scored = sorted(((sum(a * b for a, b in zip(query, stored)), record_id, snippet, source) for record_id, snippet, source, stored in records), key=lambda row: row[0], reverse=True)
        return [Evidence(record_id, snippet, source, round(score, 6)) for score, record_id, snippet, source in scored[:max(0, limit)]]


def write_index(path: Path, embedding_model: str, records: list[dict], vectors: list[list[float]]) -> None:
    """Escribe el índice JSON con un archivo temporal para evitar archivos a medias.

    ``records`` trae ``record_id``, ``snippet`` y ``source``; ``vectors`` trae
    un vector por registro, en el mismo orden. Produce ``RetrievalError`` si
    las cantidades no coinciden o no hay registros.
    """
    if not records or len(records) != len(vectors):
        raise RetrievalError("La cantidad de vectores no coincide con la de registros")
    payload = {"version": INDEX_VERSION, "embedding_model": embedding_model, "dimension": len(vectors[0]), "records": [{**record, "vector": [round(value, _VECTOR_DECIMALS) for value in vector]} for record, vector in zip(records, vectors)]}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
