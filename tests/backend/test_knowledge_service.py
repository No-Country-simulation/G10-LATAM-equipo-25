"""Pruebas unitarias del servicio de la base de conocimiento con puertos falsos."""

from communitylab_backend.application.knowledge import KnowledgeService
from communitylab_backend.domain.errors import ProviderUnavailableError


class FakeBase:
    """Base de conocimiento en memoria: recuerda lo que se le pidió agregar."""

    def __init__(self):
        """Empieza sin FAQs agregadas."""
        self.added = []

    def add_faqs(self, rows, dry_run):
        """Simula la escritura: sólo asigna ids si no es vista previa."""
        if not dry_run:
            self.added.extend(rows)
        return {"dry_run": dry_run, "to_add": rows, "duplicates": [], "added": 0 if dry_run else len(rows), "new_ids": [] if dry_run else [f"faq-{i}" for i, _ in enumerate(rows, 1)], "backup": None}


class FakeHistory:
    """Historial en memoria: recuerda qué temas se marcaron resueltos."""

    def __init__(self):
        """Empieza sin temas marcados."""
        self.attached = {}

    def attach_faqs(self, topic_key, faq_ids):
        """Guarda los ids por tema y retorna cuántos guardó."""
        self.attached[topic_key] = faq_ids
        return len(faq_ids)


ROWS = [{"pregunta": "¿Qué es LangGraph?", "respuesta": "Una librería para armar flujos con estados.", "curso": "ia"}, {"pregunta": "", "respuesta": "sin pregunta", "curso": "ia"}]


def test_preview_does_not_write_nor_mark_topics():
    """En vista previa no se escribe, no se marca el tema y se reportan las filas inválidas."""
    base, history = FakeBase(), FakeHistory()
    result = KnowledgeService(base, history).import_faqs(ROWS, dry_run=True, topic="LangGraph")
    assert base.added == [] and history.attached == {}
    assert result["received"] == 2 and len(result["invalid"]) == 1 and len(result["to_add"]) == 1


def test_import_marks_topic_and_warns_when_reindex_fails():
    """Al escribir se marca el tema resuelto; si el reíndice falla, queda un aviso y las FAQs se agregan igual."""
    def broken_reindex():
        """Simula que Cohere no responde."""
        raise ProviderUnavailableError("sin Cohere")

    base, history = FakeBase(), FakeHistory()
    result = KnowledgeService(base, history, broken_reindex).import_faqs(ROWS, dry_run=False, topic="IA generativa y LangGraph")
    assert result["new_ids"] == ["faq-1"] and len(base.added) == 1
    assert list(history.attached.values()) == [["faq-1"]]
    assert result["warnings"] and "índice semántico" in result["warnings"][0]
