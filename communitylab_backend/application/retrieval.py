"""Recuperación semántica de citas para el Motor FAQ.

Combina tres puertos del dominio: embeddings para convertir la consulta en
vector, almacén vectorial para encontrar candidatas y reranker para ordenarlas
por relevancia real. No conoce Cohere ni el formato del índice: sólo usa
contratos, de modo que cada pieza se puede reemplazar sin tocar este módulo.
"""

from communitylab_backend.domain.models import Evidence
from communitylab_backend.domain.ports import EmbeddingProvider, RerankerProvider, VectorStorePort

DEFAULT_CANDIDATES = 20


class SemanticRetriever:
    """Implementa ``RetrieverPort`` con embeddings, búsqueda vectorial y rerank.

    Pertenece a la capa de aplicación. Hace como máximo dos llamadas externas
    por consulta (una de embedding y una de rerank) y ninguna si la consulta
    está vacía o el almacén no devuelve candidatas. Nunca fabrica citas: sólo
    reordena y recorta las que entrega el almacén vectorial.
    """

    def __init__(self, embeddings: EmbeddingProvider, vector_store: VectorStorePort, reranker: RerankerProvider, candidate_limit: int = DEFAULT_CANDIDATES, min_score: float = 0.0):
        """Conecta los tres puertos y fija cuántas candidatas se piden al almacén.

        ``candidate_limit`` es el tamaño del grupo que el reranker reordena;
        debe ser mayor que el ``limit`` final para que el rerank aporte valor.
        ``min_score`` descarta las citas con relevancia (del reranker) menor a
        ese valor: sin él, una duda sin respuesta en la base recibiría igual
        la FAQ "menos mala". Con 0 (por defecto) no se descarta nada.
        """
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.reranker = reranker
        self.candidate_limit = max(1, candidate_limit)
        self.min_score = min_score

    def retrieve(self, query: str, limit: int = 5) -> list[Evidence]:
        """Recupera hasta ``limit`` citas ordenadas para una consulta sanitizada.

        Flujo: embedding de la consulta, búsqueda de candidatas, rerank y
        recorte. Una consulta vacía o sin candidatas devuelve una lista vacía.
        Propaga ``ProviderUnavailableError`` si Cohere falla y
        ``RetrievalError`` si el índice es inválido.
        """
        if not query or not query.strip():
            return []
        vector = self.embeddings.embed_query(query)
        candidates = self.vector_store.search(vector, max(self.candidate_limit, limit))
        if not candidates:
            return []
        return [item for item in self.reranker.rerank(query, candidates) if item.score >= self.min_score][:limit]
