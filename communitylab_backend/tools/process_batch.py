"""Procesa lotes de interacciones desde la terminal, sin levantar la API.

Lee uno o varios archivos JSON o CSV, ejecuta el mismo flujo que
``POST /api/v1/activity/process`` y guarda cada respuesta en
``salidas/respuestas/<nombre-del-archivo>.json``. El paquete de borradores se
guarda, como siempre, en el almacenamiento configurado (carpeta local u OCI).

Uso:
    python -m communitylab_backend.tools.process_batch ejemplos
    python -m communitylab_backend.tools.process_batch ejemplos/02_dudas_machine_learning.json
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

from communitylab_backend.domain.errors import BackendError

DEFAULT_OUTPUT = Path("salidas/respuestas")


def batch_files(target: Path) -> list[Path]:
    """Devuelve los archivos ``.json`` y ``.csv`` de ``target`` en orden alfabético.

    Si ``target`` es un archivo, retorna sólo ese archivo.
    """
    target = Path(target)
    if target.is_dir():
        return sorted(path for path in target.iterdir() if path.suffix.lower() in {".json", ".csv"})
    return [target]


def main(argv: list[str] | None = None) -> int:
    """Procesa cada lote, imprime un resumen y guarda la respuesta completa.

    Retorna 0 si todos los lotes terminan bien y 1 si alguno falla. Los errores
    se muestran con su mensaje seguro; nunca imprime claves.
    """
    from communitylab_backend.api.dependencies import build_workflow
    from communitylab_backend.application.batch import process_batch
    from communitylab_backend.application.ingestion import load_batch_file
    from communitylab_backend.config.settings import Settings

    parser = argparse.ArgumentParser(description="Procesa lotes JSON o CSV con el flujo de CommunityLab.")
    parser.add_argument("target", type=Path, help="Archivo o carpeta con lotes (.json o .csv)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Carpeta de respuestas (por defecto salidas/respuestas)")
    args = parser.parse_args(argv)
    workflow = build_workflow(Settings())
    args.out.mkdir(parents=True, exist_ok=True)
    failures = 0
    for path in batch_files(args.target):
        try:
            batch = load_batch_file(path)
            response = process_batch(workflow, str(uuid.uuid4()), batch["community_source"], batch["reference_period"], batch["interactions"])
        except BackendError as exc:
            failures += 1
            print(f"[ERROR] {path.name}: {exc}", file=sys.stderr)
            continue
        destination = args.out / f"{path.stem}.json"
        destination.write_text(json.dumps({"entrada": batch, "respuesta": response}, ensure_ascii=False, indent=2), encoding="utf-8")
        kinds = ", ".join(asset["kind"] for asset in response["generated_assets"])
        print(f"[OK] {path.name}: rutas={' + '.join(response['routing']['flows'])} | activos={kinds} | citas FAQ={len(response['evidence'])} | requieren apoyo={len(response['members_needing_support'])} | guardado en {response['storage']['location']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
