"""Agrega FAQs nuevas a ``motor_educativo.db`` desde un CSV o JSON, sin levantar la API.

Por defecto sólo muestra qué haría (vista previa). Con ``--aplicar`` guarda
antes una copia de seguridad de la base en ``data/respaldos/`` y después
agrega las FAQs nuevas. Nunca toca las reseñas ni repite preguntas que ya
están en la base.

Uso:
    python -m communitylab_backend.tools.import_faqs ejemplos/faqs/faqs_nuevas_ejemplo.csv
    python -m communitylab_backend.tools.import_faqs ejemplos/faqs/faqs_nuevas_ejemplo.csv --aplicar
"""

import argparse
import sys
from pathlib import Path

from communitylab_backend.domain.errors import BackendError


def main(argv: list[str] | None = None) -> int:
    """Lee el archivo, valida las FAQs y las agrega (o sólo las muestra).

    Retorna 0 si terminó bien y 1 si el archivo o la base tienen un problema;
    los errores se muestran con su mensaje seguro.
    """
    from communitylab_backend.api.dependencies import build_knowledge
    from communitylab_backend.application.faq_import import read_faq_file
    from communitylab_backend.config.settings import Settings

    parser = argparse.ArgumentParser(description="Agrega FAQs nuevas a la base desde un CSV (pregunta,respuesta,curso) o JSON.")
    parser.add_argument("archivo", type=Path, help="Archivo .csv o .json con las FAQs")
    parser.add_argument("--aplicar", action="store_true", help="Escribe en la base (sin esto, sólo muestra la vista previa)")
    args = parser.parse_args(argv)
    try:
        result = build_knowledge(Settings()).import_faqs(read_faq_file(args.archivo.name, args.archivo.read_bytes()), dry_run=not args.aplicar)
    except (OSError, BackendError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    for warning in result["warnings"]:
        print(f"  aviso: {warning}")
    for item in result["invalid"]:
        print(f"  fila {item['row']}: {item['reason']}")
    for row in result["duplicates"]:
        print(f"  ya existe: {row['question']}")
    if args.aplicar:
        print(f"[OK] {result['added']} FAQ(s) agregadas: {', '.join(result['new_ids']) or '-'}")
        print(f"     copia de seguridad: {result['backup'] or 'no hizo falta (nada que agregar)'}")
    else:
        print(f"[VISTA PREVIA] se agregarían {len(result['to_add'])} FAQ(s); {len(result['duplicates'])} ya existen; {len(result['invalid'])} fila(s) con errores.")
        print("     Para escribir en la base, repetir con --aplicar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
