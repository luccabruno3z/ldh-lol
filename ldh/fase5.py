"""Fase 5: lo que sale de la investigación (Deng 2024, xPetu, PandaSkill, curvas de maestría).

A. Rachas y pausas: ¿te conviene seguir después de 2 derrotas? Cada persona se compara consigo misma
   (si no, el que juega peor aparece más en las rachas y parece que la racha hace perder).
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Callable

from . import estadistica as est
from .ajustes import AJUSTES
from .fase2 import GRIETA

CFG = AJUSTES["fase5"]
MIN_MS = 60_000
MODOS = {"solo": ("solo",), "normal": ("normal",), "todo": GRIETA}
# Orden y texto de las barras.
ESTADOS = {
    "inicio": "Primera de la sesión",
    "tras_victoria": "Después de ganar",
    "tras_1": "Después de 1 derrota",
    "tras_2_sigue": "Después de 2+ derrotas, seguido",
    "tras_2_corta": "Después de 2+ derrotas, cortando",
}


# ---------------------------------------------------------------- A. rachas

def _secuencia(db: sqlite3.Connection, pid: str) -> list[dict]:
    """Todas las partidas de la persona en orden (todas las colas: una ARAM también corta o alarga
    una racha). Cada una con su estado: qué venía pasando antes de empezarla."""
    filas = db.execute("""SELECT pa.inicio_ms, pa.fin_ms, pa.cola, pt.win FROM participantes pt
                          JOIN partidas pa USING(match_id) WHERE pt.persona_id = ? ORDER BY pa.inicio_ms""",
                       (pid,)).fetchall()
    out, racha, pos, fin_prev, ultimo = [], 0, 0, None, None
    for inicio, fin, cola, win in filas:
        gap = None if fin_prev is None else (inicio - fin_prev) / MIN_MS
        if gap is None or gap >= CFG["sesion_min"]:
            estado, pos = ("tras_2_corta" if racha >= 2 and gap is not None else "inicio"), 1
        else:
            pos += 1
            if racha >= 2:
                estado = "tras_2_corta" if gap >= CFG["corte_min"] else "tras_2_sigue"
            else:
                estado = "tras_victoria" if ultimo else "tras_1"
        out.append({"cola": cola, "win": int(bool(win)), "estado": estado, "pos": pos})
        racha = 0 if win else racha + 1
        ultimo, fin_prev = bool(win), fin or inicio
    return out


def _mh(estratos: list[tuple[int, int, int, int]]) -> dict:
    """Diferencia de riesgo de Mantel–Haenszel (en puntos de winrate) entre dos grupos, estratificada
    por persona: cada uno contra sí mismo. estratos: (ganadas1, n1, ganadas0, n0)."""
    num = den = var = 0.0
    for a, n1, c, n0 in estratos:
        if n1 == 0 or n0 == 0:
            continue
        p1, p0, w = a / n1, c / n0, n1 * n0 / (n1 + n0)
        num += w * (p1 - p0)
        den += w
        var += w ** 2 * (p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    if den == 0:
        return {"v": None, "lo": None, "hi": None, "ruido": True, "personas": 0}
    v, se = num / den, math.sqrt(var) / den
    z = 1.959964
    return {"v": est._r(v), "lo": est._r(v - z * se), "hi": est._r(v + z * se),
            "ruido": v - z * se <= 0 <= v + z * se, "personas": sum(1 for e in estratos if e[1] and e[3])}


def _comparar(a: list[int], b: list[int]) -> dict:
    """Una persona: winrate de a contra b, con Fisher. Señal solo con 10+ partidas de cada lado."""
    wa, wb = sum(a), sum(b)
    p = est.fisher(wa, len(a) - wa, wb, len(b) - wb) if a and b else None
    chico = min(len(a), len(b)) < CFG["min_celda"]
    return {"dif": est.diferencia([float(x) for x in a], [float(x) for x in b]), "p": est._r(p, 4),
            "senal": (p is not None and not chico and p < AJUSTES["ajuste_muestra"]["alfa"]), "muestra_chica": chico}


def rachas(db: sqlite3.Connection, pids: list[str]) -> tuple[dict, dict]:
    """(por persona, grupo). Por persona y modo: winrate de la partida según el estado en que se
    empezó, las dos comparaciones que importan y el cansancio dentro de la sesión."""
    por, grupo = {}, {}
    est_grupo = {m: defaultdict(list) for m in MODOS}
    for pid in pids:
        sec = _secuencia(db, pid)
        por[pid] = {}
        for modo, colas in MODOS.items():
            g = [x for x in sec if x["cola"] in colas]
            if not g:
                continue
            res = {e: [x["win"] for x in g if x["estado"] == e] for e in ESTADOS}
            cortas = [x["win"] for x in g if x["pos"] < CFG["largas_desde"]]
            largas = [x["win"] for x in g if x["pos"] >= CFG["largas_desde"]]
            comps = {"corta_vs_sigue": (res["tras_2_corta"], res["tras_2_sigue"]),
                     "racha_vs_victoria": (res["tras_2_sigue"], res["tras_victoria"]),
                     "largas_vs_cortas": (largas, cortas)}
            por[pid][modo] = {
                "n": len(g),
                "estados": {e: est.wilson(sum(v), len(v)) for e, v in res.items()},
                "sesion": {"primeras": est.wilson(sum(cortas), len(cortas)), "largas": est.wilson(sum(largas), len(largas))},
                "comparaciones": {k: _comparar(a, b) for k, (a, b) in comps.items()},
            }
            for k, (a, b) in comps.items():
                est_grupo[modo][k].append((sum(a), len(a), sum(b), len(b)))
    for modo in MODOS:
        grupo[modo] = {k: _mh(v) for k, v in est_grupo[modo].items()}
    return por, grupo


# ---------------------------------------------------------------- generar

def generar(db: sqlite3.Connection, filas_por: dict[str, list[dict]], escribir: Callable) -> None:
    por, grupo = rachas(db, list(filas_por))
    textos = {"estados": ESTADOS, "sesion_min": CFG["sesion_min"], "corte_min": CFG["corte_min"],
              "largas_desde": CFG["largas_desde"]}
    escribir("rachas/grupo.json", {**textos, "modos": grupo,
                                   "nota": "Diferencias de Mantel–Haenszel: cada persona contra sí misma, en puntos "
                                           "de winrate. 'Ruido' si el intervalo cruza el cero."})
    for pid, d in por.items():
        escribir(f"rachas/{pid}.json", {**textos, "modos": d})
