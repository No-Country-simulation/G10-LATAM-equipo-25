"""Construye el índice vectorial de FAQs a partir de la base ``motor_educativo.db``.

Lee las filas marcadas como FAQ, deja una sola copia de cada pregunta, calcula sus
embeddings con Cohere y escribe el archivo JSON que usa ``LocalVectorStore``.
Se ejecuta una vez (o cuando cambian las FAQs); no se ejecuta en cada consulta.

Uso: ``python -m communitylab_backend.tools.build_faq_index --db RUTA --out RUTA``
"""

import argparse
import sqlite3
from pathlib import Path

from communitylab_backend.domain.errors import RetrievalError
from communitylab_backend.domain.ports import EmbeddingProvider
from communitylab_backend.infrastructure.vector_index import write_index

QUERY = "SELECT rowid, reviews, faq_answer, course_id FROM contenido_educativo WHERE is_faq = 1 ORDER BY rowid"


def load_faq_records(db_path: Path) -> list[dict]:
    """Lee las FAQs de la base y devuelve registros con una sola copia por pregunta.

    La base repite algunas preguntas en varios cursos; se conserva la primera
    para que la búsqueda no gaste citas en preguntas idénticas.

    Cada registro trae ``record_id``, ``snippet`` (pregunta y respuesta) y
    ``source`` (el curso). Produce ``RetrievalError`` si la base no existe, no
    tiene la tabla esperada o no contiene FAQs.
    """
    if not Path(db_path).is_file():
        raise RetrievalError("No se encontró la base de datos de FAQs")
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
            rows = connection.execute(QUERY).fetchall()
    except sqlite3.Error as exc:
        raise RetrievalError("La base de datos no tiene la tabla de FAQs esperada") from exc
    seen: set[str] = set()
    records = []
    for rowid, question, answer, course in rows:
        question, answer = (question or "").strip(), (answer or "").strip()
        if not question or not answer or question.casefold() in seen:
            continue
        seen.add(question.casefold())
        records.append({"record_id": f"faq-{rowid}", "snippet": f"Pregunta: {question}\nRespuesta: {answer}", "source": f"faq:{course or 'general'}"})
    if not records:
        raise RetrievalError("La base de datos no contiene FAQs")
    return records


def build_index(db_path: Path, out_path: Path, embeddings: EmbeddingProvider, embedding_model: str) -> int:
    """Calcula los vectores de todas las FAQs y escribe el índice en ``out_path``.

    Retorna la cantidad de FAQs indexadas. Hace pocas llamadas a Cohere (una
    por cada 96 textos). Propaga ``ProviderUnavailableError`` si Cohere falla.
    """
    records = load_faq_records(db_path)
    vectors = embeddings.embed_documents([record["snippet"] for record in records])
    write_index(out_path, embedding_model, records, vectors)
    return len(records)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la línea de comandos; retorna el código de salida.

    Toma clave, modelo y dimensión de ``Settings`` (variables de entorno o
    ``.env``). Imprime la cantidad indexada y la ruta, nunca la clave.
    """
    from communitylab_backend.config.settings import Settings
    from communitylab_backend.infrastructure.cohere_adapters import CohereEmbeddingAdapter

    parser = argparse.ArgumentParser(description="Construye el índice vectorial de FAQs.")
    parser.add_argument("--db", required=True, type=Path, help="Ruta de motor_educativo.db")
    parser.add_argument("--out", type=Path, default=None, help="Archivo de salida (por defecto FAQ_INDEX_PATH)")
    args = parser.parse_args(argv)
    settings = Settings()
    out = args.out or settings.faq_index_path
    embeddings = CohereEmbeddingAdapter(settings.cohere_api_key, settings.cohere_embed_model, settings.provider_timeout_seconds, output_dimension=settings.cohere_embed_dimension)
    count = build_index(args.db, out, embeddings, settings.cohere_embed_model)
    print(f"Índice listo: {count} FAQs en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
