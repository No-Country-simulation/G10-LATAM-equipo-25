"""Punto de composición de la capa API.

Selecciona adaptadores a partir de ``Settings`` para que el dominio y el
grafo no necesiten conocer los proveedores concretos.
"""

from functools import lru_cache

from communitylab_backend.application.orchestration import ProcessingWorkflow
from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import ProviderUnavailableError
from communitylab_backend.infrastructure.external_stubs import GeminiLLMAdapter, OCIObjectStorageAdapter
from communitylab_backend.infrastructure.local import ExistingLocalRagAdapter, ExistingSanitizerAdapter, LocalObjectStorageAdapter, MockLLMProvider, MockRetriever


@lru_cache
def get_settings() -> Settings:
    """Carga y almacena en caché la configuración validada del entorno.

    Retorna ``Settings``. Puede producir un error de validación si una
    variable es inválida. Lee ``.env`` cuando existe, sin registrar secretos.
    """

    return Settings()


def build_workflow(settings: Settings) -> ProcessingWorkflow:
    """Construye el grafo con los adaptadores elegidos por ``settings``.

    Retorna ``ProcessingWorkflow``. Selecciona mocks locales por defecto;
    los stubs externos fallan de forma explícita. Produce
    ``ProviderUnavailableError`` ante una selección desconocida.
    """

    llm = MockLLMProvider(settings.success_keywords, settings.faq_keywords, settings.success_types) if settings.llm_provider == "mock" else GeminiLLMAdapter() if settings.llm_provider == "gemini" else None
    retriever = MockRetriever() if settings.retrieval_provider == "mock" else ExistingLocalRagAdapter() if settings.retrieval_provider == "existing_local" else None
    storage = LocalObjectStorageAdapter(settings.local_storage_dir) if settings.storage_provider == "local" else OCIObjectStorageAdapter() if settings.storage_provider == "oci" else None
    if llm is None or retriever is None or storage is None:
        raise ProviderUnavailableError("Unknown configured provider")
    return ProcessingWorkflow(ExistingSanitizerAdapter(), llm, retriever, storage)


def get_workflow() -> ProcessingWorkflow:
    """Entrega el flujo a FastAPI y permite sustituirlo en tests.

    Retorna un ``ProcessingWorkflow`` construido con la configuración actual.
    Puede propagar errores de configuración o proveedor.
    """

    return build_workflow(get_settings())
