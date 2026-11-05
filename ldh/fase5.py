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
import warnings
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


GIROS_VOD = 3  # minutos que más movieron la chance
MUERTES_VOD = 3  # muertes de vinculados que más la bajaron
CLASES_VOD = ("baron", "ancestral", "dragon", "heraldo", "larva", "torre", "inhib")


def momentos(p: V.Partida, m: dict, muertes_p: list[dict]) -> list[dict]:
    """Para revisar en el VOD: los minutos donde más se movió la chance (con lo que pasó en ese minuto) y
    las muertes de vinculados que más la bajaron, ordenados por tiempo. El signo del giro es el del azul
    (como la curva); quien lo muestra lo da vuelta según el lado. Es una estimación del modelo, no la causa.
    Los giros se miden entre frames (no en el minuto redondo, que cae unos ms antes del frame y deja el oro
    de ese minuto afuera), así el oro y los eventos del tramo quedan juntos."""
    tf = p.t_frames
    q = [V.prob(m, p.estado(t)) for t in tf]
    saltos = sorted(range(1, len(tf)), key=lambda k: -abs(q[k] - q[k - 1]))
    out = []
    for k in saltos[:GIROS_VOD]:
        delta = round(q[k] - q[k - 1], 3)
        if abs(delta) < 0.02:  # menos de 2 puntos no es un momento
            continue
        desde, hasta = tf[k - 1], tf[k]
        ev = [(t, c, eq) for t, c, eq, _ in p.eventos if desde < t <= hasta and (c == "kill" or c in CLASES_VOD)]
        kills = {100: sum(1 for _, c, eq in ev if c == "kill" and eq == 100),
                 200: sum(1 for _, c, eq in ev if c == "kill" and eq == 200)}
        out.append({"tipo": "giro", "t": ev[0][0] if ev else desde, "desde": desde, "hasta": hasta,
                    "delta": delta, "kills": {"azul": kills[100], "rojo": kills[200]},
                    "objetivos": [{"tipo": c, "equipo": eq} for _, c, eq in ev if c != "kill"]})
    for d in sorted(muertes_p, key=lambda d: -d["costo"])[:MUERTES_VOD]:
        if d["costo"] < 0.01:
            continue
        x = {"t": d["t"], "persona": d["persona"], "costo": d["costo"], "perdidos": d["perdidos"], "zona": d["zona"]}
        giro = next((g for g in out if g["tipo"] == "giro" and g["desde"] < d["t"] <= g["hasta"]), None)
        if giro:  # cae en un minuto que ya está en la lista: va adentro, no en otra fila
            giro.setdefault("muertes", []).append(x)
        else:
            out.append({"tipo": "muerte", **x})
    return sorted(out, key=lambda x: x["t"])


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
        # En cada frame (no en el minuto redondo, que cae unos ms antes y deja afuera el oro de ese minuto).
        curva = [round(V.prob(m, p.estado(t)), 3) for t in p.t_frames]
        eventos, muertes_p = [], []
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
                    muertes_p.append({**d, "persona": pid})
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
                         "eventos": eventos, "momentos": momentos(p, m, muertes_p),
                         "clave": None if clave is None else
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
                              # Las 400 más recientes de cada rol (con todas, el mapa de quien juega mucho se
                              # tapaba). El rol va al final: la web filtra por rol y en "Todos" toma las últimas 400.
                              "puntos": _puntos_mapa(mm)}
    import statistics
    mediana = {f"{m}|{r}": round(statistics.median(v), 4) for (m, r), v in refs.items() if len(v) >= 3}
    return por, mediana


def _puntos_mapa(muertes: list[dict], tope: int = 400) -> list[list]:
    orden = sorted((d for d in muertes if d["x"] is not None), key=lambda d: (d["inicio"], d["t"]))
    por_rol = defaultdict(list)
    for d in orden:
        por_rol[d["rol"]].append(d)
    quedan = {id(d) for g in por_rol.values() for d in g[-tope:]}
    return [[d["min"], d["x"], d["y"], round(d["costo"], 3), d["rol"]] for d in orden if id(d) in quedan]


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


# ---------------------------------------------------------------- E. pesos aprendidos

def _auc(p, y) -> float:
    """Área bajo la curva ROC (probabilidad de que una victoria tenga más puntaje que una derrota)."""
    import numpy as np
    p, y = np.asarray(p), np.asarray(y)
    orden = np.argsort(p)
    rangos = np.empty(len(p))
    rangos[orden] = np.arange(1, len(p) + 1)
    n1, n0 = y.sum(), len(y) - y.sum()
    return float((rangos[y == 1].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1))


def pesos_aprendidos() -> dict:
    """Qué distingue a los que ganan, por rol (PandaSkill): regresión logística de la victoria sobre el percentil
    por partida de cada componente del Performance, en las partidas de referencia (las tres franjas juntas: los
    percentiles ya son contra la franja de cada uno). Winrate y consistencia quedan fuera: una es el resultado y la
    otra es de jugador, no de partida. IC por bootstrap de jugadores. Se compara cuánto predice en jugadores
    apartados contra los pesos fijos. Ojo: el oro y la participación suben porque se gana; esto mide qué acompaña
    a ganar, no qué lo causa. No cambia el Performance: es para decidir."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from . import fase3 as F3
    from .referencia import cargar_filas
    filas = cargar_filas()
    fijos = F3.PERF["pesos"]
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    out = {}
    for rol in F3.ROLES:
        comps = [(c, ms) for c, _, ms in F3._componentes(rol) if c not in ("winrate", "consistencia")]
        g_rol = [f for f in filas if f["role"] == rol]
        X, y, jug = [], [], []
        for fr in {f["franja"] for f in g_rol}:
            g = [f for f in g_rol if f["franja"] == fr]
            m = F3._matriz(g)
            m["kda"] = (m["_k"] + m["_a"]) / np.maximum(m["_d"], 1)
            pct = {}
            for _, ms in comps:
                for k in ms:
                    if k in m and k not in pct:
                        ref = np.sort(m[k][~np.isnan(m[k])])
                        pct[k] = F3._pct(m[k], ref)
            cols = []
            for _, ms in comps:
                ps = [pct[k] for k in ms if k in pct]
                with np.errstate(invalid="ignore"):
                    cols.append(np.nanmean(np.stack(ps), axis=0) if ps else np.full(len(g), np.nan))
            Xg = np.stack(cols, axis=1)
            ok = ~np.isnan(Xg).any(axis=1)
            X.append(Xg[ok])
            y.append(m["_w"][ok])
            jug += [f["jugador"] for f, o in zip(g, ok) if o]
        X, y, jug = np.vstack(X), np.concatenate(y), np.array(jug)
        if len(y) < 200:
            continue
        ajuste = lambda Xa, ya: LogisticRegression(C=1.0, max_iter=1000).fit(Xa - 0.5, ya).coef_[0]  # noqa: E731
        coef = ajuste(X, y)
        jugadores = np.unique(jug)
        idx = {j: np.where(jug == j)[0] for j in jugadores}
        boot = []
        for _ in range(200):
            ii = np.concatenate([idx[j] for j in rng.choice(jugadores, size=len(jugadores))])
            boot.append(ajuste(X[ii], y[ii]))
        boot = np.array(boot)
        # Cuánto predice cada esquema en jugadores apartados (5 grupos por jugador).
        perm = rng.permutation(jugadores)
        pliegue = {j: i % 5 for i, j in enumerate(perm)}
        fold = np.array([pliegue[j] for j in jug])
        p_fijo, p_apr = np.zeros(len(y)), np.zeros(len(y))
        wf = np.array([fijos[c] for c, _ in comps])
        for k in range(5):
            tr, te = fold != k, fold == k
            p_apr[te] = (X[te] - 0.5) @ ajuste(X[tr], y[tr])
            p_fijo[te] = (X[te] - 0.5) @ wf
        positivos = np.maximum(coef, 0)
        total = sum(fijos[c] for c, _ in comps)  # lo que los pesos fijos les dan a estos componentes
        out[rol] = {
            "n_partidas": int(len(y)), "n_jugadores": int(len(jugadores)),
            "componentes": [{"clave": c, "metricas": ms, "coef": round(float(coef[i]), 3),
                             "lo": round(float(np.percentile(boot[:, i], 2.5)), 3),
                             "hi": round(float(np.percentile(boot[:, i], 97.5)), 3),
                             "peso_aprendido": round(float(positivos[i] / positivos.sum() * total), 3) if positivos.sum() else None,
                             "peso_fijo": fijos[c]} for i, (c, ms) in enumerate(comps)],
            "auc_fijo": round(_auc(p_fijo, y), 3), "auc_aprendido": round(_auc(p_apr, y), 3),
        }
    return out


def acompanan_ganar() -> dict:
    """Para mostrar (decisión de LDH: el Performance sigue con pesos fijos). Por rol y componente, cada uno por
    separado: winrate de las partidas con ese componente en la mitad de arriba de la franja contra la mitad de
    abajo, con IC bootstrap por jugador. Por separado y no en un modelo conjunto: juntos, el KDA (casi el
    resultado) se lleva todo y la participación en kills sale negativa por la correlación, lo que confunde."""
    import numpy as np
    from . import fase3 as F3
    from .referencia import cargar_filas
    filas = cargar_filas()
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    nombres = {c: n for c, n, _ in F3._componentes("Top")}
    out = {}
    for rol in F3.ROLES:
        comps = [(c, ms) for c, _, ms in F3._componentes(rol) if c not in ("winrate", "consistencia")]
        cols, ys, jug = defaultdict(list), [], []
        for fr in sorted({f["franja"] for f in filas if f["role"] == rol}):
            g = [f for f in filas if f["role"] == rol and f["franja"] == fr]
            m = F3._matriz(g)
            m["kda"] = (m["_k"] + m["_a"]) / np.maximum(m["_d"], 1)
            for c, ms in comps:
                ps = []
                for k in ms:
                    if k in m:
                        ref = np.sort(m[k][~np.isnan(m[k])])
                        ps.append(F3._pct(m[k], ref))
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    cols[c].append(np.nanmean(np.stack(ps), axis=0))
            ys.append(m["_w"])
            jug += [f["jugador"] for f in g]
        y, jug = np.concatenate(ys), np.array(jug)
        jugadores = np.unique(jug)
        idx = {j: np.where(jug == j)[0] for j in jugadores}
        res = []
        for c, ms in comps:
            x = np.concatenate(cols[c])
            ok = ~np.isnan(x)
            arriba, abajo = ok & (x >= 0.5), ok & (x < 0.5)
            dif = y[arriba].mean() - y[abajo].mean()
            boot = []
            for _ in range(300):
                ii = np.concatenate([idx[j] for j in rng.choice(jugadores, size=len(jugadores))])
                xa, ya, oka = x[ii], y[ii], ok[ii]
                a, b = oka & (xa >= 0.5), oka & (xa < 0.5)
                if a.sum() and b.sum():
                    boot.append(ya[a].mean() - ya[b].mean())
            res.append({"clave": c, "nombre": nombres.get(c, c), "metricas": ms,
                        "arriba": est.wilson(int(y[arriba].sum()), int(arriba.sum())),
                        "abajo": est.wilson(int(y[abajo].sum()), int(abajo.sum())),
                        "dif": {"v": round(float(dif), 3), "lo": round(float(np.percentile(boot, 2.5)), 3),
                                "hi": round(float(np.percentile(boot, 97.5)), 3)},
                        "peso_fijo": F3.PERF["pesos"][c]})
        out[rol] = {"n_partidas": int(len(y)), "n_jugadores": int(len(jugadores)),
                    "componentes": sorted(res, key=lambda r: -r["dif"]["v"])}
    return out


# ---------------------------------------------------------------- top de compañeros

def companeros(filas_por: dict[str, list[dict]]) -> dict:
    """¿Quién hace ganar más a los demás? Para cada jugador Q y cada compañero P del grupo: el winrate de P con Q
    en su equipo contra sin Q, en el mismo período en que coincidieron (así no pesa que P haya mejorado con el
    tiempo). Se combina entre compañeros con Mantel–Haenszel: cada P contra sí mismo. Por modo. Las filas ya
    traen 'companeros' (fase2._enriquecer)."""
    cfg = AJUSTES["sinergia"]
    out = {}
    for modo, colas in MODOS.items():
        estratos = defaultdict(list)  # Q -> [(ganadas_con, n_con, ganadas_sin, n_sin)] uno por compañero P
        detalle = defaultdict(list)
        for p, filas in filas_por.items():
            de = [f for f in filas if f["cola"] in colas and "companeros" in f]
            for q in {c for f in de for c in f["companeros"]}:
                con = [f for f in de if q in f["companeros"]]
                if len(con) < cfg["min_juntos"]:
                    continue
                t0, t1 = min(f["inicio_ms"] for f in con), max(f["inicio_ms"] for f in con)
                sin = [f for f in de if q not in f["companeros"] and t0 <= f["inicio_ms"] <= t1]
                if not sin:
                    continue
                wc, ws = sum(f["win"] for f in con), sum(f["win"] for f in sin)
                estratos[q].append((wc, len(con), ws, len(sin)))
                detalle[q].append({"companero": p, "juntos": len(con), "con": est.wilson(wc, len(con)),
                                   "sin": est.wilson(ws, len(sin))})
        tabla = []
        for q, es in estratos.items():
            mh = _mh(es)
            juntos = sum(e[1] for e in es)
            tabla.append({"persona": q, "suma": mh, "companeros": len(es), "juntos": juntos,
                          "con": est.wilson(sum(e[0] for e in es), juntos),
                          "muestra_chica": juntos < cfg["min_mejor"] * 3 or len(es) < 2,
                          "detalle": sorted(detalle[q], key=lambda d: -d["juntos"])})
        # Son ~20 personas a la vez: alguna "señal" saldría por azar. p de la normal del MH y Benjamini–Hochberg,
        # como en la sinergia de dúos.
        ps = []
        for r in tabla:
            s = r["suma"]
            se = (s["hi"] - s["lo"]) / (2 * 1.959964) if s["v"] is not None else None
            ps.append(math.erfc(abs(s["v"]) / se / math.sqrt(2)) if se else 1.0)
        for r, p, pa in zip(tabla, ps, est.benjamini_hochberg(ps) if ps else []):
            r["p"], r["p_bh"] = est._r(p, 4), est._r(pa, 4)
            r["senal"] = pa < AJUSTES["ajuste_muestra"]["alfa"] and not r["muestra_chica"]
        tabla.sort(key=lambda r: (r["muestra_chica"], -(r["suma"]["v"] or -1)))
        out[modo] = tabla
    return out


MIN_DUO = 15


def _logit(p: float) -> float:
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def _esperado_duo(pa: float, pb: float) -> float:
    """Lo que darían juntos si cada uno aporta lo suyo: logit(e) = logit(a) + logit(b) − logit(0,5)."""
    return 1 / (1 + math.exp(-(_logit(pa) + _logit(pb))))


def duos(filas_por: dict[str, list[dict]]) -> dict:
    """¿Rinden juntos más de lo que da cada uno por separado? Para cada pareja con MIN_DUO+ partidas en el mismo
    equipo: el winrate de cada uno sin el otro en el mismo período (de la primera a la última juntos) da el
    esperado; se compara con el real. Intervalo y p por bootstrap paramétrico (también el esperado tiene ruido)
    y BH entre parejas dentro de cada modo."""
    import numpy as np
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    reps = AJUSTES["bootstrap_reps"]
    min_sin = AJUSTES["min_partidas"]
    out = {}
    for modo, colas in MODOS.items():
        de = {p: [f for f in fs if f["cola"] in colas and "companeros" in f] for p, fs in filas_por.items()}
        tabla = []
        for a in sorted(de):
            for b in sorted({c for f in de[a] for c in f["companeros"]}):
                if b <= a or b not in de:
                    continue
                juntos = [f for f in de[a] if b in f["companeros"]]
                if len(juntos) < MIN_DUO:
                    continue
                t0, t1 = min(f["inicio_ms"] for f in juntos), max(f["inicio_ms"] for f in juntos)
                sin_a = [f["win"] for f in de[a] if b not in f["companeros"] and t0 <= f["inicio_ms"] <= t1]
                sin_b = [f["win"] for f in de[b] if a not in f["companeros"] and t0 <= f["inicio_ms"] <= t1]
                if len(sin_a) < min_sin or len(sin_b) < min_sin:
                    continue
                n, w = len(juntos), sum(f["win"] for f in juntos)
                na, wa, nb, wb = len(sin_a), sum(sin_a), len(sin_b), sum(sin_b)
                e = _esperado_duo(wa / na, wb / nb)
                # Bootstrap paramétrico: se vuelven a sortear las tres muestras con sus proporciones.
                ra, rb, rj = rng.binomial(na, wa / na, reps) / na, rng.binomial(nb, wb / nb, reps) / nb, rng.binomial(n, w / n, reps) / n
                la, lb = np.log(np.clip(ra, 1e-3, 1 - 1e-3) / (1 - np.clip(ra, 1e-3, 1 - 1e-3))), \
                    np.log(np.clip(rb, 1e-3, 1 - 1e-3) / (1 - np.clip(rb, 1e-3, 1 - 1e-3)))
                difs = rj - 1 / (1 + np.exp(-(la + lb)))
                p = min(1.0, max(1 / reps, 2 * min(float((difs <= 0).mean()), float((difs >= 0).mean()))))
                tabla.append({"a": a, "b": b, "juntos": n, "ganadas": w, "real": est.wilson(w, n),
                              "sin_a": est.wilson(wa, na), "sin_b": est.wilson(wb, nb), "esperado": round(e, 4),
                              "dif": {"v": round(w / n - e, 4), "lo": round(float(np.percentile(difs, 2.5)), 4),
                                      "hi": round(float(np.percentile(difs, 97.5)), 4)},
                              "p": round(p, 4), "muestra_chica": n < MIN_DUO * 2})
        for r, q in zip(tabla, est.benjamini_hochberg([r["p"] for r in tabla]) if tabla else []):
            r["p_bh"] = round(q, 4)
            r["senal"] = q < AJUSTES["ajuste_muestra"]["alfa"] and not r["muestra_chica"]
        tabla.sort(key=lambda r: (r["muestra_chica"], not r["senal"], -r["dif"]["v"]))
        out[modo] = tabla
    return out


NOTA_DUOS = ("El esperado combina el winrate de cada uno sin el otro en el mismo período (de la primera a la última "
             "partida juntos): si cada uno aporta lo suyo, juntos darían eso. Juntos − esperado es lo que suma la pareja "
             "además. Intervalo y p por bootstrap (el esperado también tiene ruido), con corrección BH entre parejas. "
             "Es una asociación: también pesan la cola, el horario y contra quién juegan cuando van juntos. 'Muestra "
             "chica' con menos de 30 partidas juntos.")


# ---------------------------------------------------------------- F. pool objetivo (Machine LoLing)

ULTIMAS_POOL = 20


def cargar_pools() -> dict:
    """Las pools que declaró cada uno con -pool (repo ldh-lol-metas, montado en ./metas). Sin el repo, nada."""
    import os
    from pathlib import Path
    from .ajustes import RAIZ
    ruta = Path(os.environ.get("LDH_METAS", RAIZ / "metas")) / "pools.json"
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _iso_ms(iso: str) -> int | None:
    from datetime import datetime
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)
    except (AttributeError, ValueError):
        return None


def _media_idx(xs: list[float], reps: int, rng) -> dict:
    v, lo, hi = _boot_media([[x] for x in xs], reps, rng)
    return {"v": v, "lo": lo, "hi": hi, "n": len(xs)}


def pool_objetivo(pools: dict, filas_por: dict[str, list[dict]], indices: dict, curvas_por: dict) -> dict:
    """Por persona, rol y modo: cuánto se juega con la pool declarada y cómo va dentro y fuera de ella.
    Las partidas son de Grieta; el índice es el de la tendencia (contra la franja y el rol)."""
    import numpy as np
    reps = AJUSTES["bootstrap_reps"] // 4
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    minimo = AJUSTES["min_partidas"]
    out = {}
    for pid, por_rol in pools.items():
        if pid not in filas_por or not isinstance(por_rol, dict):
            continue  # solo se publican las personas vinculadas
        idx_de = {(i, rol, ch): x for i, _, rol, ch, x, _ in indices.get(pid, [])}
        roles = {}
        for rol, decl in por_rol.items():
            campeones = [int(c) for c in (decl or {}).get("campeones") or [] if str(c).isdigit()]
            desde = _iso_ms((decl or {}).get("desde", ""))
            if not campeones or desde is None:
                continue
            modos = {}
            for modo, colas in MODOS.items():
                g = sorted((f for f in filas_por[pid] if f["cola"] in colas and f["rol_ldh"] == rol),
                           key=lambda f: f["inicio_ms"])
                if not g:
                    continue
                dentro = lambda f: f["champion_id"] in campeones  # noqa: E731
                idx = lambda f: idx_de.get((f["inicio_ms"], rol, f["champion_id"]))  # noqa: E731
                ult = g[-ULTIMAS_POOL:]
                antes = [f for f in g if f["inicio_ms"] < desde]
                despues = [f for f in g if f["inicio_ms"] >= desde]
                d_in = [f for f in despues if dentro(f)]
                d_out = [f for f in despues if not dentro(f)]
                wi, wo = sum(f["win"] for f in d_in), sum(f["win"] for f in d_out)
                ia = [x for f in d_in if (x := idx(f)) is not None]
                io_ = [x for f in d_out if (x := idx(f)) is not None]
                cmp_dentro = {
                    "dentro": est.wilson(wi, len(d_in)), "fuera": est.wilson(wo, len(d_out)),
                    "dif": est.diferencia([float(f["win"]) for f in d_in], [float(f["win"]) for f in d_out]),
                    "p": est._r(est.fisher(wi, len(d_in) - wi, wo, len(d_out) - wo), 4) if d_in and d_out else None,
                    "indice_dentro": _media_idx(ia, reps, rng), "indice_fuera": _media_idx(io_, reps, rng),
                    "dif_indice": est.diferencia(ia, io_) if ia and io_ else None,
                    "muestra_chica": min(len(d_in), len(d_out)) < minimo,
                }
                ia_ = [x for f in antes if (x := idx(f)) is not None]
                id_ = [x for f in despues if (x := idx(f)) is not None]
                pa, pd = sum(map(dentro, antes)), sum(map(dentro, despues))
                cmp_antes = {
                    "prop_antes": est.wilson(pa, len(antes)), "prop_despues": est.wilson(pd, len(despues)),
                    "dif_prop": est.diferencia([float(dentro(f)) for f in despues], [float(dentro(f)) for f in antes]),
                    "indice_antes": _media_idx(ia_, reps, rng), "indice_despues": _media_idx(id_, reps, rng),
                    "dif_indice": est.diferencia(id_, ia_) if ia_ and id_ else None,
                    "muestra_chica": min(len(antes), len(despues)) < minimo,
                }
                curva = {c["champ"]: c for c in (curvas_por.get(pid, {}).get(modo) or {}).get("campeones", [])
                         if c["rol"] == rol}
                por_champ = []
                for ch in campeones:
                    gc = [f for f in g if f["champion_id"] == ch]
                    xs = [x for f in gc if (x := idx(f)) is not None]
                    c = curva.get(ch)
                    por_champ.append({
                        "champ": ch, "n": len(gc), "winrate": est.wilson(sum(f["win"] for f in gc), len(gc)),
                        "indice": _media_idx(xs, reps, rng),
                        "estado": c["estado"] if c else "pocas partidas", "ahora": c["ahora"] if c else None})
                modos[modo] = {
                    "cumplimiento": {**est.wilson(sum(map(dentro, ult)), len(ult)), "ultimas": len(ult)},
                    "desde_que_la_declaraste": cmp_dentro, "antes_y_despues": cmp_antes,
                    "campeones": por_champ, "n_despues": len(despues),
                }
            roles[rol] = {"campeones": campeones, "desde": decl["desde"], "modos": modos}
        if roles:
            out[pid] = roles
    return out


NOTA_POOL = ("Tu pool objetivo la armás en el Pool Designer de Machine LoLing y la traés con -pool en el bot. "
             "Cumplimiento: qué parte de tus últimas 20 partidas del rol fueron con la pool. Dentro contra fuera: "
             "desde que la declaraste. Antes y después: cuánto jugabas esos campeones y tu nota de partida. Son asociaciones: "
             "también cambian el parche, tus rivales y tu práctica. La nota de partida es la de la tendencia (50 = la "
             "mediana de tu franja). 'Muestra chica' si algún lado tiene menos de 10 partidas.")


# ---------------------------------------------------------------- F. conversión de ventajas

MIN_P15 = 15  # la probabilidad se mide al minuto 15; hace falta que la partida llegue al 16
TRAMOS_P15 = {"ventaja": (0.6, 1.01), "pareja": (0.4, 0.6), "desventaja": (-0.01, 0.4)}
MIN_CONVERSION = 15


def _p15(partidas: dict, filas_por: dict) -> dict[str, list[tuple[str, str, float, int]]]:
    """Por persona: (match, cola, p15 de su equipo, ganó) en las partidas publicadas con timeline de 16+ min."""
    out = defaultdict(list)
    for pid, filas in filas_por.items():
        for f in filas:
            d = partidas.get(f["match_id"])
            if not d or len(d["curva"]) <= MIN_P15 + 1 or pid not in d["lados"]:
                continue
            azul = d["lados"][pid] == "azul"
            p = d["curva"][MIN_P15] if azul else 1 - d["curva"][MIN_P15]
            out[pid].append((f["match_id"], f["cola"], p, int(d["ganador"] == (100 if azul else 200))))
    return out


def _residuo(xs: list[tuple[float, int]], reps: int, rng) -> dict:
    """Victorias reales menos esperadas por partida, con IC bootstrap (cada partida es independiente)."""
    import numpy as np
    if not xs:
        return {"n": 0}
    p = np.array([a for a, _ in xs])
    y = np.array([b for _, b in xs])
    r = y - p
    medias = r[rng.integers(0, len(r), (reps, len(r)))].mean(axis=1)
    return {"n": len(r), "ganadas": int(y.sum()), "esperadas": round(float(p.sum()), 1),
            "v": round(float(r.mean()), 4), "lo": round(float(np.percentile(medias, 2.5)), 4),
            "hi": round(float(np.percentile(medias, 97.5)), 4), "var": float((p * (1 - p)).sum())}


def conversion(partidas: dict, filas_por: dict) -> tuple[dict, dict]:
    """(por persona, grupo) por modo y tramo de p15. El modelo se entrenó con estas partidas, así que el residuo
    del grupo sale cerca de cero por construcción: lo que se mira es cada persona contra el grupo, con una prueba
    normal (varianza de la suma de Bernoulli) y BH entre personas dentro de cada modo y tramo."""
    import numpy as np
    reps = AJUSTES["bootstrap_reps"] // 4
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    p15 = _p15(partidas, filas_por)
    por, grupo = defaultdict(dict), {}
    for modo, colas in MODOS.items():
        grupo[modo] = {}
        for tramo, (a, b) in TRAMOS_P15.items():
            filas = {pid: [(p, y) for _, c, p, y in xs if c in colas and a <= p < b] for pid, xs in p15.items()}
            # El grupo: cada partida una vez por equipo (dos del grupo en el mismo equipo no cuentan doble).
            vistos, todas = set(), []
            for pid, xs in p15.items():
                for mid, c, p, y in xs:
                    if c in colas and a <= p < b and (mid, y) not in vistos:
                        vistos.add((mid, y))
                        todas.append((p, y))
            g = _residuo(todas, reps, rng)
            g.pop("var", None)
            grupo[modo][tramo] = g
            pruebas = []
            for pid, xs in filas.items():
                r = _residuo(xs, reps, rng)
                var = r.pop("var", None)
                if r["n"]:
                    r["muestra_chica"] = r["n"] < MIN_CONVERSION
                    if var and g.get("v") is not None and not r["muestra_chica"]:  # con pocas, ni se prueba
                        z = (r["v"] - g["v"]) * r["n"] / math.sqrt(var)
                        r["p"] = round(math.erfc(abs(z) / math.sqrt(2)), 4)
                        pruebas.append((pid, r))
                    r["contra_grupo"] = round(r["v"] - g["v"], 4) if g.get("v") is not None else None
                por[pid].setdefault(modo, {})[tramo] = r
            for (pid, r), q in zip(pruebas, est.benjamini_hochberg([r["p"] for _, r in pruebas])):
                r["p_bh"] = round(q, 4)
                r["senal"] = q < 0.05 and not r["muestra_chica"]
    return dict(por), grupo


NOTA_CONVERSION = ("Con la probabilidad de ganar que da el modelo al minuto 15 (partidas de 16 minutos o más): en las que "
                   "tu equipo iba arriba (60 % o más), ¿se ganaron más o menos de lo que se esperaba? Y en las que iba "
                   "abajo (40 % o menos), ¿se remontaron? Es victorias reales menos esperadas por partida, en puntos. El "
                   "modelo se entrenó con estas mismas partidas, así que el grupo da cerca de cero por construcción: lo "
                   "que importa es cada uno contra el grupo (prueba con corrección BH entre personas). Es del equipo, no "
                   "solo tuyo, y es una asociación.")


# ---------------------------------------------------------------- G. valor de los objetivos

MINUTOS_OBJ = (10, 15, 20, 25)
# (clave del estado, nombre, cuánto suma, minutos en que tiene sentido)
OBJETIVOS_VALOR = (("dragones", "Un dragón", 1, MINUTOS_OBJ), ("larvas", "Una larva", 1, (10,)),
                   ("heraldo", "El Heraldo", 1, (15, 20)), ("torres", "Una torre", 1, MINUTOS_OBJ),
                   ("inhib", "Un inhibidor caído", 1, (20, 25)), ("baron", "El Barón activo", 1, (20, 25)))
REPS_OBJ = 50


def _valores(coef: dict) -> list[dict]:
    """En un estado parejo (todo igual, sin el término de lado): cuánto sube la probabilidad cada objetivo y su
    equivalente en oro. Incluye el oro que da al equipo (Barón y torre), que el modelo ve en la diferencia de oro."""
    out = []
    for clave, nombre, val, minutos in OBJETIVOS_VALOR:
        for t in minutos:
            tramo = max(a for a in V.TRAMOS if t >= a)
            k = f"{clave}_{tramo}" if clave in V.POR_TRAMO else clave
            oro_c = coef[f"oro_{tramo}"] / 1000
            z = coef[k] * val + ORO_OBJETIVO.get({"torres": "torre"}.get(clave, clave), 0) * oro_c
            out.append({"clave": clave, "nombre": nombre, "min": t, "dp": 1 / (1 + math.exp(-z)) - 0.5,
                        "oro": z / oro_c})
    return out


def valor_objetivos(db: sqlite3.Connection, m: dict) -> dict:
    """Valor de cada objetivo con IC de bootstrap por partida (se reentrena el modelo REPS_OBJ veces). Se cachea."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from .ajustes import CACHE
    ruta = CACHE / "fase5_objetivos.json"
    clave = f"v{V.VERSION}:{m['partidas']}:{REPS_OBJ}"
    if ruta.exists():
        c = json.loads(ruta.read_text(encoding="utf-8"))
        if c.get("clave") == clave:
            return c["datos"]
    base = _valores(dict(zip(m["variables"], m["coef"])))
    X, y, mids, _, _ = V._filas(db)
    unicas = np.unique(mids)
    idx = {g: np.where(mids == g)[0] for g in unicas}
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    reps = []
    for _ in range(REPS_OBJ):
        ii = np.concatenate([idx[g] for g in rng.choice(unicas, size=len(unicas))])
        fit = LogisticRegression(C=1.0, max_iter=2000, fit_intercept=False).fit(*V._simetrico(X[ii], y[ii]))
        reps.append(_valores(dict(zip(m["variables"], fit.coef_[0]))))
    filas = []
    for i, b in enumerate(base):
        dps, oros = [r[i]["dp"] for r in reps], [r[i]["oro"] for r in reps]
        filas.append({"clave": b["clave"], "nombre": b["nombre"], "min": b["min"],
                      "dp": {"v": round(b["dp"], 4), "lo": round(float(np.percentile(dps, 2.5)), 4),
                             "hi": round(float(np.percentile(dps, 97.5)), 4)},
                      "oro": {"v": round(b["oro"]), "lo": round(float(np.percentile(oros, 2.5))),
                              "hi": round(float(np.percentile(oros, 97.5)))}})
    datos = {"filas": filas, "minutos": list(MINUTOS_OBJ), "reps": REPS_OBJ, "partidas": m["partidas"]}
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"clave": clave, "datos": datos}, ensure_ascii=False), encoding="utf-8")
    return datos


NOTA_OBJETIVOS = ("Cuánto sube la probabilidad de ganar de tu equipo cada objetivo, según el modelo, en una partida pareja "
                  "(mismo oro, XP, kills y torres). Incluye el oro que da al equipo (Barón y torres). El equivalente en "
                  "oro es la diferencia de oro que pesaría lo mismo en ese minuto. Es nuestro elo (LAS, de Hierro a "
                  "Esmeralda) y una estimación del modelo, no un experimento: si el rival te da un objetivo es porque "
                  "algo más pasaba. El intervalo sale de reentrenar el modelo con partidas remuestreadas.")


# ---------------------------------------------------------------- generar

def generar(db: sqlite3.Connection, filas_por: dict[str, list[dict]], escribir: Callable, indices: dict | None = None) -> None:
    if indices is not None:
        cp, cg = curvas(indices)
        nota = ("Tu nota de partida (la de la tendencia, contra tu franja y rol) menos tu nivel normal en ese rol, "
                "según cuántas partidas llevabas con el campeón en ese rol. 0 = tu nivel normal.")
        tramos = [f"{a}–{b}" if b < 10_000 else f"{a}+" for a, b in TRAMOS_CURVA]
        escribir("curvas/grupo.json", {"modos": cg, "tramos": tramos, "nota": nota,
                                       "nota_grupo": "Solo campeones que aparecen después del primer mes del historial "
                                                     "(el historial arranca el 8/1: antes no se sabe si eran nuevos)."})
        for pid, d in cp.items():
            escribir(f"curvas/{pid}.json", {"modos": d, "tramos": tramos, "nota": nota})
        for pid, d in pool_objetivo(cargar_pools(), filas_por, indices, cp).items():
            escribir(f"pool_objetivo/{pid}.json", {"roles": d, "ultimas": ULTIMAS_POOL, "nota": NOTA_POOL})
    escribir("rankings/companeros.json", {
        "modos": companeros(filas_por),
        "nota": "Cuántos puntos de winrate les suma cada uno a sus compañeros del grupo: el winrate de cada compañero "
                "con él contra sin él, en el mismo período, combinado entre compañeros (Mantel–Haenszel, cada uno "
                "contra sí mismo). 'Ruido' si el intervalo cruza el cero."})
    escribir("rankings/duos.json", {"modos": duos(filas_por), "min_juntos": MIN_DUO, "nota": NOTA_DUOS})
    escribir("acompanan_ganar.json", {
        "roles": acompanan_ganar(),
        "nota": "Cada componente por separado, en las partidas de referencia: winrate cuando está en la mitad de arriba "
                "de la franja contra la mitad de abajo. Acompaña a ganar, no lo causa: el que gana mata más y muere menos. "
                "Tu Performance sigue con los pesos fijos."})
    m = modelo(db)
    objetivos = valor_objetivos(db, m) if m["validacion"]["aprobado"] else None
    escribir("modelo_victoria.json", {**m, "equivalencias": _equivalencias(m),
                                      **({"objetivos": {**objetivos, "nota": NOTA_OBJETIVOS}} if objetivos else {})})
    if m["validacion"]["aprobado"]:  # sin un modelo validado no se publica nada que dependa de él
        ms, partidas = muertes_y_partidas(db, m)
        por, mediana = muertes(ms, filas_por)
        nota = ("Caída estimada por una muerte: el modelo compara a tu equipo un minuto después, con y sin la kill, "
                "su oro y lo que el rival tomó en ese minuto. En puntos de 0 a 100. Es una estimación, no la causa "
                "demostrada: parte de esos objetivos el rival quizás los tomaba igual. No se recortan valores; nunca da "
                "negativa porque en el modelo más oro, kills y objetivos siempre suman, así que eso no prueba nada.")
        for pid, d in por.items():
            escribir(f"muertes/{pid}.json", {"modos": d, "mediana_grupo": mediana, "zonas": ZONAS, "nota": nota})
        for mid, d in partidas.items():
            escribir(f"partida/{mid}.json", d)
        cpor, cgrupo = conversion(partidas, filas_por)
        for pid, d in cpor.items():
            escribir(f"conversion/{pid}.json", {"modos": d, "grupo": cgrupo, "tramos": TRAMOS_P15, "nota": NOTA_CONVERSION})
    por, grupo = rachas(db, list(filas_por))
    textos = {"estados": ESTADOS, "sesion_min": CFG["sesion_min"], "corte_min": CFG["corte_min"],
              "largas_desde": CFG["largas_desde"]}
    escribir("rachas/grupo.json", {**textos, "modos": grupo,
                                   "nota": "Diferencias de Mantel–Haenszel: cada persona contra sí misma, en puntos "
                                           "de winrate. 'Ruido' si el intervalo cruza el cero."})
    for pid, d in por.items():
        escribir(f"rachas/{pid}.json", {**textos, "modos": d})
