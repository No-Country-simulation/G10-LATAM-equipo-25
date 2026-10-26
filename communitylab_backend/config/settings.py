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
    retrieval_provider: Literal["mock", "faq_db", "semantic"] = "faq_db"
    storage_provider: Literal["local", "oci"] = "local"
    state_provider: Literal["local", "oci"] = "local"
    secret_provider: Literal["environment", "oci"] = "environment"
    local_storage_dir: Path = Path("salidas/paquetes")
    gemini_api_key: str | None = Field(default=None, repr=False)
    cohere_api_key: str | None = Field(default=None, repr=False)
    gemini_model: str = "gemini-3.8-flash"
    cohere_embed_model: str = "embed-v4.0"
    cohere_rerank_model: str = "rerank-v4.0-pro"
    cohere_embed_dimension: int | None = None
    provider_timeout_seconds: float = 30.0
    faq_index_path: Path = Path("data/faq_index.json")
    faq_db_path: Path = Path("data/motor_educativo.db")
    faq_backup_dir: Path = Path("data/respaldos")
    history_db_path: Path = Path("data/historial_dudas.db")
    retrieval_candidates: int = 20
    retrieval_min_score: float = 0.5
    oci_region: str | None = None
    oci_namespace: str | None = None
    oci_bucket: str | None = None
    oci_compartment_id: str | None = None
    oci_auth: Literal["config", "instance_principal"] = "config"
    oci_config_file: Path = Path("~/.oci/config")
    oci_config_profile: str = "DEFAULT"
    oci_object_prefix: str = "activos"
    oci_state_prefix: str = "estado"
    oci_vault_id: str | None = None
    # Vacíos: el Vault usa OCI_REGION y OCI_CONFIG_PROFILE (los del bucket).
    # Sirven cuando el Vault está en otra región o en otra cuenta de OCI.
    oci_vault_region: str | None = None
    oci_vault_config_profile: str | None = None
    oci_secret_gemini: str = "communitylab-gemini-api-key"
    oci_secret_cohere: str = "communitylab-cohere-api-key"
    success_keywords: str = "conseguí trabajo,quedé seleccionad,me contrataron,logré,certifiqué,gradué,success,got a job"
    faq_keywords: str = "cómo,como,how,ayuda,error,problema,help,?"
    success_types: str = "testimonial,testimonio,logro"
    faq_types: str = "question,pregunta,pregunta_tecnica,duda"
