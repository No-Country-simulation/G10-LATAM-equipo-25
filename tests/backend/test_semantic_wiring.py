"""Pruebas del cableado de la búsqueda semántica en la composición de la API."""

import pytest

from communitylab_backend.application.retrieval import SemanticRetriever
from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import ProviderUnavailableError


@pytest.fixture
def dependencies():
    """Importa la composición de la API.

    Antes se inyectaba un ``dataset_builder`` falso porque el módulo no
    estaba en el repositorio; desde la integración el sanitizador es propio
    (``infrastructure/pii.py``) y ya no hace falta.
    """
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


def test_default_retrieval_is_the_faq_database(dependencies):
    """Por defecto se busca en ``motor_educativo.db``, sin claves ni red."""
    assert type(dependencies.build_retriever(settings())).__name__ == "SqliteFaqRetriever"
