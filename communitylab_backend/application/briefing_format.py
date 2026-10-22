"""Respuesta en el formato exacto del ejemplo de salida del briefing.

Pertenece a la capa de aplicación. Traduce la respuesta del backend (en
inglés y pensada para el panel) a la estructura en español que muestra el
briefing del hackathon: ``status``, ``resumen_comunidad``,
``activos_distribucion_generados`` y ``almacenamiento_oci``. No llama a
proveedores ni modifica la respuesta original: sólo la reordena.
"""

SENTIMENT_LABELS = {"positive": "Positivo", "neutral": "Neutral", "negative": "Negativo", "mixed": "Mixto"}
NEWSLETTER_SECTIONS = {"success_story": "Logros de la Comunidad", "faq": "Tip de la Semana", "community_highlight": "Novedades de la Comunidad"}


def predominant_sentiment(sentiment: str, rows: list[dict]) -> str:
    """Convierte el sentimiento del lote en la etiqueta del briefing.

    ``sentiment`` es el del análisis (``positive``, ``neutral``...) y
    ``rows`` el análisis por mensaje. Retorna "Altamente Positivo" si el lote
    es positivo y al menos el 75% de los mensajes son positivos; si no,
    Positivo, Neutral, Negativo o Mixto.
    """
    positives = sum(row["sentiment"] == "positive" for row in rows)
    if sentiment == "positive" and rows and positives / len(rows) >= 0.75:
        return "Altamente Positivo"
    return SENTIMENT_LABELS.get(sentiment, sentiment)


def engagement_potential(rows: list[dict]) -> str:
    """Estima el potencial de engagement con la relevancia máxima del lote.

    Retorna "Alto" desde 0.8, "Medio" desde 0.5 y "Bajo" en otro caso.
    """
    best = max((row["relevance"] for row in rows), default=0.0)
    return "Alto" if best >= 0.8 else "Medio" if best >= 0.5 else "Bajo"


def storage_summary(storage: dict) -> dict:
    """Describe dónde quedó el paquete con los nombres del briefing.

    Con OCI separa el bucket y la ruta del objeto de una ubicación
    ``oci://<namespace>/<bucket>/<objeto>``. En modo local el bucket es
    ``None``, la ruta es la del archivo y el estado ``guardado_local``.
    """
    location = storage.get("location", "")
    if storage.get("provider") == "oci" and location.startswith("oci://"):
        parts = location.removeprefix("oci://").split("/", 2)
        if len(parts) == 3:
            return {"bucket": parts[1], "ruta_objeto": parts[2], "status": "guardado_con_exito"}
    return {"bucket": None, "ruta_objeto": location, "status": "guardado_local"}


def _origin(prefix: str, ids: list[str], people: dict[str, dict]) -> str:
    """Arma "<prefix> <autor> en <canal>" con el primer mensaje de ``ids``.

    ``people`` indexa el análisis por mensaje (con autor y canal). Si hay más
    mensajes, agrega cuántos. Usa textos neutros si falta autor o canal.
    """
    first = people.get(ids[0], {}) if ids else {}
    text = f"{prefix} {first.get('author') or 'un miembro de la comunidad'} en {first.get('channel') or 'la comunidad'}"
    return text + (f" (y {len(ids) - 1} más)" if len(ids) > 1 else "")


def build_briefing_format(response: dict, brief_ids: dict[str, list[str]]) -> dict:
    """Construye ``formato_briefing`` a partir de la respuesta del backend.

    ``response`` es la respuesta pública ya armada (con ``interaction_analysis``
    y activos con su ``flow``) y ``brief_ids`` indica, por ruta, qué mensajes
    usó su encargo. Sólo incluye los activos que realmente se generaron.
    Con varios temas de dudas, ``sugerencia_contenido_faq`` y el tip de la
    newsletter toman el tema con más dudas, y ``contenido_educativo`` reúne
    tutorial, tip y tema de documentación de cada tema. Retorna un
    diccionario apto para JSON; no tiene efectos secundarios.
    """
    rows = response["interaction_analysis"]
    people = {row["id"]: row for row in rows}
    assets: dict[str, dict] = {}
    for asset in response["generated_assets"]:
        assets.setdefault(asset["kind"], asset)
    topics = response.get("faq_topics", [])
    summary = response["community_summary"]
    generated = {}
    if "linkedin_post" in assets:
        post = assets["linkedin_post"]
        generated["post_linkedin"] = {"titulo": post["title"], "copy": post["body"], "canal_recomendado": "LinkedIn Oficial", "potencial_engagement": engagement_potential(rows)}
    news = assets.get("newsletter_highlight") or assets.get("weekly_tip")
    if news:
        generated["destaque_newsletter_semanal"] = {"seccion": NEWSLETTER_SECTIONS.get(news.get("flow"), "Novedades de la Comunidad"), "titular": news["title"], "resumen": news["body"]}
    faq = assets.get("quick_tutorial") or assets.get("faq_content")
    if faq:
        origin_ids = topics[0]["interaction_ids"] if topics else brief_ids.get("faq", [])
        generated["sugerencia_contenido_faq"] = {"tema": faq.get("topic") or faq["title"].removeprefix("FAQ: "), "origen": _origin("Duda planteada por", origin_ids, people), "status": "respuesta_con_faq_oficial" if faq.get("evidence_ids") else "derivado_a_mentoria"}
    if "success_story" in assets:
        story = assets["success_story"]
        generated["caso_exito"] = {"titulo": story["title"], "origen": _origin("Logro compartido por", brief_ids.get("success_story", []), people), "borrador": story["body"], "status": "validar_con_la_persona"}
    educational = []
    for item in topics:
        by_kind = {asset["kind"]: asset for asset in response["generated_assets"] if asset.get("topic") == item["topic"]}
        tutorial, tip, doc = by_kind.get("quick_tutorial"), by_kind.get("weekly_tip"), by_kind.get("doc_topic")
        educational.append({
            "tema": item["topic"], "dudas": item["questions"],
            "tutorial_rapido": {"titulo": tutorial["title"], "contenido": tutorial["body"]} if tutorial else None,
            "tip_semana": tip["body"] if tip else None,
            "tema_documentacion": {"titulo": doc["title"], "propuesta": doc["body"]} if doc else None,
            "respaldo_faq_oficial": item["evidence_ids"],
            "status": "respuesta_con_faq_oficial" if tutorial and tutorial.get("evidence_ids") else "derivado_a_mentoria",
        })
    if educational:
        generated["contenido_educativo"] = educational
    return {
        "status": "exito",
        "resumen_comunidad": {"total_interacciones_procesadas": summary["total_interactions_processed"], "sentimiento_predominante": predominant_sentiment(summary["predominant_sentiment"], rows), "temas_principales": summary["main_topics"]},
        "activos_distribucion_generados": generated,
        "almacenamiento_oci": storage_summary(response["storage"]),
    }
