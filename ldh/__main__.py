"""python -m ldh [ingestar|reconstruir|publicar|todo]"""

from __future__ import annotations

import sys

from .ajustes import cargar_env


def main(argv: list[str]) -> int:
    # Riot IDs con caracteres fuera de cp1252 (な, ˇ) rompían el print con la salida redirigida en Windows.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    orden = argv[0] if argv else "todo"
    if orden in ("ingestar", "todo"):
        from .ingesta import correr
        correr()
    if orden in ("reconstruir", "todo"):
        from .base import reconstruir
        reconstruir()
    if orden in ("publicar", "todo"):
        from .publicar import publicar
        publicar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
