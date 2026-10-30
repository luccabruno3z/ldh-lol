"""python -m ldh [ingestar|reconstruir|publicar|todo|referencia [armar]|timelines empaquetar|desempaquetar <carpeta>]"""

from __future__ import annotations

import sys

from .ajustes import cargar_env


def main(argv: list[str]) -> int:
    # Riot IDs con caracteres fuera de cp1252 (な, ˇ) rompían el print con la salida redirigida en Windows.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    orden = argv[0] if argv else "todo"
    if orden == "referencia":
        # Aparte de "todo": gasta API por horas y se corre a mano (python -m ldh referencia [armar]).
        from . import referencia
        if "armar" not in argv[1:]:
            referencia.scoutear()
        referencia.armar_filas()
        return 0
    if orden in ("ingestar", "todo"):
        from .ingesta import correr
        correr()
    if orden == "timelines":
        from . import timelines
        accion, carpeta = argv[1], argv[2]
        if accion == "empaquetar":
            desde = float(argv[argv.index("--desde") + 1]) if "--desde" in argv else None
            timelines.empaquetar(carpeta, desde)
        else:
            timelines.desempaquetar(carpeta)
        return 0
    if orden in ("reconstruir", "todo"):
        from .base import reconstruir
        from .timelines import verificar
        verificar()
        reconstruir()
    if orden in ("publicar", "todo"):
        from .publicar import publicar
        publicar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
