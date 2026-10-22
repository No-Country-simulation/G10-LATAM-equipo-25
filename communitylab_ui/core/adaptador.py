"""
Adaptador: respuesta del backend -> datos que dibuja el panel.

QUE ES ESTO
-----------
El backend devuelve su respuesta en ingles (community_summary,
generated_assets, evidence...). El panel trabaja en espanol y necesita
algunos datos agregados de varios lotes a la vez. Este archivo hace esa
traduccion en UN solo lugar.

Si el backend cambia el nombre de un campo, se ajusta aqui y las vistas no
se enteran. Esta es la regla que antes cumplia data/resultados_ejemplo.json.

Una "corrida" es un lote procesado:
    {"nombre": str, "lote": <entrada del briefing>, "respuesta": <respuesta del backend>}

CAMPOS DEL BACKEND QUE SE USAN
------------------------------
  routing.flows / routing.reasons  -> rutas activas del lote (puede haber varias)
  generated_assets[].flow          -> ruta que encargo cada activo
  interaction_analysis             -> texto sin datos personales, sentimiento, categoria y relevancia por mensaje
  highlights                       -> los 3 mejores momentos del lote
  members_needing_support          -> mensajes de personas que necesitan apoyo
  discarded                        -> mensajes que no entraron a ningun activo
Las respuestas guardadas antes de estos campos siguen funcionando: se usa la
ruta principal (routing.selected_flow) y el sentimiento del lote.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from datetime import datetime, timezone

SENTIMIENTO_ES = {
    "positive": "positivo",
    "neutral": "neutro",
    "negative": "negativo",
    "mixed": "mixto",
}

RUTA_ES = {
    "faq": "FAQ / Tip educativo",
    "success_story": "Historia de éxito",
    "community_highlight": "Resumen de comunidad",
}

# Nombres cortos de ruta para tablas angostas
RUTA_CORTA = {
    "faq": "FAQ",
    "success_story": "Historia de éxito",
    "community_highlight": "Resumen",
}

CATEGORIA_ES = {
    "logro": "Logro",
    "duda": "Duda",
    "apoyo": "Pide apoyo",
    "comentario": "Comentario",
}

# categoria del mensaje -> ruta que lo usa (si esa ruta esta activa en el lote)
RUTA_DE_CATEGORIA = {
    "logro": "success_story",
    "duda": "faq",
    "apoyo": "faq",
    "comentario": "community_highlight",
}

# tipo del backend -> (tipo del panel, canal sugerido)
TIPO_ACTIVO = {
    "quick_tutorial": ("tutorial_rapido", "Documentación / Canal de dudas fijado"),
    "weekly_tip": ("tip_semana", "Discord · Newsletter semanal"),
    "doc_topic": ("tema_documentacion", "Documentación del curso (propuesta)"),
    "faq_content": ("tip_faq", "Documentación / Canal de dudas fijado"),
    "newsletter_highlight": ("destacado_newsletter", "Newsletter semanal"),
    "linkedin_post": ("post_linkedin", "LinkedIn oficial"),
    "success_story": ("caso_exito", "Blog / Testimonios (validar con la persona)"),
}

# tipo del backend -> nombre corto para tablas y listas
ETIQUETA_ACTIVO = {
    "quick_tutorial": "Tutorial rápido",
    "weekly_tip": "Tip de la semana",
    "doc_topic": "Tema de documentación",
    "faq_content": "FAQ",
    "newsletter_highlight": "Newsletter",
    "linkedin_post": "LinkedIn",
    "success_story": "Historia de éxito",
}

# ruta que encargo el destacado de newsletter -> seccion de la newsletter
SECCION_NEWSLETTER = {
    "success_story": "Logros de la comunidad",
    "faq": "Dudas de la semana",
    "community_highlight": "Novedades de la comunidad",
}

TIPOS_PREGUNTA = {"pregunta", "pregunta_tecnica", "question", "duda"}


def _es_pregunta(interaccion: dict) -> bool:
    """Una interaccion cuenta como duda si lo declara su tipo o si trae signo de pregunta."""
    return interaccion.get("tipo", "").lower() in TIPOS_PREGUNTA or "?" in interaccion.get("texto", "")


def _faq_de(snippet: str) -> tuple[str, str]:
    """Separa 'Pregunta: ... / Respuesta: ...' de una cita de la FAQ oficial."""
    pregunta, _, respuesta = snippet.partition("\nRespuesta:")
    return pregunta.replace("Pregunta:", "", 1).strip(), respuesta.strip()


def rutas_de(respuesta: dict) -> list[str]:
    """Rutas activas del lote, en orden de prioridad. Respuestas antiguas: solo la principal."""
    routing = respuesta["routing"]
    return routing.get("flows") or [routing["selected_flow"]]


def resumen_respuesta(respuesta: dict) -> str:
    """Frase corta para avisar en pantalla que un lote se proceso bien."""
    rutas = " + ".join(f"**{RUTA_ES.get(r, r)}**" for r in rutas_de(respuesta))
    apoyo = len(respuesta.get("members_needing_support", []))
    return (
        f"Rutas: {rutas}. {numero_activos(respuesta)} activos generados, "
        f"{len(respuesta.get('evidence', []))} citas de la FAQ oficial, "
        f"{apoyo} persona(s) requieren apoyo. Guardado en `{ubicacion(respuesta['storage'])}`."
    )


def numero_activos(respuesta: dict) -> int:
    """Cuantos borradores genero el backend para un lote."""
    return len(respuesta["generated_assets"])


def ubicacion(paquete: dict | str) -> str:
    """
    Donde quedo guardado un paquete. Acepta el bloque `storage` del backend
    o el texto ya traducido (sesiones guardadas con versiones anteriores del panel).
    """
    return paquete if isinstance(paquete, str) else paquete.get("location", "")


def resumen_guardado(respuesta: dict) -> dict:
    """Traduce la respuesta de guardar la curaduria (aprobados, rechazados y ubicacion)."""
    return {"aprobados": respuesta["approved"], "rechazados": respuesta["rejected"],
            "ubicacion": ubicacion(respuesta["storage"])}


def estado_motor(estado: dict | None) -> dict | None:
    """
    Traduce GET /api/v1/status a llaves en espanol. None si el backend no responde.

    `almacen.tipo` es "oci" o "local"; las demas llaves del almacen solo traen
    valor en el tipo que corresponde.
    """
    if estado is None:
        return None
    almacen = estado.get("storage", {})
    return {
        "proveedor_llm": estado.get("llm_provider"),
        "modelo_llm": estado.get("llm_model"),
        "busqueda": estado.get("retrieval_provider"),
        "almacen": {
            "tipo": "oci" if almacen.get("provider") == "oci" else "local",
            "bucket": almacen.get("bucket"),
            "region": almacen.get("region"),
            "prefijo": almacen.get("prefix"),
            "carpeta": almacen.get("directory"),
        },
    }


DECISION_BACKEND = {"aprobado": "approved", "rechazado": "rejected"}


def decision_backend(estado: str) -> str | None:
    """Decision del panel en el formato del backend. None si el activo sigue pendiente."""
    return DECISION_BACKEND.get(estado)


def activo_para_guardar(act: dict, decision: str, texto: str) -> dict:
    """Un activo revisado en el formato de POST /api/v1/assets/review."""
    return {"kind": act["kind"], "title": act["titulo"], "body": texto,
            "decision": decision, "evidence_ids": act["evidence_ids"]}


def _analisis_por_mensaje(interacciones: list[dict], resp: dict) -> list[dict | None]:
    """
    Analisis del backend para cada mensaje del lote, en el mismo orden.

    Se empareja por id y, si los ids no coinciden (por ejemplo, en respuestas
    guardadas donde el backend genero los ids), por posicion.
    """
    analisis = resp.get("interaction_analysis", [])
    por_id = {a["id"]: a for a in analisis}
    return [por_id.get(m["id"]) or (analisis[i] if i < len(analisis) else None)
            for i, m in enumerate(interacciones)]


def armar_vista(corridas: list[dict]) -> dict:
    """Junta todas las corridas de la sesion en la estructura que usan las vistas."""
    distribucion: Counter = Counter()
    temas: Counter = Counter()
    activos, mensajes, grupos, filas_corridas, ubicaciones = [], [], [], [], []

    for n, corrida in enumerate(corridas, 1):
        lote, resp = corrida["lote"], corrida["respuesta"]
        resumen = resp["community_summary"]
        rutas = rutas_de(resp)
        razones = resp["routing"].get("reasons") or {rutas[0]: resp["routing"].get("reason", "")}
        sentimiento_lote = SENTIMIENTO_ES.get(resumen["predominant_sentiment"], resumen["predominant_sentiment"])
        interacciones = lote["interacciones"]
        prefijo = f"L{n}"

        temas.update(resumen["main_topics"])
        ubicaciones.append(ubicacion(resp["storage"]))

        # id del backend -> id del panel, para traducir highlights, apoyo y descartados
        analisis = _analisis_por_mensaje(interacciones, resp)
        id_panel = {a["id"]: f"{prefijo}-{m['id']}" for m, a in zip(interacciones, analisis) if a}
        destacados = {id_panel.get(i) for i in resp.get("highlights", [])}
        descartados = {id_panel.get(i) for i in resp.get("discarded", [])}

        mensajes_lote = []
        for m, a in zip(interacciones, analisis):
            mid = f"{prefijo}-{m['id']}"
            sentimiento = SENTIMIENTO_ES.get(a["sentiment"], a["sentiment"]) if a else sentimiento_lote
            categoria = a["category"] if a else ("duda" if _es_pregunta(m) else "comentario")
            ruta = RUTA_DE_CATEGORIA.get(categoria)
            ruta = ruta if ruta in rutas else rutas[0]
            distribucion[sentimiento] += 1
            mensaje = {
                "id": mid,
                "autor": m.get("autor", "Anónimo"),
                "canal": m.get("canal", ""),
                # Texto con los datos personales ya ocultos por el backend
                # ([EMAIL], [TELEFONO]...). Las respuestas guardadas antes de
                # este campo no lo traen: en ese caso se usa el del lote.
                "texto": (a.get("text") if a else None) or m["texto"],
                "tipo_detectado": m.get("tipo", "comentario"),
                "sentimiento_detectado": sentimiento,
                "categoria": CATEGORIA_ES.get(categoria, categoria),
                "score_relevancia": a["relevance"] if a else None,
                "requiere_apoyo": bool(a and a["needs_support"]),
                "mejor_momento": mid in destacados,
                "descartado": mid in descartados,
                "ruta": ruta,
                "tema_detectado": ", ".join(resumen["main_topics"]),
                "tema_duda": (a.get("topic") if a else None) or "",
                "lote": corrida["nombre"],
                "decision": "Descartado: no entró a ningún activo" if mid in descartados else f"Ruta {RUTA_ES.get(ruta, ruta)}",
            }
            mensajes_lote.append(mensaje)
        mensajes.extend(mensajes_lote)

        citas = resp.get("evidence", [])
        for i, asset in enumerate(resp["generated_assets"], 1):
            tipo, canal = TIPO_ACTIVO.get(asset["kind"], (asset["kind"], "Por definir"))
            ruta_activo = asset.get("flow") or rutas[0]
            usadas = [c for c in citas if c["record_id"] in asset.get("evidence_ids", [])]
            tema = asset.get("topic")
            origen = [m["id"] for m in mensajes_lote if m["ruta"] == ruta_activo and not m["descartado"]
                      and (not tema or m["tema_duda"] == tema)]
            activos.append({
                "activo_id": f"{prefijo}-act{i}",
                "kind": asset["kind"],
                "tipo_activo": tipo,
                "titulo": asset["title"],
                "contenido": asset["body"],
                "canal_sugerido": canal,
                "etiqueta": ETIQUETA_ACTIVO.get(asset["kind"], asset["kind"]),
                "tema": asset.get("topic"),
                "lote": corrida["nombre"],
                "ruta": RUTA_ES.get(ruta_activo, ruta_activo),
                "seccion_newsletter": SECCION_NEWSLETTER.get(ruta_activo, "Novedades de la comunidad"),
                "request_id": resp["request_id"],
                "origen_comunidad": lote["origen_comunidad"],
                "periodo_referencia": lote["periodo_referencia"],
                "mensajes_origen": origen or [m["id"] for m in mensajes_lote],
                "evidencia": [{"id": c["record_id"], "fuente": c["source"], "pregunta": _faq_de(c["snippet"])[0], "respuesta": _faq_de(c["snippet"])[1], "score": c.get("score", 0)} for c in usadas],
                "evidence_ids": asset.get("evidence_ids", []),
            })

        preguntas = [m for m, a in zip(interacciones, analisis) if (a["category"] == "duda" if a else _es_pregunta(m))]
        temas_faq = resp.get("faq_topics", [])
        for t in temas_faq:
            del_tema = [m for m in mensajes_lote if m["id"] in {id_panel.get(i) for i in t["interaction_ids"]}]
            grupos.append({
                "tema": t["topic"],
                "cantidad_preguntas": t["questions"],
                "autores_distintos": len({m["autor"] for m in del_tema}),
                "canales": sorted({m["canal"] for m in del_tema}),
                "citas_faq": len(t["evidence_ids"]),
                "es_recurrente": t["questions"] >= 2,
            })
        if "faq" in rutas and not temas_faq:
            faq = next((a for a in resp["generated_assets"] if a["kind"] == "faq_content"), None)
            grupos.append({
                "tema": faq["title"] if faq else ", ".join(resumen["main_topics"]),
                "cantidad_preguntas": len(preguntas),
                "autores_distintos": len({m.get("autor") for m in preguntas}),
                "canales": sorted({m.get("canal", "") for m in preguntas}),
                "citas_faq": len(citas),
                "es_recurrente": len(preguntas) >= 2,
            })

        filas_corridas.append({
            "lote": corrida["nombre"],
            "mensajes": len(interacciones),
            "ruta": " + ".join(RUTA_ES.get(r, r) for r in rutas),
            "ruta_corta": " + ".join(RUTA_CORTA.get(r, r) for r in rutas),
            "razon": "; ".join(razones.values()),
            "sentimiento": sentimiento_lote,
            "activos": ", ".join(ETIQUETA_ACTIVO.get(a["kind"], a["kind"]) for a in resp["generated_assets"]),
            "citas": len(citas),
            "apoyo": sum(1 for m in mensajes_lote if m["requiere_apoyo"]),
            "descartados": sum(1 for m in mensajes_lote if m["descartado"]),
            "insights": resp.get("insights", []),
        })

    total = sum(distribucion.values())
    con_puntaje = [m for m in mensajes if m["score_relevancia"] is not None]
    return {
        "origen_comunidad": ", ".join(sorted({c["lote"]["origen_comunidad"] for c in corridas})),
        "periodo_referencia": ", ".join(sorted({c["lote"]["periodo_referencia"] for c in corridas})),
        "comunidades": sorted({c["lote"]["origen_comunidad"] for c in corridas}),
        "periodos": sorted({c["lote"]["periodo_referencia"] for c in corridas}),
        "procesado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resumen_comunidad": {
            "total_interacciones_procesadas": total,
            "total_lotes": len(corridas),
            "sentimiento_predominante": distribucion.most_common(1)[0][0] if distribucion else "neutro",
            "distribucion_sentimiento": dict(distribucion),
            "temas_principales": [{"tema": t, "menciones": c} for t, c in temas.most_common(6)],
            "citas_faq": sum(f["citas"] for f in filas_corridas),
            "requieren_apoyo": sum(1 for m in mensajes if m["requiere_apoyo"]),
            "descartados": sum(1 for m in mensajes if m["descartado"]),
            "sentimiento_por_mensaje": bool(con_puntaje),
        },
        "corridas": filas_corridas,
        "dudas_recurrentes_detectadas": grupos,
        "activos_distribucion_generados": activos,
        "interacciones_muestra": mensajes,
        "mejores_momentos": sorted((m for m in mensajes if m["mejor_momento"]),
                                   key=lambda m: -(m["score_relevancia"] or 0)),
        "requieren_apoyo": [m for m in mensajes if m["requiere_apoyo"]],
        "descartados": [m for m in mensajes if m["descartado"]],
        "almacenamiento": ubicaciones,
    }


# ---------------------------------------------------------------------------
# Base de conocimiento (motor_educativo.db)
# ---------------------------------------------------------------------------
SENTIMIENTO_BASE = {"Positivo": "positivo", "Neutral": "neutro", "Negativo": "negativo"}


def citas_en_sesion(corridas: list[dict]) -> Counter:
    """Cuantas veces cito cada FAQ de la base algun borrador de la sesion (id -> veces)."""
    citas: Counter = Counter()
    for corrida in corridas:
        for asset in corrida["respuesta"].get("generated_assets", []):
            citas.update(asset.get("evidence_ids", []))
    return citas


def vista_base(resumen: dict, faqs: dict, corridas: list[dict]) -> dict:
    """
    Junta el resumen de la base, sus FAQs y lo que se uso en la sesion.

    `citada_en` dice en cuantos borradores aparece cada FAQ: es la prueba de
    que el motor esta respondiendo con la base del equipo.
    """
    citas = citas_en_sesion(corridas)
    lista = [{
        "id": f["record_id"],
        "pregunta": f["question"],
        "respuesta": f["answer"],
        "curso": f["source"].removeprefix("faq:"),
        "citada_en": citas.get(f["record_id"], 0),
    } for f in faqs.get("faqs", [])]
    lista.sort(key=lambda f: -f["citada_en"])
    return {
        "archivo": resumen["file"],
        "faqs_unicas": resumen["unique_faqs"],
        "filas_faq": resumen["faq_rows"],
        "resenas": resumen["reviews"],
        "resenas_distintas": resumen.get("unique_reviews", resumen["reviews"]),
        "cursos": resumen["courses"],
        "desde": resumen["date_range"][0],
        "hasta": resumen["date_range"][1],
        "distribucion_sentimiento": {SENTIMIENTO_BASE.get(k, k.lower()): v for k, v in resumen["sentiment"].items()},
        "notas": resumen["ratings"],
        "cursos_top": [{"tema": c["course"], "menciones": c["reviews"]} for c in resumen["top_courses"]],
        "faqs": lista,
        "faqs_citadas": sum(1 for f in lista if f["citada_en"]),
        "citas_totales": sum(citas.values()),
    }


def resultados_busqueda(respuesta: dict) -> list[dict]:
    """Traduce las citas de /api/v1/rag/query a {id, pregunta, respuesta, curso, puntaje}."""
    return [{
        "id": c["record_id"],
        "pregunta": _faq_de(c["snippet"])[0],
        "respuesta": _faq_de(c["snippet"])[1],
        "curso": c["source"].removeprefix("faq:"),
        "puntaje": c.get("score", 0),
    } for c in respuesta.get("evidence", [])]


def tabla_resenas(respuesta: dict) -> list[dict]:
    """Reseñas reales de la base en el formato de una tabla del panel."""
    return [{
        "id": r["id"], "autor": r["author"], "fecha": r["date"], "nota": r["rating"],
        "curso": r["course"], "sentimiento": SENTIMIENTO_BASE.get(r["sentiment"], r["sentiment"]),
        "texto": r["text"],
    } for r in respuesta.get("reviews", [])]


def lote_desde_resenas(respuesta: dict) -> dict:
    """
    Convierte reseñas reales de la base en un lote con el formato del briefing,
    listo para enviarlo al motor como cualquier otro lote.
    """
    resenas = respuesta.get("reviews", [])
    anios = sorted({r["date"][:4] for r in resenas if r.get("date")}) or ["s/f"]
    return {
        "origen_comunidad": "Base_motor_educativo",
        "periodo_referencia": f"Reseñas_{anios[0]}_{anios[-1]}" if len(anios) > 1 else f"Reseñas_{anios[0]}",
        "interacciones": [{
            "id": r["id"], "autor": r["author"], "canal": f"Reseñas Coursera · {r['course']}",
            "tipo": "reseña", "texto": r["text"],
        } for r in resenas],
    }


def resultado_importacion(respuesta: dict) -> dict:
    """Traduce la respuesta de /api/v1/knowledge/faqs/import al formato del panel."""
    def fila(f: dict) -> dict:
        """Pasa una FAQ del backend a llaves en espanol."""
        return {"pregunta": f["question"], "respuesta": f["answer"], "curso": f["course"]}
    return {
        "vista_previa": respuesta.get("dry_run", True),
        "recibidas": respuesta.get("received", 0),
        "a_agregar": [fila(f) for f in respuesta.get("to_add", [])],
        "repetidas": [fila(f) for f in respuesta.get("duplicates", [])],
        "con_errores": [{"fila": e["row"], "motivo": e["reason"]} for e in respuesta.get("invalid", [])],
        "agregadas": respuesta.get("added", 0),
        "ids_nuevos": respuesta.get("new_ids", []),
        "respaldo": respuesta.get("backup"),
    }


# ---------------------------------------------------------------------------
# Dudas frecuentes (historial del motor)
# ---------------------------------------------------------------------------
def ranking_dudas(respuesta: dict) -> dict:
    """
    Traduce /api/v1/knowledge/frequent-doubts al formato del panel.

    `respaldo` dice si el tema ya tiene FAQ oficial, si no la tiene (hay que
    crear contenido) o si todavia no se busco (temas que no se redactaron).
    """
    def respaldo(valor):
        """Texto que explica si el tema tiene FAQ oficial."""
        return {True: "FAQ oficial", False: "Sin respuesta oficial: crear contenido"}.get(valor, "Sin buscar todavía")
    temas = [{
        "tema": t["topic"], "dudas": t["count"], "semanas": t["weeks"], "lotes": t["batches"],
        "primera_vez": t["first_seen"], "ultima_vez": t["last_seen"],
        "respaldo": respaldo(t["has_official_faq"]), "sin_respuesta": t["has_official_faq"] is False,
        "faqs": ", ".join(t["faq_ids"]), "ejemplo": (t["examples"] or [""])[0],
    } for t in respuesta.get("topics", [])]
    return {
        "total_dudas": respuesta.get("total_doubts", 0),
        "temas": temas,
        "sin_respuesta": sum(1 for t in temas if t["sin_respuesta"]),
        "recurrentes": sum(1 for t in temas if t["dudas"] >= 2),
    }


# ---------------------------------------------------------------------------
# Formato del briefing (campo formato_briefing de la respuesta)
# ---------------------------------------------------------------------------
def briefing_de(corrida: dict) -> dict | None:
    """
    El resultado del lote con la estructura exacta del ejemplo del briefing.

    Lo arma el backend en `formato_briefing`. Las respuestas guardadas antes
    de ese campo no lo traen: en ese caso devuelve None.
    """
    return corrida["respuesta"].get("formato_briefing")


# ---------------------------------------------------------------------------
# Motor de FAQ: de dudas frecuentes a contenido educativo
# ---------------------------------------------------------------------------
TIPOS_EDUCATIVOS = ("quick_tutorial", "weekly_tip", "doc_topic")


def _clave_tema(tema: str | None) -> str:
    """Nombre de tema normalizado (minusculas, sin tildes), igual que en el backend."""
    plano = unicodedata.normalize("NFKD", (tema or "").strip().lower())
    return " ".join("".join(c for c in plano if not unicodedata.combining(c)).split()) or "general"


def motor_faq(ranking: dict, datos: dict | None) -> list[dict]:
    """
    Une, tema por tema, la frecuencia de las dudas con el contenido generado.

    `ranking` es el resultado de `ranking_dudas` (historial de todos los
    lotes) y `datos` la vista de la sesion (`armar_vista`). Por cada tema
    devuelve su frecuencia, si tiene FAQ oficial, las preguntas reales de la
    comunidad y el tutorial, tip y tema de documentacion mas recientes que
    genero el motor (si se proceso un lote con ese tema en la sesion).
    Ordena por cantidad de dudas.
    """
    activos = datos["activos_distribucion_generados"] if datos else []
    mensajes = {m["id"]: m for m in datos["interacciones_muestra"]} if datos else {}
    temas: dict[str, dict] = {}
    for t in ranking.get("temas", []):
        temas[_clave_tema(t["tema"])] = {**t, "preguntas": [t["ejemplo"]] if t["ejemplo"] else [], "contenido": {}}
    for a in activos:
        if a["kind"] not in TIPOS_EDUCATIVOS or not a.get("tema"):
            continue
        tema = temas.setdefault(_clave_tema(a["tema"]), {
            "tema": a["tema"], "dudas": 0, "lotes": 1, "semanas": 1, "ultima_vez": "",
            "respaldo": "FAQ oficial" if a["evidencia"] else "Sin respuesta oficial: crear contenido",
            "sin_respuesta": not a["evidencia"], "faqs": "", "ejemplo": "", "preguntas": [], "contenido": {}})
        tema["contenido"][a["kind"]] = a          # el lote mas reciente reemplaza al anterior
    for tema in temas.values():
        tutorial = tema["contenido"].get("quick_tutorial")
        if tutorial:
            textos = [mensajes[i]["texto"] for i in tutorial["mensajes_origen"] if i in mensajes]
            tema["preguntas"] = textos[:3] or tema["preguntas"]
            tema["mensajes"] = [mensajes[i] for i in tutorial["mensajes_origen"] if i in mensajes]
            tema["dudas"] = tema["dudas"] or len(textos)
    return sorted(temas.values(), key=lambda t: (-t["dudas"], not t["contenido"]))

