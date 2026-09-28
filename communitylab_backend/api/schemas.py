"""Modelos de entrada y salida JSON de la capa API.

FastAPI publica sus campos en OpenAPI para Streamlit y otros clientes.
La validación ocurre antes de llamar al grafo o a un proveedor.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InteractionInput(BaseModel):
    """Interacción recibida por HTTP antes de la sanitización.

    Pertenece a API. Acepta ``author`` para compatibilidad del cliente, pero
    la aplicación no lo envía al grafo ni a proveedores externos.
    """

    id: str | None = Field(default=None, max_length=100, description="Identificador opcional de la interacción; se genera uno local si falta.")
    author: str | None = Field(default=None, max_length=200, description="Autor opcional; se descarta antes de invocar el flujo.")
    channel: str | None = Field(default=None, max_length=100, description="Canal o espacio de origen, por ejemplo #community.")
    type: str | None = Field(default=None, max_length=60, description="Tipo declarado, por ejemplo testimonial, question o comment.")
    text: str = Field(min_length=1, max_length=10000, description="Texto recibido; se sanitiza antes del análisis y la búsqueda.")
    timestamp: datetime | None = Field(default=None, description="Fecha opcional; no se envía a proveedores en esta versión.")


class ProcessRequest(BaseModel):
    """Lote de interacciones para el flujo principal.

    Pertenece a API. Limita la carga para proteger el servicio local; no
    realiza el análisis ni conserva el texto original.
    """

    community_source: str = Field(min_length=1, max_length=100, description="Nombre de la comunidad o integración de origen.")
    reference_period: str = Field(min_length=1, max_length=100, description="Período al que pertenecen las interacciones, por ejemplo week_04.")
    interactions: list[InteractionInput] = Field(min_length=1, max_length=100, description="Entre 1 y 100 interacciones que se procesan juntas.")


class ProcessResponse(BaseModel):
    """Resultado público de procesamiento con borradores pendientes.

    Pertenece a API y resume el estado del grafo. No aprueba ni publica
    contenido; la revisión humana siempre queda pendiente.
    """

    status: Literal["success"] = Field(default="success", description="Indica que el flujo terminó y guardó los borradores.")
    request_id: str = Field(description="Identificador para correlacionar respuesta, almacenamiento y logs.")
    community_summary: dict = Field(description="Total procesado, sentimiento predominante y temas principales.")
    insights: list[str] = Field(description="Señales resumidas; el mock sólo produce ejemplos demostrativos.")
    routing: dict = Field(description="Ruta seleccionada y razón usada por el grafo.")
    generated_assets: list[dict] = Field(description="Dos o más piezas de contenido en estado draft.")
    human_review: dict = Field(description="Siempre indica required=true y status=pending.")
    storage: dict = Field(description="Proveedor, estado y ubicación del paquete guardado.")
    evidence: list[dict] = Field(description="Citas recuperadas; puede estar vacío con MockRetriever.")
    warnings: list[str] = Field(default_factory=list, description="Avisos no fatales del flujo, si existen.")


class RagQueryRequest(BaseModel):
    """Consulta de búsqueda recibida por HTTP.

    Pertenece a API; el endpoint sanitiza su texto antes de usar RetrieverPort.
    """

    query: str = Field(min_length=1, max_length=2000, description="Pregunta o términos que se sanitizan antes de recuperar evidencia.")
    limit: int = Field(default=5, ge=1, le=20, description="Máximo de citas a devolver, entre 1 y 20.")


class RagQueryResponse(BaseModel):
    """Resultado de búsqueda que contiene sólo citas.

    Pertenece a API; no genera una respuesta textual ni asigna relevancia
    humana a los resultados.
    """

    request_id: str = Field(description="Identificador de correlación del request.")
    evidence: list[dict] = Field(description="Lista de citas sanitizadas, posiblemente vacía.")
    provider: str = Field(description="Nombre del recuperador activo.")
