"""
Tema visual del panel de CommunityLab.

QUE ES ESTO
-----------
Todo el CSS y los colores viven aqui, separados de la logica y del dibujo.
Si el equipo quiere cambiar la paleta, se toca este archivo y nada mas.

CRITERIO DE DISENO
------------------
1. La "piel" sigue Material Design en su forma de panel de administracion:
   barra lateral oscura, tarjetas con elevacion, cuadros de icono en
   degradado, tipografia Roboto y animaciones de entrada.

2. Los colores que CODIFICAN DATOS (sentimiento, relevancia) no se eligen
   por gusto. Usan una escala divergente azul/rojo con gris neutro al
   centro, que sigue siendo legible para personas con daltonismo.
   Verde/rojo, que es lo habitual para sentimiento, es justo la peor
   pareja posible en ese aspecto. Ademas ningun color viaja solo: cada
   valor lleva siempre su etiqueta de texto al lado.

NOTA SOBRE SELECTORES
---------------------
Streamlit cambia sus nombres internos entre versiones. Los selectores de
aqui estan verificados contra Streamlit 1.64 mirando el DOM real. Si un
dia algo deja de pintarse, lo primero que hay que revisar es si el
data-testid cambio.
"""

# --- Piel Material -----------------------------------------------------
PRIMARY = "#1565C0"
PRIMARY_LIGHT = "#42A5F5"
PRIMARY_DARK = "#0D47A1"
SURFACE = "#FFFFFF"
BACKGROUND = "#F4F6F8"
INK = "#1A1A1A"
INK_SECONDARY = "#5F6368"
INK_MUTED = "#80868B"
DIVIDER = "#E3E6EA"

# Barra lateral
SIDE_BG = "#161C24"
SIDE_BG_2 = "#212B36"
SIDE_INK = "#C4CDD5"
SIDE_INK_ACTIVE = "#FFFFFF"

# Degradados de los cuadros de icono: (inicio, fin, sombra)
GRADIENTES = {
    "azul":    ("#1565C0", "#42A5F5", "rgba(21,101,192,.34)"),
    "naranja": ("#B35309", "#F0883E", "rgba(179,83,9,.30)"),
    "verde":   ("#0A6B0A", "#4CAF50", "rgba(10,107,10,.28)"),
    "violeta": ("#4A3AA7", "#8E7CF0", "rgba(74,58,167,.30)"),
    "rojo":    ("#A62C2C", "#EF5350", "rgba(166,44,44,.28)"),
}

# --- Colores que codifican datos --------------------------------------
SENTIMIENTO = {
    "muy_positivo": "#184F95",
    "positivo":     "#3987E5",
    "neutro":       "#80868B",
    "negativo":     "#D03B3B",
}

ESTADO = {
    "pendiente": ("#8A6D00", "#FFF4D6"),
    "aprobado":  ("#0A6B0A", "#E3F5E3"),
    "rechazado": ("#A62C2C", "#FBE5E5"),
}

TIPO_ACTIVO = {
    "tip_faq":              ("Tip / FAQ",     "#0D47A1", "#E3EDFB"),
    "post_linkedin":        ("Post LinkedIn", "#4A3AA7", "#EAE7F8"),
    "destacado_newsletter": ("Newsletter",    "#8A4B00", "#FBEEE0"),
}

SECCIONES = ["Resumen", "Mensajes procesados", "Curaduría de activos", "Configuración"]


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Roboto+Mono:wght@400;500&display=swap');

/* Tipografia base. Ojo: NO usar selectores amplios tipo [class*="st-"],
   porque pisan la fuente de los iconos de Streamlit y los rompe. */
html, body, .stApp, .stMarkdown, p, span, div, label,
button, input, textarea, select {{
    font-family: 'Roboto', -apple-system, 'Segoe UI', sans-serif;
}}

/* Restaurar la fuente de iconos de Streamlit por si algo la pisa. */
span[data-testid="stIconMaterial"],
.material-symbols-rounded,
span[class*="material-symbols"] {{
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
    font-feature-settings: 'liga' !important;
}}

/* ---------- MODO OSCURO: forzar tema claro ----------
   Si el sistema esta en modo oscuro y .streamlit/config.toml no se aplica,
   Streamlit pinta el texto en blanco sobre nuestros fondos claros y queda
   invisible. Estas reglas fijan el tema claro pase lo que pase.          */
:root, .stApp, body {{ color-scheme: light !important; }}
.stApp {{ background: {BACKGROUND} !important; color: {INK} !important; }}

.block-container {{
    padding-top: 1.6rem;
    padding-bottom: 4rem;
    max-width: 1280px;
}}

/* ===================== BARRA LATERAL ===================== */
section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {SIDE_BG} 0%, {SIDE_BG_2} 100%) !important;
    border-right: none;
    width: 268px !important;
}}
section[data-testid="stSidebar"] > div {{ padding-top: .8rem; }}

.cl-marca {{
    display: flex; align-items: center; gap: 12px;
    padding: 4px 4px 18px 4px;
    border-bottom: 1px solid rgba(255,255,255,.08);
    margin-bottom: 16px;
}}
.cl-marca .logo {{
    width: 42px; height: 42px; border-radius: 12px;
    background: linear-gradient(135deg, {PRIMARY_DARK}, {PRIMARY_LIGHT});
    box-shadow: 0 6px 16px rgba(21,101,192,.45);
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-size: 18px; font-weight: 700; flex-shrink: 0;
}}
.cl-marca .txt b {{
    color: #fff; font-size: 15.5px; font-weight: 500;
    display: block; line-height: 1.25;
}}
.cl-marca .txt span {{
    color: rgba(255,255,255,.52); font-size: 11.5px; font-weight: 300;
}}

.cl-nav-label {{
    color: rgba(255,255,255,.38); font-size: 10.5px; font-weight: 500;
    letter-spacing: 1.1px; text-transform: uppercase;
    padding: 0 6px 6px 6px;
}}

/* Opciones de navegacion (st.radio en la barra lateral) */
section[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 4px; }}
section[data-testid="stSidebar"] [role="radiogroup"] label {{
    padding: 10px 14px;
    border-radius: 10px;
    transition: background .16s ease, box-shadow .16s ease;
    cursor: pointer;
    margin: 0;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label p,
section[data-testid="stSidebar"] [role="radiogroup"] label div {{
    color: {SIDE_INK} !important;
    font-size: 13.5px !important;
    font-weight: 400 !important;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
    background: rgba(255,255,255,.06);
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover p {{
    color: #fff !important;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
    background: linear-gradient(90deg, rgba(21,101,192,.36), rgba(21,101,192,.10));
    box-shadow: inset 3px 0 0 {PRIMARY_LIGHT};
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {{
    color: {SIDE_INK_ACTIVE} !important;
    font-weight: 500 !important;
}}
/* El circulo del radio se convierte en un punto indicador discreto.
   Estructura real en Streamlit 1.64:
     label[data-testid=stRadioOption] > span(input oculto) + div > div(circulo) + div(texto)
   Por eso NO sirve label > div:first-child. */
section[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {{
    width: 7px !important;
    height: 7px !important;
    min-width: 7px !important;
    background-color: rgba(255,255,255,.22) !important;
    border: none !important;
    box-shadow: none !important;
    margin-right: 4px;
    transition: background-color .16s ease;
}}
section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {{
    background-color: {PRIMARY_LIGHT} !important;
    box-shadow: 0 0 0 3px rgba(66,165,245,.22) !important;
}}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {{ display: none; }}

.cl-side-pie {{
    color: rgba(255,255,255,.34); font-size: 11px; line-height: 1.7;
    padding: 16px 6px 6px 6px; border-top: 1px solid rgba(255,255,255,.08);
    margin-top: 16px;
}}

/* ===================== CABECERA DE PAGINA ===================== */
.cl-head {{
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: 16px; flex-wrap: wrap; margin-bottom: 22px;
    animation: clUp .4s ease both;
}}
.cl-head h1 {{
    font-size: 25px; font-weight: 500; color: {INK};
    margin: 0 0 4px 0; letter-spacing: .1px;
}}
.cl-head p {{
    margin: 0; font-size: 13.5px; color: {INK_SECONDARY}; font-weight: 300;
    line-height: 1.6; max-width: 780px;
}}
.cl-pill {{
    background: {SURFACE}; border: 1px solid {DIVIDER}; border-radius: 22px;
    padding: 7px 16px; font-size: 12.5px; color: {INK_SECONDARY};
    box-shadow: 0 1px 3px rgba(0,0,0,.06); white-space: nowrap;
}}
.cl-pill b {{ color: {INK}; font-weight: 500; }}

@keyframes clUp {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to   {{ opacity: 1; transform: none; }}
}}

/* ---------- Aviso de version de prueba ---------- */
.cl-banner {{
    display: flex; gap: 12px; align-items: flex-start;
    background: #FFF8E1;
    border-left: 4px solid #F5A623;
    border-radius: 8px;
    padding: 13px 16px;
    margin-bottom: 22px;
    font-size: 13px; color: #5C4600; line-height: 1.55;
    animation: clUp .4s ease both;
}}
.cl-banner b {{ color: #3E2F00; font-weight: 500; }}

/* ---------- Titulos y textos sueltos ---------- */
.cl-h2 {{
    font-size: 17px; font-weight: 500; color: {INK};
    margin: 8px 0 2px 0; letter-spacing: .1px;
}}
.cl-sub {{
    font-size: 13px; color: {INK_SECONDARY};
    margin: 0 0 16px 0; line-height: 1.65; font-weight: 300;
}}
.cl-asset-meta {{ font-size: 12.5px; color: {INK_SECONDARY}; }}
.cl-id {{
    font-family: 'Roboto Mono', monospace; font-size: 11.5px;
    background: #F1F3F4; color: {INK_SECONDARY};
    padding: 2px 7px; border-radius: 4px;
}}
.cl-quote {{
    border-left: 3px solid {DIVIDER}; padding: 2px 0 2px 14px;
    margin: 0 0 12px 0; font-size: 14px; color: {INK}; line-height: 1.6;
}}
.cl-divider {{ height: 1px; background: {DIVIDER}; margin: 26px 0; border: 0; }}

/* ---------- Tarjetas (contenedores con borde de Streamlit) ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    background: {SURFACE} !important;
    border: 1px solid {DIVIDER} !important;
    border-radius: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04);
    transition: box-shadow .2s ease;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
    box-shadow: 0 6px 18px rgba(0,0,0,.10), 0 2px 6px rgba(0,0,0,.06);
}}

/* ---------- Botones ---------- */
.stButton > button {{
    border-radius: 10px;
    font-weight: 500; font-size: 13px; letter-spacing: .3px;
    padding: 7px 18px;
    border: 1px solid {DIVIDER};
    background: {SURFACE};
    color: {INK_SECONDARY};
    box-shadow: none;
    transition: all .16s ease;
}}
.stButton > button:hover {{
    border-color: {PRIMARY}; color: {PRIMARY}; background: #F5F9FF;
    transform: translateY(-1px);
}}
.stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, {PRIMARY_DARK}, {PRIMARY});
    color: #fff; border: none;
    box-shadow: 0 3px 10px rgba(21,101,192,.32);
}}
.stButton > button[kind="primary"]:hover {{
    box-shadow: 0 6px 16px rgba(21,101,192,.42);
    color: #fff; transform: translateY(-1px);
}}
.stDownloadButton > button {{
    border-radius: 10px; font-weight: 500; font-size: 13px;
    background: linear-gradient(135deg, {PRIMARY_DARK}, {PRIMARY});
    color: #fff; border: none; padding: 9px 20px;
    box-shadow: 0 3px 10px rgba(21,101,192,.3);
}}
.stDownloadButton > button:hover {{
    color: #fff; box-shadow: 0 6px 16px rgba(21,101,192,.4);
}}

/* ---------- Campos ---------- */
.stTextArea textarea {{
    border-radius: 10px; font-size: 13.5px; line-height: 1.65;
    background: #FAFBFC; border: 1px solid {DIVIDER};
    color: {INK} !important;
    -webkit-text-fill-color: {INK} !important;
}}
.stTextArea textarea:focus {{ border-color: {PRIMARY}; box-shadow: none; }}

div[data-testid="stExpander"] details {{
    border: 1px solid {DIVIDER}; border-radius: 10px;
    background: #FAFBFC !important;
}}
div[data-testid="stExpander"] summary p {{ font-size: 13px; font-weight: 500; }}

/* ---------- Colores de texto en widgets (sobreviven al tema oscuro) ---------- */
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label,
.stCheckbox p, .stCheckbox label,
.stMultiSelect label, .stSelectbox label,
.stTextArea label, .stTextInput label,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {{
    color: {INK} !important;
}}
.stMultiSelect div[data-baseweb="select"] > div,
.stSelectbox div[data-baseweb="select"] > div {{
    background-color: {SURFACE} !important;
    color: {INK} !important;
    border-color: {DIVIDER} !important;
    border-radius: 10px;
}}
/* El cuadro del checkbox: Streamlit no le pone data-testid propio. */
.stCheckbox label > div:first-of-type,
.stCheckbox span[aria-hidden="true"] {{
    background-color: {SURFACE} !important;
    border: 1px solid {DIVIDER} !important;
}}
.stCheckbox input:checked + div,
.stCheckbox input:checked ~ div:first-of-type {{
    background-color: {PRIMARY} !important;
    border-color: {PRIMARY} !important;
}}

/* Ocultar chrome de Streamlit */
#MainMenu, footer, header {{ visibility: hidden; }}
</style>
"""
