"""Pruebas del recuperador semántico con puertos falsos, sin red."""

import pytest

from communitylab_backend.application.retrieval import SemanticRetriever
from communitylab_backend.domain.errors import ProviderUnavailableError, RetrievalError
from communitylab_backend.domain.models import Evidence


class FakeEmbeddings:
    """Embeddings falsos que registran las consultas recibidas."""

    def __init__(self, error=None):
        """Configura un error opcional y la lista de consultas."""
        self.queries, self.error = [], error

    def embed_documents(self, texts):
        """No se usa en estas pruebas; devuelve un vector por texto."""
        return [[1.0] for _ in texts]

    def embed_query(self, text):
        """Registra la consulta y devuelve un vector fijo."""
        if self.error:
            raise self.error
        self.queries.append(text)
        return [1.0, 0.0]


class FakeStore:
    """Almacén falso con candidatas fijas."""

    def __init__(self, candidates):
        """Guarda las candidatas y los límites pedidos."""
        self.candidates, self.limits = candidates, []

    def search(self, vector, limit):
        """Registra el límite y devuelve las candidatas."""
        self.limits.append(limit)
        return list(self.candidates)


class FakeReranker:
    """Reranker falso que invierte el orden de las candidatas."""

    def __init__(self):
        """Inicializa el registro de llamadas."""
        self.calls = 0

    def rerank(self, query, candidates):
        """Devuelve las candidatas en orden inverso."""
        self.calls += 1
        return list(reversed(candidates))


def cites(count):
    """Crea ``count`` citas de prueba."""
    return [Evidence(f"r{i}", f"texto {i}", "faq", 0.5) for i in range(count)]


def test_retrieve_reranks_and_trims_to_limit():
    """Reordena con el reranker y recorta al límite pedido."""
    embeddings, reranker = FakeEmbeddings(), FakeReranker()
    retriever = SemanticRetriever(embeddings, FakeStore(cites(5)), reranker, candidate_limit=10)
    result = retriever.retrieve("¿Qué es MDP?", limit=2)
    assert [item.record_id for item in result] == ["r4", "r3"]
    assert embeddings.queries == ["¿Qué es MDP?"] and reranker.calls == 1


def test_candidate_limit_never_below_requested_limit():
    """Pide al almacén al menos tantas candidatas como el límite final."""
    store = FakeStore(cites(3))
    SemanticRetriever(FakeEmbeddings(), store, FakeReranker(), candidate_limit=2).retrieve("q", limit=7)
    assert store.limits == [7]


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_query_makes_no_calls(query):
    """Una consulta vacía no gasta cuota ni toca el almacén."""
    embeddings, store, reranker = FakeEmbeddings(), FakeStore(cites(2)), FakeReranker()
    assert SemanticRetriever(embeddings, store, reranker).retrieve(query) == []
    assert embeddings.queries == [] and store.limits == [] and reranker.calls == 0


def test_no_candidates_skips_rerank():
    """Sin candidatas no se llama al reranker."""
    reranker = FakeReranker()
    assert SemanticRetriever(FakeEmbeddings(), FakeStore([]), reranker).retrieve("q") == []
    assert reranker.calls == 0


def test_provider_errors_propagate():
    """Un fallo de Cohere llega intacto a la capa API."""
    with pytest.raises(ProviderUnavailableError):
        SemanticRetriever(FakeEmbeddings(ProviderUnavailableError("x")), FakeStore(cites(1)), FakeReranker()).retrieve("q")


def test_store_errors_propagate():
    """Un índice inválido se informa como error de recuperación."""
    class BrokenStore:
        """Almacén que siempre falla."""

        def search(self, vector, limit):
            """Lanza un error de recuperación."""
            raise RetrievalError("índice dañado")

    with pytest.raises(RetrievalError):
        SemanticRetriever(FakeEmbeddings(), BrokenStore(), FakeReranker()).retrieve("q")


def test_min_score_drops_irrelevant_citations():
    """Con umbral, las citas de baja relevancia se descartan."""
    candidates = [Evidence("buena", "texto", "faq", 0.9), Evidence("irrelevante", "texto", "faq", 0.2)]
    retriever = SemanticRetriever(FakeEmbeddings(), FakeStore(candidates), FakeReranker(), min_score=0.5)
    assert [item.record_id for item in retriever.retrieve("q", limit=3)] == ["buena"]
    assert len(SemanticRetriever(FakeEmbeddings(), FakeStore(candidates), FakeReranker()).retrieve("q", limit=3)) == 2
