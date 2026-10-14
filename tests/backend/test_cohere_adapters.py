"""Pruebas de los adaptadores de Cohere con clientes falsos, sin red."""

from types import SimpleNamespace

import pytest

from communitylab_backend.domain.errors import ProviderUnavailableError
from communitylab_backend.domain.models import Evidence
from communitylab_backend.infrastructure.cohere_adapters import CohereEmbeddingAdapter, CohereRerankerAdapter


class FakeApiError(Exception):
    """Error falso con ``status_code`` como el del SDK."""

    def __init__(self, status_code):
        """Guarda el código HTTP simulado."""
        super().__init__("secreto-en-el-mensaje")
        self.status_code = status_code


class FakeClient:
    """Cliente falso que registra llamadas y devuelve respuestas fijas."""

    def __init__(self, error=None, rerank_results=None):
        """Configura el error a lanzar o los resultados de rerank."""
        self.calls = []
        self.error = error
        self.rerank_results = rerank_results

    def embed(self, **kwargs):
        """Devuelve un vector de un elemento por texto recibido."""
        self.calls.append(("embed", kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(embeddings=SimpleNamespace(float_=[[float(len(t))] for t in kwargs["texts"]]))

    def rerank(self, **kwargs):
        """Devuelve los resultados configurados."""
        self.calls.append(("rerank", kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(results=self.rerank_results)


def evidences(count):
    """Crea ``count`` citas de prueba."""
    return [Evidence(f"r{i}", f"texto {i}", "faq", 0.1) for i in range(count)]


def test_embed_documents_batches_and_keeps_order():
    """Parte en lotes y conserva el orden de los vectores."""
    client = FakeClient()
    adapter = CohereEmbeddingAdapter(None, batch_size=2, client=client)
    vectors = adapter.embed_documents(["a", "bb", "ccc"])
    assert vectors == [[1.0], [2.0], [3.0]]
    assert [c[1]["input_type"] for c in client.calls] == ["search_document"] * 2
    assert client.calls[0][1]["request_options"] == {"max_retries": 0}


def test_embed_documents_empty_makes_no_call():
    """Una lista vacía no consume cuota."""
    client = FakeClient()
    assert CohereEmbeddingAdapter(None, client=client).embed_documents([]) == []
    assert client.calls == []


def test_embed_query_uses_query_type_and_rejects_empty():
    """La consulta usa ``search_query`` y no acepta texto vacío."""
    client = FakeClient()
    adapter = CohereEmbeddingAdapter(None, client=client)
    assert adapter.embed_query("hola") == [4.0]
    assert client.calls[0][1]["input_type"] == "search_query"
    with pytest.raises(ProviderUnavailableError):
        adapter.embed_query("  ")


def test_embed_errors_are_translated_without_leaking():
    """Los errores del SDK se traducen sin copiar su mensaje."""
    with pytest.raises(ProviderUnavailableError) as limit:
        CohereEmbeddingAdapter(None, client=FakeClient(FakeApiError(429))).embed_query("x")
    assert "límite" in str(limit.value) and "secreto" not in str(limit.value)
    with pytest.raises(ProviderUnavailableError) as other:
        CohereEmbeddingAdapter(None, client=FakeClient(FakeApiError(500))).embed_query("x")
    assert "secreto" not in str(other.value)


def test_missing_key_is_unavailable():
    """Sin clave el adaptador falla de forma explícita."""
    with pytest.raises(ProviderUnavailableError):
        CohereEmbeddingAdapter(None)
    with pytest.raises(ProviderUnavailableError):
        CohereRerankerAdapter("")


def test_rerank_reorders_and_keeps_record_ids():
    """Reordena por relevancia, conserva ``record_id`` y actualiza ``score``."""
    results = [SimpleNamespace(index=2, relevance_score=0.9), SimpleNamespace(index=0, relevance_score=0.4)]
    client = FakeClient(rerank_results=results)
    ranked = CohereRerankerAdapter(None, top_n=2, client=client).rerank("q", evidences(3))
    assert [e.record_id for e in ranked] == ["r2", "r0"]
    assert [e.score for e in ranked] == [0.9, 0.4]
    assert client.calls[0][1]["top_n"] == 2


def test_rerank_skips_api_for_zero_or_one_candidate():
    """Con menos de dos citas no se llama al proveedor."""
    client = FakeClient()
    adapter = CohereRerankerAdapter(None, client=client)
    assert adapter.rerank("q", []) == []
    assert len(adapter.rerank("q", evidences(1))) == 1
    assert client.calls == []


@pytest.mark.parametrize("results", [[], [SimpleNamespace(index=9, relevance_score=1)], [SimpleNamespace(index=0, relevance_score=1), SimpleNamespace(index=0, relevance_score=1)]])
def test_rerank_rejects_invalid_responses(results):
    """Respuestas vacías, fuera de rango o duplicadas fallan."""
    with pytest.raises(ProviderUnavailableError):
        CohereRerankerAdapter(None, client=FakeClient(rerank_results=results)).rerank("q", evidences(3))


def test_rerank_translates_errors():
    """Un fallo del SDK se traduce a error de dominio."""
    with pytest.raises(ProviderUnavailableError):
        CohereRerankerAdapter(None, client=FakeClient(FakeApiError(429))).rerank("q", evidences(2))
