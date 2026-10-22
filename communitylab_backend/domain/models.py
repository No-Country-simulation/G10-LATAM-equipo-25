"""Modelos inmutables del dominio compartidos por el flujo y sus proveedores.

Estos tipos no dependen de FastAPI, LangGraph ni SDK externos.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class SanitizedInteraction:
    """Representa una interacción cuyo texto ya pasó por sanitización.

    Pertenece al dominio. Sólo esta proyección puede llegar a un proveedor;
    no conserva autor ni texto original y colabora con ``LLMProvider``.
    """

    id: str
    text_sanitized: str
    channel: str | None = None
    type: str | None = None


FLOW_KINDS = {
    "success_story": ("success_story", "linkedin_post"),
    "faq": ("faq_content", "newsletter_highlight"),
    "community_highlight": ("linkedin_post", "newsletter_highlight"),
}
"""Activos que produce cada ruta con ``LLMProvider.generate`` (versión anterior, se conserva)."""

BRIEF_KINDS = {
    "success_story": ("success_story", "linkedin_post"),
    "faq": ("quick_tutorial", "weekly_tip", "doc_topic"),
    "community_highlight": ("linkedin_post", "newsletter_highlight"),
}
"""Activos que encarga cada rama del grafo. La rama ``faq`` es el Motor de FAQ
dinámico: por cada tema de dudas pide un tutorial rápido, un tip de la semana
y una propuesta de tema de documentación."""

MAX_FAQ_TOPICS = 2
"""Temas de dudas que se redactan por lote (los de más dudas), para cuidar la cuota de Gemini."""

ASSET_KINDS = Literal["linkedin_post", "newsletter_highlight", "faq_content", "success_story", "quick_tutorial", "weekly_tip", "doc_topic"]
"""Todos los tipos de activo que puede producir el motor."""

FLOW_ORDER = ("success_story", "faq", "community_highlight")
"""Prioridad de las rutas: la primera activa es la ruta principal del lote."""


@dataclass(frozen=True)
class InteractionSignal:
    """Resultado del análisis de UNA interacción del lote.

    Pertenece al dominio. Lo produce ``LLMProvider.analyze`` y la aplicación
    lo usa para elegir qué mensajes entran a cada ruta. ``category`` es
    ``logro``, ``duda``, ``apoyo`` o ``comentario``; ``relevance`` va de 0 a 1
    y sirve para elegir los mejores momentos. ``topic`` es el tema del
    mensaje en pocas palabras: con él se agrupan las dudas y se mide cuáles
    son frecuentes. No contiene el autor.
    """

    id: str
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    category: Literal["logro", "duda", "apoyo", "comentario"]
    relevance: float
    needs_support: bool = False
    topic: str | None = None


@dataclass(frozen=True)
class Analysis:
    """Agrupa señales del dominio para decidir la ruta de contenido.

    La aplicación usa estas señales y la API muestra un resumen. Esta clase
    no decide la ruta ni llama a proveedores. ``interaction_signals`` trae
    una señal por interacción; puede estar vacía si el proveedor no las da.
    """

    sentiment: str
    topics: list[str]
    insights: list[str]
    success_story_candidate: bool = False
    recurring_question: bool = False
    interaction_signals: list[InteractionSignal] = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    """Representa una cita de contexto sanitizado con su fuente e identidad.

    El recuperador crea la cita; el generador puede referenciarla. ``score``
    es una pista de recuperación y no una evaluación humana de relevancia.
    """

    record_id: str
    snippet: str
    source: str
    score: float = 0.0


@dataclass(frozen=True)
class DraftAsset:
    """Representa contenido no publicado que espera revisión humana.

    Pertenece al dominio y puede ser guardado por ``ObjectStoragePort``.
    No contiene una operación de publicación ni aprobación automática.
    ``flow`` indica la ruta que encargó el activo; el nodo ``compose`` lo
    completa y vale ``None`` si el activo se generó con ``generate``.
    ``topic`` es el tema de dudas al que responde (sólo en la ruta ``faq``).
    """

    kind: ASSET_KINDS
    title: str
    body: str
    status: Literal["draft"] = "draft"
    evidence_ids: list[str] = field(default_factory=list)
    flow: str | None = None
    topic: str | None = None


@dataclass(frozen=True)
class ContentBrief:
    """Encargo de contenido que arma una rama del grafo antes de redactar.

    Pertenece al dominio. Cada rama (``success_story``, ``faq`` o
    ``community_highlight``) elige qué interacciones y qué evidencia usar y
    qué activos (``kinds``) pedir; ``reason`` explica la elección. La rama
    ``faq`` arma un encargo por tema de dudas, con ``topic`` y la evidencia
    de ese tema. No llama al LLM: ``LLMProvider.generate_assets`` redacta
    todos los encargos juntos.
    """

    flow: str
    kinds: tuple[str, ...]
    interactions: list[SanitizedInteraction]
    evidence: list[Evidence] = field(default_factory=list)
    reason: str = ""
    topic: str | None = None
