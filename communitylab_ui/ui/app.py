"""
CommunityLab - Panel de curaduria
Hackathon ONE G10 - Equipo 25

QUE ES ESTO
-----------
La interfaz donde el equipo de marketing envia lotes de mensajes de la
comunidad al motor, revisa lo que genero y decide que se publica y que no.

COMO FLUYEN LOS DATOS
---------------------
  1. "Procesar lote": se elige un ejemplo, se sube un JSON/CSV o se escriben
     mensajes. El panel los envia al backend (POST /api/v1/activity/process).
  2. El backend analiza cada mensaje, activa una o varias rutas (FAQ,
     historia de exito o resumen), genera los borradores y guarda el
     paquete (carpeta local u OCI).
  3. Cada respuesta se guarda en la sesion como una "corrida". El adaptador
     (core/adaptador.py) las junta para las demas vistas.
  4. En "Curaduria" se edita, aprueba o rechaza, y se guarda la decision en
     el backend (POST /api/v1/assets/review).

DONDE ESTA CADA COSA
--------------------
  ui/app.py           <- LOGICA: vistas, estado, aprobar/rechazar
  ui/mui_blocks.py    <- DIBUJO con Material UI (streamlit-mui-elements)
  ui/theme.py         <- Colores y CSS
  core/backend.py     <- Llamadas HTTP al backend
  core/adaptador.py   <- Traduce la respuesta del backend a lo que dibuja el panel
  core/ingesta.py     <- Lee lotes JSON/CSV y los ejemplos de data/lotes_ejemplo
  core/secretos.py    <- Lectura de variables y secretos

COMO EJECUTARLO
---------------
    pip install -r requirements.txt
    streamlit run ui/app.py
"""

import hmac
import json
from datetime import datetime
import re
import sys
from collections import Counter
from html import escape
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import backend                    # noqa: E402
from core import ingesta                    # noqa: E402
from core.secretos import obtener_secreto   # noqa: E402
from core.adaptador import armar_vista, resumen_respuesta  # noqa: E402
from core.adaptador import lote_desde_resenas, resultado_importacion, resultados_busqueda, tabla_resenas  # noqa: E402
from core.adaptador import vista_base as armar_base  # noqa: E402
from core.adaptador import briefing_de, motor_faq, ranking_dudas  # noqa: E402
from core.adaptador import estado_motor, numero_activos, resumen_guardado, ubicacion  # noqa: E402
from core.adaptador import activo_para_guardar, decision_backend  # noqa: E402
from ui import mui_blocks as B              # noqa: E402
from ui import previas as P                 # noqa: E402
from ui import theme as T                   # noqa: E402


# Bandeja de curaduria: punto de color por estado (Markdown de Streamlit) y filtros
PUNTO_ESTADO = {"pendiente": ":orange[●]", "aprobado": ":green[●]", "rechazado": ":red[●]"}
FILTROS_ESTADO = {"Pendientes": "pendiente", "Aprobados": "aprobado", "Rechazados": "rechazado", "Todos": None}


# ---------------------------------------------------------------------------
# Estado de la sesion
#   corridas  : lotes procesados (entrada + respuesta del backend)
#   curaduria : activo_id -> pendiente | aprobado | rechazado
#   guardados : resultados de guardar la curaduria en el backend
#   ediciones : activo_id -> texto editado en la bandeja (sobrevive al
#               cambiar de activo; el cuadro de texto solo existe para el
#               activo abierto y Streamlit borra su estado al ocultarlo)
# Vive en memoria de la sesion. No necesitamos base de datos para el MVP.
# ---------------------------------------------------------------------------
ESTADO_SESION = ("corridas", "curaduria", "guardados", "ediciones")
# Copia local de la sesion para recuperarla si se recarga la pagina. Vive en la
# carpeta del panel y no se sube a git (ver .gitignore): trae textos de la comunidad.
ARCHIVO_SESION = RAIZ / "data" / "sesion_guardada.json"


def init_estado() -> None:
    """Crea en la sesion las llaves que faltan con su valor inicial."""
    for clave in ESTADO_SESION:
        if clave not in st.session_state:
            st.session_state[clave] = [] if clave in ("corridas", "guardados") else {}


def guardar_sesion() -> None:
    """
    Guarda en disco la sesion (lotes, decisiones y ediciones) si cambio.

    Streamlit pierde todo al recargar la pagina; con esta copia se puede
    recuperar desde «Procesar lote». Si no hay lotes, no guarda nada.
    """
    if not st.session_state.corridas:
        return
    datos = {"guardado_en": datetime.now().strftime("%Y-%m-%d %H:%M"),
             "faqs_desde_curaduria": st.session_state.get("faqs_desde_curaduria", {}),
             **{clave: st.session_state[clave] for clave in ESTADO_SESION}}
    contenido = json.dumps({k: v for k, v in datos.items() if k != "guardado_en"}, ensure_ascii=False, sort_keys=True)
    if st.session_state.get("_sesion_firma") == contenido:
        return
    try:
        ARCHIVO_SESION.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO_SESION.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        st.session_state["_sesion_firma"] = contenido
    except OSError:
        pass  # si no se puede guardar, el panel sigue funcionando igual


def recuperar_sesion() -> None:
    """Carga la ultima sesion guardada en disco (boton de «Procesar lote»)."""
    try:
        datos = json.loads(ARCHIVO_SESION.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.session_state["_sesion_error"] = True
        return
    for clave in ESTADO_SESION:
        st.session_state[clave] = datos.get(clave, [] if clave in ("corridas", "guardados") else {})
    st.session_state["faqs_desde_curaduria"] = datos.get("faqs_desde_curaduria", {})


def oferta_recuperar() -> None:
    """Si hay una sesion guardada y la actual esta vacia, ofrece recuperarla."""
    if st.session_state.corridas or not ARCHIVO_SESION.is_file() or st.session_state.get("_sesion_descartada"):
        return
    try:
        datos = json.loads(ARCHIVO_SESION.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    n = len(datos.get("corridas", []))
    if not n:
        return
    with st.container(border=True):
        st.markdown(f"**Hay una sesión anterior guardada** ({n} lote(s), {datos.get('guardado_en', 'sin fecha')}). "
                    "Puedes recuperar los lotes, las decisiones de curaduría y las ediciones.")
        c1, c2, _ = st.columns([1.2, 1, 3])
        c1.button("Recuperar sesión", type="primary", on_click=recuperar_sesion, key="sesion_recuperar", width="stretch")
        c2.button("Empezar de cero", key="sesion_descartar", width="stretch",
                  on_click=lambda: st.session_state.update({"_sesion_descartada": True}))
    if st.session_state.pop("_sesion_error", False):
        st.error("No se pudo leer la sesión guardada.")


def agregar_corrida(nombre: str, lote: dict, respuesta: dict) -> None:
    """Guarda una corrida y deja sus activos pendientes de revision."""
    st.session_state.corridas.append({"nombre": nombre, "lote": lote, "respuesta": respuesta})
    n = len(st.session_state.corridas)
    for i in range(1, numero_activos(respuesta) + 1):
        st.session_state.curaduria.setdefault(f"L{n}-act{i}", "pendiente")


def procesar(nombre: str, lote: dict) -> bool:
    """Envia el lote al backend y guarda la corrida. Devuelve True si salio bien."""
    try:
        respuesta = backend.procesar_lote(lote)
    except backend.BackendNoDisponible as e:
        st.error(f"{nombre}: {e}")
        return False
    agregar_corrida(nombre, lote, respuesta)
    st.success(f"**{nombre}** → {resumen_respuesta(respuesta)}")
    return True


def marcar(activo_id: str, estado: str, orden: list[str] | None = None) -> None:
    """
    Registra la decision sobre un activo.

    Si recibe el `orden` de la bandeja, abre el siguiente activo pendiente
    (como en una bandeja de entrada: decides y pasas al siguiente).
    """
    st.session_state.curaduria[activo_id] = estado
    if orden:
        i = orden.index(activo_id) if activo_id in orden else -1
        siguientes = orden[i + 1:] + orden[:i + 1]
        destino = next((a for a in siguientes if st.session_state.curaduria.get(a) == "pendiente"), None)
        if destino:
            st.session_state["bandeja_sel"] = destino


def html(contenido: str) -> None:
    """Pinta HTML propio del panel (estilos de theme.py)."""
    st.markdown(contenido, unsafe_allow_html=True)


def cabecera(titulo: str, subtitulo: str, pastilla: str = "") -> None:
    """Titulo y subtitulo de cada vista, con una pastilla opcional a la derecha."""
    extra = f'<div class="cl-pill">{pastilla}</div>' if pastilla else ""
    html(f'<div class="cl-head"><div><h1>{titulo}</h1><p>{subtitulo}</p></div>{extra}</div>')


def sin_datos() -> None:
    """Aviso cuando todavia no hay lotes procesados (ofrece recuperar la sesion guardada)."""
    oferta_recuperar()
    st.info("Todavía no hay lotes procesados. Ve a **Procesar lote** y envía un ejemplo o tu propio archivo.")


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
def vista_procesar(estado: dict | None) -> None:
    """Vista para enviar un lote al backend: ejemplos, archivo propio o texto pegado."""
    cabecera(
        "Procesar lote",
        "Envía mensajes de la comunidad al motor. Cada lote pasa por análisis, "
        "decisión de ruta, generación de borradores y almacenamiento.",
        f'<b>{len(st.session_state.corridas)}</b> lotes procesados en esta sesión',
    )

    if estado is None:
        st.warning(
            f"El backend no responde en `{backend.url_backend()}`. Enciéndelo con "
            "`uvicorn communitylab_backend.main:app --reload` desde la raíz del "
            "repositorio del backend. Mientras tanto puedes cargar respuestas "
            "guardadas (pestaña **Respuesta guardada**)."
        )

    oferta_recuperar()
    ejemplos = ingesta.lotes_ejemplo()
    t_ej, t_arch, t_texto, t_guardada = st.tabs(
        ["Lotes de ejemplo", "Subir archivo", "Escribir mensajes", "Respuesta guardada"])

    with t_ej:
        if not ejemplos:
            st.info("No hay lotes en data/lotes_ejemplo.")
        else:
            st.caption("Los ejemplos cubren las tres rutas del motor: historia de éxito, FAQ y resumen de comunidad.")
            nombre = st.selectbox("Lote", list(ejemplos))
            lote = ingesta.leer_ejemplo(ejemplos[nombre])
            with st.expander(f"Ver los {len(lote['interacciones'])} mensajes del lote"):
                st.dataframe(lote["interacciones"], use_container_width=True, hide_index=True)
            c1, c2, _ = st.columns([1, 1.4, 2])
            if c1.button("Procesar este lote", type="primary", disabled=estado is None, use_container_width=True):
                with st.spinner("El motor está analizando..."):
                    procesar(nombre, lote)
            if c2.button(f"Procesar los {len(ejemplos)} ejemplos (demo)", disabled=estado is None, use_container_width=True):
                with st.spinner("Procesando todos los ejemplos..."):
                    for n, ruta in ejemplos.items():
                        procesar(n, ingesta.leer_ejemplo(ruta))

    with t_arch:
        st.caption("JSON con el formato del briefing, o CSV con columnas autor, canal, tipo, texto (solo texto es obligatoria).")
        archivo = st.file_uploader("Archivo de interacciones", type=["json", "csv"], key="subida_lote")
        c1, c2 = st.columns(2)
        origen = c1.text_input("Comunidad de origen (opcional)", key="origen_arch")
        periodo = c2.text_input("Período (opcional)", key="periodo_arch")
        if archivo is not None:
            try:
                lote = ingesta.leer_archivo(archivo.name, archivo.getvalue(), origen, periodo)
            except ingesta.LoteInvalido as e:
                st.error(str(e))
            else:
                st.dataframe(lote["interacciones"], use_container_width=True, hide_index=True)
                if st.button("Procesar archivo", type="primary", disabled=estado is None):
                    with st.spinner("El motor está analizando..."):
                        procesar(Path(archivo.name).stem, lote)

    with t_texto:
        st.caption("Un mensaje por línea. Útil para probar en vivo durante la demo.")
        c1, c2, c3, c4 = st.columns(4)
        origen = c1.text_input("Comunidad", value="Discord_Grupo_ONE_G10", key="origen_txt")
        periodo = c2.text_input("Período", value="Demo_en_vivo", key="periodo_txt")
        canal = c3.text_input("Canal", value="#general", key="canal_txt")
        tipo = c4.selectbox("Tipo", ["pregunta_tecnica", "testimonio", "comentario"], key="tipo_txt")
        texto = st.text_area("Mensajes", height=140, key="mensajes_txt",
                             placeholder="¿Cómo evito el sobreajuste en mi modelo?")
        if st.button("Procesar mensajes", type="primary", disabled=estado is None or not texto.strip()):
            filas = [{"autor": "Participante", "canal": canal, "tipo": tipo, "texto": linea}
                     for linea in texto.splitlines() if linea.strip()]
            try:
                lote = ingesta.lote_desde_dict(
                    {"origen_comunidad": origen, "periodo_referencia": periodo, "interacciones": filas}, periodo)
            except ingesta.LoteInvalido as e:
                st.error(str(e))
            else:
                with st.spinner("El motor está analizando..."):
                    procesar(f"{periodo} ({len(filas)} mensajes)", lote)

    with t_guardada:
        st.caption("Archivos de salidas/respuestas del backend, generados con "
                   "`python -m communitylab_backend.tools.process_batch ejemplos`. "
                   "No necesita el backend encendido.")
        guardadas = st.file_uploader("Respuestas guardadas", type=["json"],
                                     accept_multiple_files=True, key="subida_resp")
        if guardadas and st.button("Cargar respuestas", type="primary"):
            for archivo in guardadas:
                try:
                    lote, respuesta = ingesta.leer_respuesta_guardada(archivo.name, archivo.getvalue())
                except ingesta.LoteInvalido as e:
                    st.error(f"{archivo.name}: {e}")
                    continue
                agregar_corrida(Path(archivo.name).stem, lote, respuesta)
            st.success("Respuestas cargadas. Revisa Resumen y Curaduría.")

    if st.session_state.corridas:
        html('<hr class="cl-divider">')
        if st.button("Limpiar la sesión (borrar lotes procesados)"):
            for clave in list(st.session_state):
                if clave in ESTADO_SESION or clave in ("bandeja_sel", "faqs_desde_curaduria", "_sesion_firma") or clave.startswith("txt_"):
                    del st.session_state[clave]
            ARCHIVO_SESION.unlink(missing_ok=True)
            st.rerun()


def vista_resumen(datos: dict) -> None:
    """Resumen de la comunidad: metricas, sentimiento, temas y miembros que piden apoyo."""
    r = datos["resumen_comunidad"]
    comunidades, periodos = datos["comunidades"], datos["periodos"]
    cabecera(
        "Resumen del periodo",
        "Qué pasó en la comunidad y qué decidió el motor con cada lote.",
        (escape(comunidades[0]) if len(comunidades) == 1 else f"<b>{len(comunidades)}</b> comunidades")
        + " &nbsp;·&nbsp; "
        + (f"<b>{escape(periodos[0])}</b>" if len(periodos) == 1 else f"<b>{len(periodos)}</b> períodos"),
    )

    B.fila_metricas("resumen", [
        {"label": "Interacciones procesadas", "valor": r["total_interacciones_procesadas"],
         "icono": "Forum", "grad": "azul",
         "nota": f"Sentimiento predominante: {r['sentimiento_predominante']}"},
        {"label": "Lotes procesados", "valor": r["total_lotes"],
         "icono": "AccountTree", "grad": "violeta",
         "nota": "Cada lote sigue una ruta del motor"},
        {"label": "Activos generados", "valor": len(datos["activos_distribucion_generados"]),
         "icono": "AutoAwesome", "grad": "verde",
         "nota": "Listos para curaduría"},
        {"label": "Citas de la FAQ oficial", "valor": r["citas_faq"],
         "icono": "MenuBook", "grad": "naranja",
         "nota": "Respaldo de las respuestas FAQ"},
        {"label": "Requieren apoyo", "valor": r["requieren_apoyo"],
         "icono": "SupportAgent", "grad": "rojo",
         "nota": f"{r['descartados']} mensaje(s) descartados"},
    ])

    izq, der = st.columns(2, gap="large")
    with izq:
        B.barra_apilada_sentimiento(
            r["distribucion_sentimiento"],
            f"{r['total_interacciones_procesadas']} mensajes, según el análisis de cada uno"
            if r["sentimiento_por_mensaje"] else
            f"{r['total_interacciones_procesadas']} mensajes, según el sentimiento de su lote")
    with der:
        B.panel_temas(r["temas_principales"], "Lotes en los que aparece cada tema", "lote(s)")

    B.tabla_corridas(datos["corridas"])
    if datos["dudas_recurrentes_detectadas"]:
        B.tabla_grupos(datos["dudas_recurrentes_detectadas"])

    if datos["mejores_momentos"]:
        st.markdown("#### Mejores momentos")
        st.caption("Los 5 mensajes con mayor puntaje de relevancia (0 a 1) entre los lotes de la sesión.")
        B.lista_mensajes(datos["mejores_momentos"][:5], clave="mejores")
    if datos["requieren_apoyo"]:
        B.tabla_apoyo(datos["requieren_apoyo"])

    with st.expander("Hallazgos del motor por lote"):
        for fila in datos["corridas"]:
            st.markdown(f"**{fila['lote']}** — " + "; ".join(fila["insights"])
                        + (f"  \n_Por qué esas rutas:_ {fila['razon']}" if fila.get("razon") else ""))


def vista_ingesta(datos: dict) -> None:
    """Mensajes procesados: tabla con categoria, sentimiento y relevancia de cada uno."""
    cabecera(
        "Mensajes procesados",
        "Las interacciones que entraron al motor, con el análisis de cada una "
        "(sentimiento, categoría y relevancia) y la ruta que la usó. Los datos "
        "personales (correos, teléfonos, enlaces) se ocultan antes de llegar al modelo.",
        f'{len(datos["interacciones_muestra"])} mensajes',
    )

    c1, c2, c3 = st.columns([1.3, 1.3, 1])
    filtro = c1.multiselect(
        "Filtrar por tipo declarado",
        options=sorted({m["tipo_detectado"] for m in datos["interacciones_muestra"]}),
        default=[],
    )
    filtro_cat = c2.multiselect(
        "Filtrar por categoría detectada",
        options=sorted({m["categoria"] for m in datos["interacciones_muestra"]}),
        default=[],
    )
    vista = c3.radio("Mostrar", ["Todos", "Requieren apoyo", "Descartados"])

    mensajes = datos["interacciones_muestra"]
    if filtro:
        mensajes = [m for m in mensajes if m["tipo_detectado"] in filtro]
    if filtro_cat:
        mensajes = [m for m in mensajes if m["categoria"] in filtro_cat]
    if vista == "Requieren apoyo":
        mensajes = [m for m in mensajes if m["requiere_apoyo"]]
    elif vista == "Descartados":
        mensajes = [m for m in mensajes if m["descartado"]]

    if not mensajes:
        st.info("Ningún mensaje coincide con el filtro.")
        return

    B.lista_mensajes(mensajes)


def texto_actual(act: dict) -> str:
    """Contenido del activo con las ediciones hechas en el panel."""
    return st.session_state.ediciones.get(act["activo_id"], act["contenido"])


def guardar_edicion(activo_id: str) -> None:
    """Copia el cuadro de texto a `ediciones` para no perderlo al cambiar de activo."""
    st.session_state.ediciones[activo_id] = st.session_state[f"txt_{activo_id}"]


def restaurar(activo_id: str, original: str) -> None:
    """
    Descarta las ediciones y vuelve al borrador que genero el motor.

    Se ASIGNA el texto original al cuadro de texto: si solo se borrara su
    clave, el navegador seguiria mostrando el texto editado.
    """
    st.session_state.ediciones.pop(activo_id, None)
    st.session_state[f"txt_{activo_id}"] = original


def abrir(activo_id: str) -> None:
    """Abre un activo en la bandeja (botones Anterior / Siguiente)."""
    st.session_state["bandeja_sel"] = activo_id


def _md_seguro(texto: str) -> str:
    """Escapa los simbolos de Markdown para mostrar un titulo tal cual en una etiqueta."""
    return re.sub(r"([*_`\[\]<>#~|\\])", r"\\\1", texto)


def fila_bandeja(act: dict, estado: str) -> str:
    """Primera linea de una fila de la bandeja: estado, marca de editado y titulo."""
    titulo = act["titulo"] if len(act["titulo"]) <= 60 else act["titulo"][:58] + "…"
    editado = "✎ " if act["activo_id"] in st.session_state.ediciones else ""
    return f"{PUNTO_ESTADO[estado]} {editado}**{_md_seguro(titulo)}**"


def exportar_markdown(aprobados: list[dict]) -> str:
    """Activos aprobados en Markdown, listos para pegar en un documento o en la newsletter."""
    lineas = ["# Activos aprobados · CommunityLab", ""]
    for a in aprobados:
        lineas += [f"## {a['etiqueta']} · {a['titulo']}",
                   f"_Lote: {a['lote']} · Canal: {a['canal_sugerido']}_", "", a["contenido"], ""]
    return "\n".join(lineas)


def guardar_en_backend(activos: list, estados: dict, revisor: str) -> None:
    """Envia al backend las decisiones ya tomadas, agrupadas por procesamiento."""
    por_request: dict[str, list] = {}
    for act in activos:
        decision = decision_backend(estados[act["activo_id"]])
        if decision:
            por_request.setdefault(act["request_id"], []).append((act, decision))
    if not por_request:
        st.warning("Aprueba o rechaza al menos un activo antes de guardar.")
        return
    for request_id, items in por_request.items():
        primero = items[0][0]
        cuerpo = [activo_para_guardar(a, d, texto_actual(a)) for a, d in items]
        try:
            res = backend.guardar_curaduria(request_id, primero["origen_comunidad"],
                                            primero["periodo_referencia"], cuerpo, revisor)
        except backend.BackendNoDisponible as e:
            st.error(f"{primero['lote']}: {e}")
            continue
        guardado = resumen_guardado(res)
        st.session_state.guardados.append(guardado["ubicacion"])
        st.success(f"{primero['lote']}: {guardado['aprobados']} aprobados, {guardado['rechazados']} rechazados. "
                   f"Guardado en `{guardado['ubicacion']}`.")


def vista_curaduria(datos: dict) -> None:
    """
    Bandeja de curaduria: lista compacta a la izquierda y el activo abierto a
    la derecha (decision, editor, vista previa por canal y fuente).
    """
    activos = datos["activos_distribucion_generados"]
    por_id = {a["activo_id"]: a for a in activos}
    estados = st.session_state.curaduria
    conteo = Counter(estados[a["activo_id"]] for a in activos)
    revisados = conteo["aprobado"] + conteo["rechazado"]
    todos = [a["activo_id"] for a in activos]

    cabecera(
        "Curaduría de activos",
        "Abre un borrador de la bandeja, revísalo junto a su vista previa y a los "
        "mensajes que lo originaron, edítalo si hace falta y decide. Al aprobar o "
        "rechazar se abre el siguiente pendiente.",
        f"<b>{conteo['pendiente']}</b> pendientes · <b>{conteo['aprobado']}</b> aprobados · "
        f"<b>{conteo['rechazado']}</b> rechazados",
    )
    st.progress(revisados / len(activos) if activos else 0.0,
                text=f"{revisados} de {len(activos)} borradores revisados")
    aviso = st.session_state.pop("aviso_curaduria", None)
    if aviso:
        st.success(aviso)

    izq, der = st.columns([1, 1.9], gap="medium")

    # --- Bandeja (izquierda) ---------------------------------------------
    with izq:
        filtro = st.segmented_control(
            "Estado", list(FILTROS_ESTADO), default="Pendientes", key="bandeja_filtro",
            format_func=lambda f: f"{f} {conteo[FILTROS_ESTADO[f]] if FILTROS_ESTADO[f] else len(activos)}",
            label_visibility="collapsed")
        c1, c2 = st.columns(2)
        tipos = c1.multiselect("Tipo", sorted({a["etiqueta"] for a in activos}),
                               placeholder="Todos los tipos", label_visibility="collapsed")
        lote = c2.selectbox("Lote", ["Todos los lotes"] + list(dict.fromkeys(a["lote"] for a in activos)),
                            label_visibility="collapsed")
        estado_filtro = FILTROS_ESTADO.get(filtro)
        visibles = [a for a in activos
                    if (estado_filtro is None or estados[a["activo_id"]] == estado_filtro)
                    and (not tipos or a["etiqueta"] in tipos)
                    and (lote == "Todos los lotes" or a["lote"] == lote)]
        orden = [a["activo_id"] for a in visibles]
        if orden and st.session_state.get("bandeja_sel") not in orden:
            st.session_state["bandeja_sel"] = orden[0]
        with st.container(height=600, key="cl_bandeja"):
            if orden:
                st.radio("Bandeja", orden, key="bandeja_sel",
                         format_func=lambda aid: fila_bandeja(por_id[aid], estados[aid]),
                         captions=[f"{a['etiqueta']} · {a['ruta']} · {a['lote']}" for a in visibles],
                         label_visibility="collapsed")
            else:
                st.caption("No hay borradores con estos filtros.")

    # --- Activo abierto (derecha) ------------------------------------------
    with der:
        aid = st.session_state.get("bandeja_sel") if orden else None
        if not aid:
            html('<div class="cl-vacio"><b>Bandeja al día</b>No quedan borradores con estos filtros. '
                 'Elige «Todos» para volver a ver lo ya decidido, o guarda la curaduría abajo.</div>')
        else:
            act, i = por_id[aid], orden.index(aid)
            B.cabecera_activo(act, estados[aid], 0)

            b1, b2, b3, _, b4, b5 = st.columns([1.2, 1.2, 1.2, 0.8, 0.5, 0.5])
            b1.button("Aprobar", key=f"ok_{aid}", type="primary", width="stretch",
                      on_click=marcar, args=(aid, "aprobado", todos))
            b2.button("Rechazar", key=f"no_{aid}", width="stretch",
                      on_click=marcar, args=(aid, "rechazado", todos))
            b3.button("Restaurar", key=f"rs_{aid}", width="stretch",
                      help="Descarta tus ediciones y vuelve al borrador del motor",
                      on_click=restaurar, args=(aid, act["contenido"]),
                      disabled=aid not in st.session_state.ediciones)
            b4.button("←", key="nav_prev", width="stretch", help="Borrador anterior",
                      on_click=abrir, args=(orden[max(i - 1, 0)],), disabled=i == 0)
            b5.button("→", key="nav_next", width="stretch", help="Borrador siguiente",
                      on_click=abrir, args=(orden[min(i + 1, len(orden) - 1)],),
                      disabled=i + 1 >= len(orden))
            html(f'<div class="cl-progreso">Borrador <b>{i + 1}</b> de <b>{len(orden)}</b> en esta lista · '
                 f'canal sugerido: <b>{escape(act["canal_sugerido"])}</b></div>')

            indice_msg = {m["id"]: m for m in datos["interacciones_muestra"]}
            mensajes = [indice_msg[m] for m in act["mensajes_origen"] if m in indice_msg]
            if act["kind"] == "quick_tutorial" and not act["evidencia"]:
                agregar_tutorial_a_base(act, mensajes)
            t_prev, t_edit, t_src = st.tabs([
                "Vista previa", "Editar texto",
                f"Fuente y FAQ ({len(mensajes)} mensaje(s) · {len(act['evidencia'])} FAQ)"])
            with t_edit:
                # El valor inicial va por session_state (no por `value=`) para que
                # Restaurar pueda reemplazarlo sin el aviso de Streamlit.
                if f"txt_{aid}" not in st.session_state:
                    st.session_state[f"txt_{aid}"] = texto_actual(act)
                st.text_area("Contenido", height=320, key=f"txt_{aid}",
                             on_change=guardar_edicion, args=(aid,), label_visibility="collapsed")
                nota, excedido = P.contador(act["kind"], texto_actual(act))
                editado = " · editado en el panel" if aid in st.session_state.ediciones else ""
                html(f'<div class="cl-contador{" excedido" if excedido else ""}">{escape(nota)}{editado}</div>')
            with t_prev:
                html(P.previa(act, texto_actual(act)))
                st.caption("Texto final, listo para copiar (botón de copiar arriba a la derecha):")
                st.code(texto_actual(act), language=None, wrap_lines=True)
            with t_src:
                html(f'<div class="cl-asset-meta">Lote <b>{escape(act["lote"])}</b> · ruta '
                     f'<b>{escape(act["ruta"])}</b></div>' + P.fuente(mensajes, act["evidencia"]))

    # --- Cierre: guardar y exportar --------------------------------------
    html('<hr class="cl-divider">')
    aprobados = [{**a, "contenido": texto_actual(a)} for a in activos
                 if estados[a["activo_id"]] == "aprobado"]
    c1, c2, c3, c4 = st.columns([1.2, 1.4, 1.2, 1.2])
    revisor = c1.text_input("Revisado por", value="Equipo de marketing")
    with c2:
        st.write("")
        if st.button("Guardar curaduría en el backend", type="primary", width="stretch"):
            guardar_en_backend(activos, estados, revisor)
    with c3:
        st.write("")
        st.download_button(f"Aprobados en JSON ({len(aprobados)})",
                           data=json.dumps(aprobados, ensure_ascii=False, indent=2),
                           file_name="activos_aprobados.json", mime="application/json",
                           disabled=not aprobados, width="stretch")
    with c4:
        st.write("")
        st.download_button(f"Aprobados en Markdown ({len(aprobados)})",
                           data=exportar_markdown(aprobados),
                           file_name="activos_aprobados.md", mime="text/markdown",
                           disabled=not aprobados, width="stretch")


def agregar_tutorial_a_base(act: dict, mensajes: list[dict]) -> None:
    """
    Cierra el ciclo del Motor de FAQ dinamico.

    Cuando un tutorial responde un tema que NO tiene FAQ oficial, se puede
    aprobar y agregar a la base en un solo paso: la pregunta es la duda real
    de la comunidad (ya sin datos personales) y la respuesta es el tutorial
    con las ediciones del panel. Desde ese momento, una duda parecida se
    responde con esta FAQ en lugar de ir a mentoria.
    """
    aid = act["activo_id"]
    hechas = st.session_state.setdefault("faqs_desde_curaduria", {})
    if aid in hechas:
        st.success(f"Agregado a la base como **{hechas[aid]}**. La próxima duda parecida se responderá con esta FAQ.")
        return
    c1, c2 = st.columns([2.2, 1.3])
    c1.caption("Este tema no tiene FAQ oficial en la base. Si el tutorial está bien (revísalo o edítalo "
               "antes), puedes aprobarlo y guardarlo como FAQ nueva para las próximas dudas.")
    if c2.button("Aprobar y agregar a la base", key=f"faq_base_{aid}", type="primary", width="stretch"):
        pregunta = (mensajes[0]["texto"] if mensajes else act.get("tema") or act["titulo"])[:500]
        # El aviso "Sin FAQ oficial..." es para quien revisa, no para la FAQ que se guarda.
        respuesta = texto_actual(act).replace("Sin FAQ oficial: borrador para validar con un mentor.", "").strip()
        fila = {"pregunta": pregunta, "respuesta": respuesta[:5000], "curso": act.get("tema") or "comunidad"}
        try:
            resultado = backend.importar_faqs([fila], vista_previa=False, tema=act.get("tema"))
        except backend.BackendNoDisponible as e:
            st.error(str(e))
            return
        st.session_state.curaduria[aid] = "aprobado"
        nuevos = resultado_importacion(resultado)["ids_nuevos"]
        hechas[aid] = nuevos[0] if nuevos else "una FAQ que ya existía"
        st.session_state["aviso_curaduria"] = (
            f"«{act['titulo']}» quedó aprobado y agregado a la base como **{hechas[aid]}**. "
            "La próxima duda parecida se responderá con esta FAQ en lugar de ir a mentoría.")
        st.rerun()


FLUJO_MOTOR = (
    '<div class="cl-flujo"><span>Dudas de la comunidad</span><b>→</b><span>Agrupadas por tema y frecuencia</span>'
    '<b>→</b><span class="cl-flujo-core">Tutorial rápido · Tip de la semana · Tema de documentación</span>'
    '<b>→</b><span>Revisión humana</span><b>→</b><span>Base de FAQs que crece</span></div>'
)


def ir_a_curaduria(activo_id: str) -> None:
    """Abre un borrador en la bandeja de curaduria (boton «Revisar» del Motor de FAQ)."""
    st.session_state["seccion"] = "Curaduría de activos"
    st.session_state["bandeja_filtro"] = "Todos"
    st.session_state["bandeja_sel"] = activo_id


def _tarjeta_tema(t: dict) -> None:
    """Un tema: lo que pregunta la comunidad → tutorial, tip y tema de documentacion."""
    with st.container(border=True):
        clase = "pv-chip-red" if t["sin_respuesta"] else "pv-chip-green"
        html(f'<div class="cl-tema-head"><span class="cl-tema-nombre">{escape(t["tema"])}</span>'
             f'<span class="pv-chip pv-chip-blue">{t["dudas"]} duda(s)</span>'
             f'<span class="pv-chip">{t["lotes"]} lote(s) · {t["semanas"]} semana(s)</span>'
             f'<span class="pv-chip {clase}">{escape(t["respaldo"])}</span></div>')
        c1, c0, c2, c3, c4 = st.columns([1.1, 0.12, 1.3, 1.05, 1.3])
        with c1:
            preguntas = "".join(f'<div class="cl-quote cl-mini-q">{_texto_html(p)}</div>' for p in t["preguntas"][:3])
            html('<div class="cl-col-titulo">Lo que pregunta la comunidad</div>' + (preguntas or ""))
        with c0:
            html('<div class="cl-flecha">→</div>')
        for col, kind, titulo in ((c2, "quick_tutorial", "Tutorial rápido"), (c3, "weekly_tip", "Tip de la semana"),
                                  (c4, "doc_topic", "Tema de documentación")):
            with col:
                html(f'<div class="cl-col-titulo">{titulo}</div>')
                act = t["contenido"].get(kind)
                if not act:
                    st.caption("Se genera al procesar un lote con este tema.")
                    continue
                html(f'<div class="cl-mini">{P.previa(act, texto_actual(act))}</div>')
                estado = st.session_state.curaduria.get(act["activo_id"], "pendiente")
                st.button(f"Revisar · {estado}", key=f"motor_{act['activo_id']}", width="stretch",
                          on_click=ir_a_curaduria, args=(act["activo_id"],))
        tutorial = t["contenido"].get("quick_tutorial")
        if tutorial and not tutorial["evidencia"]:
            agregar_tutorial_a_base(tutorial, t.get("mensajes", []))


def vista_motor_faq(datos: dict | None, estado: dict | None) -> None:
    """
    El corazon del proyecto en una sola pantalla: cada duda frecuente de la
    comunidad y el contenido educativo que el motor genero para ella.

    Une el historial de dudas (todos los lotes) con los borradores de la
    sesion. Por tema muestra lo que pregunta la comunidad y, al lado, el
    tutorial rapido, el tip de la semana y el tema de documentacion, con su
    estado y el atajo para agregar a la base lo que no tenia FAQ oficial.
    """
    cabecera("Motor de FAQ",
             "De dudas frecuentes a contenido educativo: cada tema que pregunta la comunidad se convierte en un "
             "tutorial rápido, un tip de la semana y una propuesta de documentación. Lo que se aprueba sin "
             "respaldo oficial entra a la base y la próxima duda se responde sola.")
    html(FLUJO_MOTOR)
    if estado is None:
        st.warning("El backend no responde: enciéndelo para ver el historial de dudas.")
        return
    try:
        ranking = ranking_dudas(backend.dudas_frecuentes())
    except backend.BackendNoDisponible as e:
        st.error(str(e))
        return
    temas = motor_faq(ranking, datos)
    if not temas:
        st.info("Todavía no hay dudas. Procesa lotes en **Procesar lote** (o carga respuestas guardadas) y vuelve aquí.")
        return
    generados = sum(len(t["contenido"]) for t in temas)
    B.fila_metricas("motor", [
        {"label": "Dudas registradas", "valor": ranking["total_dudas"] or sum(t["dudas"] for t in temas),
         "icono": "QuestionAnswer", "grad": "azul", "nota": "En todos los lotes procesados"},
        {"label": "Temas", "valor": len(temas), "icono": "Topic", "grad": "violeta",
         "nota": f"{sum(1 for t in temas if t['dudas'] >= 2)} con 2 o más dudas"},
        {"label": "Contenidos generados", "valor": generados, "icono": "AutoAwesome", "grad": "verde",
         "nota": "Tutoriales, tips y documentación"},
        {"label": "Sin respuesta oficial", "valor": sum(1 for t in temas if t["sin_respuesta"]),
         "icono": "ReportProblem", "grad": "rojo", "nota": "Prioridad para crear contenido"},
        {"label": "FAQs aprendidas", "valor": len(st.session_state.get("faqs_desde_curaduria", {})),
         "icono": "School", "grad": "naranja", "nota": "Agregadas a la base en la sesión"},
    ])
    solo = st.toggle("Ver solo los temas con contenido generado en esta sesión", value=bool(generados),
                     key="motor_solo_contenido")
    for t in temas:
        if solo and not t["contenido"]:
            continue
        _tarjeta_tema(t)
    if not generados:
        st.caption("Los temas aparecen con su contenido cuando se procesa un lote o se cargan respuestas guardadas.")
    with st.expander(f"Ranking completo de dudas frecuentes ({len(ranking['temas'])} temas del historial)"):
        if ranking["temas"]:
            st.dataframe(ranking["temas"], hide_index=True, width="stretch",
                         column_order=["tema", "dudas", "semanas", "lotes", "ultima_vez", "respaldo", "faqs", "ejemplo"],
                         column_config={"tema": st.column_config.TextColumn("Tema", width="medium"),
                                        "dudas": st.column_config.ProgressColumn(
                                            "Dudas", format="%d", min_value=0,
                                            max_value=max(t["dudas"] for t in ranking["temas"])),
                                        "semanas": "Semanas", "lotes": "Lotes", "ultima_vez": "Última vez",
                                        "respaldo": st.column_config.TextColumn("Respaldo", width="medium"),
                                        "faqs": "FAQs oficiales",
                                        "ejemplo": st.column_config.TextColumn("Ejemplo (sin datos personales)", width="large")})
        else:
            st.caption("El historial está vacío: se llena al procesar lotes con el backend.")


def _texto_html(texto: str | None) -> str:
    """Texto escapado con sus saltos de linea, para mostrarlo dentro de una cita."""
    return escape(texto or "").replace("\n", "<br>")


def _bloque(titulo: str, filas: list[tuple[str, str | None]]) -> None:
    """Tarjeta con un titulo y pares etiqueta/valor (los valores vacios no se muestran)."""
    with st.container(border=True):
        st.markdown(f"**{titulo}**")
        for etiqueta, valor in filas:
            if valor:
                html(f'<div class="cl-asset-meta" style="margin-top:6px">{escape(etiqueta)}</div>'
                     f'<div class="cl-quote" style="margin-top:4px">{_texto_html(str(valor))}</div>')


def vista_semana() -> None:
    """
    Muestra el resultado de un lote con la estructura exacta del ejemplo de
    salida del briefing (formato_briefing), en lenguaje claro y descargable.
    """
    corridas = st.session_state.corridas
    cabecera("Esta semana",
             "El resultado de cada lote con la misma estructura del ejemplo de salida del briefing: "
             "resumen de la comunidad, activos listos para distribuir y dónde quedó guardado.")
    if not corridas:
        sin_datos()
        return
    nombres = [c["nombre"] for c in corridas]
    elegido = st.selectbox("Lote", nombres, index=len(nombres) - 1, key="semana_lote")
    corrida = corridas[nombres.index(elegido)]
    fb = briefing_de(corrida)
    if not fb:
        st.info("Esta respuesta se guardó antes de que existiera el formato del briefing. Vuelve a procesar el lote.")
        return
    r, act, alm = fb["resumen_comunidad"], fb["activos_distribucion_generados"], fb["almacenamiento_oci"]
    B.fila_metricas("semana", [
        {"label": "Estado", "valor": fb["status"], "icono": "CheckCircle", "grad": "verde", "nota": "Respuesta del motor"},
        {"label": "Interacciones", "valor": r["total_interacciones_procesadas"], "icono": "Forum", "grad": "azul",
         "nota": "Procesadas en el lote"},
        {"label": "Sentimiento", "valor": r["sentimiento_predominante"], "icono": "Insights", "grad": "violeta",
         "nota": "Predominante"},
        {"label": "Almacenamiento", "valor": "OCI" if alm["bucket"] else "Local", "icono": "CloudUpload",
         "grad": "naranja", "nota": alm["status"]},
    ])
    st.markdown("**Temas principales:** " + " · ".join(escape(t) for t in r["temas_principales"]))

    bloques = []
    if act.get("post_linkedin"):
        p = act["post_linkedin"]
        bloques.append(("Post para LinkedIn", [("Título", p["titulo"]), ("Texto", p["copy"]),
                                                ("Canal recomendado", p["canal_recomendado"]),
                                                ("Potencial de engagement", p["potencial_engagement"])]))
    if act.get("destaque_newsletter_semanal"):
        n = act["destaque_newsletter_semanal"]
        bloques.append(("Destacado de la newsletter semanal", [("Sección", n["seccion"]), ("Titular", n["titular"]),
                                                               ("Resumen", n["resumen"])]))
    if act.get("sugerencia_contenido_faq"):
        f = act["sugerencia_contenido_faq"]
        estado = {"respuesta_con_faq_oficial": "Respondida con la FAQ oficial",
                  "derivado_a_mentoria": "Sin FAQ oficial: derivada a mentoría"}.get(f["status"], f["status"])
        bloques.append(("Sugerencia de contenido FAQ", [("Tema", f["tema"]), ("Origen", f["origen"]), ("Estado", estado)]))
    if act.get("caso_exito"):
        c = act["caso_exito"]
        bloques.append(("Caso de éxito", [("Título", c["titulo"]), ("Origen", c["origen"]),
                                          ("Borrador", c["borrador"]), ("Estado", c["status"])]))
    for i in range(0, len(bloques), 2):
        columnas = st.columns(2, gap="medium")
        for col, (titulo, filas) in zip(columnas, bloques[i:i + 2]):
            with col:
                _bloque(titulo, filas)

    for c in act.get("contenido_educativo", []):
        with st.container(border=True):
            respaldo = ("Con FAQ oficial: " + ", ".join(c["respaldo_faq_oficial"])) if c["status"] == "respuesta_con_faq_oficial" \
                else "Sin FAQ oficial: un mentor debe validarlo"
            st.markdown(f"**Contenido educativo · {escape(c['tema'])}** · {c['dudas']} duda(s) · {respaldo}")
            t1, t2, t3 = st.columns(3)
            with t1:
                if c.get("tutorial_rapido"):
                    html(f'<div class="cl-asset-meta">Tutorial rápido</div><div class="cl-quote"><b>{escape(c["tutorial_rapido"]["titulo"])}</b><br>{_texto_html(c["tutorial_rapido"]["contenido"])}</div>')
            with t2:
                if c.get("tip_semana"):
                    html(f'<div class="cl-asset-meta">Tip de la semana</div><div class="cl-quote">{_texto_html(c["tip_semana"])}</div>')
            with t3:
                if c.get("tema_documentacion"):
                    html(f'<div class="cl-asset-meta">Tema de documentación</div><div class="cl-quote"><b>{escape(c["tema_documentacion"]["titulo"])}</b><br>{_texto_html(c["tema_documentacion"]["propuesta"])}</div>')

    _bloque("Almacenamiento", [("Bucket", alm["bucket"] or "Carpeta local (sin OCI)"), ("Ruta del objeto", alm["ruta_objeto"]),
                               ("Estado", alm["status"])])
    st.download_button("Descargar en formato del briefing (JSON)",
                       data=json.dumps(fb, ensure_ascii=False, indent=2),
                       file_name=f"formato_briefing_{elegido.replace(' ', '_')}.json",
                       mime="application/json", key="semana_descarga")


def vista_base_conocimiento(estado: dict | None) -> None:
    """
    Muestra lo que hay en motor_educativo.db y como lo usa el motor.

    Sirve para comprobar que la base esta cargada, ver que FAQs citaron los
    borradores de la sesion, buscar en las FAQs con el mismo buscador del
    motor y convertir reseñas reales de la base en un lote.
    """
    if estado is None:
        cabecera("Base de conocimiento", "Lo que hay en la base del equipo de datos.")
        st.warning("El backend no responde: enciéndelo para consultar la base.")
        return
    try:
        base = armar_base(backend.resumen_base(), backend.faqs_base(), st.session_state.corridas)
    except backend.BackendNoDisponible as e:
        cabecera("Base de conocimiento", "Lo que hay en la base del equipo de datos.")
        st.error(str(e))
        return

    cabecera(
        "Base de conocimiento",
        "La base del equipo de datos: las FAQs oficiales con las que el motor responde "
        "las dudas de la comunidad y las reseñas reales de los cursos.",
        f'<b>{escape(base["archivo"])}</b> &nbsp;·&nbsp; cargada',
    )
    B.fila_metricas("base", [
        {"label": "FAQs oficiales", "valor": base["faqs_unicas"], "icono": "MenuBook", "grad": "azul",
         "nota": f"{base['filas_faq']} filas (algunas preguntas se repiten)"},
        {"label": "Reseñas reales", "valor": f"{base['resenas']:,}".replace(",", "."), "icono": "RateReview",
         "grad": "violeta", "nota": f"{base['resenas_distintas']:,} distintas · {base['desde'][:4]} a {base['hasta'][:4]}".replace(",", ".")},
        {"label": "Cursos", "valor": base["cursos"], "icono": "School", "grad": "verde",
         "nota": "Con reseñas de estudiantes"},
        {"label": "FAQs usadas en la sesión", "valor": base["faqs_citadas"], "icono": "FactCheck",
         "grad": "naranja", "nota": f"{base['citas_totales']} cita(s) en los borradores"},
    ])

    izq, der = st.columns(2, gap="large")
    with izq:
        B.barra_apilada_sentimiento(base["distribucion_sentimiento"],
                                    f"{base['resenas']} reseñas, según la etiqueta del equipo de datos")
    with der:
        B.panel_temas(base["cursos_top"], "Cursos con más reseñas", "reseñas")

    t_buscar, t_faqs, t_resenas, t_agregar = st.tabs(
        ["Buscar en las FAQs", f"FAQs oficiales ({base['faqs_unicas']})", "Reseñas reales", "Agregar FAQs"])

    with t_agregar:
        agregar_faqs()

    with t_buscar:
        st.caption("Escribe una duda como la escribiría alguien de la comunidad. Se usa el mismo "
                   "buscador que el motor usa para responder (también entiende español).")
        consulta = st.text_input("Duda", placeholder="¿Cómo evito el sobreajuste en mi modelo?",
                                 label_visibility="collapsed", key="base_consulta")
        if consulta.strip():
            try:
                resultados = resultados_busqueda(backend.buscar_faq(consulta, 5))
            except backend.BackendNoDisponible as e:
                st.error(str(e))
                resultados = None
            if resultados == []:
                st.info("Ninguna FAQ oficial se parece lo suficiente. En el motor, esta duda "
                        "quedaría marcada para que la responda un mentor.")
            for r in resultados or []:
                html(f'<div class="pv-src"><div class="pv-src-head"><span class="cl-id">{escape(r["id"])}</span>'
                     f'<span>{escape(r["curso"])} · puntaje {r["puntaje"]:.1f}</span></div>'
                     f'<div class="cl-quote"><b>{escape(r["pregunta"])}</b><br>{escape(r["respuesta"])}</div></div>')

    with t_faqs:
        st.caption("Primero aparecen las FAQs que citaron los borradores de esta sesión: el número "
                   "(por ejemplo faq-2067) es el mismo que ves en la pestaña «Fuente y FAQ» de la curaduría.")
        solo_citadas = st.checkbox("Ver solo las usadas en esta sesión", key="base_solo_citadas",
                                   disabled=not base["faqs_citadas"])
        filas = [f for f in base["faqs"] if f["citada_en"] or not solo_citadas]
        st.dataframe(filas, hide_index=True, width="stretch", height=420,
                     column_order=["id", "citada_en", "pregunta", "respuesta", "curso"],
                     column_config={"id": "FAQ",
                                    "citada_en": st.column_config.NumberColumn("Citas", width="small"),
                                    "pregunta": st.column_config.TextColumn("Pregunta", width="medium"),
                                    "respuesta": st.column_config.TextColumn("Respuesta", width="large"),
                                    "curso": "Curso"})

    with t_resenas:
        st.caption("Reseñas reales de estudiantes guardadas en la base (el texto se muestra sin datos "
                   "personales). Puedes enviarlas al motor como un lote más.")
        try:
            cursos = backend.resenas_base(limite=1)["courses"]
        except backend.BackendNoDisponible as e:
            st.error(str(e))
            return
        c1, c2, c3 = st.columns([2, 1.2, 1])
        curso = c1.selectbox("Curso", ["Todos los cursos"] + cursos, key="base_curso")
        sentimiento = c2.selectbox("Sentimiento", ["Todos", "Positivo", "Neutral", "Negativo"], key="base_sent")
        cantidad = c3.number_input("Cantidad", min_value=3, max_value=50, value=10, step=1, key="base_cant")
        try:
            respuesta = backend.resenas_base(None if curso == "Todos los cursos" else curso,
                                             None if sentimiento == "Todos" else sentimiento, int(cantidad))
        except backend.BackendNoDisponible as e:
            st.error(str(e))
            return
        filas = tabla_resenas(respuesta)
        if not filas:
            st.info("No hay reseñas con esos filtros.")
            return
        st.dataframe(filas, hide_index=True, width="stretch", height=360,
                     column_order=["autor", "fecha", "nota", "sentimiento", "curso", "texto"],
                     column_config={"texto": st.column_config.TextColumn("Texto", width="large")})
        costo = (" Con Gemini activo gasta 2 llamadas de la cuota diaria."
                 if estado["proveedor_llm"] == "gemini" else "")
        st.caption(f"Se enviarán estas {len(filas)} reseñas al motor, como si llegaran de la comunidad.{costo}")
        if st.button(f"Procesar estas {len(filas)} reseñas como lote", type="primary", key="base_procesar"):
            nombre = f"Base · {curso if curso != 'Todos los cursos' else 'varios cursos'} · {sentimiento.lower()}"
            with st.spinner("El motor está analizando las reseñas..."):
                if procesar(nombre, lote_desde_resenas(respuesta)):
                    st.info("Listo. Revisa los borradores en **Curaduría de activos**.")


def agregar_faqs() -> None:
    """
    Carga FAQs nuevas a la base desde un CSV o JSON, en dos pasos.

    1. Vista previa: el backend dice que agregaria, que ya existe y que filas
       tienen errores. No escribe nada.
    2. Confirmar: el backend guarda una copia de seguridad de la base y
       agrega solo las FAQs nuevas. Nunca toca las reseñas.
    """
    st.caption("Sube un CSV con las columnas **pregunta, respuesta, curso** (o un JSON con esos campos). "
               "Primero verás qué se agregaría; nada se escribe hasta que confirmes. Antes de escribir, "
               "el motor guarda una copia de seguridad de la base y nunca toca las reseñas.")
    st.download_button("Descargar plantilla CSV", data=ingesta.PLANTILLA_FAQS.encode("utf-8"),
                       file_name="plantilla_faqs.csv", mime="text/csv", key="faq_plantilla")
    ultimo = st.session_state.get("faq_ultimo_resultado")
    if ultimo:
        st.success(f"Se agregaron **{ultimo['agregadas']}** FAQ(s) a la base ({', '.join(ultimo['ids_nuevos'])}). "
                   f"Copia de seguridad: `{ultimo['respaldo']}`. El motor ya las usa para responder.")
    archivo = st.file_uploader("Archivo de FAQs", type=["csv", "json"], key="faq_subida")
    if archivo is None:
        return
    try:
        filas = ingesta.leer_faqs(archivo.name, archivo.getvalue())
        previa = resultado_importacion(backend.importar_faqs(filas, vista_previa=True))
    except ingesta.LoteInvalido as e:
        st.error(str(e))
        return
    except backend.BackendNoDisponible as e:
        st.error(str(e))
        return
    n = len(previa["a_agregar"])
    st.markdown(f"**Vista previa:** se agregarían **{n}** FAQ(s) · {len(previa['repetidas'])} ya existen en la base · "
                f"{len(previa['con_errores'])} fila(s) con errores.")
    if n:
        st.dataframe(previa["a_agregar"], hide_index=True, width="stretch",
                     column_config={"respuesta": st.column_config.TextColumn("respuesta", width="large")})
    if previa["repetidas"]:
        with st.expander(f"Ya existen en la base ({len(previa['repetidas'])}): no se agregan"):
            st.dataframe(previa["repetidas"], hide_index=True, width="stretch")
    if previa["con_errores"]:
        with st.expander(f"Filas con errores ({len(previa['con_errores'])})"):
            st.dataframe(previa["con_errores"], hide_index=True, width="stretch")
    if not n:
        st.info("No hay FAQs nuevas para agregar en este archivo.")
        return
    if st.button(f"Agregar {n} FAQ(s) a la base", type="primary", key="faq_confirmar"):
        try:
            hecho = resultado_importacion(backend.importar_faqs(filas, vista_previa=False))
        except backend.BackendNoDisponible as e:
            st.error(str(e))
            return
        st.session_state["faq_ultimo_resultado"] = hecho
        st.rerun()


def vista_config(datos: dict | None, estado: dict | None) -> None:
    """Estado del motor, donde se guardan los paquetes y que secretos estan configurados."""
    cabecera(
        "Configuración y estado",
        "Estado del motor, del almacenamiento y de las credenciales del proyecto.",
    )

    ubicaciones = (datos or {}).get("almacenamiento", []) + [ubicacion(g) for g in st.session_state.guardados]
    B.tarjeta_almacenamiento(estado, ubicaciones)
    B.tarjeta_origen(backend.url_backend(), estado)

    try:
        from core.secretos import diagnostico
        B.tarjeta_secretos(diagnostico())
    except Exception as e:
        st.error(f"No se pudo leer el diagnóstico de secretos: {e}")

    if datos:
        with st.expander("Ver datos de la sesión (JSON)"):
            st.json(datos)


# ---------------------------------------------------------------------------
def barra_lateral() -> str:
    """Menu de secciones y datos de la sesion. Devuelve la seccion elegida."""
    with st.sidebar:
        html(
            '<div class="cl-marca">'
            '  <div class="logo">CL</div>'
            '  <div class="txt"><b>CommunityLab</b>'
            '  <span>Hackathon ONE G10 · Equipo 25</span></div>'
            '</div>'
            '<div class="cl-nav-label">Panel</div>'
        )
        seccion = st.radio("Sección", T.SECCIONES, label_visibility="collapsed", key="seccion")
        html(
            '<div class="cl-side-pie">'
            'Motor de FAQ dinámico<br>y contenido educativo'
            '</div>'
        )
    return seccion


def banner(estado: dict | None) -> None:
    """Aviso arriba de la pagina si el backend no responde o corre en modo local."""
    if estado is None:
        html('<div class="cl-banner"><span style="font-size:16px;line-height:1.2">⚠</span>'
             '<span><b>Backend sin conexión.</b> Enciende el backend para procesar lotes, '
             'o carga respuestas guardadas desde <b>Procesar lote</b>.</span></div>')
    elif estado["proveedor_llm"] == "mock":
        html('<div class="cl-banner"><span style="font-size:16px;line-height:1.2">ℹ</span>'
             '<span><b>Modo local.</b> El motor usa reglas locales en lugar de Gemini: los '
             'borradores reutilizan los mensajes y la FAQ oficial tal cual. Para redacción con '
             'IA, configura <b>LLM_PROVIDER=gemini</b> en el .env del backend.</span></div>')


def acceso_permitido() -> bool:
    """
    Pide la contrasena del panel cuando esta publicado en internet.

    Si PANEL_PASSWORD no esta configurada (uso local), deja pasar sin pedir
    nada. Si esta, muestra un formulario y solo deja pasar con la contrasena
    correcta; la comparacion no revela por tiempo cuantas letras coinciden.
    El acceso dura lo que dure la pestana del navegador.
    """
    clave = obtener_secreto("PANEL_PASSWORD", obligatorio=False)
    if not clave or st.session_state.get("_acceso_panel"):
        return True
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        html('<div class="cl-head"><div><h1>CommunityLab</h1><p>Panel de curaduría · acceso del equipo</p></div></div>')
        with st.form("acceso_panel"):
            intento = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", type="primary", width="stretch"):
                if hmac.compare_digest(intento.encode("utf-8"), clave.encode("utf-8")):
                    st.session_state["_acceso_panel"] = True
                    st.rerun()
                st.error("Contraseña incorrecta.")
    return False


def main() -> None:
    """Punto de entrada del panel: configura la pagina y muestra la seccion elegida."""
    st.set_page_config(
        page_title="CommunityLab · Panel de curaduría",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    html(T.CSS)
    if not acceso_permitido():
        return
    init_estado()

    estado = estado_motor(backend.estado())
    seccion = barra_lateral()
    banner(estado)

    datos = armar_vista(st.session_state.corridas) if st.session_state.corridas else None

    if seccion == "Procesar lote":
        vista_procesar(estado)
    elif seccion == "Base de conocimiento":
        vista_base_conocimiento(estado)
    elif seccion == "Motor de FAQ":
        vista_motor_faq(datos, estado)
    elif seccion == "Esta semana":
        vista_semana()
    elif seccion == "Configuración":
        vista_config(datos, estado)
    elif datos is None:
        sin_datos()
    elif seccion == "Resumen":
        vista_resumen(datos)
    elif seccion == "Mensajes procesados":
        vista_ingesta(datos)
    else:
        vista_curaduria(datos)
    guardar_sesion()


if __name__ == "__main__":
    main()
