"""Rosters (fase 7): los equipos declarados a mano y sus métricas en dos capas.

Declarados. Un roster lo crea y lo edita solo Lucca desde el bot (-roster crear/sumar/sacar). Vive en el repo
ldh-lol-metas (rosters.json, montado en ./metas como las pools): id fijo, nombre, carpeta (virguhouse o srx) y
plantel con rol y titular o suplente. Solo cuentan los jugadores vinculados.

Sugerencias. Para la Virguhouse, el grafo de quién juega con quién propone grupos (comunidades de Louvain con
semilla fija; se suma a quien jugó 10+ partidas con 3+ del grupo). No se publican como rosters: son una
propuesta para declarar con un clic. Las que ya se pisan con un roster declarado no se muestran.

Dos capas de métricas:
- Plantel: desde las partidas de cada jugador en su rol (rango oficial, partidas, winrate, Performance, oro a
  los 15 contra su rival y campeones). Está desde el primer día, aunque nunca hayan jugado juntos.
- Equipo: solo las partidas de Flex y Normales con 4+ del plantel en el mismo lado. Con 20 a 40 partidas por mes
  el winrate casi siempre da ruido, así que el foco está en el proceso, cada métrica con su intervalo del 95 % y
  su n: oro a los 14, primer dragón, primer Heraldo, placas antes del 14 (tomadas − cedidas), visión por minuto,
  parte de los objetivos grandes y cierre (ganadas con 60 %+ de chance al minuto 15). Se comparan contra la
  referencia (las demás partidas de Flex y Normales del grupo). Es descriptivo, no la causa.
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
from .ajustes import AJUSTES, SALIDA
from .almacen import _ruta
from .fase5 import modelo

RAIZ = Path(__file__).resolve().parent.parent
API = SALIDA / "api"
ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")
CARPETAS = ("virguhouse", "srx")
COLAS = ("flex", "normal")
MIN_JUNTOS = 4  # del plantel en el mismo lado
MIN_PARTIDAS = 10  # para proponer un grupo como sugerencia
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


def cargar_declarados() -> dict:
    """Los rosters que declaró Lucca con -roster (repo ldh-lol-metas, montado en ./metas). Sin el repo, ninguno."""
    import os
    ruta = Path(os.environ.get("LDH_METAS", RAIZ / "metas")) / "rosters.json"
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _leer(rel: str) -> dict | None:
    ruta = API / rel
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _lados(db: sqlite3.Connection) -> dict[tuple[str, str], set[str]]:
    lados = defaultdict(set)
    for mid, lado, pid in db.execute(f"""SELECT p.match_id, p.lado, p.persona_id FROM participantes p
                                          JOIN partidas m USING(match_id)
                                          WHERE p.persona_id IS NOT NULL AND m.cola IN {COLAS}"""):
        lados[(mid, lado)].add(pid)
    return lados


def _rid(nucleo: list[str]) -> str:
    return "r" + hashlib.sha1("|".join(sorted(nucleo)).encode()).hexdigest()[:8]


def sugerir(db: sqlite3.Connection, nombres: dict[str, str]) -> list[dict]:
    """Grupos que juegan juntos (para la Virguhouse): plantel, núcleo y sus lados de partida."""
    import networkx as nx

    lados = _lados(db)
    g = nx.Graph()
    for s in (s for s in lados.values() if len(s) >= MIN_JUNTOS):
        for a, b in itertools.combinations(sorted(s), 2):
            w = g.get_edge_data(a, b, {"weight": 0})["weight"]
            g.add_edge(a, b, weight=w + 1)
    planteles = [set(c) for c in nx.community.louvain_communities(g, weight="weight", seed=1)] if g else []
    # Louvain pone a cada jugador en una sola comunidad: el que juega con varios grupos quedaría afuera de todos.
    # Se suma a quien jugó 10+ partidas con 3+ del plantel (una sola pasada, sin arrastrar a otros).
    for plantel in planteles:
        con = Counter(q for s in lados.values() if len(s & plantel) >= SUMAR_CON for q in s - plantel)
        plantel |= {q for q, n in con.items() if n >= MIN_PARTIDAS}
    out = []
    for plantel in planteles:
        ks = [k for k, s in lados.items() if len(s & plantel) >= MIN_JUNTOS]
        if len(ks) < MIN_PARTIDAS:
            continue
        cuenta = Counter(p for k in ks for p in lados[k] & plantel)
        nucleo = [p for p, _ in sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))[:3]]
        out.append({"id": "s" + hashlib.sha1("|".join(sorted(nucleo)).encode()).hexdigest()[:8],
                    "nombre": " · ".join(nombres.get(p, p) for p in nucleo), "nucleo": nucleo,
                    "plantel": plantel, "lados": ks, "cuenta": cuenta})
    return sorted(out, key=lambda r: -len(r["lados"]))


def _roles_en(db: sqlite3.Connection, lados: list[tuple[str, str]], plantel: set[str]) -> tuple[dict, dict]:
    """(rol más jugado de cada uno en esas partidas, quiénes del plantel jugaron cada partida)."""
    roles, presentes = defaultdict(Counter), {}
    for mid, lado in lados:
        presentes[mid] = []
        for pid, rol in db.execute("SELECT persona_id, rol FROM participantes WHERE match_id=? AND lado=? "
                                   "AND persona_id IS NOT NULL", (mid, lado)):
            if pid in plantel:
                presentes[mid].append(pid)
                if rol:
                    roles[pid][rol] += 1
    return {p: c.most_common(1)[0][0] for p, c in roles.items() if c}, presentes


def _jugador(pid: str, nombre: str, rol: str | None) -> dict:
    """La capa del plantel: lo que se sabe de un jugador en su rol desde sus partidas, aunque no haya jugado con
    el equipo. Sale de lo que ya publicó el pipeline (perfil, roles, coaching y campeones)."""
    d = {"id": pid, "nombre": nombre, "rol": rol}
    perfil = _leer(f"perfil/{pid}.json") or {}
    solo = [c["solo"] for c in (perfil.get("rango") or {}).values() if c.get("solo")]
    if solo:
        m = max(solo, key=lambda r: r.get("valor") or -1)
        d["rango"] = {k: m.get(k) for k in ("tier", "division", "lp")}
    if not rol:
        return d
    fila = next((r for r in (_leer(f"roles/{pid}.json") or {}).get("tabla", []) if r["cola"] == "todo" and r["rol"] == rol), None)
    if fila:
        d["en_rol"] = {"n": fila["n"], "winrate": fila["winrate"], "dif_oro15": fila.get("dif_oro15"),
                       "muestra_chica": fila.get("muestra_chica")}
    c = (_leer(f"coaching/{pid}.json") or {}).get("roles", {}).get(rol) or {}
    if c.get("performance"):
        d["performance"] = {**c["performance"], "franja": c.get("franja"), "n": c.get("n")}
    camps = sorted((r for r in (_leer(f"campeones/{pid}.json") or {}).get("tabla", []) if r["cola"] == "todo" and r["rol"] == rol),
                   key=lambda r: -r["n"])[:3]
    d["campeones"] = [{"champ": r["champ"], "n": r["n"], "winrate": r["winrate"]["v"]} for r in camps]
    return d


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


def _equipo(db, fila, plantel: set[str], ultima: int, ref: list[dict]) -> dict:
    """La capa del equipo: las partidas con 4+ del plantel juntos (o todos, si son menos de 4)."""
    juntos = min(MIN_JUNTOS, max(len(plantel), 2))
    lados = [k for k, s in _lados(db).items() if len(s & plantel) >= juntos]
    roles, presentes = _roles_en(db, lados, plantel)
    filas = sorted((f for k in lados if (f := fila(k))), key=lambda f: -f["inicio"])
    ventanas = {}
    for v, dias in VENTANAS.items():
        fs = filas if dias is None else [f for f in filas if f["inicio"] >= ultima - dias * DIA_MS]
        ventanas[v] = {"n": len(fs), "metricas": _resumen(fs)}
    lado_de = dict(lados)
    por_semana = defaultdict(list)
    for f in filas:
        por_semana[semana_iso(f["inicio"])].append(f)
    semanas = {w: {"n": len(fs), "metricas": _resumen(fs),
                   "partidas": [{"match": f["match"], "inicio": f["inicio"], "cola": f["cola"], "win": f["win"],
                                 "lado": lado_de[f["match"]], "jugadores": sorted(presentes[f["match"]])} for f in fs]}
               for w, fs in sorted(por_semana.items(), reverse=True)[:SEMANAS]}
    cuenta = Counter(p for ps in presentes.values() for p in ps)
    return {"lados": lados, "roles": roles, "cuenta": cuenta, "juntos": juntos, "partidas": len(filas),
            "ultima": filas[0]["inicio"] if filas else None, "ventanas": ventanas, "semanas": semanas,
            "contra_referencia": _contra(filas, ref),
            "historial": [{"match": f["match"], "inicio": f["inicio"], "cola": f["cola"], "win": f["win"],
                           "jugadores": sorted(presentes[f["match"]])} for f in filas[:20]]}


def generar(db: sqlite3.Connection, escribir: Callable) -> list[dict]:
    """Publica los rosters declarados (api/roster/<id>.json) y las sugerencias (en api/roster/index.json).
    Corre después de las fases 2 a 5: la capa del plantel lee lo que ya publicaron."""
    nombres = dict(db.execute("SELECT id, nombre FROM personas"))
    m = modelo(db)
    declarados = {rid: r for rid, r in cargar_declarados().items() if isinstance(r, dict)}
    cache: dict[tuple[str, str], dict | None] = {}

    def fila(k):
        if k not in cache:
            cache[k] = _partida(db, m, *k)
        return cache[k]

    ultima = db.execute(f"SELECT MAX(inicio_ms) FROM partidas WHERE cola IN {COLAS}").fetchone()[0]
    planteles = {rid: {x["id"] for x in r.get("plantel") or [] if x.get("id") in nombres} for rid, r in declarados.items()}
    juntos_de = {rid: min(MIN_JUNTOS, max(len(p), 2)) for rid, p in planteles.items()}
    lados = _lados(db)
    de_roster = {k for rid, p in planteles.items() if p for k, s in lados.items() if len(s & p) >= juntos_de[rid]}
    ref = [f for k in lados if k not in de_roster and (f := fila(k))]
    ref_res = _resumen(ref)

    indice, detalles = [], []
    for rid, r in declarados.items():
        plantel_ids = planteles[rid]
        eq = _equipo(db, fila, plantel_ids, ultima, ref) if plantel_ids else None
        miembros = []
        for x in r.get("plantel") or []:
            if x.get("id") not in nombres:
                continue  # solo vinculados: el que se desvinculó deja de publicarse
            j = _jugador(x["id"], nombres[x["id"]], x.get("rol"))
            miembros.append({**j, "estado": x.get("estado", "titular"), "desde": x.get("desde"),
                             "partidas_juntos": eq["cuenta"].get(x["id"], 0) if eq else 0})
        titulares = {x["rol"]: x["nombre"] for x in miembros if x["estado"] == "titular" and x.get("rol")}
        d = {"id": rid, "nombre": r.get("nombre") or rid, "carpeta": r.get("carpeta", "virguhouse"),
             "plantel": miembros, "cobertura": {rol: titulares.get(rol) for rol in ROLES},
             "partidas": eq["partidas"] if eq else 0, "ultima": eq["ultima"] if eq else None,
             "juntos": eq["juntos"] if eq else MIN_JUNTOS,
             "ventanas": eq["ventanas"] if eq else {v: {"n": 0, "metricas": _resumen([])} for v in VENTANAS},
             "semanas": eq["semanas"] if eq else {}, "historial": eq["historial"] if eq else [],
             "referencia": {"n": len(ref), "metricas": ref_res},
             "contra_referencia": eq["contra_referencia"] if eq else _contra([], ref),
             "metricas": {k: {"nombre": a, "unidad": b, "tipo": c} for k, (a, b, c) in METRICAS.items()},
             "nota": NOTA}
        detalles.append(d)
        indice.append({k: d[k] for k in ("id", "nombre", "carpeta", "partidas", "ultima", "cobertura")}
                      | {"plantel": [{k: p.get(k) for k in ("id", "nombre", "rol", "estado", "partidas_juntos")} for p in miembros]})
    _etiquetar(detalles)
    for d in detalles:
        escribir(f"roster/{d['id']}.json", d)

    # Sugerencias: los grupos que juegan juntos y que no se pisan con un roster declarado (4+ en común).
    sugerencias = []
    for g in sugerir(db, nombres):
        if any(len(g["plantel"] & p) >= MIN_JUNTOS for p in planteles.values()):
            continue
        roles, _ = _roles_en(db, g["lados"], g["plantel"])
        sugerencias.append({"id": g["id"], "nombre": g["nombre"], "partidas": len(g["lados"]),
                            "plantel": [{"id": pid, "nombre": nombres.get(pid, pid), "rol": roles.get(pid), "partidas": n}
                                        for pid, n in sorted(g["cuenta"].items(), key=lambda x: (-x[1], x[0]))]})
    escribir("roster/index.json", {"rosters": indice, "sugerencias": sugerencias, "nota": NOTA})
    return indice
