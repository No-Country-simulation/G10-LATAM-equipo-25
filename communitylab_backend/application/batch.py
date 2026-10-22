"""Casos de uso de la aplicación: procesar un lote y registrar la curaduría.

Pertenece a la capa de aplicación. La API HTTP y la herramienta de línea de
comandos (``tools/process_batch.py``) usan estas mismas funciones, así que un
lote produce exactamente la misma respuesta desde cualquiera de las dos.
"""

from dataclasses import asdict
from datetime import datetime, timezone

from communitylab_backend.application.briefing_format import build_briefing_format
from communitylab_backend.application.orchestration import ProcessingWorkflow, topic_key
from communitylab_backend.domain.errors import StorageError

HIGHLIGHTS = 3


def interaction_rows(raw: list[dict], authors: dict[str, str | None], analysis, sanitized: list | None = None) -> list[dict]:
    """Une el análisis de cada mensaje con su autor y su canal, en el orden del lote.

    ``raw`` son las interacciones que entraron al grafo, ``authors`` asocia
    cada id con su autor, ``analysis`` es el ``Analysis`` final y
    ``sanitized`` las ``SanitizedInteraction`` del grafo. ``topic`` es el
    tema del mensaje que asignó el análisis. ``text`` es el
    texto con los datos personales ya ocultos (``[EMAIL]``, ``[TELEFONO]``...),
    para que el panel nunca muestre el original. Un mensaje sin señal
    aparece neutro, como comentario y con relevancia 0.
    """
    signals = {signal.id: signal for signal in analysis.interaction_signals}
    texts = {item.id: item.text_sanitized for item in sanitized or []}
    rows = []
    for item in raw:
        signal = signals.get(item["id"])
        rows.append({"id": item["id"], "author": authors.get(item["id"]), "channel": item.get("channel"), "text": texts.get(item["id"]), "sentiment": signal.sentiment if signal else "neutral", "category": signal.category if signal else "comentario", "relevance": signal.relevance if signal else 0.0, "needs_support": signal.needs_support if signal else False, "topic": signal.topic if signal else None})
    return rows


def process_batch(workflow: ProcessingWorkflow, request_id: str, community_source: str, reference_period: str, interactions: list[dict]) -> dict:
    """Ejecuta el grafo para un lote y devuelve la respuesta pública.

    ``interactions`` trae diccionarios con ``text`` y, opcionalmente, ``id``,
    ``author``, ``channel`` y ``type``. El autor NUNCA entra al grafo ni al
    LLM: se separa aquí y sólo se une por ``id`` al armar la respuesta, para
    decir quién logró un hito o quién necesita apoyo. La fecha no se usa.
    Si el flujo tiene historial de dudas, le pasa al análisis los temas ya
    conocidos y guarda las dudas del lote para el ranking de frecuentes (si
    eso falla, el lote se procesa igual y queda un aviso). Retorna un
    diccionario con la forma de ``ProcessResponse``, incluidos
    ``faq_topics`` y ``formato_briefing``. Propaga los errores del dominio.
    """
    raw = [{"id": item.get("id") or f"interaction-{index}", "text": item["text"], "channel": item.get("channel"), "type": item.get("type")} for index, item in enumerate(interactions, 1)]
    authors = {row["id"]: item.get("author") for row, item in zip(raw, interactions)}
    history = getattr(workflow, "history", None)
    known = history.known_topics() if history else []
    result = workflow.invoke({"request_id": request_id, "community_source": community_source, "reference_period": reference_period, "interactions": raw, "known_topics": known, "warnings": []})
    analysis = result["analysis"]
    rows = interaction_rows(raw, authors, analysis, result.get("sanitized_interactions"))
    brief_ids: dict[str, list[str]] = {}
    for brief in result.get("briefs", []):
        brief_ids.setdefault(brief.flow, []).extend(item.id for item in brief.interactions)
    used = {identifier for ids in brief_ids.values() for identifier in ids}
    faq_topics = [{"topic": brief.topic, "questions": len(brief.interactions), "interaction_ids": [item.id for item in brief.interactions], "evidence_ids": [item.record_id for item in brief.evidence], "has_official_faq": bool(brief.evidence)} for brief in result.get("briefs", []) if brief.flow == "faq" and brief.topic]
    warnings = list(result.get("warnings", []))
    if history:
        searched = {topic_key(item["topic"]): item["evidence_ids"] for item in faq_topics}
        doubts = [{"topic": row["topic"] or "General", "topic_key": topic_key(row["topic"]), "interaction_id": row["id"], "text": row["text"], "faq_ids": searched.get(topic_key(row["topic"]))} for row in rows if row["category"] == "duda"]
        try:
            history.record(request_id, community_source, doubts)
        except StorageError:
            warnings.append("No se pudo guardar el historial de dudas; el lote se procesó igual")
    response = {
        "status": "success",
        "request_id": request_id,
        "community_summary": {"total_interactions_processed": len(raw), "predominant_sentiment": analysis.sentiment, "main_topics": analysis.topics},
        "insights": analysis.insights,
        "routing": result["routing_decision"],
        "generated_assets": [asdict(asset) for asset in result["generated_assets"]],
        "human_review": {"required": True, "status": "pending"},
        "storage": result["storage_result"],
        "evidence": [asdict(item) for item in result["retrieved_evidence"]],
        "interaction_analysis": rows,
        "highlights": [row["id"] for row in sorted(rows, key=lambda row: -row["relevance"])[:HIGHLIGHTS]],
        "members_needing_support": [{"id": row["id"], "author": row["author"], "channel": row["channel"], "category": row["category"]} for row in rows if row["needs_support"]],
        "discarded": [row["id"] for row in rows if row["id"] not in used],
        "faq_topics": faq_topics,
        "warnings": warnings,
    }
    response["formato_briefing"] = build_briefing_format(response, brief_ids)
    return response


def save_review(workflow: ProcessingWorkflow, request_id: str, community_source: str, reference_period: str, reviewer: str | None, assets: list[dict]) -> dict:
    """Guarda la versión revisada de los activos junto al borrador original.

    El paquete se llama ``<request_id>-curaduria`` y usa el mismo
    almacenamiento del flujo (carpeta local u OCI Object Storage). Retorna
    conteos y ubicación. Puede propagar ``StorageError``.
    """
    approved = [asset for asset in assets if asset["decision"] == "approved"]
    package = {
        "request_id": request_id,
        "community_source": community_source,
        "reference_period": reference_period,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reviewer": reviewer,
        "human_review": {"required": True, "status": "completed"},
        "approved_assets": approved,
        "rejected_assets": [asset for asset in assets if asset["decision"] == "rejected"],
    }
    location = workflow.storage.save(f"{request_id}-curaduria", package)
    return {"status": "stored", "request_id": request_id, "approved": len(approved), "rejected": len(assets) - len(approved), "storage": {"provider": workflow.storage.provider, "status": "stored", "location": location}}
