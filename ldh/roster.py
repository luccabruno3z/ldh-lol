"""Rosters premade (fase 7): grupos de vinculados que juegan juntos en Flex y Normales, y sus métricas de
proceso partida a partida.

Detección. Se arma el grafo de quién juega con quién: cada lado de partida con 4 o más vinculados suma 1 a
cada par. Las comunidades de ese grafo (Louvain, semilla fija) son los planteles: titulares y suplentes.
Una partida es del roster cuando hay 4 o más del plantel en el mismo lado. Un roster se publica con
10 partidas o más. config/rosters.json permite nombrar un roster o fijar su plantel a mano.

Métricas. Con 20 a 40 partidas por mes el winrate casi siempre da ruido, así que el foco está en el proceso
(lo que el equipo controla), cada una con su intervalo del 95 % y su n:
- oro a los 14 (diferencia del equipo), primer dragón, primer Heraldo, placas antes del 14 (tomadas − cedidas),
  visión por minuto del equipo, parte de los objetivos grandes que se lleva el equipo, y cierre
  (ganadas con 60 % o más de chance al minuto 15).
Se comparan contra la referencia: las demás partidas de Flex y Normales del grupo (lados con algún vinculado
que no son de ningún roster). Es una comparación descriptiva, no la causa.
"""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from . import estadistica as est
from . import victoria as V
from .ajustes import AJUSTES
from .almacen import _ruta
from .fase5 import modelo

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config" / "rosters.json"
COLAS = ("flex", "normal")
MIN_JUNTOS = 4  # del plantel en el mismo lado
MIN_PARTIDAS = 10  # para publicar un roster
SUMAR_CON = 3  # se suma al plantel quien jugó MIN_PARTIDAS o más con 3+ del plantel (un jugador puede estar en varios)
MIN_COMPARAR = AJUSTES["min_partidas"]  # el umbral único de «muestra chica»
ALFA = AJUSTES["ajuste_muestra"]["alfa"]
DIA_MS = 86_400_000
SEMANAS = 8  # semanas ISO con partidas que se publican (para el informe semanal)
HORA_AR = timezone(timedelta(hours=-3))
VENTANAS = {"semana": 7, "mes": 28, "temporada": None}  # días hacia atrás desde la última partida guardada
MIN_ORO = 14
MIN_P15 = 15
CIERRE = 0.6
GRANDES = ("dragon", "heraldo", "baron", "ancestral", "larva")

METRICAS = {  # clave: (nombre, unidad, tipo); tipo "prop" = 0/1 por partida, "media" = número por partida
    "oro14": ("Oro a los 14", "oro de diferencia", "media"),
    "primer_dragon": ("Primer dragón", "% de las partidas", "prop"),
    "primer_heraldo": ("Primer Heraldo", "% de las partidas", "prop"),
    "placas": ("Placas antes del 14", "tomadas − cedidas", "media"),
    "vision": ("Visión del equipo", "por minuto", "media"),
    "objetivos": ("Objetivos grandes", "% que se lleva el equipo", "media"),
    "cierre": ("Cierre", "% ganadas con 60 %+ al 15", "prop"),
    "winrate": ("Winrate", "% (solo contexto)", "prop"),
}
NOTA = ("Métricas de proceso por partida del roster, con el intervalo del 95 % (Wilson para proporciones, "
        "bootstrap para medias) y su n. «Contra la referencia» compara con las demás partidas de Flex y "
        "Normales del grupo: «señal» si el intervalo de la diferencia no toca el cero. Es descriptivo, no la "
        "causa. El winrate va solo como contexto: con estas muestras casi siempre es ruido.")


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def _lados(db: sqlite3.Connection) -> dict[tuple[str, str], set[str]]:
    lados = defaultdict(set)
    for mid, lado, pid in db.execute(f"""SELECT p.match_id, p.lado, p.persona_id FROM participantes p
                                          JOIN partidas m USING(match_id)
                                          WHERE p.persona_id IS NOT NULL AND m.cola IN {COLAS}"""):
        lados[(mid, lado)].add(pid)
    return lados


def _rid(nucleo: list[str]) -> str:
    return "r" + hashlib.sha1("|".join(sorted(nucleo)).encode()).hexdigest()[:8]


def detectar(db: sqlite3.Connection, nombres: dict[str, str]) -> list[dict]:
    """Los rosters: plantel, núcleo (los 3 con más partidas, que dan el id estable) y sus lados de partida."""
    import networkx as nx

    lados = _lados(db)
    juntos = {k: s for k, s in lados.items() if len(s) >= MIN_JUNTOS}
    g = nx.Graph()
    for s in juntos.values():
        for a, b in itertools.combinations(sorted(s), 2):
            w = g.get_edge_data(a, b, {"weight": 0})["weight"]
            g.add_edge(a, b, weight=w + 1)
    planteles = [set(c) for c in nx.community.louvain_communities(g, weight="weight", seed=1)] if g else []
    cfg = _config()
    fijos = [r for r in cfg.get("rosters", []) if r.get("plantel")]
    for r in fijos:  # un plantel fijado a mano reemplaza a la comunidad con la que más se pisa
        p = set(r["plantel"])
        if planteles:
            planteles.remove(max(planteles, key=lambda c: len(c & p)))
        planteles.append(p)
    # Louvain pone a cada jugador en una sola comunidad: el que juega con varios grupos queda afuera de todos.
    # Se suma a quien jugó 10+ partidas con 3+ del plantel (una sola pasada, sin arrastrar a otros). Los planteles
    # fijados a mano no se tocan.
    manuales = [set(r["plantel"]) for r in fijos]
    for plantel in planteles:
        if plantel in manuales:
            continue
        con = Counter(q for s in lados.values() if len(s & plantel) >= SUMAR_CON for q in s - plantel)
        plantel |= {q for q, n in con.items() if n >= MIN_PARTIDAS}
    nombres_cfg = {r["id"]: r["nombre"] for r in cfg.get("rosters", []) if r.get("id") and r.get("nombre")}
    out = []
    for plantel in planteles:
        ks = [k for k, s in lados.items() if len(s & plantel) >= MIN_JUNTOS]
        if len(ks) < MIN_PARTIDAS:
            continue
        cuenta = Counter(p for k in ks for p in lados[k] & plantel)
        nucleo = [p for p, _ in sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))[:3]]
        rid = next((r["id"] for r in fijos if set(r["plantel"]) == plantel and r.get("id")), None) or _rid(nucleo)
        out.append({"id": rid, "nombre": nombres_cfg.get(rid) or " · ".join(nombres.get(p, p) for p in nucleo),
                    "nucleo": nucleo, "plantel": plantel, "lados": ks, "cuenta": cuenta})
    return sorted(out, key=lambda r: -len(r["lados"]))


def _partida(db: sqlite3.Connection, m: dict, mid: str, lado: str) -> dict | None:
    """Las métricas de proceso de un lado de una partida (None si no tiene timeline)."""
    fila = db.execute("SELECT inicio_ms, ganador, cola, duracion_seg, tiene_timeline FROM partidas WHERE match_id=?",
                      (mid,)).fetchone()
    inicio, ganador, cola, dur, tl = fila
    eq = 100 if lado == "azul" else 200
    signo = 1 if eq == 100 else -1
    vision = db.execute("SELECT SUM(vision) FROM participantes WHERE match_id=? AND lado=?", (mid, lado)).fetchone()[0]
    d = {"match": mid, "inicio": inicio, "cola": cola, "win": int(ganador == eq), "winrate": int(ganador == eq),
         "vision": round(vision / (dur / 60), 2) if vision is not None and dur else None}
    if not tl:
        return d
    crudo = json.loads(gzip.decompress(_ruta("timelines", mid, inicio).read_bytes()))
    p = V.Partida(crudo)
    if len(p.oro) > MIN_ORO:
        d["oro14"] = signo * p.oro[MIN_ORO]
    for clase, k in (("dragon", "primer_dragon"), ("heraldo", "primer_heraldo")):
        primero = next((e for e in p.eventos if e[1] == clase), None)
        if primero:
            d[k] = int(primero[2] == eq)
    # Solo antes del 14: en este parche hay placas en las 3 torres de cada línea y caen toda la partida, así que
    # contarlas todas mide quién ganó, no el arranque.
    placas = [e for f in crudo["info"]["frames"] for e in f["events"]
              if e["type"] == "TURRET_PLATE_DESTROYED" and e.get("timestamp", 0) < MIN_ORO * 60_000]
    d["placas"] = sum(e.get("teamId") != eq for e in placas) - sum(e.get("teamId") == eq for e in placas)
    grandes = [e[2] for e in p.eventos if e[1] in GRANDES]
    if grandes:
        d["objetivos"] = round(sum(x == eq for x in grandes) / len(grandes), 3)
    if len(p.t_frames) > MIN_P15 + 1:
        p15 = V.prob(m, p.estado(p.t_frames[MIN_P15]), eq)
        d["p15"] = round(p15, 3)
        if p15 >= CIERRE:
            d["cierre"] = d["win"]
    return d


def semana_iso(ms: int) -> str:
    """'2026-W45': la semana ISO (lunes a domingo, hora de Argentina) de un instante en ms."""
    a, w, _ = datetime.fromtimestamp(ms / 1000, HORA_AR).isocalendar()
    return f"{a}-W{w:02d}"


def _resumen(filas: list[dict]) -> dict:
    out = {}
    for k, (_, _, tipo) in METRICAS.items():
        xs = [f[k] for f in filas if f.get(k) is not None]
        out[k] = est.wilson(sum(xs), len(xs)) if tipo == "prop" else est.media(xs)
    return out


def _diferencia(a: list[float], b: list[float]) -> dict:
    """Diferencia de medias a − b con intervalo bootstrap y p bilateral del bootstrap (para BH)."""
    xa, xb = np.array(a, dtype=float), np.array(b, dtype=float)
    chica = len(xa) < MIN_COMPARAR
    if len(xa) < 2 or len(xb) < 2:
        return {"v": None, "lo": None, "hi": None, "n": len(xa), "n_ref": len(xb), "p": None, "muestra_chica": True}
    rng = np.random.default_rng(est.SEMILLA)
    dif = (xa[rng.integers(0, len(xa), (est.REPS, len(xa)))].mean(1)
           - xb[rng.integers(0, len(xb), (est.REPS, len(xb)))].mean(1))
    lo, hi = np.percentile(dif, est._Q)
    p = min(1.0, 2 * min((dif <= 0).mean(), (dif >= 0).mean()))
    return {"v": est._r(xa.mean() - xb.mean()), "lo": est._r(lo), "hi": est._r(hi), "n": len(xa), "n_ref": len(xb),
            "p": None if chica else est._r(p, 4), "muestra_chica": chica}


def _contra(filas: list[dict], ref: list[dict]) -> dict:
    return {k: _diferencia([f[k] for f in filas if f.get(k) is not None], [f[k] for f in ref if f.get(k) is not None])
            for k in METRICAS if k != "winrate"}


def _etiquetar(rosters: list[dict]) -> None:
    """Señal / a confirmar / ruido, con BH sobre todas las comparaciones de todos los rosters (como la web)."""
    todas = [x for d in rosters for x in d["contra_referencia"].values() if x["p"] is not None]
    for x, pb in zip(todas, est.benjamini_hochberg([x["p"] for x in todas])):
        x["p_bh"] = est._r(pb, 4)
    for d in rosters:
        for x in d["contra_referencia"].values():
            if x["p"] is None:
                x["nivel"] = "muestra chica" if x["v"] is not None else None
            elif x["p_bh"] < ALFA:
                x["nivel"] = "señal"
            elif not (x["lo"] <= 0 <= x["hi"]):
                x["nivel"] = "a confirmar"
            else:
                x["nivel"] = "ruido"


def generar(db: sqlite3.Connection, escribir: Callable) -> list[dict]:
    nombres = dict(db.execute("SELECT id, nombre FROM personas"))
    m = modelo(db)
    rosters = detectar(db, nombres)
    if not rosters:
        escribir("roster/index.json", {"rosters": [], "nota": NOTA})
        return []
    de_roster = {k for r in rosters for k in r["lados"]}
    cache: dict[tuple[str, str], dict | None] = {}

    def fila(k):
        if k not in cache:
            cache[k] = _partida(db, m, *k)
        return cache[k]

    ref = [f for k in _lados(db) if k not in de_roster and (f := fila(k))]
    ref_res = _resumen(ref)
    ultima = db.execute(f"SELECT MAX(inicio_ms) FROM partidas WHERE cola IN {COLAS}").fetchone()[0]
    indice, detalles = [], []
    for r in rosters:
        filas = sorted((f for k in r["lados"] if (f := fila(k))), key=lambda f: -f["inicio"])
        roles, presentes = defaultdict(Counter), {}
        for mid, lado in r["lados"]:
            presentes[mid] = []
            for pid, rol in db.execute("SELECT persona_id, rol FROM participantes WHERE match_id=? AND lado=? "
                                       "AND persona_id IS NOT NULL", (mid, lado)):
                if pid in r["plantel"]:
                    presentes[mid].append(pid)
                    if rol:
                        roles[pid][rol] += 1
        plantel = [{"id": pid, "nombre": nombres.get(pid, pid), "partidas": n,
                    "rol": roles[pid].most_common(1)[0][0] if roles[pid] else None, "nucleo": pid in r["nucleo"]}
                   for pid, n in sorted(r["cuenta"].items(), key=lambda x: (-x[1], x[0]))]
        ventanas = {}
        for v, dias in VENTANAS.items():
            fs = filas if dias is None else [f for f in filas if f["inicio"] >= ultima - dias * DIA_MS]
            ventanas[v] = {"n": len(fs), "metricas": _resumen(fs)}
        lado_de = dict(r["lados"])  # match -> lado del roster
        por_semana = defaultdict(list)
        for f in filas:
            por_semana[semana_iso(f["inicio"])].append(f)
        semanas = {w: {"n": len(fs), "metricas": _resumen(fs),
                       "partidas": [{"match": f["match"], "inicio": f["inicio"], "cola": f["cola"], "win": f["win"],
                                     "lado": lado_de[f["match"]], "jugadores": sorted(presentes[f["match"]])} for f in fs]}
                   for w, fs in sorted(por_semana.items(), reverse=True)[:SEMANAS]}
        d = {"id": r["id"], "nombre": r["nombre"], "plantel": plantel, "partidas": len(filas),
             "ultima": filas[0]["inicio"] if filas else None, "ventanas": ventanas, "semanas": semanas,
             "referencia": {"n": len(ref), "metricas": ref_res}, "contra_referencia": _contra(filas, ref),
             "historial": [{"match": f["match"], "inicio": f["inicio"], "cola": f["cola"], "win": f["win"],
                            "jugadores": sorted(presentes[f["match"]])} for f in filas[:20]],
             "metricas": {k: {"nombre": a, "unidad": b, "tipo": c} for k, (a, b, c) in METRICAS.items()},
             "nota": NOTA}
        detalles.append(d)
        indice.append({k: d[k] for k in ("id", "nombre", "partidas", "ultima")}
                      | {"plantel": [{k: p[k] for k in ("id", "nombre", "rol", "partidas", "nucleo")} for p in plantel]})
    _etiquetar(detalles)
    for d in detalles:
        escribir(f"roster/{d['id']}.json", d)
    escribir("roster/index.json", {"rosters": indice, "nota": NOTA})
    return indice
