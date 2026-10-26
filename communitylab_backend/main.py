"""Entrada HTTP del backend CommunityLab.

La capa API publica salud, estado, procesamiento, búsqueda y curaduría en
FastAPI. Traduce
errores del dominio a HTTP y registra metadatos de cada solicitud sin texto
sensible. La lógica del flujo permanece en la capa de aplicación.
"""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from communitylab_backend.api.dependencies import build_state_mirror, get_knowledge, get_settings, get_workflow
from communitylab_backend.api.schemas import FaqImportRequest, ProcessRequest, ProcessResponse, RagQueryRequest, RagQueryResponse, ReviewRequest, ReviewResponse
from communitylab_backend.application.batch import process_batch, save_review
from communitylab_backend.application.knowledge import KnowledgeService
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Restaura la memoria del motor desde OCI al encender, si está activa.

    Con ``STATE_PROVIDER=oci`` baja el historial de dudas y la base de
    conocimiento antes de atender la primera solicitud. Si OCI falla, lo
    registra y deja que cada solicitud lo reintente (y responda 503 mientras
    tanto); nunca trabaja con una memoria vacía.
    """

    try:
        build_state_mirror(get_settings())
    except BackendError as exc:
        logging.getLogger(__name__).error("state_restore_failed", extra={"provider": "oci", "error_type": type(exc).__name__})
    yield


app = FastAPI(lifespan=lifespan, title="Backend de CommunityLab", version="0.1.0", description="Procesa interacciones de una comunidad y prepara borradores para revisión humana. Funciona localmente sin credenciales externas.")


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


@app.get("/api/v1/status", summary="Ver qué proveedores están activos", description="Indica qué LLM, buscador de FAQs, almacenamiento y fuente de secretos usa el backend según el .env. Nunca devuelve claves ni rutas privadas.", response_description="Proveedores activos y destino de almacenamiento.")
def status():
    """Devuelve la configuración activa sin secretos, para el panel de curaduría.

    Sólo lee ``Settings``; no llama a proveedores ni comprueba credenciales.
    """

    settings = get_settings()
    storage = {"provider": settings.storage_provider, "bucket": settings.oci_bucket, "region": settings.oci_region, "prefix": settings.oci_object_prefix} if settings.storage_provider == "oci" else {"provider": "local", "directory": settings.local_storage_dir.as_posix()}
    return {"llm_provider": settings.llm_provider, "llm_model": settings.gemini_model if settings.llm_provider == "gemini" else "reglas locales (mock)", "retrieval_provider": settings.retrieval_provider, "storage": storage, "secret_provider": settings.secret_provider, "state_provider": settings.state_provider}


@app.get("/api/v1/knowledge/summary", summary="Resumen de la base de conocimiento", description="Cuenta las FAQs oficiales, las reseñas reales y los cursos de motor_educativo.db, con el reparto de sentimiento y de notas. Sólo lee la base; no llama a proveedores.", response_description="Totales, rango de fechas, sentimiento, notas y cursos con más reseñas.", responses={502: {"description": "La base no existe o no tiene el formato esperado."}})
def knowledge_summary(knowledge: KnowledgeService = Depends(get_knowledge)):
    """Resume ``motor_educativo.db`` para que el panel muestre que la base está cargada.

    ``knowledge`` es el servicio de la base (``FAQ_DB_PATH``). Puede propagar
    ``RetrievalError``, que el manejador convierte en 502.
    """

    return knowledge.summary()


@app.get("/api/v1/knowledge/faqs", summary="Listar las FAQs oficiales", description="Devuelve las FAQs oficiales de motor_educativo.db, sin preguntas repetidas, con su identificador (el mismo que citan los borradores) y su curso.", response_description="Lista de FAQs con record_id, question, answer y source.", responses={502: {"description": "La base no existe o no tiene el formato esperado."}})
def knowledge_faqs(limit: int = Query(default=200, ge=1, le=500, description="Máximo de FAQs a devolver."), knowledge: KnowledgeService = Depends(get_knowledge)):
    """Devuelve hasta ``limit`` FAQs oficiales en el orden de la base.

    Puede propagar ``RetrievalError`` si la base no está disponible.
    """

    return {"faqs": knowledge.faqs(limit)}


@app.post("/api/v1/knowledge/faqs/import", summary="Agregar FAQs nuevas a la base", description="Valida FAQs nuevas (pregunta, respuesta y curso) y, con dry_run=false, guarda antes una copia de seguridad de motor_educativo.db en data/respaldos/ y después las agrega. No toca las reseñas ni repite preguntas que ya existen. Con dry_run=true (por defecto) sólo muestra qué haría.", response_description="FAQs a agregar o agregadas, repetidas, filas con errores, ids nuevos y ubicación de la copia de seguridad.", responses={422: {"description": "Archivo vacío, demasiadas FAQs o datos inválidos."}, 502: {"description": "No se pudo copiar o escribir la base."}})
def import_faqs(payload: FaqImportRequest, knowledge: KnowledgeService = Depends(get_knowledge)):
    """Valida las FAQs recibidas y las agrega a la base (o sólo las muestra).

    ``payload`` trae las filas del archivo, ``dry_run`` y, opcionalmente, el
    tema de dudas que responden (el ranking lo marca resuelto). Si la búsqueda
    semántica está activa, reconstruye su índice para incluir las FAQs nuevas
    (si eso falla, devuelve un aviso). Escribir tiene el
    efecto secundario de modificar ``motor_educativo.db`` (con copia previa).
    Puede propagar ``InvalidInteractionError``, ``RetrievalError`` o
    ``StorageError``, que el manejador convierte en 422 o 502.
    """

    return knowledge.import_faqs(payload.rows, payload.dry_run, payload.topic)


@app.get("/api/v1/knowledge/frequent-doubts", summary="Ranking de dudas frecuentes", description="Cuenta, a partir del historial local, qué temas de dudas se repiten más, en cuántas semanas y lotes aparecieron y si ya tienen FAQ oficial. No usa IA.", response_description="Total de dudas y temas ordenados por cantidad.", responses={502: {"description": "No se pudo leer el historial."}})
def frequent_doubts(days: int | None = Query(default=None, ge=1, le=365, description="Sólo los últimos N días (vacío: todo el historial)."), limit: int = Query(default=20, ge=1, le=100, description="Máximo de temas."), knowledge: KnowledgeService = Depends(get_knowledge)):
    """Devuelve el ranking de dudas frecuentes del historial local.

    Sólo lee el archivo del historial. Puede propagar ``StorageError``.
    """

    return knowledge.frequent_doubts(days, limit)


@app.get("/api/v1/knowledge/reviews", summary="Ver reseñas reales de la base", description="Devuelve reseñas reales de cursos guardadas en motor_educativo.db, filtradas por curso y por sentimiento (Positivo, Neutral o Negativo). El texto se entrega sin datos personales. Sirven para armar un lote con datos reales.", response_description="Reseñas con id, autor, fecha, nota, curso, sentimiento y texto, más la lista de cursos disponibles.", responses={502: {"description": "La base no existe o no tiene el formato esperado."}})
def knowledge_reviews(course: str | None = Query(default=None, max_length=200, description="Curso (course_id) por el que filtrar."), sentiment: str | None = Query(default=None, max_length=30, description="Sentimiento: Positivo, Neutral o Negativo."), limit: int = Query(default=20, ge=1, le=100, description="Máximo de reseñas, entre 1 y 100."), knowledge: KnowledgeService = Depends(get_knowledge)):
    """Devuelve reseñas reales y los cursos disponibles para filtrarlas.

    Sólo lee la base. Puede propagar ``RetrievalError`` si no está disponible.
    """

    return knowledge.reviews(course, sentiment, limit)


@app.get("/health", summary="Comprobar que la API responde", description="Verifica que el proceso FastAPI está activo. No comprueba ni llama a Gemini, Cohere u OCI.", response_description="Estado del proceso y nombre del servicio.")
def health():
    """Devuelve el estado del proceso sin depender de credenciales externas."""

    return {"status": "ok", "service": "communitylab_backend"}


@app.post("/api/v1/activity/process", response_model=ProcessResponse, summary="Procesar interacciones y preparar borradores", description="Recibe un lote JSON de interacciones (acepta los nombres del briefing: origen_comunidad, periodo_referencia, interacciones con autor, canal, tipo y texto). Sanitiza el texto, ejecuta LangGraph (un lote puede activar varias rutas a la vez), genera al menos dos activos draft y guarda un paquete pendiente de revisión humana. El autor y la fecha no se envían a proveedores.", response_description="Resumen, rutas, análisis por mensaje, evidencia, borradores, ubicación de almacenamiento y la misma respuesta en el formato del briefing.", responses={422: {"description": "JSON inválido o interacción vacía."}, 502: {"description": "Falló recuperación, generación o almacenamiento."}, 503: {"description": "El proveedor configurado no está disponible."}})
def process_activity(payload: ProcessRequest, request: Request, workflow: ProcessingWorkflow = Depends(get_workflow)):
    """Procesa un lote validado y devuelve su paquete de borradores.

    ``payload`` contiene 1 a 100 interacciones; ``request`` aporta el ID de
    correlación y ``workflow`` ejecuta los nodos. Devuelve ``ProcessResponse``.
    Puede propagar errores de proveedor, recuperación, generación o escritura
    al manejador HTTP. Guarda el paquete mediante ``ObjectStoragePort``.
    """

    # La fecha se descarta. El autor sólo lo usa process_batch para la respuesta: nunca entra al grafo.
    interactions = [{"id": item.id, "author": item.author, "text": item.text, "channel": item.channel, "type": item.type} for item in payload.interactions]
    return process_batch(workflow, request.state.request_id, payload.community_source, payload.reference_period, interactions)


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


@app.post("/api/v1/assets/review", response_model=ReviewResponse, summary="Guardar la curaduría de los activos", description="Recibe los activos revisados en el panel (aprobados o rechazados, con sus ediciones) y guarda el paquete final junto al borrador, en la carpeta local o en OCI Object Storage.", response_description="Conteos y ubicación del paquete revisado.", responses={422: {"description": "Datos de revisión inválidos."}, 502: {"description": "Falló el almacenamiento."}, 503: {"description": "El almacenamiento configurado no está disponible."}})
def review_assets(payload: ReviewRequest, workflow: ProcessingWorkflow = Depends(get_workflow)):
    """Guarda la decisión humana sobre los activos de un procesamiento.

    ``payload`` trae el ``request_id`` original y los activos revisados. No
    publica nada: deja registro de qué se aprobó para publicar. Puede
    propagar ``StorageError`` o ``ProviderUnavailableError``.
    """

    return save_review(workflow, payload.request_id, payload.community_source, payload.reference_period, payload.reviewer, [asset.model_dump() for asset in payload.assets])
