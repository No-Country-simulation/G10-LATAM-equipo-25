"""Construye el índice vectorial de FAQs a partir de la base ``motor_educativo.db``.

Lee las filas marcadas como FAQ, deja una sola copia de cada pregunta, calcula sus
embeddings con Cohere y escribe el archivo JSON que usa ``LocalVectorStore``.
Se ejecuta una vez (o cuando cambian las FAQs); no se ejecuta en cada consulta.

Uso: ``python -m communitylab_backend.tools.build_faq_index`` (por defecto lee
``data/motor_educativo.db`` y escribe ``data/faq_index.json``).
"""

import argparse
from pathlib import Path

from communitylab_backend.domain.ports import EmbeddingProvider
from communitylab_backend.infrastructure.faq_database import load_faq_records as read_faq_database
from communitylab_backend.infrastructure.vector_index import write_index


def load_faq_records(db_path: Path) -> list[dict]:
    """Lee las FAQs de la base y devuelve registros con una sola copia por pregunta.

    Reutiliza la lectura de ``infrastructure.faq_database`` para que el índice
    vectorial y la búsqueda local partan exactamente de las mismas FAQs. Cada
    registro trae ``record_id``, ``snippet`` (pregunta y respuesta) y
    ``source`` (el curso). Produce ``RetrievalError`` si la base no existe, no
    tiene la tabla esperada o no contiene FAQs.
    """
    return [{key: record[key] for key in ("record_id", "snippet", "source")} for record in read_faq_database(db_path)]


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

    Toma modelo y dimensión de ``Settings`` (variables de entorno o ``.env``)
    y la clave de Cohere de ``get_api_key`` (entorno u OCI Vault, según
    ``SECRET_PROVIDER``). Imprime la cantidad indexada y la ruta, nunca la clave.
    """
    from communitylab_backend.api.dependencies import get_api_key
    from communitylab_backend.config.settings import Settings
    from communitylab_backend.infrastructure.cohere_adapters import CohereEmbeddingAdapter

    parser = argparse.ArgumentParser(description="Construye el índice vectorial de FAQs.")
    parser.add_argument("--db", type=Path, default=None, help="Ruta de motor_educativo.db (por defecto FAQ_DB_PATH)")
    parser.add_argument("--out", type=Path, default=None, help="Archivo de salida (por defecto FAQ_INDEX_PATH)")
    args = parser.parse_args(argv)
    settings = Settings()
    out = args.out or settings.faq_index_path
    embeddings = CohereEmbeddingAdapter(get_api_key(settings, "COHERE_API_KEY"), settings.cohere_embed_model, settings.provider_timeout_seconds, output_dimension=settings.cohere_embed_dimension)
    count = build_index(args.db or settings.faq_db_path, out, embeddings, settings.cohere_embed_model)
    print(f"Índice listo: {count} FAQs en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
