"""Reglas locales para ocultar datos personales en el texto de la comunidad.

Pertenece a infraestructura. Reemplaza el módulo ``dataset_builder.pii`` que
el adaptador de sanitización esperaba y que nunca llegó al repositorio. Usa
sólo expresiones regulares de la librería estándar: no llama a servicios ni
guarda el texto original.

Cada dato encontrado se cambia por una etiqueta como ``[EMAIL]``, de modo que
el modelo de lenguaje sepa que ahí había un dato, pero no cuál.
"""

import re

# El orden importa: primero lo más largo (URL, correo) para que sus partes no
# se confundan después con un usuario o un teléfono.
RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("url", "[URL]", re.compile(r"\b(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)),
    ("email", "[EMAIL]", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("ip", "[IP]", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("phone", "[TELEFONO]", re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")),
    ("user", "[USUARIO]", re.compile(r"(?<![\w@])@[A-Za-z0-9_.]{2,32}\b|<@!?\d{5,}>")),
)


def sanitize(text: str, enabled: dict[str, bool] | None = None) -> tuple[str, dict[str, int]]:
    """Oculta los datos personales de ``text`` según las reglas activas.

    ``enabled`` indica qué reglas aplicar (``email``, ``phone``, ``url``,
    ``ip``, ``user``); si es ``None`` se aplican todas. Retorna el texto
    seguro y un conteo de reemplazos por regla, útil para auditar sin guardar
    el dato. No tiene efectos secundarios.
    """
    safe = text or ""
    report: dict[str, int] = {}
    for name, label, pattern in RULES:
        if enabled is not None and not enabled.get(name, False):
            continue
        safe, count = pattern.subn(label, safe)
        if count:
            report[name] = count
    return safe, report
