"""Grafo LangGraph de la capa de aplicación.

Coordina sanitización, análisis, recuperación, routing, generación y
persistencia mediante puertos del dominio. No depende de SDK externos.
"""

import logging
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from communitylab_backend.domain.errors import AssetGenerationError
from communitylab_backend.domain.models import Analysis, DraftAsset, Evidence, SanitizedInteraction
from communitylab_backend.domain.ports import LLMProvider, ObjectStoragePort, RetrieverPort, SanitizationPort

logger = logging.getLogger(__name__)


class ProcessingState(TypedDict, total=False):
    """Estado mínimo compartido por los nodos del flujo.

    Pertenece a aplicación. El texto de entrada sólo existe hasta el nodo
    ``sanitize``; los siguientes nodos reciben interacciones sanitizadas.
    """

    request_id: str
    community_source: str
    reference_period: str
    interactions: list[dict] | None
    sanitized_interactions: list[SanitizedInteraction]
    analysis: Analysis
    retrieved_evidence: list[Evidence]
    routing_decision: dict[str, str]
    generated_assets: list[DraftAsset]
    storage_result: dict[str, str]
    warnings: list[str]


class ProcessingWorkflow:
    """Compone y ejecuta el flujo de procesamiento de la aplicación.

    Recibe puertos de sanitización, LLM, recuperación y almacenamiento.
    No implementa proveedores ni publica contenidos; registra cada nodo y
    conserva la revisión humana pendiente.
    """

    def __init__(self, sanitizer: SanitizationPort, llm: LLMProvider, retriever: RetrieverPort, storage: ObjectStoragePort):
        """Conecta ``sanitizer``, ``llm``, ``retriever`` y ``storage`` al grafo.

        Compila el flujo una vez. No llama todavía a proveedores ni guarda
        datos; esas operaciones ocurren en ``invoke``.
        """
        self.sanitizer, self.llm, self.retriever, self.storage = sanitizer, llm, retriever, storage
        graph = StateGraph(ProcessingState)
        for name, fn in (("sanitize", self._sanitize), ("analyze", self._analyze), ("retrieve", self._retrieve), ("route", self._route), ("success_story", self._generate), ("faq", self._generate), ("community_highlight", self._generate), ("persist", self._persist)):
            graph.add_node(name, self._timed(name, fn))
        graph.add_edge(START, "sanitize")
        graph.add_edge("sanitize", "analyze")
        graph.add_edge("analyze", "retrieve")
        graph.add_edge("retrieve", "route")
        graph.add_conditional_edges("route", self._selected_flow, {name: name for name in ("success_story", "faq", "community_highlight")})
        for name in ("success_story", "faq", "community_highlight"):
            graph.add_edge(name, "persist")
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
                logger.info("workflow_node", extra={"request_id": state["request_id"], "node": name, "provider": self.llm.name if name in {"analyze", "success_story", "faq", "community_highlight"} else self.storage.provider if name == "persist" else "local", "status": "success", "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
                return result
            except Exception as exc:
                # Un error de SDK puede incluir prompts o cabeceras: sólo registramos el tipo.
                logger.error("workflow_node_failed", extra={"request_id": state["request_id"], "node": name, "status": "error", "error_type": type(exc).__name__, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
                raise
        return run

    def _selected_flow(self, state: ProcessingState) -> str:
        """Lee del ``state`` la ruta decidida y la entrega a LangGraph."""

        return state["routing_decision"]["selected_flow"]

    def _sanitize(self, state: ProcessingState) -> dict:
        """Sanitiza cada interacción y borra el texto crudo del ``state``.

        Retorna la lista segura. Puede producir ``InvalidInteractionError``;
        el adaptador usa las reglas locales de PII de ``dataset_builder``.
        """
        safe = [self.sanitizer.sanitize(item["id"], item["text"], item.get("channel"), item.get("type")) for item in state["interactions"] or []]
        return {"sanitized_interactions": safe, "interactions": None}

    def _analyze(self, state: ProcessingState) -> dict:
        """Envía interacciones sanitizadas al LLM y retorna ``Analysis``.

        Puede propagar errores del proveedor. Nunca recibe texto original.
        """
        return {"analysis": self.llm.analyze(state["sanitized_interactions"])}

    def _retrieve(self, state: ProcessingState) -> dict:
        """Construye una consulta acotada y recupera citas para el ``state``.

        Retorna evidencia, posiblemente vacía. Puede producir
        ``RetrievalError`` si falla el índice seleccionado.
        """
        query = " ".join(item.text_sanitized[:200] for item in state["sanitized_interactions"])[:500]
        return {"retrieved_evidence": self.retriever.retrieve(query)}

    def _route(self, state: ProcessingState) -> dict:
        """Elige historia, FAQ o resumen a partir de señales analizadas.

        Retorna ruta y razón. La historia tiene prioridad sobre la pregunta;
        el mock obtiene esas señales con reglas configurables.
        """
        analysis = state["analysis"]
        flow, reason = ("success_story", "Señal de historia de éxito") if analysis.success_story_candidate else ("faq", "Señal de pregunta recurrente") if analysis.recurring_question else ("community_highlight", "Actividad general de la comunidad")
        return {"routing_decision": {"selected_flow": flow, "reason": reason}}

    def _generate(self, state: ProcessingState) -> dict:
        """Pide assets al LLM y exige al menos dos borradores.

        Recibe ruta, análisis, texto seguro y citas desde ``state``.
        Retorna los assets o produce ``AssetGenerationError``.
        """
        assets = self.llm.generate(state["routing_decision"]["selected_flow"], state["analysis"], state["sanitized_interactions"], state["retrieved_evidence"])
        if len(assets) < 2 or any(asset.status != "draft" for asset in assets):
            raise AssetGenerationError("El proveedor debe devolver al menos dos activos draft")
        return {"generated_assets": assets}

    def _persist(self, state: ProcessingState) -> dict:
        """Guarda un paquete sanitizado mediante ``ObjectStoragePort``.

        Retorna proveedor, estado y ubicación. Tiene el efecto secundario de
        escribir un borrador y puede propagar ``StorageError``.
        """
        package = {"request_id": state["request_id"], "community_source": state["community_source"], "reference_period": state["reference_period"], "sanitized_interactions": [item.__dict__ for item in state["sanitized_interactions"]], "analysis": state["analysis"].__dict__, "routing": state["routing_decision"], "evidence": [item.__dict__ for item in state["retrieved_evidence"]], "generated_assets": [item.__dict__ for item in state["generated_assets"]], "human_review": {"required": True, "status": "pending"}}
        location = self.storage.save(state["request_id"], package)
        return {"storage_result": {"provider": self.storage.provider, "status": "stored", "location": location}}

    def invoke(self, state: ProcessingState) -> ProcessingState:
        """Ejecuta el grafo completo con el ``state`` inicial.

        Retorna el estado final y registra inicio y fin. Puede propagar
        errores de validación, proveedores, recuperación o almacenamiento;
        la API se encarga de convertirlos a HTTP.
        """

        logger.info("workflow_start", extra={"request_id": state["request_id"], "status": "start"})
        result = self.graph.invoke(state)
        logger.info("workflow_end", extra={"request_id": state["request_id"], "status": "success"})
        return result
