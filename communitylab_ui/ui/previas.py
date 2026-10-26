"""
Vista previa de cada activo tal como se veria en su canal.

QUE ES ESTO
-----------
La bandeja de curaduria muestra, al lado del editor, como quedaria el texto
publicado: una tarjeta de LinkedIn, un bloque de newsletter, una entrada de
FAQ o un borrador de historia de exito. Asi quien revisa decide viendo el
resultado final, no un cuadro de texto.

Todo es HTML simple (sin iframes de Material UI) para que se dibuje rapido
al cambiar de activo. El texto SIEMPRE se escapa antes de insertarlo: viene
de la comunidad o del modelo y no debe poder inyectar HTML en el panel.

REGLA DE FORMATO
----------------
st.markdown interpreta Markdown fuera de las etiquetas HTML. Por eso cada
bloque se arma en UNA sola linea, sin lineas en blanco: los saltos del texto
se convierten en <br>.
"""

from __future__ import annotations

import html
import re

from ui import theme as T

LINKEDIN_PLIEGUE = 210      # caracteres que LinkedIn muestra antes de "...ver mas"
LINKEDIN_MAXIMO = 3000      # limite de una publicacion de LinkedIn
NEWSLETTER_RECOMENDADO = 600

# tipo del activo -> (limite recomendado o None, nota para quien revisa)
LIMITES = {
    "linkedin_post": (LINKEDIN_MAXIMO, f"LinkedIn muestra ~{LINKEDIN_PLIEGUE} caracteres antes de «…ver más» · máximo {LINKEDIN_MAXIMO:,}".replace(",", ".")),
    "newsletter_highlight": (NEWSLETTER_RECOMENDADO, f"Recomendado: hasta {NEWSLETTER_RECOMENDADO} caracteres para un destacado"),
    "faq_content": (None, "Sin límite: conviene una respuesta breve y paso a paso"),
    "success_story": (None, "Validar el texto con la persona antes de publicar"),
    "quick_tutorial": (900, "Recomendado: hasta 900 caracteres y de 3 a 5 pasos"),
    "weekly_tip": (280, "Un solo consejo · hasta 280 caracteres (cabe en un mensaje de Discord)"),
    "doc_topic": (700, "Propuesta para el equipo de contenidos · hasta 700 caracteres"),
}


def _texto(valor: str) -> str:
    """Escapa el texto y convierte los saltos de linea en <br>."""
    return html.escape(valor or "").replace("\n", "<br>")


def _hashtags(texto_html: str) -> str:
    """Pinta los #hashtags con el azul de LinkedIn (sobre texto ya escapado)."""
    return re.sub(r"(?<![\w&])#(\w+)", r'<span class="pv-tag">#\1</span>', texto_html)


def contador(kind: str, texto: str) -> tuple[str, bool]:
    """Devuelve la nota de largo del texto y si se paso del limite del canal."""
    limite, nota = LIMITES.get(kind, (None, ""))
    n = len(texto or "")
    excedido = limite is not None and n > limite
    return f"{n:,} caracteres · {nota}".replace(",", "."), excedido


def _linkedin(texto: str, comunidad: str) -> str:
    """Tarjeta con la forma de una publicacion del feed de LinkedIn."""
    corte = LINKEDIN_PLIEGUE
    if len(texto) > corte and " " in texto[:corte]:
        corte = texto.rfind(" ", 0, corte) + 1     # cortar entre palabras, como LinkedIn
    visible, resto = texto[:corte], texto[corte:]
    cuerpo = _hashtags(_texto(visible))
    if resto:
        cuerpo += ('<span class="pv-fold">…ver más · lo que sigue solo se ve al expandir</span>'
                   f'<span class="pv-rest">{_hashtags(_texto(resto))}</span>')
    return (
        '<div class="pv-li">'
        '<div class="pv-li-head"><div class="pv-li-avatar">CL</div><div>'
        f'<div class="pv-li-name">CommunityLab · {html.escape(comunidad)}</div>'
        '<div class="pv-li-sub">Comunidad tech · Ahora · 🌐</div></div></div>'
        f'<div class="pv-li-body">{cuerpo}</div>'
        '<div class="pv-li-react">👍❤️👏 <span>Vista previa: así se vería en el feed</span></div>'
        '<div class="pv-li-actions"><span>Recomendar</span><span>Comentar</span><span>Compartir</span><span>Enviar</span></div>'
        '</div>'
    )


def _newsletter(titulo: str, texto: str, seccion: str, comunidad: str, periodo: str) -> str:
    """Bloque con la forma de una seccion de la newsletter semanal."""
    return (
        '<div class="pv-nl"><div class="pv-nl-card">'
        f'<div class="pv-nl-top"><b>Newsletter semanal</b><span>{html.escape(comunidad)} · {html.escape(periodo)}</span></div>'
        f'<div class="pv-nl-sec">{html.escape(seccion)}</div>'
        f'<div class="pv-nl-title">{html.escape(titulo)}</div>'
        f'<div class="pv-nl-body">{_texto(texto)}</div>'
        '<div class="pv-nl-cta">Leer más en la comunidad →</div>'
        '</div></div>'
    )


def _faq(titulo: str, texto: str, evidencia: list[dict]) -> str:
    """Entrada de la base de conocimiento, con el respaldo de la FAQ oficial."""
    if evidencia:
        pie = ('<div class="pv-faq-ok">✔ Respaldada por la FAQ oficial: '
               + " ".join(f'<span class="cl-id">{html.escape(e["id"])}</span>' for e in evidencia)
               + '</div>')
    else:
        pie = '<div class="pv-faq-warn">⚠ Sin FAQ oficial que la respalde: conviene derivarla a mentoría antes de publicar.</div>'
    return (
        '<div class="pv-faq">'
        '<div class="pv-faq-label">Pregunta frecuente</div>'
        f'<div class="pv-faq-title">{html.escape(titulo)}</div>'
        f'<div class="pv-faq-body">{_texto(texto)}</div>{pie}</div>'
    )


def _caso_exito(titulo: str, texto: str) -> str:
    """Borrador de historia de exito para el blog o la seccion de testimonios."""
    return (
        '<div class="pv-story">'
        '<div class="pv-story-warn">Antes de publicar: pedir permiso a la persona y validar los datos.</div>'
        '<div class="pv-story-label">Historias de la comunidad</div>'
        f'<div class="pv-story-title">{html.escape(titulo)}</div>'
        f'<div class="pv-story-body">{_texto(texto)}</div></div>'
    )


def _respaldo(evidencia: list[dict]) -> str:
    """Franja que dice si el contenido se apoya en una FAQ oficial o hay que crearlo."""
    if evidencia:
        return ('<div class="pv-faq-ok">✔ Respaldado por la FAQ oficial: '
                + " ".join(f'<span class="cl-id">{html.escape(e["id"])}</span>' for e in evidencia) + '</div>')
    return ('<div class="pv-faq-warn">⚠ Sin FAQ oficial: un mentor debe validarlo. Si lo apruebas, '
            'puedes agregarlo a la base como FAQ nueva.</div>')


def _tutorial(titulo: str, texto: str, tema: str, evidencia: list[dict]) -> str:
    """Tutorial rápido con la forma de una ficha de aprendizaje."""
    return (
        '<div class="pv-faq">'
        f'<div class="pv-faq-label">Tutorial rápido · {html.escape(tema)}</div>'
        f'<div class="pv-faq-title">{html.escape(titulo)}</div>'
        f'<div class="pv-faq-body">{_texto(texto)}</div>{_respaldo(evidencia)}</div>'
    )


def _tip(texto: str, tema: str, comunidad: str) -> str:
    """Tip de la semana con la forma de un mensaje fijado en Discord."""
    return (
        '<div class="pv-tip"><div class="pv-tip-head"><span class="pv-tip-bot">CL</span>'
        f'<b>CommunityLab</b><span class="pv-tip-tag">BOT</span><span class="pv-tip-ch"># {html.escape(comunidad)}</span></div>'
        f'<div class="pv-tip-card"><div class="pv-tip-title">💡 Tip de la semana · {html.escape(tema)}</div>'
        f'<div>{_texto(texto)}</div></div></div>'
    )


def _documentacion(titulo: str, texto: str, tema: str, evidencia: list[dict]) -> str:
    """Propuesta de página de documentación, como una ficha para el equipo de contenidos."""
    return (
        '<div class="pv-doc"><div class="pv-doc-bar">Propuesta para la documentación · '
        f'{html.escape(tema)}</div><div class="pv-doc-body">'
        f'<div class="pv-faq-title">{html.escape(titulo)}</div>'
        f'<div class="pv-faq-body">{_texto(texto)}</div>{_respaldo(evidencia)}</div></div>'
    )


def previa(act: dict, texto: str) -> str:
    """HTML de la vista previa del activo `act` con su `texto` actual (editado o no)."""
    kind = act["kind"]
    if kind == "linkedin_post":
        return _linkedin(texto, act["origen_comunidad"])
    if kind == "newsletter_highlight":
        return _newsletter(act["titulo"], texto, act.get("seccion_newsletter", ""), act["origen_comunidad"], act["periodo_referencia"])
    if kind == "faq_content":
        return _faq(act["titulo"], texto, act.get("evidencia", []))
    if kind == "quick_tutorial":
        return _tutorial(act["titulo"], texto, act.get("tema") or "", act.get("evidencia", []))
    if kind == "weekly_tip":
        return _tip(texto, act.get("tema") or "", act["origen_comunidad"])
    if kind == "doc_topic":
        return _documentacion(act["titulo"], texto, act.get("tema") or "", act.get("evidencia", []))
    return _caso_exito(act["titulo"], texto)


def fuente(mensajes: list[dict], evidencia: list[dict]) -> str:
    """Mensajes de la comunidad que originaron el activo y FAQs oficiales que lo respaldan."""
    partes = []
    for m in mensajes:
        chips = [f'<span class="pv-chip">{html.escape(m.get("categoria", ""))}</span>']
        if m.get("score_relevancia") is not None:
            chips.append(f'<span class="pv-chip pv-chip-blue">Relevancia {m["score_relevancia"]:.2f}</span>')
        if m.get("mejor_momento"):
            chips.append('<span class="pv-chip pv-chip-green">Mejor momento</span>')
        if m.get("requiere_apoyo"):
            chips.append('<span class="pv-chip pv-chip-red">Requiere apoyo</span>')
        color = T.SENTIMIENTO.get(m.get("sentimiento_detectado"), T.INK_MUTED)
        partes.append(
            '<div class="pv-src">'
            f'<div class="pv-src-head"><span class="cl-id">{html.escape(m["id"])}</span>'
            f'<b>{html.escape(m.get("autor", ""))}</b><span>{html.escape(m.get("canal", ""))}</span>'
            f'<span class="pv-dot" style="background:{color}"></span><span>{html.escape(m.get("sentimiento_detectado", ""))}</span></div>'
            f'<div class="cl-quote">{_texto(m["texto"])}</div>'
            f'<div class="pv-chips">{"".join(chips)}</div></div>'
        )
    if evidencia:
        partes.append('<div class="pv-src-title">FAQ oficial usada como respaldo · motor_educativo.db</div>')
        for ev in evidencia:
            partes.append(
                '<div class="pv-src">'
                f'<div class="pv-src-head"><span class="cl-id">{html.escape(ev["id"])}</span>'
                f'<span>{html.escape(ev["fuente"])} · puntaje {ev["score"]:.2f}</span></div>'
                f'<div class="cl-quote"><b>{html.escape(ev["pregunta"])}</b><br>{_texto(ev["respuesta"])}</div></div>'
            )
    else:
        partes.append('<div class="pv-src-title">Este activo no cita FAQs oficiales.</div>')
    return "".join(partes)
