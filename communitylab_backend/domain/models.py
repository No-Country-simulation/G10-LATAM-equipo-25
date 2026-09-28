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


@dataclass(frozen=True)
class Analysis:
    """Agrupa señales del dominio para decidir la ruta de contenido.

    La aplicación usa estas señales y la API muestra un resumen. Esta clase
    no decide la ruta ni llama a proveedores.
    """

    sentiment: str
    topics: list[str]
    insights: list[str]
    success_story_candidate: bool = False
    recurring_question: bool = False


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
    """

    kind: Literal["linkedin_post", "newsletter_highlight", "faq_content", "success_story"]
    title: str
    body: str
    status: Literal["draft"] = "draft"
    evidence_ids: list[str] = field(default_factory=list)
