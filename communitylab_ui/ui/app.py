"""
CommunityLab - Panel de curaduria
Hackathon ONE G10

QUE ES ESTO
-----------
La interfaz donde el equipo de marketing revisa lo que genero el motor y
decide que se publica y que no.

IMPORTANTE PARA EL EQUIPO:
Hoy este panel NO llama al backend. Lee el archivo data/resultados_ejemplo.json,
que es un ejemplo escrito a mano. Eso es intencional: permite construir y
demostrar toda la interfaz antes de que el motor exista.

Cuando el backend este listo, solo cambia la funcion cargar_resultados().
Nada mas del archivo se toca.

COMO EJECUTARLO
---------------
    pip install -r requirements.txt
    streamlit run ui/app.py
"""

import json
import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ARCHIVO_MOCK = RAIZ / "data" / "resultados_ejemplo.json"

ETIQUETAS_ACTIVO = {
    "tip_faq": "Tip / FAQ",
    "post_linkedin": "Post LinkedIn",
    "destacado_newsletter": "Newsletter",
}

COLOR_SENTIMIENTO = {
    "muy_positivo": "#1a7f37",
    "positivo": "#2da44e",
    "neutro": "#6e7781",
    "negativo": "#cf222e",
}


# ---------------------------------------------------------------------------
# UNICO punto de contacto con el origen de datos.
# Sprint 2: reemplazar el contenido por una llamada al backend.
# ---------------------------------------------------------------------------
def cargar_resultados() -> dict:
    """
    Devuelve los resultados del motor.

    HOY: lee el archivo de ejemplo.
    SPRINT 2: UNION BACK
        import requests
        return requests.post(URL_BACKEND, json=lote).json()
    """
    with open(ARCHIVO_MOCK, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Estado de curaduria: que se aprobo y que se rechazo.
# Vive en memoria de la sesion. No necesitamos base de datos para el MVP.
# ---------------------------------------------------------------------------
def init_estado(datos: dict) -> None:
    if "curaduria" not in st.session_state:
        st.session_state.curaduria = {
            a["activo_id"]: a.get("estado_curaduria", "pendiente")
            for a in datos["activos_distribucion_generados"]
        }


def marcar(activo_id: str, estado: str) -> None:
    st.session_state.curaduria[activo_id] = estado


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
def vista_resumen(datos: dict) -> None:
    r = datos["resumen_comunidad"]

    st.subheader("Resumen del periodo")
    st.caption(
        f"Comunidad: **{datos['origen_comunidad']}**  ·  "
        f"Periodo: **{datos['periodo_referencia']}**"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Interacciones procesadas", r["total_interacciones_procesadas"])
    c2.metric("Descartadas por el motor", r["total_descartadas"])
    c3.metric("Activos generados", len(datos["activos_distribucion_generados"]))
    c4.metric("Miembros que requieren apoyo", r["miembros_que_requieren_apoyo"])

    st.divider()

    izq, der = st.columns(2)

    with izq:
        st.markdown("**Distribucion de sentimiento**")
        dist = r["distribucion_sentimiento"]
        total = sum(dist.values()) or 1
        for clave, valor in dist.items():
            pct = valor / total
            st.markdown(
                f"<span style='color:{COLOR_SENTIMIENTO.get(clave, '#6e7781')}'>"
                f"● {clave.replace('_', ' ')}</span> — {valor} ({pct:.0%})",
                unsafe_allow_html=True,
            )
            st.progress(pct)

    with der:
        st.markdown("**Temas principales**")
        temas = r["temas_principales"]
        maximo = max((t["menciones"] for t in temas), default=1)
        for t in temas:
            st.markdown(f"{t['tema']} — {t['menciones']} menciones")
            st.progress(t["menciones"] / maximo)

    st.divider()

    st.markdown("**Dudas recurrentes detectadas**")
    st.caption(
        "El motor agrupa preguntas que significan lo mismo aunque esten escritas "
        "distinto. Un grupo se considera recurrente a partir de 3 preguntas de "
        "autores distintos."
    )

    for g in datos["dudas_recurrentes_detectadas"]:
        if g["es_recurrente"]:
            etiqueta = "RECURRENTE"
            cuerpo = (
                f"**{g['tema']}**  \n"
                f"{g['cantidad_preguntas']} preguntas de {g['autores_distintos']} "
                f"personas distintas  ·  canales: {', '.join(g['canales'])}  ·  "
                f"relevancia {g['score_relevancia']:.2f}"
            )
            st.success(f"{etiqueta} — genera Tip/FAQ")
            st.markdown(cuerpo)
        else:
            st.info("NO RECURRENTE — no genera activo")
            st.markdown(
                f"**{g['tema']}**  \n"
                f"{g['cantidad_preguntas']} pregunta  ·  "
                f"relevancia {g['score_relevancia']:.2f}"
            )


def vista_ingesta(datos: dict) -> None:
    st.subheader("Mensajes procesados")
    st.caption(
        "Muestra de las interacciones que entraron al motor y que decidio con "
        "cada una. Sirve para demostrar que el sistema tambien descarta: un "
        "motor que convierte el 100% de los mensajes en contenido esta roto."
    )

    filtro = st.multiselect(
        "Filtrar por tipo detectado",
        options=sorted({m["tipo_detectado"] for m in datos["interacciones_muestra"]}),
        default=[],
    )

    mensajes = datos["interacciones_muestra"]
    if filtro:
        mensajes = [m for m in mensajes if m["tipo_detectado"] in filtro]

    for m in mensajes:
        descartado = m["decision"].startswith("descartado") or m["decision"].startswith("no_recurrente")
        with st.container(border=True):
            cab, sc = st.columns([5, 1])
            cab.markdown(
                f"`{m['id']}`  ·  **{m['autor']}**  ·  {m['canal']}  ·  "
                f"{m['timestamp'][:10]}  ·  {m['reacciones']} reacciones"
            )
            sc.markdown(f"**{m['score_relevancia']:.2f}**")

            st.markdown(f"> {m['texto']}")

            a, b, c = st.columns(3)
            a.markdown(
                f"Sentimiento: <span style='color:{COLOR_SENTIMIENTO.get(m['sentimiento_detectado'], '#6e7781')}'>"
                f"**{m['sentimiento_detectado']}**</span>",
                unsafe_allow_html=True,
            )
            b.markdown(f"Tema: **{m['tema_detectado']}**")
            c.markdown(f"Tipo: **{m['tipo_detectado']}**")

            if descartado:
                st.caption(f"Decision del motor: {m['decision']}  (sin activo)")
            else:
                st.caption(f"Decision del motor: {m['decision']}")


def vista_curaduria(datos: dict) -> None:
    st.subheader("Activos generados")
    st.caption(
        "Cada activo muestra el mensaje que lo origino. Ese vinculo es lo que "
        "permite que marketing confie en lo generado."
    )

    activos = datos["activos_distribucion_generados"]
    estados = st.session_state.curaduria

    a, b, c = st.columns(3)
    a.metric("Pendientes", sum(1 for v in estados.values() if v == "pendiente"))
    b.metric("Aprobados", sum(1 for v in estados.values() if v == "aprobado"))
    c.metric("Rechazados", sum(1 for v in estados.values() if v == "rechazado"))

    st.divider()

    solo_pendientes = st.checkbox("Ver solo pendientes", value=False)

    for act in activos:
        aid = act["activo_id"]
        estado = estados[aid]
        if solo_pendientes and estado != "pendiente":
            continue

        with st.container(border=True):
            top, badge = st.columns([4, 1])
            top.markdown(
                f"**{act['titulo']}**  \n"
                f"{ETIQUETAS_ACTIVO.get(act['tipo_activo'], act['tipo_activo'])}  ·  "
                f"Canal sugerido: {act['canal_sugerido']}  ·  "
                f"Relevancia {act['score_relevancia']:.2f}"
            )
            if estado == "aprobado":
                badge.success("Aprobado")
            elif estado == "rechazado":
                badge.error("Rechazado")
            else:
                badge.warning("Pendiente")

            st.text_area(
                "Contenido",
                value=act["contenido"],
                height=200,
                key=f"txt_{aid}",
                label_visibility="collapsed",
            )

            with st.expander("Ver de donde salio"):
                if act.get("grupo_origen"):
                    grupo = next(
                        (g for g in datos["dudas_recurrentes_detectadas"]
                         if g["grupo_id"] == act["grupo_origen"]),
                        None,
                    )
                    if grupo:
                        st.markdown(
                            f"Grupo de duda recurrente **{grupo['tema']}** — "
                            f"{grupo['cantidad_preguntas']} preguntas de "
                            f"{grupo['autores_distintos']} personas."
                        )
                st.markdown("Mensajes de origen:")
                indice = {m["id"]: m for m in datos["interacciones_muestra"]}
                for mid in act["mensajes_origen"]:
                    m = indice.get(mid)
                    if m:
                        st.markdown(f"- `{mid}` ({m['autor']}, {m['canal']}): _{m['texto']}_")
                    else:
                        st.markdown(f"- `{mid}`")

            b1, b2, b3 = st.columns([1, 1, 4])
            b1.button("Aprobar", key=f"ok_{aid}",
                      on_click=marcar, args=(aid, "aprobado"))
            b2.button("Rechazar", key=f"no_{aid}",
                      on_click=marcar, args=(aid, "rechazado"))

    st.divider()
    aprobados = [a for a in activos if estados[a["activo_id"]] == "aprobado"]
    st.download_button(
        f"Descargar {len(aprobados)} activos aprobados (JSON)",
        data=json.dumps(aprobados, ensure_ascii=False, indent=2),
        file_name="activos_aprobados.json",
        mime="application/json",
        disabled=not aprobados,
    )


def vista_config(datos: dict) -> None:
    st.subheader("Configuracion y estado")

    st.markdown("**Almacenamiento en OCI Object Storage**")
    oci = datos["almacenamiento_oci"]
    if oci["status"] == "simulado":
        st.warning(
            "Estado: SIMULADO. Todavia no se sube nada real. "
            "Esta es la estructura que el backend debera devolver."
        )
    else:
        st.success("Estado: guardado correctamente.")
    st.code(
        f"bucket      : {oci['bucket']}\n"
        f"region      : {oci['region']}\n"
        f"ruta objeto : {oci['ruta_objeto']}\n"
        f"tamano      : {oci['tamano_bytes']} bytes\n"
        f"guardado en : {oci['guardado_en']}",
        language="text",
    )

    st.divider()

    st.markdown("**Secretos**")
    st.caption(
        "Nunca se muestra el valor de un secreto, solo si esta configurado. "
        "Cada integrante puede verificar aqui su entorno sin pedir ayuda."
    )
    try:
        from core.secretos import diagnostico
        filas = diagnostico()
        for f in filas:
            if f["estado"] == "configurado":
                st.markdown(f"✅ `{f['secreto']}` — {f['descripcion']}")
            else:
                st.markdown(f"⛔ `{f['secreto']}` — FALTA. {f['descripcion']}")
        st.caption(f"Fuente activa: **{filas[0]['fuente']}**" if filas else "")
    except Exception as e:
        st.error(f"No se pudo leer el diagnostico de secretos: {e}")

    st.info(
        "Sprint 1: los secretos se leen del archivo .env local.  \n"
        "Sprint 2: se migran a OCI Vault cambiando FUENTE_SECRETOS=vault. "
        "Ningun otro archivo del proyecto cambia."
    )

    st.divider()
    st.markdown("**Origen de los datos de este panel**")
    st.warning(
        f"Leyendo de `{ARCHIVO_MOCK.relative_to(RAIZ)}` (datos de ejemplo). "
        "Cuando el backend este listo, se cambia unicamente la funcion "
        "`cargar_resultados()` en este archivo."
    )
    with st.expander("Ver JSON completo (contrato de datos)"):
        st.json(datos)


# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title="CommunityLab · Panel de curaduria",
        page_icon="📋",
        layout="wide",
    )

    datos = cargar_resultados()
    init_estado(datos)

    st.title("CommunityLab")
    st.caption("Panel de curaduria · Hackathon ONE G10 · Motor de FAQ dinamico y contenido educativo")

    st.info(
        "**Version de prueba (Sprint 1).** Los datos que ves son un ejemplo "
        "escrito a mano, no salen todavia del motor. El objetivo de esta "
        "entrega es fijar la estructura de datos y demostrar el flujo completo "
        "de la interfaz.",
        icon="ℹ️",
    )

    t1, t2, t3, t4 = st.tabs(
        ["Resumen", "Mensajes procesados", "Curaduria de activos", "Configuracion"]
    )
    with t1:
        vista_resumen(datos)
    with t2:
        vista_ingesta(datos)
    with t3:
        vista_curaduria(datos)
    with t4:
        vista_config(datos)


if __name__ == "__main__":
    main()
