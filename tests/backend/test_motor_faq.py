"""Pruebas del Motor de FAQ dinámico: dudas agrupadas por tema, formatos educativos e historial."""

from communitylab_backend.application.batch import process_batch
from communitylab_backend.application.orchestration import ProcessingWorkflow, topic_key
from communitylab_backend.domain.models import Evidence
from communitylab_backend.infrastructure.doubt_history import DoubtHistory
from communitylab_backend.infrastructure.local import ExistingSanitizerAdapter, LocalObjectStorageAdapter, MockLLMProvider


class TopicRetriever:
    """Recuperador falso: devuelve una FAQ sólo si la consulta habla de sobreajuste."""

    def __init__(self):
        """Registra las consultas recibidas."""
        self.queries = []

    def retrieve(self, query, limit=5):
        """Devuelve la FAQ de sobreajuste o nada, según ``query``."""
        self.queries.append(query)
        if "sobreajuste" in query.lower():
            return [Evidence("faq-1", "Pregunta: What is overfitting?\nRespuesta: Overfitting memorizes data. Use regularization.", "faq:ml", 9.0)][:limit]
        return []


def lote():
    """Tres dudas de dos temas y un comentario."""
    return [
        {"id": "a", "author": "Ana", "text": "¿Cómo evito el sobreajuste en mi modelo?", "type": "pregunta"},
        {"id": "b", "author": "Beto", "text": "¿Por qué mi modelo tiene sobreajuste con pocos datos?", "type": "pregunta"},
        {"id": "c", "author": "Caro", "text": "¿Cómo estructuro un router en LangGraph?", "type": "pregunta"},
        {"id": "d", "author": "Dani", "text": "Excelente sesión de ayer", "type": "comentario"},
    ]


def test_topic_key_ignores_case_accents_and_spaces():
    """El mismo tema escrito distinto cuenta como uno solo."""
    assert topic_key(" Sobreajúste ") == topic_key("sobreajuste") and topic_key(None) == "general"


def test_doubts_are_grouped_by_topic_with_three_formats_each(tmp_path):
    """Cada tema recibe tutorial, tip y tema de documentación con su propia evidencia."""
    retriever = TopicRetriever()
    history = DoubtHistory(tmp_path / "historial.db")
    workflow = ProcessingWorkflow(ExistingSanitizerAdapter(), MockLLMProvider(), retriever, LocalObjectStorageAdapter(tmp_path / "paquetes"), history)
    response = process_batch(workflow, "r1", "comunidad", "semana", lote())
    topics = response["faq_topics"]
    assert [(item["topic"], item["questions"], item["has_official_faq"]) for item in topics] == [("Machine learning", 2, True), ("IA generativa y LangGraph", 1, False)]
    assert len(retriever.queries) == 2
    kinds = [(asset["kind"], asset["topic"]) for asset in response["generated_assets"]]
    assert kinds == [(kind, topic) for topic in ("Machine learning", "IA generativa y LangGraph") for kind in ("quick_tutorial", "weekly_tip", "doc_topic")]
    langgraph_tutorial = next(asset for asset in response["generated_assets"] if asset["kind"] == "quick_tutorial" and asset["topic"] == "IA generativa y LangGraph")
    assert langgraph_tutorial["evidence_ids"] == [] and "Todavía no hay una FAQ oficial" in langgraph_tutorial["body"]
    educational = response["formato_briefing"]["activos_distribucion_generados"]["contenido_educativo"]
    assert [item["status"] for item in educational] == ["respuesta_con_faq_oficial", "derivado_a_mentoria"]
    assert response["formato_briefing"]["activos_distribucion_generados"]["destaque_newsletter_semanal"]["seccion"] == "Tip de la Semana"
    assert "d" in response["discarded"]


def test_history_counts_frequent_topics_across_batches(tmp_path):
    """El ranking suma lotes, distingue temas con y sin FAQ y sugiere nombres conocidos."""
    history = DoubtHistory(tmp_path / "historial.db")
    workflow = ProcessingWorkflow(ExistingSanitizerAdapter(), MockLLMProvider(), TopicRetriever(), LocalObjectStorageAdapter(tmp_path / "paquetes"), history)
    for request_id in ("r1", "r2"):
        process_batch(workflow, request_id, "comunidad", "semana", lote())
    ranking = history.ranking()
    first = ranking["topics"][0]
    assert ranking["total_doubts"] == 6
    assert (first["topic"], first["count"], first["batches"], first["has_official_faq"], first["faq_ids"]) == ("Machine learning", 4, 2, True, ["faq-1"])
    assert ranking["topics"][1]["has_official_faq"] is False
    assert history.known_topics()[0] == "Machine learning"
    assert "[EMAIL]" not in first["examples"][0] and "Ana" not in str(ranking)


def test_missing_history_file_is_an_empty_ranking(tmp_path):
    """Sin historial todavía, el ranking está vacío y no hay temas conocidos."""
    history = DoubtHistory(tmp_path / "no-existe.db")
    assert history.ranking() == {"total_doubts": 0, "topics": []} and history.known_topics() == []


def test_attach_faqs_marks_topic_as_resolved(tmp_path):
    """Al agregar una FAQ para un tema sin respaldo, el ranking lo marca resuelto."""
    history = DoubtHistory(tmp_path / "historial.db")
    workflow = ProcessingWorkflow(ExistingSanitizerAdapter(), MockLLMProvider(), TopicRetriever(), LocalObjectStorageAdapter(tmp_path / "paquetes"), history)
    process_batch(workflow, "r1", "comunidad", "semana", lote())
    assert history.attach_faqs(topic_key("IA generativa y LangGraph"), ["faq-99"]) == 1
    langgraph = next(item for item in history.ranking()["topics"] if item["topic"] == "IA generativa y LangGraph")
    assert langgraph["has_official_faq"] is True and langgraph["faq_ids"] == ["faq-99"]
