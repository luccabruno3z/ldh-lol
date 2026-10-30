"""Fase 5: lo que sale de la investigación (Deng 2024, xPetu, PandaSkill, curvas de maestría).

A. Rachas y pausas: ¿te conviene seguir después de 2 derrotas? Cada persona se compara consigo misma
   (si no, el que juega peor aparece más en las rachas y parece que la racha hace perder).
B. Probabilidad de ganar minuto a minuto (ldh.victoria): se entrena, se valida y se publica con su calibración.
C. Cuánto te costó cada muerte (la regla 9 del doc de lecciones, medida) y el gráfico de cada partida.
D. Curva de aprendizaje: cuánto rendís con un campeón según cuántas partidas llevás con él, contra tu nivel
   normal en ese rol (cada uno contra sí mismo, como en las curvas de maestría de iTero).
"""

from __future__ import annotations

import gzip
import json
import math
import sqlite3
from collections import defaultdict
from typing import Callable

from . import estadistica as est
from . import victoria as V
from .ajustes import AJUSTES
from .almacen import _ruta
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


# ---------------------------------------------------------------- B. modelo

def modelo(db: sqlite3.Connection) -> dict:
    """El modelo de probabilidad de ganar: se reentrena solo si cambiaron las partidas."""
    n = db.execute("SELECT count(*) FROM partidas WHERE cola IN ('solo','flex','normal') AND tiene_timeline=1").fetchone()[0]
    m = V.cargar_modelo()
    if not m or m.get("version") != V.VERSION or m.get("partidas") != n:
        m = V.entrenar(db)
        V.guardar_modelo(m)
    return m


def _equivalencias(m: dict) -> list[dict]:
    """Cuánto vale cada cosa en oro, a mitad de partida (tramo 20–30): coeficiente / coeficiente del oro.
    Es lo que suma además del oro que ya da (ese está en la diferencia de oro)."""
    c = dict(zip(m["variables"], m["coef"]))
    oro = c["oro_20"] / 1000
    nombres = {"baron": "Barón activo", "ancestral": "Dragón Ancestral activo", "inhib": "Un inhibidor caído",
               "dragones": "Un dragón", "alma": "El alma (además de sus dragones)", "torres_20": "Una torre",
               "kills_20": "Una kill", "larvas": "Una larva", "heraldo": "El Heraldo"}
    return [{"clave": k, "nombre": n, "oro": round(c[k] / oro)} for k, n in nombres.items() if k in c]


# ---------------------------------------------------------------- C. muertes y partidas

VENTANA_MS = 60_000  # lo que el rival se llevó después de la muerte, y cuándo se mide
# Oro aproximado que da cada objetivo al equipo (la parte que el frame ya cuenta y hay que devolver).
ORO_OBJETIVO = {"baron": 1500, "torre": 250}
FASES = (("temprana", 0, 14), ("media", 14, 25), ("tardia", 25, 999))
ESPEJO = (14750, 14860)  # dos veces el centro del minimapa de Data Dragon (de −120 a 14.870 y 14.980)


def zona(x: int, y: int, lado: str) -> str:
    """Región del mapa, vista desde el lado de la persona (tu jungla / la del rival)."""
    if x < 4200 and y < 4200:
        z = "base_azul"
    elif x > 10600 and y > 10600:
        z = "base_roja"
    elif (x < 2300 and y > 4200) or (y > 12500 and x < 10600):
        return "top"
    elif (y < 2300 and x > 4200) or (x > 12500 and y < 10600):
        return "bot"
    elif abs(x - y) < 1600:
        return "mid"
    elif abs(x + y - 14800) < 1800:
        return "rio_arriba" if y > x else "rio_abajo"
    else:
        z = "jungla_azul" if x + y < 14800 else "jungla_roja"
    propio = "azul" if lado == "azul" else "roja"
    if z.startswith("base"):
        return "tu_base" if z.endswith(propio) else "base_rival"
    return "tu_jungla" if z.endswith(propio) else "jungla_rival"


ZONAS = {"top": "Top", "mid": "Mid", "bot": "Bot", "rio_arriba": "Río de arriba", "rio_abajo": "Río de abajo",
         "tu_jungla": "Tu jungla", "jungla_rival": "Jungla rival", "tu_base": "Tu base", "base_rival": "Base rival"}
OBJETIVOS = {"baron": "el Barón", "ancestral": "el Ancestral", "dragon": "un dragón", "heraldo": "el Heraldo",
             "larva": "larvas", "torre": "una torre", "inhib": "un inhibidor"}


def _fase(minuto: float) -> str:
    return next(n for n, a, b in FASES if a <= minuto < b)


def _costo(p: V.Partida, m: dict, k: int, equipo: int) -> tuple[float, list[str]]:
    """Probabilidad de ganar que el equipo de la víctima pierde por la muerte k (índice en p.eventos):
    el modelo un minuto después, con la muerte y sin ella. Sin ella = sin la kill, sin su oro (bounty,
    shutdown y asistencias, ~50 % más si hubo) y sin lo que el rival tomó en ese minuto."""
    t, _, eq_kill, e = p.eventos[k]
    t_eval = min(t + VENTANA_MS, p.fin)
    oro = (e.get("bounty", 0) + e.get("shutdownBounty", 0)) * (1.5 if e.get("assistingParticipantIds") else 1)
    sacar, perdidos = {k}, []
    for j in range(k + 1, len(p.eventos)):
        tj, clase, eqj, _ = p.eventos[j]
        if tj > t + VENTANA_MS:
            break
        if eqj == eq_kill and clase in OBJETIVOS:
            sacar.add(j)
            perdidos.append(clase)
            oro += ORO_OBJETIVO.get(clase, 0)
    signo = 1 if eq_kill == 100 else -1  # el oro extra se le saca al que mató
    real = V.prob(m, p.estado(t_eval), equipo)
    sin = V.prob(m, p.estado(t_eval, frozenset(sacar), -signo * oro), equipo)
    return sin - real, perdidos


def muertes_y_partidas(db: sqlite3.Connection, m: dict) -> tuple[dict, dict]:
    """(muertes por persona, curva de cada partida). Cada muerte: minuto, costo, zona, fase, lo que se perdió
    y si el equipo iba arriba. Cada partida: la probabilidad del azul por minuto y los momentos clave."""
    amigos = defaultdict(dict)  # match -> participant_id -> (persona, lado, rol)
    for mid, part, pid, lado, rol in db.execute("""SELECT match_id, participant_id, persona_id, lado, rol
                                                    FROM participantes WHERE persona_id IS NOT NULL"""):
        amigos[mid][part] = (pid, lado, rol)
    muertes = defaultdict(list)
    partidas = {}
    for mid, inicio, cola, ganador in db.execute("""SELECT match_id, inicio_ms, cola, ganador FROM partidas
                                                    WHERE cola IN ('solo','flex','normal') AND tiene_timeline=1"""):
        if mid not in amigos:
            continue
        p = V.Partida(json.loads(gzip.decompress(_ruta("timelines", mid, inicio).read_bytes())))
        curva = [round(V.prob(m, p.estado(t)), 3) for t in range(0, p.fin + 1, MIN_MS)]
        eventos = []
        for k, (t, clase, eq, e) in enumerate(p.eventos):
            if clase == "kill":
                vic, mat = e.get("victimId"), e.get("killerId")
                if vic in amigos[mid]:
                    pid, lado, rol = amigos[mid][vic]
                    equipo = 100 if lado == "azul" else 200
                    costo, perdidos = _costo(p, m, k, equipo)
                    antes = V.prob(m, p.estado(t), equipo)
                    pos = e.get("position") or {}
                    # El mapa es simétrico respecto del centro: las del lado rojo se espejan para que todo quede
                    # visto desde tu base abajo a la izquierda (juntar los dos lados sin esto inventa patrones).
                    vx, vy = pos.get("x"), pos.get("y")
                    if vx is not None and lado == "rojo":
                        vx, vy = ESPEJO[0] - vx, ESPEJO[1] - vy
                    d = {"match": mid, "t": t, "min": round(t / MIN_MS, 1), "costo": round(costo, 4),
                         "zona": zona(pos.get("x", 0), pos.get("y", 0), lado), "fase": _fase(t / MIN_MS),
                         "perdidos": perdidos, "arriba": antes > 0.5, "x": vx, "y": vy,
                         "rol": rol, "cola": cola, "inicio": inicio}
                    muertes[pid].append(d)
                    eventos.append({"min": d["min"], "tipo": "muerte", "persona": pid, "costo": d["costo"],
                                    "perdidos": perdidos})
                if mat in amigos[mid]:
                    eventos.append({"min": round(t / MIN_MS, 1), "tipo": "kill", "persona": amigos[mid][mat][0]})
            elif clase in ("baron", "ancestral", "dragon", "heraldo", "inhib"):
                eventos.append({"min": round(t / MIN_MS, 1), "tipo": clase, "equipo": eq})
        saltos = [abs(b - a) for a, b in zip(curva, curva[1:])]
        clave = max(range(len(saltos)), key=saltos.__getitem__) + 1 if saltos else None
        partidas[mid] = {"curva": curva, "ganador": ganador, "cola": cola, "inicio": inicio,
                         "lados": {pid: lado for pid, lado, _ in amigos[mid].values()},
                         "eventos": eventos, "clave": None if clave is None else
                         {"min": clave, "delta": round(curva[clave] - curva[clave - 1], 3)}}
    return muertes, partidas


def _resumen_muertes(ms: list[dict], n_partidas: int, reps: int) -> dict:
    """Costo medio por muerte y por partida (en puntos de probabilidad), con IC bootstrap por partida."""
    import numpy as np
    if not ms:
        return {"n": 0, "partidas": n_partidas}
    por_partida = defaultdict(list)
    for d in ms:
        por_partida[d["match"]].append(d["costo"])
    grupos = list(por_partida.values())
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    medias = []
    for _ in range(reps):
        g = [grupos[i] for i in rng.integers(0, len(grupos), len(grupos))]
        medias.append(np.mean([c for x in g for c in x]))
    costo = float(np.mean([d["costo"] for d in ms]))
    lo, hi = np.percentile(medias, (2.5, 97.5))
    fases = {f: [d["costo"] for d in ms if d["fase"] == f] for f, _, _ in FASES}
    zonas = defaultdict(list)
    for d in ms:
        zonas[d["zona"]].append(d["costo"])
    return {"n": len(ms), "partidas": n_partidas,
            "por_muerte": {"v": round(costo, 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4)},
            "por_partida": round(sum(d["costo"] for d in ms) / max(n_partidas, 1), 4),
            "muertes_partida": round(len(ms) / max(n_partidas, 1), 2),
            "con_objetivo": round(sum(1 for d in ms if d["perdidos"]) / len(ms), 3),
            "fases": {f: {"n": len(v), "costo": round(float(np.mean(v)), 4) if v else None,
                          "total": round(sum(v), 3)} for f, v in fases.items()},
            "zonas": sorted(({"zona": z, "nombre": ZONAS.get(z, z), "n": len(v), "costo": round(float(np.mean(v)), 4),
                              "total": round(sum(v), 3)} for z, v in zonas.items()), key=lambda x: -x["total"])}


def muertes(muertes_por: dict, filas_por: dict) -> tuple[dict, dict]:
    """(por persona, mediana del grupo) por modo y rol ("Todos" = todos los roles)."""
    reps = AJUSTES["bootstrap_reps"] // 4
    por, refs = {}, defaultdict(list)
    for pid, filas in filas_por.items():
        ms = muertes_por.get(pid, [])
        por[pid] = {}
        for modo, colas in MODOS.items():
            con_tl = {f["match_id"]: f for f in filas if f["cola"] in colas}
            mm = [d for d in ms if d["cola"] in colas]
            jugadas = defaultdict(set)
            for d in mm:
                jugadas[d["rol"]].add(d["match"])
            roles = {}
            n_rol = defaultdict(int)
            for f in con_tl.values():
                n_rol[f["rol_ldh"] or "Sin rol"] += 1
            for rol in ["Todos", *[r for r in n_rol if r != "Sin rol"]]:
                sub = mm if rol == "Todos" else [d for d in mm if d["rol"] == rol]
                n = len(con_tl) if rol == "Todos" else n_rol[rol]
                if n < AJUSTES["min_partidas"]:
                    continue
                roles[rol] = _resumen_muertes(sub, n, reps)
                if roles[rol]["n"]:
                    refs[(modo, rol)].append(roles[rol]["por_partida"])
            ultimas = sorted(mm, key=lambda d: -d["inicio"])
            vistas, recientes = set(), []
            for d in ultimas:
                if len(vistas) >= 20 and d["match"] not in vistas:
                    break
                vistas.add(d["match"])
                recientes.append(d)
            caras = sorted(recientes, key=lambda d: -d["costo"])[:3]
            por[pid][modo] = {"roles": roles, "caras": [{k: d[k] for k in ("match", "min", "costo", "zona", "fase",
                                                                         "perdidos", "arriba", "rol")} | {"zona_nombre": ZONAS.get(d["zona"])}
                                                        for d in caras],
                              # Las 400 más recientes: con todas, el mapa de quien juega mucho se tapaba.
                              "puntos": [[d["min"], d["x"], d["y"], round(d["costo"], 3)]
                                         for d in sorted(mm, key=lambda d: (d["inicio"], d["t"])) if d["x"] is not None][-400:]}
    import statistics
    mediana = {f"{m}|{r}": round(statistics.median(v), 4) for (m, r), v in refs.items() if len(v) >= 3}
    return por, mediana


# ---------------------------------------------------------------- D. curvas de aprendizaje

TRAMOS_CURVA = ((1, 3), (4, 7), (8, 15), (16, 30), (31, 10_000))
DIA_MS = 86_400_000


def _tramo(n: int) -> int:
    return next(i for i, (a, b) in enumerate(TRAMOS_CURVA) if a <= n <= b)


def _boot_media(grupos: list[list[float]], reps: int, rng) -> tuple[float | None, float | None, float | None]:
    """Media de todas las partidas con IC bootstrap que remuestrea grupos (persona y campeón): las partidas de un
    mismo par no son independientes."""
    import numpy as np
    vals = [v for g in grupos for v in g]
    if len(vals) < 3:
        return None, None, None
    medias = []
    for _ in range(reps):
        g = [grupos[i] for i in rng.integers(0, len(grupos), len(grupos))]
        x = [v for gg in g for v in gg]
        if x:
            medias.append(sum(x) / len(x))
    lo, hi = np.percentile(medias, (2.5, 97.5))
    return round(sum(vals) / len(vals), 2), round(float(lo), 2), round(float(hi), 2)


def curvas(indices: dict) -> tuple[dict, dict]:
    """(por persona, grupo) por modo. Cada partida se ubica por cuántas llevabas con ese campeón en ese rol
    (contando todas las colas) y se mide como tu índice menos tu nivel normal en el rol. El grupo usa solo
    campeones que aparecen después del primer mes del historial: antes no se sabe si eran nuevos."""
    import numpy as np
    from .ajustes import INICIO_HISTORIAL
    corte = (INICIO_HISTORIAL + 30 * 86_400) * 1000
    reps = AJUSTES["bootstrap_reps"] // 4
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    por, grupo_pares = {}, {m: defaultdict(list) for m in MODOS}
    for pid, filas in indices.items():
        cuenta, primera = defaultdict(int), {}
        numeradas = []
        for inicio, cola, rol, champ, idx, win in filas:
            cuenta[(champ, rol)] += 1
            primera.setdefault((champ, rol), inicio)
            numeradas.append((cuenta[(champ, rol)], inicio, cola, rol, champ, idx, win))
        por[pid] = {}
        for modo, colas in MODOS.items():
            sub = [x for x in numeradas if x[2] in colas and x[5] is not None]
            normal = defaultdict(list)
            for n, _, _, rol, _, idx, _ in sub:
                normal[rol].append(idx)
            normal = {r: sum(v) / len(v) for r, v in normal.items() if len(v) >= AJUSTES["min_partidas"]}
            pares = defaultdict(list)
            for n, inicio, _, rol, champ, idx, win in sub:
                if rol in normal:
                    pares[(champ, rol)].append((n, idx - normal[rol], win))
            campeones = []
            for (champ, rol), g in pares.items():
                nuevo = primera[(champ, rol)] >= corte
                if nuevo:
                    grupo_pares[modo][(pid, champ, rol)] = g
                if len(g) < AJUSTES["min_partidas"]:
                    continue
                tramos = []
                for t, (a, b) in enumerate(TRAMOS_CURVA):
                    xs = [d for n, d, _ in g if a <= n <= b]
                    wins = [w for n, _, w in g if a <= n <= b]
                    v, lo, hi = _boot_media([[x] for x in xs], reps, rng) if len(xs) >= 3 else (None, None, None)
                    tramos.append({"tramo": f"{a}–{b}" if b < 10_000 else f"{a}+", "n": len(xs), "v": v, "lo": lo, "hi": hi,
                                   "winrate": est.wilson(sum(wins), len(wins))})
                # Cómo rendís hoy con él: tus últimas 10 partidas con ese campeón contra tu nivel normal. Los tramos
                # de 3 partidas tienen intervalos tan anchos que "en qué partida llegaste" no se puede decir.
                ult = [d for _, d, _ in g[-AJUSTES["min_partidas"]:]]
                v, lo, hi = _boot_media([[x] for x in ult], reps, rng)
                estado = "por encima" if lo is not None and lo > 0 else "por debajo" if hi is not None and hi < 0 else "a tu nivel"
                campeones.append({"champ": champ, "rol": rol, "n": len(g), "nuevo": nuevo, "tramos": tramos,
                                  "ahora": {"v": v, "lo": lo, "hi": hi, "n": len(ult)}, "estado": estado})
            por[pid][modo] = {"normal": {r: round(v, 1) for r, v in normal.items()},
                              "campeones": sorted(campeones, key=lambda c: -c["n"])}
    grupo = {}
    for modo, pares in grupo_pares.items():
        tramos = []
        for t, (a, b) in enumerate(TRAMOS_CURVA):
            grupos = [[d for n, d, _ in g if a <= n <= b] for g in pares.values()]
            grupos = [g for g in grupos if g]
            v, lo, hi = _boot_media(grupos, reps, rng)
            wins = [w for g in pares.values() for n, _, w in g if a <= n <= b]
            tramos.append({"tramo": f"{a}–{b}" if b < 10_000 else f"{a}+", "n": sum(len(g) for g in grupos),
                           "pares": len(grupos), "v": v, "lo": lo, "hi": hi,
                           "winrate": est.wilson(sum(wins), len(wins))})
        grupo[modo] = {"tramos": tramos, "pares": len(pares)}
    return por, grupo


# ---------------------------------------------------------------- generar

def generar(db: sqlite3.Connection, filas_por: dict[str, list[dict]], escribir: Callable, indices: dict | None = None) -> None:
    if indices is not None:
        cp, cg = curvas(indices)
        nota = ("Tu índice por partida (el de la tendencia, contra tu franja y rol) menos tu nivel normal en ese rol, "
                "según cuántas partidas llevabas con el campeón en ese rol. 0 = tu nivel normal.")
        tramos = [f"{a}–{b}" if b < 10_000 else f"{a}+" for a, b in TRAMOS_CURVA]
        escribir("curvas/grupo.json", {"modos": cg, "tramos": tramos, "nota": nota,
                                       "nota_grupo": "Solo campeones que aparecen después del primer mes del historial "
                                                     "(el historial arranca el 8/1: antes no se sabe si eran nuevos)."})
        for pid, d in cp.items():
            escribir(f"curvas/{pid}.json", {"modos": d, "tramos": tramos, "nota": nota})
    m = modelo(db)
    escribir("modelo_victoria.json", {**m, "equivalencias": _equivalencias(m)})
    if m["validacion"]["aprobado"]:  # sin un modelo validado no se publica nada que dependa de él
        ms, partidas = muertes_y_partidas(db, m)
        por, mediana = muertes(ms, filas_por)
        nota = ("Costo de una muerte: cuánta probabilidad de ganar pierde tu equipo por ella, medida un minuto "
                "después: la kill, su oro y lo que el rival tomó en ese minuto. En puntos de 0 a 100.")
        for pid, d in por.items():
            escribir(f"muertes/{pid}.json", {"modos": d, "mediana_grupo": mediana, "zonas": ZONAS, "nota": nota})
        for mid, d in partidas.items():
            escribir(f"partida/{mid}.json", d)
    por, grupo = rachas(db, list(filas_por))
    textos = {"estados": ESTADOS, "sesion_min": CFG["sesion_min"], "corte_min": CFG["corte_min"],
              "largas_desde": CFG["largas_desde"]}
    escribir("rachas/grupo.json", {**textos, "modos": grupo,
                                   "nota": "Diferencias de Mantel–Haenszel: cada persona contra sí misma, en puntos "
                                           "de winrate. 'Ruido' si el intervalo cruza el cero."})
    for pid, d in por.items():
        escribir(f"rachas/{pid}.json", {**textos, "modos": d})
