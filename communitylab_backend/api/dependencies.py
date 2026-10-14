"""Punto de composición de la capa API.

Selecciona adaptadores a partir de ``Settings`` para que el dominio y el
grafo no necesiten conocer los proveedores concretos.
"""

from functools import lru_cache

from communitylab_backend.application.orchestration import ProcessingWorkflow
from communitylab_backend.application.retrieval import SemanticRetriever
from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import ProviderUnavailableError
from communitylab_backend.infrastructure.cohere_adapters import CohereEmbeddingAdapter, CohereRerankerAdapter
from communitylab_backend.infrastructure.gemini_adapter import GeminiLLMAdapter
from communitylab_backend.infrastructure.oci_storage import OCIObjectStorageAdapter
from communitylab_backend.infrastructure.vector_index import LocalVectorStore
from communitylab_backend.infrastructure.local import ExistingLocalRagAdapter, ExistingSanitizerAdapter, LocalObjectStorageAdapter, MockLLMProvider, MockRetriever


@lru_cache
def get_settings() -> Settings:
    """Carga y almacena en caché la configuración validada del entorno.

    Retorna ``Settings``. Puede producir un error de validación si una
    variable es inválida. Lee ``.env`` cuando existe, sin registrar secretos.
    """

    return Settings()


def build_retriever(settings: Settings):
    """Elige el recuperador según ``settings.retrieval_provider``.

    Retorna un ``RetrieverPort`` o ``None`` si la selección es desconocida. La
    opción ``semantic`` usa Cohere (embedding y rerank) y el índice local de
    FAQs; produce ``ProviderUnavailableError`` si no se configuró Cohere.
    """

    if settings.retrieval_provider == "mock":
        return MockRetriever()
    if settings.retrieval_provider == "existing_local":
        return ExistingLocalRagAdapter()
    if settings.retrieval_provider == "semantic":
        if settings.embedding_provider != "cohere" or settings.reranker_provider != "cohere":
            raise ProviderUnavailableError("La búsqueda semántica requiere EMBEDDING_PROVIDER=cohere y RERANKER_PROVIDER=cohere")
        embeddings = CohereEmbeddingAdapter(settings.cohere_api_key, settings.cohere_embed_model, settings.provider_timeout_seconds, output_dimension=settings.cohere_embed_dimension)
        reranker = CohereRerankerAdapter(settings.cohere_api_key, settings.cohere_rerank_model, settings.provider_timeout_seconds)
        return SemanticRetriever(embeddings, LocalVectorStore(settings.faq_index_path), reranker, settings.retrieval_candidates)
    return None


def build_storage(settings: Settings):
    """Elige el almacenamiento de paquetes según ``settings.storage_provider``.

    Retorna un ``ObjectStoragePort`` o ``None`` si la selección es desconocida.
    La opción ``oci`` guarda en un bucket de OCI; produce
    ``ProviderUnavailableError`` si falta namespace, bucket o la sesión de OCI.
    """

    if settings.storage_provider == "local":
        return LocalObjectStorageAdapter(settings.local_storage_dir)
    if settings.storage_provider == "oci":
        return OCIObjectStorageAdapter(settings.oci_namespace, settings.oci_bucket, settings.oci_region, settings.oci_object_prefix, settings.oci_auth, settings.oci_config_file, settings.oci_config_profile, settings.provider_timeout_seconds)
    return None


def build_workflow(settings: Settings) -> ProcessingWorkflow:
    """Construye el grafo con los adaptadores elegidos por ``settings``.

    Retorna ``ProcessingWorkflow``. Selecciona mocks locales por defecto;
    los stubs externos fallan de forma explícita. Produce
    ``ProviderUnavailableError`` ante una selección desconocida.
    """

    llm = MockLLMProvider(settings.success_keywords, settings.faq_keywords, settings.success_types) if settings.llm_provider == "mock" else GeminiLLMAdapter(settings.gemini_api_key, settings.gemini_model, settings.provider_timeout_seconds) if settings.llm_provider == "gemini" else None
    retriever = build_retriever(settings)
    storage = build_storage(settings)
    if llm is None or retriever is None or storage is None:
        raise ProviderUnavailableError("Unknown configured provider")
    return ProcessingWorkflow(ExistingSanitizerAdapter(), llm, retriever, storage)


def get_workflow() -> ProcessingWorkflow:
    """Entrega el flujo a FastAPI y permite sustituirlo en tests.

    Retorna un ``ProcessingWorkflow`` construido con la configuración actual.
    Puede propagar errores de configuración o proveedor.
    """

    return build_workflow(get_settings())
