"""Punto de composición de la capa API.

Selecciona adaptadores a partir de ``Settings`` para que el dominio y el
grafo no necesiten conocer los proveedores concretos.
"""

from functools import lru_cache

from communitylab_backend.application.knowledge import KnowledgeService
from communitylab_backend.application.orchestration import ProcessingWorkflow
from communitylab_backend.application.retrieval import SemanticRetriever
from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import ProviderUnavailableError
from communitylab_backend.infrastructure.cohere_adapters import CohereEmbeddingAdapter, CohereRerankerAdapter
from communitylab_backend.infrastructure.doubt_history import DoubtHistory
from communitylab_backend.infrastructure.faq_database import SqliteFaqRetriever, SqliteKnowledgeBase
from communitylab_backend.infrastructure.gemini_adapter import GeminiLLMAdapter
from communitylab_backend.infrastructure.oci_storage import OCIObjectStorageAdapter
from communitylab_backend.infrastructure.oci_vault import OCIVaultSecretProvider
from communitylab_backend.infrastructure.vector_index import LocalVectorStore
from communitylab_backend.infrastructure.local import ExistingSanitizerAdapter, LocalObjectStorageAdapter, MockLLMProvider, MockRetriever

SECRET_SETTINGS = {"GEMINI_API_KEY": ("gemini_api_key", "oci_secret_gemini", "OCI_SECRET_GEMINI"), "COHERE_API_KEY": ("cohere_api_key", "oci_secret_cohere", "OCI_SECRET_COHERE")}


@lru_cache
def get_settings() -> Settings:
    """Carga y almacena en caché la configuración validada del entorno.

    Retorna ``Settings``. Puede producir un error de validación si una
    variable es inválida. Lee ``.env`` cuando existe, sin registrar secretos.
    """

    return Settings()


@lru_cache
def _vault_provider(vault_id: str | None, secret_names: tuple, region: str | None, auth: str, config_file, profile: str, timeout_seconds: float) -> OCIVaultSecretProvider:
    """Crea una sola vez por configuración el lector de OCI Vault.

    ``build_workflow`` se ejecuta en cada solicitud; esta caché evita abrir
    otra sesión con OCI y volver a pedir los secretos. Recibe valores simples
    de ``Settings`` para poder usarlos como clave de la caché. Produce
    ``ProviderUnavailableError`` si falta el Vault o la sesión de OCI.
    """

    return OCIVaultSecretProvider(vault_id, dict(secret_names), region, auth, config_file, profile, timeout_seconds)


def build_secret_provider(settings: Settings) -> OCIVaultSecretProvider:
    """Devuelve el lector de OCI Vault configurado en ``settings``.

    Sólo se usa con ``SECRET_PROVIDER=oci``. Produce
    ``ProviderUnavailableError`` si falta ``OCI_VAULT_ID`` o la sesión de OCI.
    """

    names = tuple((name, getattr(settings, field)) for name, (_, field, _) in SECRET_SETTINGS.items())
    return _vault_provider(settings.oci_vault_id, names, settings.oci_region, settings.oci_auth, settings.oci_config_file, settings.oci_config_profile, settings.provider_timeout_seconds)


def get_api_key(settings: Settings, name: str) -> str | None:
    """Obtiene la clave ``name`` (``GEMINI_API_KEY`` o ``COHERE_API_KEY``).

    Con ``SECRET_PROVIDER=environment`` retorna el valor de ``Settings`` tal
    como antes (entorno o ``.env``), o ``None`` si falta. Con ``oci`` la pide
    a OCI Vault y produce ``ProviderUnavailableError`` si el Vault no tiene el
    secreto. Nunca registra ni incluye el valor en los mensajes.
    """

    setting, field, variable = SECRET_SETTINGS[name]
    if settings.secret_provider != "oci":
        return getattr(settings, setting)
    value = build_secret_provider(settings).get(name)
    if not value:
        raise ProviderUnavailableError(f"OCI Vault no tiene el secreto '{getattr(settings, field)}' para {name} (revisar OCI_VAULT_ID y {variable})")
    return value


def build_retriever(settings: Settings):
    """Elige el recuperador según ``settings.retrieval_provider``.

    Retorna un ``RetrieverPort`` o ``None`` si la selección es desconocida. La
    opción ``faq_db`` (por defecto) busca en ``motor_educativo.db`` sin claves;
    ``semantic`` usa Cohere (embedding y rerank) y el índice vectorial de
    FAQs; produce ``ProviderUnavailableError`` si no se configuró Cohere. La
    clave de Cohere sale de ``get_api_key`` (entorno u OCI Vault).
    """

    if settings.retrieval_provider == "mock":
        return MockRetriever()
    if settings.retrieval_provider == "faq_db":
        return SqliteFaqRetriever(settings.faq_db_path)
    if settings.retrieval_provider == "semantic":
        if settings.embedding_provider != "cohere" or settings.reranker_provider != "cohere":
            raise ProviderUnavailableError("La búsqueda semántica requiere EMBEDDING_PROVIDER=cohere y RERANKER_PROVIDER=cohere")
        cohere_key = get_api_key(settings, "COHERE_API_KEY")
        embeddings = CohereEmbeddingAdapter(cohere_key, settings.cohere_embed_model, settings.provider_timeout_seconds, output_dimension=settings.cohere_embed_dimension)
        reranker = CohereRerankerAdapter(cohere_key, settings.cohere_rerank_model, settings.provider_timeout_seconds)
        return SemanticRetriever(embeddings, LocalVectorStore(settings.faq_index_path), reranker, settings.retrieval_candidates, settings.retrieval_min_score)
    return None


def rebuild_semantic_index(settings: Settings) -> int | None:
    """Reconstruye el índice semántico si la búsqueda semántica está activa.

    Se usa después de agregar FAQs a la base, para que la búsqueda con Cohere
    también las encuentre. Con otro buscador no hace nada y retorna ``None``;
    si no, retorna cuántas FAQs indexó. Gasta unas 2 llamadas a Cohere y
    puede propagar ``ProviderUnavailableError``.
    """

    if settings.retrieval_provider != "semantic":
        return None
    from communitylab_backend.tools.build_faq_index import build_index

    embeddings = CohereEmbeddingAdapter(get_api_key(settings, "COHERE_API_KEY"), settings.cohere_embed_model, settings.provider_timeout_seconds, output_dimension=settings.cohere_embed_dimension)
    return build_index(settings.faq_db_path, settings.faq_index_path, embeddings, settings.cohere_embed_model)


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
    los stubs externos fallan de forma explícita. Con Gemini, la clave sale
    de ``get_api_key`` (entorno u OCI Vault). Produce
    ``ProviderUnavailableError`` ante una selección desconocida.
    """

    llm = MockLLMProvider(settings.success_keywords, settings.faq_keywords, settings.success_types, settings.faq_types) if settings.llm_provider == "mock" else GeminiLLMAdapter(get_api_key(settings, "GEMINI_API_KEY"), settings.gemini_model, settings.provider_timeout_seconds) if settings.llm_provider == "gemini" else None
    retriever = build_retriever(settings)
    storage = build_storage(settings)
    if llm is None or retriever is None or storage is None:
        raise ProviderUnavailableError("Unknown configured provider")
    return ProcessingWorkflow(ExistingSanitizerAdapter(), llm, retriever, storage, DoubtHistory(settings.history_db_path))


def get_workflow() -> ProcessingWorkflow:
    """Entrega el flujo a FastAPI y permite sustituirlo en tests.

    Retorna un ``ProcessingWorkflow`` construido con la configuración actual.
    Puede propagar errores de configuración o proveedor.
    """

    return build_workflow(get_settings())


def build_knowledge(settings: Settings) -> KnowledgeService:
    """Construye el servicio de la base de conocimiento con los adaptadores locales.

    Usa ``motor_educativo.db`` (``FAQ_DB_PATH``), el historial de dudas
    (``HISTORY_DB_PATH``) y, al agregar FAQs, reconstruye el índice semántico
    si esa búsqueda está activa. No abre archivos hasta que se usa.
    """

    return KnowledgeService(SqliteKnowledgeBase(settings.faq_db_path, settings.faq_backup_dir), DoubtHistory(settings.history_db_path), lambda: rebuild_semantic_index(settings))


def get_knowledge() -> KnowledgeService:
    """Entrega el servicio de conocimiento a FastAPI y permite sustituirlo en tests."""

    return build_knowledge(get_settings())
