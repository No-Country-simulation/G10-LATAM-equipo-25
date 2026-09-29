"""
CommunityLab - Panel de curaduria
Hackathon ONE G10 - Equipo 25

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

DONDE ESTA CADA COSA
--------------------
  ui/app.py         <- LOGICA: cargar datos, estado, aprobar/rechazar, filtros
  ui/mui_blocks.py  <- DIBUJO con Material UI (streamlit-mui-elements)
  ui/theme.py       <- Colores y CSS de los widgets nativos de Streamlit

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

from ui import theme as T          # noqa: E402
from ui import mui_blocks as B     # noqa: E402

ARCHIVO_MOCK = RAIZ / "data" / "resultados_ejemplo.json"


# ---------------------------------------------------------------------------
# UNICO punto de contacto con el origen de datos.
# Sprint 2: reemplazar el contenido por una llamada al backend.
# ---------------------------------------------------------------------------
def cargar_resultados() -> dict:
    """
    Devuelve los resultados del motor.

    HOY: lee el archivo de ejemplo.
    SPRINT 2: sera algo como
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


def html(contenido: str) -> None:
    st.markdown(contenido, unsafe_allow_html=True)


def cabecera(titulo: str, subtitulo: str, pastilla: str = "") -> None:
    extra = f'<div class="cl-pill">{pastilla}</div>' if pastilla else ""
    html(f'<div class="cl-head"><div><h1>{titulo}</h1><p>{subtitulo}</p></div>{extra}</div>')


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
def vista_resumen(datos: dict) -> None:
    r = datos["resumen_comunidad"]
    total = r["total_interacciones_procesadas"]
    descartadas = r["total_descartadas"]
    aprovechadas = total - descartadas

    cabecera(
        "Resumen del periodo",
        "Qué pasó en la comunidad y qué decidió el motor con cada interacción.",
        f'{datos["origen_comunidad"]} &nbsp;·&nbsp; <b>{datos["periodo_referencia"]}</b>',
    )

    B.fila_metricas("resumen", [
        {"label": "Interacciones procesadas", "valor": total,
         "icono": "Forum", "grad": "azul",
         "nota": f"{aprovechadas} con valor comunicacional"},
        {"label": "Descartadas por el motor", "valor": descartadas,
         "icono": "FilterAlt", "grad": "naranja",
         "nota": f"{descartadas / total:.0%} del total" if total else ""},
        {"label": "Activos generados", "valor": len(datos["activos_distribucion_generados"]),
         "icono": "AutoAwesome", "grad": "verde",
         "nota": "Listos para curaduría"},
        {"label": "Requieren apoyo", "valor": r["miembros_que_requieren_apoyo"],
         "icono": "VolunteerActivism", "grad": "rojo",
         "nota": "Señales de bloqueo prolongado"},
    ])

    izq, der = st.columns(2, gap="large")
    with izq:
        B.barra_apilada_sentimiento(r["distribucion_sentimiento"])
    with der:
        B.panel_temas(r["temas_principales"])

    B.tabla_grupos(datos["dudas_recurrentes_detectadas"])


def vista_ingesta(datos: dict) -> None:
    cabecera(
        "Mensajes procesados",
        "Muestra de las interacciones que entraron al motor y qué decidió con cada "
        "una. Sirve para demostrar que el sistema también descarta: un motor que "
        "convierte el 100% de los mensajes en contenido está roto.",
        f'{len(datos["interacciones_muestra"])} mensajes de muestra',
    )

    filtro = st.multiselect(
        "Filtrar por tipo detectado",
        options=sorted({m["tipo_detectado"] for m in datos["interacciones_muestra"]}),
        default=[],
    )

    mensajes = datos["interacciones_muestra"]
    if filtro:
        mensajes = [m for m in mensajes if m["tipo_detectado"] in filtro]

    if not mensajes:
        st.info("Ningún mensaje coincide con el filtro.")
        return

    B.lista_mensajes(mensajes)


def vista_curaduria(datos: dict) -> None:
    activos = datos["activos_distribucion_generados"]
    estados = st.session_state.curaduria
    pendientes = sum(1 for v in estados.values() if v == "pendiente")

    cabecera(
        "Curaduría de activos",
        "Cada activo muestra el mensaje que lo originó. Ese vínculo es lo que "
        "permite que marketing confíe en lo generado.",
        f"<b>{pendientes}</b> pendientes de revisar",
    )

    B.fila_metricas("curaduria", [
        {"label": "Pendientes", "valor": pendientes,
         "icono": "HourglassTop", "grad": "naranja"},
        {"label": "Aprobados",
         "valor": sum(1 for v in estados.values() if v == "aprobado"),
         "icono": "CheckCircle", "grad": "verde"},
        {"label": "Rechazados",
         "valor": sum(1 for v in estados.values() if v == "rechazado"),
         "icono": "Cancel", "grad": "rojo"},
    ])

    solo_pendientes = st.checkbox("Ver solo pendientes", value=False)

    indice_msg = {m["id"]: m for m in datos["interacciones_muestra"]}

    for i, act in enumerate(activos):
        aid = act["activo_id"]
        estado = estados[aid]
        if solo_pendientes and estado != "pendiente":
            continue

        with st.container(border=True):
            # Cabecera dibujada con Material UI
            B.cabecera_activo(act, estado, i)

            # Widgets nativos: no pueden ir dentro del bloque MUI
            st.text_area(
                "Contenido", value=act["contenido"], height=190,
                key=f"txt_{aid}", label_visibility="collapsed",
            )

            with st.expander("Ver de dónde salió"):
                if act.get("grupo_origen"):
                    grupo = next(
                        (g for g in datos["dudas_recurrentes_detectadas"]
                         if g["grupo_id"] == act["grupo_origen"]), None,
                    )
                    if grupo:
                        html(
                            f'<div class="cl-asset-meta">Grupo de duda recurrente '
                            f'<b>{grupo["tema"]}</b> — {grupo["cantidad_preguntas"]} '
                            f'preguntas de {grupo["autores_distintos"]} personas.</div>'
                        )
                for mid in act["mensajes_origen"]:
                    m = indice_msg.get(mid)
                    if m:
                        html(
                            f'<div style="margin:8px 0">'
                            f'<span class="cl-id">{mid}</span> '
                            f'<span style="font-size:12.5px;color:{T.INK_SECONDARY}">'
                            f'{m["autor"]} · {m["canal"]}</span>'
                            f'<div class="cl-quote" style="margin-top:6px;font-size:13.5px">'
                            f'{m["texto"]}</div></div>'
                        )
                    else:
                        html(f'<div style="margin:8px 0">'
                             f'<span class="cl-id">{mid}</span></div>')

            b1, b2, _ = st.columns([1, 1, 4])
            b1.button("Aprobar", key=f"ok_{aid}", type="primary",
                      on_click=marcar, args=(aid, "aprobado"),
                      use_container_width=True)
            b2.button("Rechazar", key=f"no_{aid}",
                      on_click=marcar, args=(aid, "rechazado"),
                      use_container_width=True)

    html('<hr class="cl-divider">')
    aprobados = [a for a in activos if estados[a["activo_id"]] == "aprobado"]
    st.download_button(
        f"Descargar {len(aprobados)} activos aprobados (JSON)",
        data=json.dumps(aprobados, ensure_ascii=False, indent=2),
        file_name="activos_aprobados.json",
        mime="application/json",
        disabled=not aprobados,
    )


def vista_config(datos: dict) -> None:
    cabecera(
        "Configuración y estado",
        "Estado de la infraestructura y de las credenciales del proyecto.",
    )

    B.tarjeta_almacenamiento(datos["almacenamiento_oci"])

    try:
        from core.secretos import diagnostico
        B.tarjeta_secretos(diagnostico())
    except Exception as e:
        st.error(f"No se pudo leer el diagnóstico de secretos: {e}")

    B.tarjeta_origen(str(ARCHIVO_MOCK.relative_to(RAIZ)))

    with st.expander("Ver JSON completo (contrato de datos)"):
        st.json(datos)


# ---------------------------------------------------------------------------
def barra_lateral() -> str:
    with st.sidebar:
        html(
            '<div class="cl-marca">'
            '  <div class="logo">CL</div>'
            '  <div class="txt"><b>CommunityLab</b>'
            '  <span>Hackathon ONE G10 · Equipo 25</span></div>'
            '</div>'
            '<div class="cl-nav-label">Panel</div>'
        )
        seccion = st.radio("Sección", T.SECCIONES, label_visibility="collapsed")
        html(
            '<div class="cl-side-pie">'
            'Motor de FAQ dinámico<br>y contenido educativo<br><br>'
            'Sprint 1 · datos de ejemplo'
            '</div>'
        )
    return seccion


def main() -> None:
    st.set_page_config(
        page_title="CommunityLab · Panel de curaduría",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    html(T.CSS)

    datos = cargar_resultados()
    init_estado(datos)

    seccion = barra_lateral()

    html(
        '<div class="cl-banner">'
        '  <span style="font-size:16px;line-height:1.2">⚠</span>'
        '  <span><b>Versión de prueba (Sprint 1).</b> Los datos que ves son un '
        'ejemplo escrito a mano, no salen todavía del motor. El objetivo de esta '
        'entrega es fijar la estructura de datos y demostrar el flujo completo '
        'de la interfaz.</span>'
        '</div>'
    )

    if seccion == "Resumen":
        vista_resumen(datos)
    elif seccion == "Mensajes procesados":
        vista_ingesta(datos)
    elif seccion == "Curaduría de activos":
        vista_curaduria(datos)
    else:
        vista_config(datos)


if __name__ == "__main__":
    main()
