"""Prueba rápida de la búsqueda semántica desde la terminal.

Construye el mismo recuperador que usa la API (embedding, índice local y
rerank de Cohere) y muestra las citas para una pregunta. Gasta 2 llamadas a
Cohere por ejecución.

Uso: ``python -m communitylab_backend.tools.search_faq "¿Qué es MDP?"``
"""

import argparse

from communitylab_backend.api.dependencies import get_api_key
from communitylab_backend.application.retrieval import SemanticRetriever
from communitylab_backend.config.settings import Settings
from communitylab_backend.infrastructure.cohere_adapters import CohereEmbeddingAdapter, CohereRerankerAdapter
from communitylab_backend.infrastructure.vector_index import LocalVectorStore


def main(argv: list[str] | None = None) -> int:
    """Busca la pregunta recibida e imprime las citas; retorna el código de salida.

    Usa ``Settings`` para modelos e índice y ``get_api_key`` para la clave de
    Cohere (entorno u OCI Vault). Propaga los errores de
    dominio con su mensaje seguro.
    """
    parser = argparse.ArgumentParser(description="Busca FAQs similares a una pregunta.")
    parser.add_argument("question", help="Pregunta del estudiante")
    parser.add_argument("--limit", type=int, default=3, help="Cantidad de citas a mostrar")
    args = parser.parse_args(argv)
    settings = Settings()
    cohere_key = get_api_key(settings, "COHERE_API_KEY")
    retriever = SemanticRetriever(
        CohereEmbeddingAdapter(cohere_key, settings.cohere_embed_model, settings.provider_timeout_seconds, output_dimension=settings.cohere_embed_dimension),
        LocalVectorStore(settings.faq_index_path),
        CohereRerankerAdapter(cohere_key, settings.cohere_rerank_model, settings.provider_timeout_seconds),
        settings.retrieval_candidates,
    )
    for position, item in enumerate(retriever.retrieve(args.question, args.limit), 1):
        print(f"{position}. [{item.score:.3f}] {item.source} ({item.record_id})\n   {item.snippet}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
