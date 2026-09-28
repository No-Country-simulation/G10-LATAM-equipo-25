"""Configuración central de la aplicación.

La capa de configuración lee variables de entorno con Pydantic Settings.
Los valores por defecto ejecutan el backend sin claves ni red.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Selecciona proveedores y ubicación de borradores para la composición.

Pertenece a la capa de configuración. ``api.dependencies`` usa sus valores
para construir adaptadores; esta clase no realiza llamadas a proveedores.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "local"
    log_level: str = "INFO"
    llm_provider: Literal["mock", "gemini"] = "mock"
    embedding_provider: Literal["mock", "cohere"] = "mock"
    reranker_provider: Literal["mock", "cohere"] = "mock"
    vector_store_provider: Literal["local", "oci"] = "local"
    retrieval_provider: Literal["mock", "existing_local"] = "mock"
    storage_provider: Literal["local", "oci"] = "local"
    secret_provider: Literal["environment", "oci"] = "environment"
    local_storage_dir: Path = Path("output/backend/drafts")
    gemini_api_key: str | None = Field(default=None, repr=False)
    cohere_api_key: str | None = Field(default=None, repr=False)
    oci_region: str | None = None
    oci_namespace: str | None = None
    oci_bucket: str | None = None
    oci_compartment_id: str | None = None
    success_keywords: str = "conseguí trabajo,logré,certifiqué,gradué,success,got a job"
    faq_keywords: str = "cómo,como,how,ayuda,error,problema,help,?"
    success_types: str = "testimonial"
