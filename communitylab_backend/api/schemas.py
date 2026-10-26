"""Modelos de entrada y salida JSON de la capa API.

FastAPI publica sus campos en OpenAPI para Streamlit y otros clientes.
La validación ocurre antes de llamar al grafo o a un proveedor.

La entrada acepta los nombres en inglés del backend y también los del
briefing del hackathon (``origen_comunidad``, ``interacciones``, ``texto``...),
para que el ejemplo oficial funcione tal cual.
"""

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class InteractionInput(BaseModel):
    """Interacción recibida por HTTP antes de la sanitización.

    Pertenece a API. Acepta ``author`` para decir en la respuesta quién logró
    un hito o necesita apoyo, pero la aplicación no lo envía al grafo ni a
    proveedores externos.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, max_length=100, description="Identificador opcional de la interacción; se genera uno local si falta.")
    author: str | None = Field(default=None, max_length=200, validation_alias=AliasChoices("author", "autor"), description="Autor opcional (también `autor`); no llega al grafo ni al LLM, sólo se une por id al armar la respuesta.")
    channel: str | None = Field(default=None, max_length=100, validation_alias=AliasChoices("channel", "canal"), description="Canal o espacio de origen (también `canal`), por ejemplo #community.")
    type: str | None = Field(default=None, max_length=60, validation_alias=AliasChoices("type", "tipo"), description="Tipo declarado (también `tipo`), por ejemplo testimonio, pregunta_tecnica o comment.")
    text: str = Field(min_length=1, max_length=10000, validation_alias=AliasChoices("text", "texto"), description="Texto recibido (también `texto`); se sanitiza antes del análisis y la búsqueda.")
    timestamp: datetime | None = Field(default=None, validation_alias=AliasChoices("timestamp", "fecha"), description="Fecha opcional; no se envía a proveedores en esta versión.")


class ProcessRequest(BaseModel):
    """Lote de interacciones para el flujo principal.

    Pertenece a API. Limita la carga para proteger el servicio local; no
    realiza el análisis ni conserva el texto original.
    """

    model_config = ConfigDict(populate_by_name=True)

    community_source: str = Field(min_length=1, max_length=100, validation_alias=AliasChoices("community_source", "origen_comunidad"), description="Nombre de la comunidad o integración de origen (también `origen_comunidad`).")
    reference_period: str = Field(min_length=1, max_length=100, validation_alias=AliasChoices("reference_period", "periodo_referencia"), description="Período de las interacciones (también `periodo_referencia`), por ejemplo Semana_04.")
    interactions: list[InteractionInput] = Field(min_length=1, max_length=100, validation_alias=AliasChoices("interactions", "interacciones"), description="Entre 1 y 100 interacciones (también `interacciones`) que se procesan juntas.")


class ProcessResponse(BaseModel):
    """Resultado público de procesamiento con borradores pendientes.

    Pertenece a API y resume el estado del grafo. No aprueba ni publica
    contenido; la revisión humana siempre queda pendiente.
    """

    status: Literal["success"] = Field(default="success", description="Indica que el flujo terminó y guardó los borradores.")
    request_id: str = Field(description="Identificador para correlacionar respuesta, almacenamiento y logs.")
    community_summary: dict = Field(description="Total procesado, sentimiento predominante y temas principales.")
    insights: list[str] = Field(description="Señales resumidas; el mock sólo produce ejemplos demostrativos.")
    routing: dict = Field(description="Rutas activas del lote: `flows` (lista), `reasons` (ruta -> razón) y, por compatibilidad, `selected_flow` y `reason` de la ruta principal.")
    generated_assets: list[dict] = Field(description="Dos o más piezas de contenido en estado draft; `flow` indica la ruta que encargó cada una.")
    human_review: dict = Field(description="Siempre indica required=true y status=pending.")
    storage: dict = Field(description="Proveedor, estado y ubicación del paquete guardado.")
    evidence: list[dict] = Field(description="Citas recuperadas de la FAQ oficial; puede estar vacía si ninguna aplica.")
    interaction_analysis: list[dict] = Field(default_factory=list, description="Análisis por mensaje: id, author, channel, text (texto con datos personales ya ocultos), sentiment, category (logro, duda, apoyo o comentario), relevance (0 a 1) y needs_support.")
    highlights: list[str] = Field(default_factory=list, description="Ids de los 3 mensajes más relevantes del lote (los mejores momentos).")
    members_needing_support: list[dict] = Field(default_factory=list, description="Mensajes de personas que necesitan apoyo: id, author, channel y category.")
    discarded: list[str] = Field(default_factory=list, description="Ids de mensajes que no entraron a ningún encargo de contenido.")
    faq_topics: list[dict] = Field(default_factory=list, description="Temas de dudas que se redactaron en este lote: tema, cantidad de dudas, ids, FAQs oficiales encontradas y si hay respaldo oficial.")
    formato_briefing: dict = Field(default_factory=dict, description="La misma respuesta con la estructura exacta del ejemplo de salida del briefing.")
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


class ReviewedAsset(BaseModel):
    """Activo después de la revisión humana en el panel de curaduría.

    Pertenece a API. ``body`` puede traer la versión editada por la persona
    que revisó; ``decision`` registra si se aprobó o se rechazó.
    """

    kind: str = Field(max_length=60, description="Tipo de activo, por ejemplo faq_content o linkedin_post.")
    title: str = Field(max_length=300, description="Título final del activo.")
    body: str = Field(min_length=1, max_length=20000, description="Contenido final, con las ediciones del equipo.")
    decision: Literal["approved", "rejected"] = Field(description="Resultado de la revisión humana.")
    evidence_ids: list[str] = Field(default_factory=list, description="Citas de FAQ que respaldan el activo.")


class ReviewRequest(BaseModel):
    """Decisiones de curaduría sobre los activos de un procesamiento.

    Pertenece a API. ``request_id`` es el del procesamiento original, para
    poder relacionar en el almacenamiento el borrador con su versión revisada.
    """

    request_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,100}$", description="ID devuelto por /api/v1/activity/process.")
    community_source: str = Field(default="", max_length=100, description="Comunidad de origen, sólo informativo.")
    reference_period: str = Field(default="", max_length=100, description="Período de referencia, sólo informativo.")
    reviewer: str | None = Field(default=None, max_length=100, description="Nombre o rol de quien revisó (opcional).")
    assets: list[ReviewedAsset] = Field(min_length=1, max_length=50, description="Activos con su decisión.")


class ReviewResponse(BaseModel):
    """Confirmación de que la curaduría quedó guardada.

    Pertenece a API. Indica cuántos activos se aprobaron y dónde se guardó el
    paquete final (carpeta local u OCI Object Storage).
    """

    status: Literal["stored"] = Field(default="stored", description="El paquete revisado se guardó.")
    request_id: str = Field(description="ID del procesamiento original.")
    approved: int = Field(description="Cantidad de activos aprobados.")
    rejected: int = Field(description="Cantidad de activos rechazados.")
    storage: dict = Field(description="Proveedor, estado y ubicación del paquete revisado.")


class FaqImportRequest(BaseModel):
    """FAQs nuevas para agregar a la base ``motor_educativo.db``.

    Pertenece a API. ``rows`` trae las filas tal como vienen del CSV o JSON
    (con ``pregunta``/``question``, ``respuesta``/``answer`` y
    ``curso``/``course``); la validación ocurre en la aplicación. Por
    seguridad, ``dry_run`` vale ``True`` por defecto: sólo muestra qué haría.
    """

    rows: list[dict] = Field(min_length=1, max_length=200, description="Entre 1 y 200 FAQs con pregunta, respuesta y curso (opcional).")
    dry_run: bool = Field(default=True, description="true: sólo vista previa. false: copia de seguridad y escritura en la base.")
    topic: str | None = Field(default=None, max_length=120, description="Tema de dudas al que responden estas FAQs (opcional). Si se indica, el ranking de dudas frecuentes lo marca como resuelto.")

