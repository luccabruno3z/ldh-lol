"""Las timelines crudas fuera de git.

Pesan ~300 MB y crecen con cada partida, así que no van a la rama `datos` (doc de lecciones).
La copia local está en ./timelines (LDH_TIMELINES) y la durable son los assets del release
"timelines" del repo: un .tar por plataforma y mes (timelines-la2-2026-01.tar). Los .json.gz
de adentro ya vienen comprimidos, el .tar no se vuelve a comprimir.

    python -m ldh timelines empaquetar <carpeta> [--desde <epoch>]   # meses tocados desde epoch
    python -m ldh timelines desempaquetar <carpeta>
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from .ajustes import DATOS, TIMELINES

# Si faltan más que esto, la reconstrucción se frena: sin timelines la base saldría sin las
# métricas a los 10 y 15 y sin eventos, y se publicaría en silencio algo peor.
TOPE_FALTANTES = 0.05


def _meses() -> list[Path]:
    return sorted(p for p in TIMELINES.glob("*/*") if p.is_dir())


def empaquetar(destino: str, desde: float | None = None) -> list[Path]:
    salida = Path(destino)
    salida.mkdir(parents=True, exist_ok=True)
    hechos = []
    for mes in _meses():
        archivos = sorted(mes.glob("*.json.gz"))
        if not archivos or (desde and max(a.stat().st_mtime for a in archivos) < desde):
            continue
        tar = salida / f"timelines-{mes.parent.name}-{mes.name}.tar"
        with tarfile.open(tar, "w") as t:
            for a in archivos:
                t.add(a, arcname=f"{mes.parent.name}/{mes.name}/{a.name}")
        hechos.append(tar)
        print(f"  {tar.name}: {len(archivos)} timelines", flush=True)
    return hechos


def desempaquetar(origen: str) -> int:
    n = 0
    for tar in sorted(Path(origen).glob("timelines-*.tar")):
        with tarfile.open(tar) as t:
            t.extractall(TIMELINES, filter="data")
            n += len(t.getnames())
    print(f"{n} timelines en {TIMELINES}", flush=True)
    return n


def verificar() -> None:
    """Frena si faltan timelines de muchas partidas guardadas (por ejemplo, si no se bajó el release)."""
    partidas = list((DATOS / "partidas").glob("*/*/*.json.gz"))
    if not partidas:
        return
    faltan = sum(not (TIMELINES / p.relative_to(DATOS / "partidas")).exists() for p in partidas)
    if faltan / len(partidas) > TOPE_FALTANTES:
        raise SystemExit(f"Faltan las timelines de {faltan} de {len(partidas)} partidas en {TIMELINES}. "
                         "¿Se bajó el release 'timelines'? No reconstruyo para no publicar datos incompletos.")
