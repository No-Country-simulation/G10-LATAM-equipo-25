"""Casos de uso de la base de conocimiento: consultar, ampliar y medir dudas.

Pertenece a la capa de aplicación. Reúne lo que antes hacían los endpoints
``/api/v1/knowledge/*`` llamando directo a SQLite: ahora la API y la
herramienta de terminal piden todo a ``KnowledgeService``, que sólo conoce
los puertos ``KnowledgeBasePort`` y ``DoubtHistoryPort``. Así se puede
cambiar la base (por ejemplo, a una en la nube) sin tocar la API.

No llama a proveedores de IA. La única escritura es agregar FAQs, con copia
de seguridad previa (la hace el adaptador de la base).
"""

from collections.abc import Callable

from communitylab_backend.application.faq_import import clean_faq_rows
from communitylab_backend.application.orchestration import topic_key
from communitylab_backend.domain.errors import BackendError
from communitylab_backend.domain.ports import DoubtHistoryPort, KnowledgeBasePort


class KnowledgeService:
    """Consulta y amplía la base de conocimiento y el historial de dudas.

    ``base`` es la base de FAQs y reseñas; ``history`` el historial de dudas;
    ``reindex`` es opcional y se llama después de agregar FAQs (por ejemplo,
    para reconstruir el índice de la búsqueda semántica).
    """

    def __init__(self, base: KnowledgeBasePort, history: DoubtHistoryPort, reindex: Callable[[], object] | None = None):
        """Guarda los puertos; no abre la base hasta que se usa."""
        self.base, self.history, self.reindex = base, history, reindex

    def summary(self) -> dict:
        """Totales de la base, para mostrar en el panel que está cargada."""
        return self.base.summary()

    def faqs(self, limit: int) -> list[dict]:
        """Hasta ``limit`` FAQs oficiales, con el mismo id que citan los borradores."""
        return self.base.faqs(limit)

    def reviews(self, course: str | None, sentiment: str | None, limit: int) -> dict:
        """Reseñas reales filtradas y la lista de cursos para el filtro."""
        return {"reviews": self.base.reviews(course, sentiment, limit), "courses": self.base.courses()}

    def frequent_doubts(self, days: int | None, limit: int) -> dict:
        """Ranking de dudas frecuentes del historial (sin IA)."""
        return self.history.ranking(days, limit)

    def import_faqs(self, rows: list[dict], dry_run: bool = True, topic: str | None = None) -> dict:
        """Valida FAQs nuevas y las agrega a la base (o sólo muestra qué haría).

        ``rows`` son las filas tal como llegaron del archivo. Las inválidas se
        devuelven con su motivo y no se escriben. Si se agregaron FAQs y se
        indicó ``topic`` (el tema de dudas que responden), el ranking marca
        ese tema como resuelto. Si ``reindex`` falla, las FAQs quedan igual y
        se devuelve un aviso. Puede propagar ``InvalidInteractionError``,
        ``RetrievalError`` o ``StorageError``.
        """
        valid, invalid = clean_faq_rows(rows)
        result = self.base.add_faqs(valid, dry_run)
        if topic and result["new_ids"]:
            self.history.attach_faqs(topic_key(topic), result["new_ids"])
        warnings = []
        if result["new_ids"] and self.reindex:
            try:
                self.reindex()
            except BackendError:
                warnings.append("Las FAQs se agregaron, pero no se pudo reconstruir el índice semántico; correr build_faq_index")
        return {**result, "received": len(rows), "invalid": invalid, "warnings": warnings}
