"""Rutas y constantes compartidas. Las constantes viven en config/ajustes.json."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AJUSTES = json.loads((RAIZ / "config" / "ajustes.json").read_text(encoding="utf-8"))

# La rama `datos` se monta como worktree en ./datos (en Actions, un segundo checkout).
DATOS = Path(os.environ.get("LDH_DATOS", RAIZ / "datos"))
# Todo lo que se publica en Pages se arma acá; nunca se commitea.
SALIDA = Path(os.environ.get("LDH_SALIDA", RAIZ / "salida"))
CACHE = Path(os.environ.get("LDH_CACHE", RAIZ / ".cache"))
# Las timelines crudas no van a git (doc de lecciones): viven acá y su copia durable son los
# assets del release "timelines" del repo (un .tar por mes, ver ldh/timelines.py).
TIMELINES = Path(os.environ.get("LDH_TIMELINES", RAIZ / "timelines"))

INICIO_HISTORIAL = int(
    datetime.fromisoformat(AJUSTES["inicio_historial"].replace("Z", "+00:00")).timestamp()
)


def cargar_env() -> None:
    """Lee .env local si existe (en Actions las variables vienen de los secretos)."""
    archivo = RAIZ / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"'))


def cola_de(queue_id: int | None) -> str:
    return AJUSTES["colas"].get(str(queue_id), "otra")
