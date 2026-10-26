"""Comprueba docstrings del código nuevo mediante el AST de Python.

Este módulo del backend revisa sus archivos y ``tests/backend`` sin importar
el código. No recorre ``dataset_builder`` ni evaluaciones congeladas porque
son trabajo anterior fuera del alcance de esta fase.

Uso: ``python -m communitylab_backend.documentation_check``.
"""

import ast
from pathlib import Path


def check_file(path: Path) -> list[str]:
    """Devuelve faltas de docstring de un archivo Python propio.

    ``path`` es un archivo legible. Comprueba módulo, clases, funciones y
    métodos, incluso anidados. Retorna mensajes con ruta y línea; puede
    producir errores de lectura o sintaxis si el archivo es inválido.
    No ejecuta el módulo ni modifica archivos.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing = []
    if not ast.get_docstring(tree):
        missing.append(f"{path}:1: falta docstring del módulo")
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and not ast.get_docstring(node):
            kind = "clase" if isinstance(node, ast.ClassDef) else "función o método"
            missing.append(f"{path}:{node.lineno}: falta docstring de {kind} {node.name}")
    return missing


def owned_files(root: Path) -> list[Path]:
    """Lista Python propio de backend y sus tests, ordenado por ruta.

    ``root`` es la raíz del repositorio. Excluye archivos generados y
    ``__pycache__`` por ubicación; no incluye el pipeline heredado.
    No tiene efectos secundarios.
    """

    return sorted(path for folder in (root / "communitylab_backend", root / "tests" / "backend") for path in folder.rglob("*.py") if "__pycache__" not in path.parts)


def check_documentation(root: Path) -> list[str]:
    """Comprueba todos los archivos propios bajo ``root``.

    Retorna faltas legibles para CI. Propaga errores de lectura o sintaxis
    para que la suite falle también ante un archivo Python roto.
    """

    return [problem for path in owned_files(root) for problem in check_file(path)]


def main() -> int:
    """Ejecuta el chequeo desde CLI y retorna 0 si no hay faltas.

    Imprime los problemas encontrados; no llama a servicios ni escribe
    archivos. La raíz se obtiene desde la ubicación de este módulo.
    """

    root = Path(__file__).resolve().parent.parent
    problems = check_documentation(root)
    for problem in problems:
        print(problem)
    if not problems:
        print("Documentación del backend completa")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
