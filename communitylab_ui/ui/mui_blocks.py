"""
Bloques visuales construidos con streamlit-mui-elements (Material UI).

QUE ES ESTO
-----------
Aqui vive TODO el dibujo de la interfaz. La logica (cargar datos, aprobar,
rechazar, filtrar) vive en ui/app.py y no se toca desde aqui.

LIMITACIONES CONOCIDAS DEL PAQUETE (verificadas en pruebas)
-----------------------------------------------------------
1. Los componentes de transicion de MUI (Fade, Grow, Slide) dejan el bloque
   en blanco. Por eso las animaciones se escriben como CSS dentro de `sx`,
   que si funciona.

2. mui.GlobalStyles rompe el componente ("Component Error"). Para forzar el
   fondo claro dentro del iframe se usa un telon de fondo con position
   fixed (ver _lienzo).

3. El tema por defecto no es el MUI estandar: color="primary" sale rojo y
   boxShadow via sx no se aplica. Por eso aqui se declaran los colores y
   las sombras de forma explicita.

4. Cada bloque `elements()` se dibuja dentro de un iframe. Los widgets
   interactivos de Streamlit (botones, campos) no pueden ir dentro, asi que
   se colocan justo debajo desde app.py.
"""

from streamlit_mui_elements import elements, mui

from ui import theme as T

# --- Animaciones (CSS, porque Fade/Grow no funcionan en este paquete) ------
ENTRADA = {
    "animation": "clEntrada .45s cubic-bezier(.2,.7,.3,1) both",
    "@keyframes clEntrada": {
        "from": {"opacity": 0, "transform": "translateY(12px)"},
        "to": {"opacity": 1, "transform": "none"},
    },
}

SOMBRA = "0 1px 3px rgba(0,0,0,.09), 0 1px 2px rgba(0,0,0,.05)"
SOMBRA_HOVER = "0 10px 26px rgba(0,0,0,.12), 0 3px 8px rgba(0,0,0,.07)"


def _lienzo():
    """
    Fondo claro que cubre todo el iframe.

    Cada bloque `elements()` es un iframe aparte. Si Streamlit resuelve tema
    oscuro (sistema en modo oscuro y sin .streamlit/config.toml), MUI pinta
    el fondo del iframe en negro y se ven bandas oscuras detras de las
    tarjetas. Este telon lo evita pase lo que pase.
    """
    mui.Box(sx={
        "position": "fixed", "top": 0, "left": 0, "right": 0, "bottom": 0,
        "backgroundColor": T.BACKGROUND, "zIndex": -1,
    })
    return mui.Box(sx={
        "backgroundColor": T.BACKGROUND,
        "color": T.INK,
        "width": "100%",
        "minHeight": "100%",
        "p": 0, "m": 0,
    })


def _tarjeta_sx(delay: float = 0.0, hover: bool = True, p: float = 2.5) -> dict:
    sx = {
        "p": p,
        "borderRadius": "14px",
        "backgroundColor": T.SURFACE,
        "border": f"1px solid {T.DIVIDER}",
        "boxShadow": SOMBRA,
        "transition": "box-shadow .22s ease, transform .22s ease",
        **ENTRADA,
        "animationDelay": f"{delay:.2f}s",
    }
    if hover:
        sx["&:hover"] = {"boxShadow": SOMBRA_HOVER, "transform": "translateY(-3px)"}
    return sx


def _chip(label: str, color_texto: str, color_fondo: str):
    mui.Chip(label=label, size="small", sx={
        "backgroundColor": color_fondo, "color": color_texto,
        "fontWeight": 500, "fontSize": "11.5px", "height": "24px",
        "fontFamily": "Roboto, sans-serif",
    })


def _chip_outline(label: str):
    mui.Chip(label=label, size="small", variant="outlined", sx={
        "borderColor": T.DIVIDER, "color": T.INK_SECONDARY,
        "fontSize": "11.5px", "height": "24px",
        "fontFamily": "Roboto, sans-serif",
    })


def _cuadro_icono(nombre_icono: str, gradiente: str, tam: int = 52):
    """Cuadro redondeado con degradado y un icono de Material dentro."""
    ini, fin, sombra = T.GRADIENTES[gradiente]
    with mui.Box(sx={
        "width": tam, "height": tam, "borderRadius": "13px", "flexShrink": 0,
        "background": f"linear-gradient(135deg, {ini}, {fin})",
        "boxShadow": f"0 7px 16px {sombra}",
        "display": "flex", "alignItems": "center", "justifyContent": "center",
    }):
        getattr(mui.icon, nombre_icono)(
            sx={"color": "#fff", "fontSize": round(tam * 0.54)})


def _cabecera_tarjeta(titulo: str, sub: str, icono: str, grad: str):
    with mui.Stack(direction="row", spacing=1.6, alignItems="center", sx={"mb": 2}):
        _cuadro_icono(icono, grad, tam=40)
        with mui.Box():
            mui.Typography(titulo, variant="h6",
                           sx={"color": T.INK, "fontSize": "15.5px",
                               "fontWeight": 500, "lineHeight": 1.3})
            mui.Typography(sub, variant="body2",
                           sx={"color": T.INK_MUTED, "fontSize": "12px"})


def _barra(etiqueta: str, valor_txt: str, fraccion: float, color: str,
           punto: bool = False, delay: float = 0.0):
    with mui.Box(sx={"mb": 1.6}):
        with mui.Stack(direction="row", justifyContent="space-between",
                       alignItems="baseline", sx={"mb": .6}):
            with mui.Stack(direction="row", alignItems="center", spacing=1):
                if punto:
                    mui.Box(sx={"width": "9px", "height": "9px",
                                "borderRadius": "50%", "backgroundColor": color})
                mui.Typography(etiqueta, variant="body2",
                               sx={"color": T.INK, "fontSize": "13px"})
            mui.Typography(valor_txt, variant="caption",
                           sx={"color": T.INK_SECONDARY, "fontSize": "12.5px"})
        mui.LinearProgress(
            variant="determinate", value=max(0.0, min(1.0, fraccion)) * 100,
            sx={
                "height": "8px", "borderRadius": "4px",
                "backgroundColor": "#EDEFF2",
                "& .MuiLinearProgress-bar": {
                    "backgroundColor": color, "borderRadius": "4px",
                },
                **ENTRADA, "animationDelay": f"{delay:.2f}s",
            })


# ===========================================================================
# BLOQUES PUBLICOS
# ===========================================================================
def fila_metricas(clave: str, items: list) -> None:
    """items = [{"label":…, "valor":…, "icono":…, "grad":…, "nota":…}, …]"""
    with elements(f"met_{clave}"):
        with _lienzo():
            with mui.Stack(direction="row", spacing=2,
                           sx={"flexWrap": "wrap", "gap": 2}):
                for i, it in enumerate(items):
                    with mui.Card(sx={**_tarjeta_sx(delay=i * .08, p=2.2),
                                      "flex": "1 1 200px", "minWidth": "190px"}):
                        with mui.Stack(direction="row", spacing=2, alignItems="center"):
                            _cuadro_icono(it["icono"], it["grad"])
                            with mui.Box(sx={"minWidth": 0}):
                                mui.Typography(
                                    it["label"].upper(), variant="overline",
                                    sx={"color": T.INK_MUTED, "fontSize": "10.5px",
                                        "fontWeight": 500, "letterSpacing": ".9px",
                                        "lineHeight": 1.4, "display": "block"})
                                mui.Typography(
                                    str(it["valor"]), variant="h4",
                                    sx={"color": T.INK, "fontWeight": 500,
                                        "lineHeight": 1.15, "fontSize": "30px"})
                        if it.get("nota"):
                            mui.Typography(it["nota"], variant="body2",
                                           sx={"color": T.INK_MUTED,
                                               "fontSize": "11.5px", "mt": 1.3})


def barra_apilada_sentimiento(distribucion: dict) -> None:
    """
    Una sola barra con los cuatro segmentos, mas leyenda debajo.

    El sentimiento va de un polo al otro, asi que se usa azul (positivo) ->
    gris (neutro) -> rojo (negativo). Cada segmento lleva su etiqueta en la
    leyenda: el color nunca es el unico portador del dato.
    """
    total = sum(distribucion.values()) or 1
    with elements("sent_stack"):
        with _lienzo():
            with mui.Card(sx=_tarjeta_sx()):
                _cabecera_tarjeta("Sentimiento de la comunidad",
                                  f"{total} interacciones clasificadas",
                                  "Insights", "azul")

                with mui.Stack(direction="row", sx={
                    "height": "26px", "borderRadius": "8px", "overflow": "hidden",
                    "gap": "2px", "mb": 2.2,
                    **ENTRADA, "animationDelay": ".15s",
                }):
                    for clave, valor in distribucion.items():
                        pct = valor / total * 100
                        if pct <= 0:
                            continue
                        mui.Box(sx={
                            "width": f"{pct}%",
                            "backgroundColor": T.SENTIMIENTO.get(clave, T.INK_MUTED),
                        })

                with mui.Stack(direction="row", sx={"flexWrap": "wrap", "gap": 2.2}):
                    for clave, valor in distribucion.items():
                        with mui.Stack(direction="row", alignItems="center", spacing=.9):
                            mui.Box(sx={
                                "width": "10px", "height": "10px",
                                "borderRadius": "3px",
                                "backgroundColor": T.SENTIMIENTO.get(clave, T.INK_MUTED),
                            })
                            mui.Typography(
                                f"{clave.replace('_', ' ').capitalize()} · {valor}",
                                variant="body2",
                                sx={"color": T.INK_SECONDARY, "fontSize": "12.5px"})


def panel_temas(temas: list) -> None:
    with elements("panel_temas"):
        with _lienzo():
            with mui.Card(sx=_tarjeta_sx()):
                _cabecera_tarjeta("Temas principales",
                                  "Menciones en el periodo", "Tag", "violeta")
                maximo = max((t["menciones"] for t in temas), default=1)
                for i, t in enumerate(temas):
                    _barra(t["tema"], f"{t['menciones']} menciones",
                           t["menciones"] / maximo, T.PRIMARY, delay=.1 + i * .08)


def tabla_grupos(grupos: list) -> None:
    """Dudas recurrentes en tabla, al estilo de los paneles de administracion."""
    filas = [{
        "id": i + 1,
        "tema": g["tema"],
        "preguntas": g["cantidad_preguntas"],
        "personas": g["autores_distintos"],
        "canales": ", ".join(g["canales"]),
        "relevancia": round(g["score_relevancia"], 2),
        "estado": "Recurrente" if g["es_recurrente"] else "No recurrente",
    } for i, g in enumerate(grupos)]

    with elements("tabla_grupos"):
        with _lienzo():
            with mui.Card(sx={**_tarjeta_sx(hover=False, p=0),
                              "overflow": "hidden"}):
                with mui.Box(sx={"p": 2.2,
                                 "borderBottom": f"1px solid {T.DIVIDER}"}):
                    _cabecera_tarjeta(
                        "Dudas recurrentes detectadas",
                        "Se considera recurrente a partir de 3 preguntas de "
                        "autores diferentes",
                        "QuestionAnswer", "naranja")
                mui.DataGrid(
                    columns=[
                        {"field": "tema", "headerName": "Tema", "flex": 2,
                         "minWidth": 230},
                        {"field": "preguntas", "headerName": "Preguntas", "width": 105},
                        {"field": "personas", "headerName": "Personas", "width": 100},
                        {"field": "canales", "headerName": "Canales", "flex": 1,
                         "minWidth": 165},
                        {"field": "relevancia", "headerName": "Relevancia",
                         "width": 110},
                        {"field": "estado", "headerName": "Estado", "width": 135},
                    ],
                    rows=filas,
                    density="comfortable",
                    hideFooter=True,
                    disableColumnMenu=True,
                    sx={
                        "height": 60 + 54 * max(len(filas), 1),
                        "border": "none",
                        "fontFamily": "Roboto, sans-serif",
                        "& .MuiDataGrid-columnHeaders": {
                            "backgroundColor": "#F7F9FB",
                            "borderBottom": f"1px solid {T.DIVIDER}",
                        },
                        "& .MuiDataGrid-columnHeaderTitle": {
                            "fontWeight": 500, "fontSize": "11.5px",
                            "color": T.INK_SECONDARY, "letterSpacing": ".5px",
                            "textTransform": "uppercase",
                        },
                        "& .MuiDataGrid-cell": {
                            "fontSize": "13px", "color": T.INK,
                            "borderBottom": f"1px solid {T.DIVIDER}",
                        },
                        "& .MuiDataGrid-row:hover": {"backgroundColor": "#F5F9FF"},
                    },
                )


def lista_mensajes(mensajes: list) -> None:
    """Todos los mensajes en un solo bloque, para no abrir un iframe por cada uno."""
    with elements("msgs"):
        with _lienzo():
            with mui.Stack(spacing=2):
                for i, m in enumerate(mensajes):
                    sin_activo = (m["decision"].startswith("descartado")
                                  or m["decision"].startswith("no_recurrente"))
                    color_sent = T.SENTIMIENTO.get(m["sentimiento_detectado"],
                                                   T.INK_MUTED)

                    with mui.Card(sx=_tarjeta_sx(delay=min(i, 8) * .06, p=2.2)):
                        with mui.Stack(direction="row",
                                       justifyContent="space-between",
                                       alignItems="center", spacing=1.5,
                                       sx={"flexWrap": "wrap", "mb": 1.2}):
                            with mui.Stack(direction="row", alignItems="center",
                                           spacing=1.2, sx={"flexWrap": "wrap"}):
                                mui.Typography(
                                    m["id"], variant="caption",
                                    sx={"fontFamily": "'Roboto Mono', monospace",
                                        "fontSize": "11.5px",
                                        "backgroundColor": "#F1F3F4",
                                        "color": T.INK_SECONDARY, "px": 1, "py": .3,
                                        "borderRadius": "4px"})
                                mui.Typography(
                                    f"{m['autor']} · {m['canal']} · "
                                    f"{m['timestamp'][:10]} · "
                                    f"{m['reacciones']} reacciones",
                                    variant="body2",
                                    sx={"color": T.INK_SECONDARY,
                                        "fontSize": "12px"})
                            with mui.Stack(direction="row", alignItems="center",
                                           spacing=1):
                                mui.Typography("Relevancia", variant="body2",
                                               sx={"color": T.INK_MUTED,
                                                   "fontSize": "11.5px"})
                                mui.Chip(
                                    label=f"{m['score_relevancia']:.2f}",
                                    size="small",
                                    sx={"backgroundColor": "#EAF2FD",
                                        "color": T.PRIMARY_DARK, "fontWeight": 500,
                                        "fontSize": "11.5px", "height": "22px",
                                        "fontFamily": "Roboto, sans-serif"})

                        mui.Typography(
                            m["texto"], variant="body1",
                            sx={"borderLeft": f"3px solid {T.DIVIDER}", "pl": 1.8,
                                "py": .3, "mb": 1.5, "color": T.INK,
                                "fontSize": "14.5px", "lineHeight": 1.6})

                        mui.Divider(sx={"mb": 1.2, "borderColor": T.DIVIDER})

                        with mui.Stack(direction="row", spacing=3,
                                       alignItems="center",
                                       sx={"flexWrap": "wrap", "gap": 1.5}):
                            with mui.Stack(direction="row", alignItems="center",
                                           spacing=.8):
                                mui.Box(sx={"width": "9px", "height": "9px",
                                            "borderRadius": "50%",
                                            "backgroundColor": color_sent})
                                mui.Typography(
                                    f"Sentimiento {m['sentimiento_detectado']}",
                                    variant="body2",
                                    sx={"color": T.INK_SECONDARY,
                                        "fontSize": "12.5px"})
                            mui.Typography(f"Tema {m['tema_detectado']}",
                                           variant="body2",
                                           sx={"color": T.INK_SECONDARY,
                                               "fontSize": "12.5px"})
                            mui.Typography(f"Tipo {m['tipo_detectado']}",
                                           variant="body2",
                                           sx={"color": T.INK_SECONDARY,
                                               "fontSize": "12.5px"})
                            mui.Typography(
                                ("Descartado · " if sin_activo else "") + m["decision"],
                                variant="body2",
                                sx={"color": T.INK_MUTED, "fontSize": "12.5px"})


def cabecera_activo(act: dict, estado: str, i: int) -> None:
    """Cabecera MUI del activo. Los botones van despues, desde app.py."""
    etiqueta_tipo, c_txt, c_bg = T.TIPO_ACTIVO.get(
        act["tipo_activo"], (act["tipo_activo"], T.INK_SECONDARY, "#EDEFF2"))
    e_txt, e_bg = T.ESTADO[estado]
    icono = {"tip_faq": "MenuBook", "post_linkedin": "Campaign",
             "destacado_newsletter": "Email"}.get(act["tipo_activo"], "Article")
    grad = {"tip_faq": "azul", "post_linkedin": "violeta",
            "destacado_newsletter": "naranja"}.get(act["tipo_activo"], "azul")

    with elements(f"act_{act['activo_id']}"):
        with _lienzo():
            with mui.Box(sx={**ENTRADA,
                             "animationDelay": f"{min(i, 6) * .07:.2f}s"}):
                with mui.Stack(direction="row", spacing=2, alignItems="flex-start"):
                    _cuadro_icono(icono, grad, tam=44)
                    with mui.Box(sx={"flex": 1, "minWidth": 0}):
                        with mui.Stack(direction="row",
                                       justifyContent="space-between",
                                       alignItems="flex-start", spacing=2,
                                       sx={"flexWrap": "wrap", "mb": 1}):
                            mui.Typography(act["titulo"], variant="h6",
                                           sx={"color": T.INK, "fontSize": "16px",
                                               "fontWeight": 500,
                                               "flex": "1 1 320px",
                                               "lineHeight": 1.45})
                            _chip(estado.upper(), e_txt, e_bg)
                        with mui.Stack(direction="row", spacing=1,
                                       sx={"flexWrap": "wrap", "gap": .8}):
                            _chip(etiqueta_tipo, c_txt, c_bg)
                            _chip_outline(act["canal_sugerido"])
                            _chip_outline(
                                f"Relevancia {act['score_relevancia']:.2f}")


def tarjeta_almacenamiento(oci: dict) -> None:
    simulado = oci["status"] == "simulado"
    with elements("oci"):
        with _lienzo():
            with mui.Card(sx=_tarjeta_sx()):
                with mui.Stack(direction="row", justifyContent="space-between",
                               alignItems="flex-start", spacing=2,
                               sx={"flexWrap": "wrap"}):
                    with mui.Box(sx={"flex": 1, "minWidth": 260}):
                        _cabecera_tarjeta(
                            "OCI Object Storage",
                            "Persistencia de los paquetes generados",
                            "CloudUpload", "azul")
                    if simulado:
                        _chip("SIMULADO", "#8A6D00", "#FFF4D6")
                    else:
                        _chip("ACTIVO", "#0A6B0A", "#E3F5E3")

                if simulado:
                    mui.Typography(
                        "Todavía no se sube nada real. Ésta es la estructura que "
                        "el backend deberá devolver.",
                        variant="body2",
                        sx={"color": T.INK_SECONDARY, "fontSize": "13px",
                            "mb": 1.6})

                texto = (f"bucket      : {oci['bucket']}\n"
                         f"region      : {oci['region']}\n"
                         f"ruta objeto : {oci['ruta_objeto']}\n"
                         f"tamaño      : {oci['tamano_bytes']} bytes\n"
                         f"guardado en : {oci['guardado_en']}")
                mui.Typography(
                    texto, component="pre",
                    sx={"fontFamily": "'Roboto Mono', monospace",
                        "fontSize": "12.5px", "backgroundColor": "#F6F8FA",
                        "border": f"1px solid {T.DIVIDER}", "borderRadius": "10px",
                        "p": 1.8, "m": 0, "lineHeight": 1.8, "color": T.INK,
                        "whiteSpace": "pre-wrap", "wordBreak": "break-all"})


def tarjeta_secretos(filas: list) -> None:
    with elements("secretos"):
        with _lienzo():
            with mui.Card(sx=_tarjeta_sx()):
                _cabecera_tarjeta(
                    "Secretos",
                    "Nunca se muestra el valor, sólo si está configurado",
                    "VpnKey", "violeta")

                for i, f in enumerate(filas):
                    ok = f["estado"] == "configurado"
                    color = (T.SENTIMIENTO["muy_positivo"] if ok
                             else T.SENTIMIENTO["negativo"])
                    with mui.Stack(direction="row", alignItems="center",
                                   spacing=1.4,
                                   sx={"py": 1.2,
                                       "borderBottom": f"1px solid {T.DIVIDER}",
                                       "flexWrap": "wrap",
                                       **ENTRADA,
                                       "animationDelay": f"{i * .07:.2f}s"}):
                        getattr(mui.icon, "CheckCircle" if ok else "Cancel")(
                            sx={"color": color, "fontSize": 19})
                        mui.Typography(f["secreto"], variant="body2",
                                       sx={"fontFamily": "'Roboto Mono', monospace",
                                           "fontSize": "12px",
                                           "backgroundColor": "#F1F3F4",
                                           "px": 1, "py": .3, "borderRadius": "4px",
                                           "color": T.INK})
                        mui.Typography("Configurado" if ok else "Falta",
                                       variant="body2",
                                       sx={"color": color, "fontSize": "12px",
                                           "fontWeight": 500})
                        mui.Typography(f["descripcion"], variant="body2",
                                       sx={"color": T.INK_SECONDARY,
                                           "fontSize": "12.5px"})

                if filas:
                    mui.Typography(f"Fuente activa: {filas[0]['fuente']}",
                                   variant="body2",
                                   sx={"color": T.INK_SECONDARY,
                                       "fontSize": "13px", "mt": 1.8})
                mui.Typography(
                    "Sprint 1: los secretos se leen del archivo .env local.  ·  "
                    "Sprint 2: se migran a OCI Vault cambiando "
                    "FUENTE_SECRETOS=vault. Ningún otro archivo del proyecto "
                    "cambia.",
                    variant="body2",
                    sx={"color": T.INK_SECONDARY, "fontSize": "12.5px", "mt": .8,
                        "lineHeight": 1.7})


def tarjeta_origen(ruta: str) -> None:
    with elements("origen"):
        with _lienzo():
            with mui.Card(sx=_tarjeta_sx()):
                _cabecera_tarjeta("Origen de los datos",
                                  "De dónde se alimenta este panel hoy",
                                  "DataObject", "naranja")
                mui.Typography(
                    f"Leyendo de {ruta} (datos de ejemplo). Cuando el backend "
                    f"esté listo, se cambia únicamente la función "
                    f"cargar_resultados() en ui/app.py.",
                    variant="body2",
                    sx={"color": T.INK_SECONDARY, "fontSize": "13px",
                        "lineHeight": 1.7})
