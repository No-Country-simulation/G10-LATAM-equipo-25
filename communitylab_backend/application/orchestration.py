"""Grafo LangGraph de la capa de aplicación.

Coordina sanitización, análisis, recuperación, routing, encargos de
contenido, redacción y persistencia mediante puertos del dominio. No depende
de SDK externos.

Un lote puede activar varias rutas a la vez: si trae un logro y una duda,
corren en paralelo las ramas ``success_story`` y ``faq``. Cada rama sólo arma
un encargo (``ContentBrief``) y el nodo ``compose`` redacta todos los
encargos con UNA llamada al LLM, para cuidar la cuota de Gemini.
"""

import logging
import operator
import time
import unicodedata
from dataclasses import asdict, replace
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from communitylab_backend.domain.errors import AssetGenerationError
from communitylab_backend.domain.models import BRIEF_KINDS, FLOW_ORDER, MAX_FAQ_TOPICS, Analysis, ContentBrief, DraftAsset, Evidence, InteractionSignal, SanitizedInteraction
from communitylab_backend.domain.ports import DoubtHistoryPort, LLMProvider, ObjectStoragePort, RetrieverPort, SanitizationPort

logger = logging.getLogger(__name__)

# Cuántos mensajes puede llevar como máximo el encargo de cada rama.
BRIEF_LIMITS = {"success_story": 3, "faq": 5, "community_highlight": 3}


class ProcessingState(TypedDict, total=False):
    """Estado mínimo compartido por los nodos del flujo.

    Pertenece a aplicación. El texto de entrada sólo existe hasta el nodo
    ``sanitize``; los siguientes nodos reciben interacciones sanitizadas.
    ``briefs`` acumula (con ``operator.add``) los encargos que dejan las
    ramas que corren en paralelo. ``known_topics`` son temas de dudas de
    lotes anteriores y ``evidence_by_topic`` las FAQs encontradas por tema.
    """

    request_id: str
    community_source: str
    reference_period: str
    interactions: list[dict] | None
    sanitized_interactions: list[SanitizedInteraction]
    known_topics: list[str]
    analysis: Analysis
    retrieved_evidence: list[Evidence]
    evidence_by_topic: dict[str, list[Evidence]]
    routing_decision: dict[str, Any]
    briefs: Annotated[list[ContentBrief], operator.add]
    generated_assets: list[DraftAsset]
    storage_result: dict[str, str]
    warnings: list[str]


def _signals_by_id(state: ProcessingState) -> dict[str, InteractionSignal]:
    """Devuelve la señal de cada interacción del ``state``, indexada por id.

    Si el proveedor no entregó la señal de algún mensaje, usa una neutra de
    relevancia 0, para que las ramas nunca fallen por un dato faltante.
    """
    given = {signal.id: signal for signal in state["analysis"].interaction_signals}
    return {item.id: given.get(item.id) or InteractionSignal(item.id, "neutral", "comentario", 0.0) for item in state["sanitized_interactions"]}


def topic_key(name: str | None) -> str:
    """Normaliza el nombre de un tema (minúsculas, sin tildes ni espacios de más).

    Así "Sobreajuste" y "sobreajuste " cuentan como el mismo tema. Un tema
    vacío se trata como ``general``.
    """
    plain = unicodedata.normalize("NFKD", (name or "").strip().lower())
    return " ".join("".join(char for char in plain if not unicodedata.combining(char)).split()) or "general"


def _question_topics(state: ProcessingState) -> list[tuple[str, list[SanitizedInteraction]]]:
    """Agrupa las dudas del lote por tema, de la más pedida a la menos pedida.

    Usa el ``topic`` de cada señal; si no hay mensajes clasificados como
    duda, usa los que necesitan apoyo. Ordena los temas por cantidad de
    dudas y, a igual cantidad, por relevancia. Retorna ``(tema, dudas)`` con
    las dudas ordenadas por relevancia.
    """
    signals = _signals_by_id(state)
    questions = _ranked(state, lambda signal: signal.category == "duda") or _ranked(state, lambda signal: signal.needs_support)
    groups: dict[str, list[SanitizedInteraction]] = {}
    names: dict[str, str] = {}
    for item in questions:
        name = (signals[item.id].topic or "").strip() or "General"
        names.setdefault(topic_key(name), name)
        groups.setdefault(topic_key(name), []).append(item)
    order = sorted(groups, key=lambda key: (-len(groups[key]), -max(signals[item.id].relevance for item in groups[key])))
    return [(names[key], groups[key]) for key in order]


def _ranked(state: ProcessingState, keep) -> list[SanitizedInteraction]:
    """Ordena por relevancia (mayor primero) las interacciones cuya señal cumple ``keep``.

    ``keep`` recibe una ``InteractionSignal`` y retorna ``bool``. A igual
    relevancia se conserva el orden original del lote.
    """
    signals = _signals_by_id(state)
    chosen = [item for item in state["sanitized_interactions"] if keep(signals[item.id])]
    return sorted(chosen, key=lambda item: -signals[item.id].relevance)


class ProcessingWorkflow:
    """Compone y ejecuta el flujo de procesamiento de la aplicación.

    Recibe puertos de sanitización, LLM, recuperación y almacenamiento.
    No implementa proveedores ni publica contenidos; registra cada nodo y
    conserva la revisión humana pendiente.
    """

    def __init__(self, sanitizer: SanitizationPort, llm: LLMProvider, retriever: RetrieverPort, storage: ObjectStoragePort, history: DoubtHistoryPort | None = None):
        """Conecta ``sanitizer``, ``llm``, ``retriever`` y ``storage`` al grafo.

        ``history`` es opcional (``DoubtHistoryPort``): el historial de dudas que usa
        ``application.batch`` para medir la frecuencia de los temas. Compila
        el flujo una vez. No llama todavía a proveedores ni guarda datos;
        esas operaciones ocurren en ``invoke``.
        """
        self.sanitizer, self.llm, self.retriever, self.storage, self.history = sanitizer, llm, retriever, storage, history
        graph = StateGraph(ProcessingState)
        for name, fn in (("sanitize", self._sanitize), ("analyze", self._analyze), ("retrieve", self._retrieve), ("route", self._route), ("success_story", self._success_story_brief), ("faq", self._faq_brief), ("community_highlight", self._community_brief), ("compose", self._compose), ("persist", self._persist)):
            graph.add_node(name, self._timed(name, fn))
        graph.add_edge(START, "sanitize")
        graph.add_edge("sanitize", "analyze")
        graph.add_edge("analyze", "retrieve")
        graph.add_edge("retrieve", "route")
        # La bifurcación devuelve una LISTA de rutas: LangGraph ejecuta esas ramas en paralelo.
        graph.add_conditional_edges("route", self._selected_flows, {name: name for name in FLOW_ORDER})
        for name in FLOW_ORDER:
            graph.add_edge(name, "compose")
        graph.add_edge("compose", "persist")
        graph.add_edge("persist", END)
        self.graph = graph.compile()

    def _timed(self, name: str, fn):
        """Envuelve el nodo ``fn`` para registrar duración, estado y proveedor.

        ``name`` identifica el nodo. Retorna una función apta para LangGraph;
        propaga cualquier error sin incluir el texto sensible en los logs.
        """
        def run(state: ProcessingState) -> dict[str, Any]:
            """Ejecuta el nodo sobre ``state`` y retorna sus campos nuevos.

            Registra tiempo y tipo de error. Propaga la excepción original.
            """
            started = time.perf_counter()
            try:
                result = fn(state)
                logger.info("workflow_node", extra={"request_id": state["request_id"], "node": name, "provider": self.llm.name if name in {"analyze", "compose"} else self.storage.provider if name == "persist" else "local", "status": "success", "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
                return result
            except Exception as exc:
                # Un error de SDK puede incluir prompts o cabeceras: sólo registramos el tipo.
                logger.error("workflow_node_failed", extra={"request_id": state["request_id"], "node": name, "status": "error", "error_type": type(exc).__name__, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
                raise
        return run

    def _selected_flows(self, state: ProcessingState) -> list[str]:
        """Lee del ``state`` las rutas activas y las entrega a LangGraph.

        Retorna una lista; con más de una ruta, sus ramas corren en paralelo.
        """

        return state["routing_decision"]["flows"]

    def _sanitize(self, state: ProcessingState) -> dict:
        """Sanitiza cada interacción y borra el texto crudo del ``state``.

        Retorna la lista segura. Puede producir ``InvalidInteractionError``;
        el adaptador usa las reglas locales de ``infrastructure/pii.py``.
        """
        safe = [self.sanitizer.sanitize(item["id"], item["text"], item.get("channel"), item.get("type")) for item in state["interactions"] or []]
        return {"sanitized_interactions": safe, "interactions": None}

    def _analyze(self, state: ProcessingState) -> dict:
        """Envía interacciones sanitizadas al LLM y retorna ``Analysis``.

        El análisis incluye una señal por mensaje (sentimiento, categoría,
        relevancia y si necesita apoyo). Puede propagar errores del
        proveedor. Nunca recibe texto original ni autor.
        """
        return {"analysis": self.llm.analyze(state["sanitized_interactions"], state.get("known_topics") or None)}

    def _retrieve(self, state: ProcessingState) -> dict:
        """Busca en la base las FAQs oficiales de cada tema de dudas.

        Hace una búsqueda por tema (los ``MAX_FAQ_TOPICS`` con más dudas),
        con el nombre del tema y el texto de sus dudas, y guarda hasta 2
        citas por tema: así una duda de otro tema no desvía la respuesta.
        Si el lote no trae dudas, busca con todo el lote como antes. Retorna
        la evidencia total y la de cada tema. Puede producir
        ``RetrievalError`` si falla el índice seleccionado.
        """
        topics = _question_topics(state)[:MAX_FAQ_TOPICS]
        if not topics:
            query = " ".join(item.text_sanitized[:200] for item in state["sanitized_interactions"])[:500]
            return {"retrieved_evidence": self.retriever.retrieve(query), "evidence_by_topic": {}}
        by_topic: dict[str, list[Evidence]] = {}
        seen: dict[str, Evidence] = {}
        for name, items in topics:
            query = f"{name} " + " ".join(item.text_sanitized[:200] for item in items)
            by_topic[name] = self.retriever.retrieve(query[:500], 2)
            for item in by_topic[name]:
                seen.setdefault(item.record_id, item)
        return {"retrieved_evidence": list(seen.values()), "evidence_by_topic": by_topic}

    def _route(self, state: ProcessingState) -> dict:
        """Decide qué rutas se activan para el lote.

        ``success_story`` si hay algún logro o testimonio, ``faq`` si hay
        alguna duda y ``community_highlight`` sólo si no aplica ninguna de las
        dos. Retorna ``flows`` (lista), ``reasons`` (ruta -> razón) y, por
        compatibilidad, ``selected_flow`` y ``reason`` de la ruta principal.
        """
        analysis, signals = state["analysis"], _signals_by_id(state).values()
        stories = sum(signal.category == "logro" for signal in signals)
        questions = sum(signal.category == "duda" for signal in signals)
        topics = len(_question_topics(state))
        reasons = {}
        if stories or analysis.success_story_candidate:
            reasons["success_story"] = f"Señal de historia de éxito: {stories} logro(s) o testimonio(s)" if stories else "Señal de historia de éxito en el análisis del lote"
        if questions or analysis.recurring_question:
            reasons["faq"] = f"Señal de pregunta recurrente: {questions} duda(s) de la comunidad en {topics} tema(s)" if questions else "Señal de pregunta recurrente en el análisis del lote"
        if not reasons:
            reasons["community_highlight"] = "Actividad general de la comunidad"
        flows = [flow for flow in FLOW_ORDER if flow in reasons]
        return {"routing_decision": {"selected_flow": flows[0], "reason": reasons[flows[0]], "flows": flows, "reasons": reasons}}

    def _brief(self, state: ProcessingState, flow: str, chosen: list[SanitizedInteraction], evidence: list[Evidence]) -> dict:
        """Arma el encargo de ``flow`` con hasta ``BRIEF_LIMITS[flow]`` mensajes.

        Si la rama no encontró mensajes propios, usa el más relevante del lote
        para no dejar el encargo vacío. Retorna el encargo dentro de una lista,
        que el reductor de ``briefs`` suma a los de las otras ramas.
        """
        chosen = (chosen or _ranked(state, lambda signal: True))[:BRIEF_LIMITS[flow]]
        brief = ContentBrief(flow, BRIEF_KINDS[flow], chosen, evidence, state["routing_decision"]["reasons"].get(flow, ""))
        return {"briefs": [brief]}

    def _success_story_brief(self, state: ProcessingState) -> dict:
        """Rama ``success_story``: elige los logros más relevantes del lote.

        No llama al LLM ni usa citas de FAQ. Retorna el encargo.
        """
        return self._brief(state, "success_story", _ranked(state, lambda signal: signal.category == "logro"), [])

    def _faq_brief(self, state: ProcessingState) -> dict:
        """Rama ``faq`` (Motor de FAQ dinámico): un encargo por tema de dudas.

        Toma los ``MAX_FAQ_TOPICS`` temas con más dudas y, para cada uno,
        encarga un tutorial rápido, un tip de la semana y una propuesta de
        tema de documentación, con las FAQs oficiales encontradas para ese
        tema. Las dudas de otros temas quedan como descartadas en este lote
        (y cuentan igual en el ranking de dudas frecuentes). No llama al LLM.
        """
        topics = _question_topics(state)[:MAX_FAQ_TOPICS]
        if not topics:
            return self._brief(state, "faq", [], state["retrieved_evidence"])
        evidence = state.get("evidence_by_topic") or {}
        briefs = [ContentBrief("faq", BRIEF_KINDS["faq"], items[:BRIEF_LIMITS["faq"]], evidence.get(name, []), f"{len(items)} duda(s) sobre «{name}»", name) for name, items in topics]
        return {"briefs": briefs}

    def _community_brief(self, state: ProcessingState) -> dict:
        """Rama ``community_highlight``: elige los mensajes más relevantes.

        No llama al LLM ni usa citas. Retorna el encargo.
        """
        return self._brief(state, "community_highlight", _ranked(state, lambda signal: True), [])

    def _compose(self, state: ProcessingState) -> dict:
        """Redacta los activos de todos los encargos con UNA llamada al LLM.

        Ordena los encargos por prioridad de ruta (los temas de la rama
        ``faq`` conservan su orden) y exige un activo ``draft`` por cada tipo
        de cada encargo, identificado por tipo y tema. Anota en cada activo la
        ruta que lo encargó. Retorna los activos en ese orden o produce
        ``AssetGenerationError``.
        """
        briefs = sorted(state["briefs"], key=lambda brief: FLOW_ORDER.index(brief.flow))
        expected = [(kind, brief.topic, brief.flow) for brief in briefs for kind in brief.kinds]
        assets = self.llm.generate_assets(briefs, state["analysis"])
        found = {(asset.kind, asset.topic): asset for asset in assets}
        if len(assets) < 2 or len(assets) != len(expected) or any(asset.status != "draft" for asset in assets) or any((kind, topic) not in found for kind, topic, _ in expected):
            raise AssetGenerationError("El proveedor debe devolver un activo draft por cada tipo de cada encargo")
        return {"generated_assets": [replace(found[(kind, topic)], flow=flow) for kind, topic, flow in expected]}

    def _persist(self, state: ProcessingState) -> dict:
        """Guarda un paquete sanitizado mediante ``ObjectStoragePort``.

        El paquete incluye los encargos de cada rama (qué mensajes y qué citas
        usó). Retorna proveedor, estado y ubicación. Tiene el efecto
        secundario de escribir un borrador y puede propagar ``StorageError``.
        """
        briefs = [{"flow": brief.flow, "topic": brief.topic, "kinds": list(brief.kinds), "interaction_ids": [item.id for item in brief.interactions], "evidence_ids": [item.record_id for item in brief.evidence], "reason": brief.reason} for brief in state["briefs"]]
        package = {"request_id": state["request_id"], "community_source": state["community_source"], "reference_period": state["reference_period"], "sanitized_interactions": [asdict(item) for item in state["sanitized_interactions"]], "analysis": asdict(state["analysis"]), "routing": state["routing_decision"], "briefs": briefs, "evidence": [asdict(item) for item in state["retrieved_evidence"]], "generated_assets": [asdict(item) for item in state["generated_assets"]], "human_review": {"required": True, "status": "pending"}}
        location = self.storage.save(state["request_id"], package)
        return {"storage_result": {"provider": self.storage.provider, "status": "stored", "location": location}}

    def invoke(self, state: ProcessingState) -> ProcessingState:
        """Ejecuta el grafo completo con el ``state`` inicial.

        Retorna el estado final y registra inicio y fin. Puede propagar
        errores de validación, proveedores, recuperación o almacenamiento;
        la API se encarga de convertirlos a HTTP.
        """

        logger.info("workflow_start", extra={"request_id": state["request_id"], "status": "start"})
        result = self.graph.invoke({"briefs": [], **state})
        logger.info("workflow_end", extra={"request_id": state["request_id"], "status": "success"})
        return result
