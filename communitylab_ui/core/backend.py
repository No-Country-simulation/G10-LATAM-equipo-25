"""
Cliente HTTP del backend de CommunityLab.

QUE ES ESTO
-----------
El UNICO lugar del panel que habla con el backend (FastAPI). Si cambia una
ruta o el puerto del backend, se toca este archivo y nada mas.

La direccion del backend se lee de la variable BACKEND_URL (archivo .env).
Por defecto: http://localhost:8000

ENDPOINTS QUE USA
-----------------
  GET  /health                  -> el backend esta encendido?
  GET  /api/v1/status           -> que LLM, buscador y almacenamiento usa
  POST /api/v1/activity/process -> procesa un lote y devuelve los borradores
  POST /api/v1/assets/review    -> guarda lo que se aprobo o rechazo
"""

from __future__ import annotations

import os

import requests

TIEMPO_ESPERA = 90  # segundos: Gemini puede tardar en responder


class BackendNoDisponible(Exception):
    """El backend no respondio o devolvio un error. El mensaje es apto para mostrarse."""


def url_backend() -> str:
    """Direccion base del backend, sin la barra final."""
    try:
        from core.secretos import obtener_secreto
        valor = obtener_secreto("BACKEND_URL", obligatorio=False)
    except Exception:
        valor = os.environ.get("BACKEND_URL")
    return (valor or "http://localhost:8000").rstrip("/")


def _llamar(metodo: str, ruta: str, **kwargs) -> dict:
    """Hace la peticion y traduce cualquier falla a BackendNoDisponible."""
    try:
        respuesta = requests.request(metodo, f"{url_backend()}{ruta}", timeout=TIEMPO_ESPERA, **kwargs)
    except requests.RequestException as exc:
        raise BackendNoDisponible(
            f"No se pudo conectar con el backend en {url_backend()}. "
            "Revisa que este encendido (uvicorn communitylab_backend.main:app)."
        ) from exc
    if respuesta.status_code >= 400:
        try:
            detalle = respuesta.json().get("detail", respuesta.text)
        except ValueError:
            detalle = respuesta.text
        raise BackendNoDisponible(f"El backend respondio {respuesta.status_code}: {detalle}")
    return respuesta.json()


def estado() -> dict | None:
    """Configuracion activa del backend, o None si no esta encendido."""
    try:
        _llamar("GET", "/health")
        return _llamar("GET", "/api/v1/status")
    except BackendNoDisponible:
        return None


def procesar_lote(lote: dict) -> dict:
    """Envia un lote (formato del briefing) y devuelve la respuesta del motor."""
    return _llamar("POST", "/api/v1/activity/process", json=lote)


def guardar_curaduria(request_id: str, origen: str, periodo: str, activos: list[dict], revisor: str | None = None) -> dict:
    """Guarda las decisiones de curaduria de un procesamiento en el almacenamiento del backend."""
    cuerpo = {
        "request_id": request_id,
        "community_source": origen,
        "reference_period": periodo,
        "reviewer": revisor or None,
        "assets": activos,
    }
    return _llamar("POST", "/api/v1/assets/review", json=cuerpo)


# ---------------------------------------------------------------------------
# Base de conocimiento (motor_educativo.db). Solo lectura.
#   GET  /api/v1/knowledge/summary  -> totales, sentimiento, notas, cursos
#   GET  /api/v1/knowledge/faqs     -> FAQs oficiales
#   GET  /api/v1/knowledge/reviews  -> reseñas reales filtradas
#   POST /api/v1/rag/query          -> buscar FAQs para una pregunta
# ---------------------------------------------------------------------------
def resumen_base() -> dict:
    """Totales de la base: FAQs, reseñas, cursos, sentimiento y notas."""
    return _llamar("GET", "/api/v1/knowledge/summary")


def faqs_base(limite: int = 500) -> dict:
    """FAQs oficiales de la base, con el mismo id que citan los borradores."""
    return _llamar("GET", "/api/v1/knowledge/faqs", params={"limit": limite})


def resenas_base(curso: str | None = None, sentimiento: str | None = None, limite: int = 20) -> dict:
    """Reseñas reales de la base (texto sin datos personales) y lista de cursos."""
    params = {"limit": limite}
    if curso:
        params["course"] = curso
    if sentimiento:
        params["sentiment"] = sentimiento
    return _llamar("GET", "/api/v1/knowledge/reviews", params=params)


def buscar_faq(consulta: str, limite: int = 5) -> dict:
    """Busca en las FAQs oficiales con el mismo buscador que usa el motor."""
    return _llamar("POST", "/api/v1/rag/query", json={"query": consulta, "limit": limite})


def importar_faqs(filas: list[dict], vista_previa: bool = True, tema: str | None = None) -> dict:
    """
    Envia FAQs nuevas a la base. Con vista_previa=True solo muestra que haria;
    con False el backend guarda una copia de seguridad de la base y las agrega.
    Si se indica el tema de dudas que responden, el ranking lo marca resuelto.
    """
    cuerpo = {"rows": filas, "dry_run": vista_previa}
    if tema:
        cuerpo["topic"] = tema
    return _llamar("POST", "/api/v1/knowledge/faqs/import", json=cuerpo)


def dudas_frecuentes(dias: int | None = None, limite: int = 30) -> dict:
    """Ranking de dudas frecuentes del historial del motor (sin IA)."""
    params = {"limit": limite}
    if dias:
        params["days"] = dias
    return _llamar("GET", "/api/v1/knowledge/frequent-doubts", params=params)
