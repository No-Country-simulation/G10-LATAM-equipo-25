"""Entrada HTTP del backend CommunityLab.

La capa API publica salud, procesamiento y búsqueda en FastAPI. Traduce
errores del dominio a HTTP y registra metadatos de cada solicitud sin texto
sensible. La lógica del flujo permanece en la capa de aplicación.
"""

import json
import logging
import time
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from communitylab_backend.api.dependencies import get_settings, get_workflow
from communitylab_backend.api.schemas import ProcessRequest, ProcessResponse, RagQueryRequest, RagQueryResponse
from communitylab_backend.application.orchestration import ProcessingWorkflow
from communitylab_backend.domain.errors import AssetGenerationError, BackendError, InvalidInteractionError, ProviderUnavailableError, RetrievalError, StorageError


class JsonFormatter(logging.Formatter):
    """Formatea metadatos de observabilidad como JSON.

    Pertenece a la capa API. Sólo incluye campos permitidos de los logs;
    no registra cuerpos HTTP, texto de interacciones ni secretos.
    """

    def format(self, record):
        """Recibe un registro de logging y devuelve su JSON seguro.

        No modifica el registro. Su única dependencia es la librería estándar.
        """
        return json.dumps({key: value for key, value in {"event": record.getMessage(), "level": record.levelname, "request_id": getattr(record, "request_id", None), "node": getattr(record, "node", None), "provider": getattr(record, "provider", None), "status": getattr(record, "status", None), "error_type": getattr(record, "error_type", None), "duration_ms": getattr(record, "duration_ms", None)}.items() if value is not None})


logging.basicConfig(level=get_settings().log_level, format="%(message)s")
for handler in logging.getLogger().handlers:
    handler.setFormatter(JsonFormatter())

app = FastAPI(title="Backend de CommunityLab", version="0.1.0", description="Procesa interacciones de una comunidad y prepara borradores para revisión humana. Funciona localmente sin credenciales externas.")


@app.middleware("http")
async def correlate_requests(request: Request, call_next):
    """Asigna un ID a toda petición, incluso si falla la validación.

    ``request`` es la solicitud entrante y ``call_next`` ejecuta el endpoint.
    Devuelve la respuesta con ``X-Request-ID`` y registra duración y estado;
    nunca registra el cuerpo de la petición.
    """

    request.state.request_id = str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    logging.getLogger(__name__).info("http_request", extra={"request_id": request.state.request_id, "status": response.status_code, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
    return response


@app.exception_handler(BackendError)
async def backend_error_handler(request: Request, exc: BackendError):
    """Convierte un error del dominio en una respuesta HTTP estable.

    ``exc`` contiene un mensaje seguro para el cliente. Devuelve 422, 502 o
    503 según el error, junto al ID de ``request``. No expone stack traces.
    """

    status = 422 if isinstance(exc, InvalidInteractionError) else 503 if isinstance(exc, ProviderUnavailableError) else 502 if isinstance(exc, (RetrievalError, AssetGenerationError, StorageError)) else 500
    return JSONResponse(status_code=status, content={"error": exc.__class__.__name__, "detail": str(exc), "request_id": getattr(request.state, "request_id", None)})


@app.get("/health", summary="Comprobar que la API responde", description="Verifica que el proceso FastAPI está activo. No comprueba ni llama a Gemini, Cohere u OCI.", response_description="Estado del proceso y nombre del servicio.")
def health():
    """Devuelve el estado del proceso sin depender de credenciales externas."""

    return {"status": "ok", "service": "communitylab_backend"}


@app.post("/api/v1/activity/process", response_model=ProcessResponse, summary="Procesar interacciones y preparar borradores", description="Recibe un lote JSON de interacciones. Sanitiza el texto, ejecuta LangGraph, genera al menos dos activos draft y guarda un paquete pendiente de revisión humana. El autor y la fecha no se envían a proveedores.", response_description="Resumen, ruta, evidencia, borradores y ubicación de almacenamiento.", responses={422: {"description": "JSON inválido o interacción vacía."}, 502: {"description": "Falló recuperación, generación o almacenamiento."}, 503: {"description": "El proveedor configurado no está disponible."}})
def process_activity(payload: ProcessRequest, request: Request, workflow: ProcessingWorkflow = Depends(get_workflow)):
    """Procesa un lote validado y devuelve su paquete de borradores.

    ``payload`` contiene 1 a 100 interacciones; ``request`` aporta el ID de
    correlación y ``workflow`` ejecuta los nodos. Devuelve ``ProcessResponse``.
    Puede propagar errores de proveedor, recuperación, generación o escritura
    al manejador HTTP. Guarda el paquete mediante ``ObjectStoragePort``.
    """

    request_id = request.state.request_id
    # Autor y fecha se descartan antes del grafo para reducir datos expuestos.
    raw = [{"id": item.id or f"interaction-{index}", "text": item.text, "channel": item.channel, "type": item.type} for index, item in enumerate(payload.interactions, 1)]
    result = workflow.invoke({"request_id": request_id, "community_source": payload.community_source, "reference_period": payload.reference_period, "interactions": raw, "warnings": []})
    analysis = result["analysis"]
    return ProcessResponse(request_id=request_id, community_summary={"total_interactions_processed": len(payload.interactions), "predominant_sentiment": analysis.sentiment, "main_topics": analysis.topics}, insights=analysis.insights, routing=result["routing_decision"], generated_assets=[asset.__dict__ for asset in result["generated_assets"]], human_review={"required": True, "status": "pending"}, storage=result["storage_result"], evidence=[item.__dict__ for item in result["retrieved_evidence"]], warnings=result.get("warnings", []))


@app.post("/api/v1/rag/query", response_model=RagQueryResponse, summary="Buscar evidencia sanitizada", description="Sanitiza la consulta y devuelve hasta el límite solicitado de citas. Con el recuperador mock la lista está vacía; no se inventa una respuesta.", response_description="Citas recuperadas, proveedor e ID de correlación.", responses={422: {"description": "Consulta o límite inválido."}, 502: {"description": "Falló el índice o el recuperador."}, 503: {"description": "Proveedor configurado pendiente o no disponible."}})
def query_knowledge(payload: RagQueryRequest, request: Request, workflow: ProcessingWorkflow = Depends(get_workflow)):
    """Recupera citas para una consulta después de sanitizarla.

    ``payload`` contiene consulta y límite; ``workflow`` aporta sanitizador
    y recuperador. Devuelve ``RagQueryResponse`` y no guarda resultados.
    Puede propagar ``InvalidInteractionError`` o ``RetrievalError``.
    """

    request_id = request.state.request_id
    safe = workflow.sanitizer.sanitize("query", payload.query, None, None)
    evidence = workflow.retriever.retrieve(safe.text_sanitized, payload.limit)
    return RagQueryResponse(request_id=request_id, evidence=[item.__dict__ for item in evidence], provider=type(workflow.retriever).__name__)
