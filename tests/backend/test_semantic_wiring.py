"""Pruebas del cableado de la búsqueda semántica en la composición de la API."""

import sys
import types

import pytest

from communitylab_backend.application.retrieval import SemanticRetriever
from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import ProviderUnavailableError


@pytest.fixture
def dependencies(monkeypatch):
    """Importa la composición con un ``dataset_builder`` falso.

    El módulo real no está en el repositorio; el falso sólo satisface el
    ``import`` de ``local.py`` y no se usa en estas pruebas.
    """
    package = types.ModuleType("dataset_builder")
    pii = types.ModuleType("dataset_builder.pii")
    pii.sanitize = lambda text, *args, **kwargs: text
    monkeypatch.setitem(sys.modules, "dataset_builder", package)
    monkeypatch.setitem(sys.modules, "dataset_builder.pii", pii)
    from communitylab_backend.api import dependencies as module
    return module


def settings(**values):
    """Crea ``Settings`` aislados del archivo ``.env`` local."""
    return Settings(_env_file=None, **values)


def test_semantic_retrieval_builds_the_full_chain(dependencies, tmp_path):
    """La opción ``semantic`` arma embeddings, índice y reranker de Cohere."""
    config = settings(retrieval_provider="semantic", embedding_provider="cohere", reranker_provider="cohere", cohere_api_key="clave-falsa", faq_index_path=tmp_path / "i.json", retrieval_candidates=7)
    retriever = dependencies.build_workflow(config).retriever
    assert isinstance(retriever, SemanticRetriever) and retriever.candidate_limit == 7


def test_semantic_requires_cohere_providers(dependencies):
    """Sin ``cohere`` en embeddings y rerank la composición falla con un mensaje claro."""
    with pytest.raises(ProviderUnavailableError, match="EMBEDDING_PROVIDER"):
        dependencies.build_retriever(settings(retrieval_provider="semantic", cohere_api_key="clave-falsa"))


def test_semantic_without_key_is_unavailable(dependencies):
    """Sin clave de Cohere la composición falla de forma explícita."""
    with pytest.raises(ProviderUnavailableError):
        dependencies.build_retriever(settings(retrieval_provider="semantic", embedding_provider="cohere", reranker_provider="cohere"))


def test_default_retrieval_is_still_the_mock(dependencies):
    """El comportamiento por defecto no cambia: sigue usando el mock."""
    assert type(dependencies.build_retriever(settings())).__name__ == "MockRetriever"
