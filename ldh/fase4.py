"""Fase 4: equipos (5 ideal, balanceador de inhouses), matchups, heatmaps y jungla.

Reglas del doc de lecciones que pesan acá:
- 13. Rol no es clase: la experiencia que cuenta es la del par (campeón, posición).
- 14. Muestra mínima también al recomendar: nadie va a un rol con menos de `min_rol` partidas.
- Balanceador: experiencia mínima por posición, no el mismo campeón en los dos equipos, y si no
  hay ninguna asignación donde todos cumplan, decirlo y mostrar el mejor compromiso.
- 4. No mezclar contextos: heatmaps y jungla van separados por lado del mapa.
"""

from __future__ import annotations

import gzip
import itertools
import json
import sqlite3
from collections import defaultdict
from typing import Callable

from . import estadistica as est
from .ajustes import AJUSTES, CACHE
from .almacen import _ruta
from .fase2 import colas_de

CFG = AJUSTES["fase4"]
ROLES = ["Top", "Jungla", "Mid", "ADC", "Support"]
GRIETA = ("solo", "flex", "normal")
K = AJUSTES["ajuste_muestra"]["k_tasa"]


def _aj(w: int, n: int) -> float:
    return (w + K * 0.5) / (n + K)


# ------------------------------------------------------------------ equipos

def equipos(filas_por: dict[str, list[dict]], nombres: dict) -> dict:
    """Por persona y rol: partidas, winrate ajustado y campeones jugados ahí (todas las colas de Grieta).
    Es lo que usan el 5 ideal y el balanceador de la web y del bot."""
    jugadores = {}
    for pid, filas in filas_por.items():
        roles = {}
        for rol in ROLES:
            g = [f for f in filas if f["cola"] in GRIETA and f["rol_ldh"] == rol]
            if not g:
                continue
            w = sum(f["win"] for f in g)
            champs = defaultdict(list)
            for f in g:
                champs[f["champion_id"]].append(f["win"])
            top = sorted(((c, len(v), sum(v)) for c, v in champs.items() if len(v) >= CFG["min_campeon"]),
                         key=lambda x: (-_aj(x[2], x[1]), -x[1]))[:6]
            roles[rol] = {"n": len(g), "wr_aj": round(_aj(w, len(g)), 3), "winrate": est.wilson(w, len(g)),
                          "campeones": [{"id": c, "n": n, "wr_aj": round(_aj(ww, n), 3)} for c, n, ww in top]}
        if roles:
            jugadores[pid] = {"nombre": nombres.get(pid, pid), "roles": roles}
    return {"min_rol": CFG["min_rol"], "min_campeon": CFG["min_campeon"], "jugadores": jugadores,
            "ideal": ideal(jugadores),
            "nota": "Fuerza = winrate ajustado en ese rol (suma 10 partidas al 50 %), en solo, flex y normales juntas. "
                    "Nadie va a un rol con menos de min_rol partidas ahí."}


def ideal(jugadores: dict, top: int = 3) -> list[dict]:
    """Las mejores asignaciones de 5 personas distintas a los 5 roles, con muestra mínima en cada uno."""
    cand = {rol: sorted(((pid, j["roles"][rol]) for pid, j in jugadores.items()
                         if rol in j["roles"] and j["roles"][rol]["n"] >= CFG["min_rol"]),
                        key=lambda x: -x[1]["wr_aj"])[:8] for rol in ROLES}
    if any(not c for c in cand.values()):
        return []
    mejores = []
    for combo in itertools.product(*(cand[r] for r in ROLES)):
        pids = [pid for pid, _ in combo]
        if len(set(pids)) < 5:
            continue
        fuerza = sum(r["wr_aj"] for _, r in combo) / 5
        mejores.append((fuerza, combo))
    mejores.sort(key=lambda x: -x[0])
    return [{"fuerza": round(f, 3), "equipo": [{"rol": rol, "persona": pid, "n": r["n"], "wr_aj": r["wr_aj"]}
                                               for rol, (pid, r) in zip(ROLES, combo)]} for f, combo in mejores[:top]]


# ------------------------------------------------------------------ matchups

def matchups(db: sqlite3.Connection, filas: list[dict]) -> list[dict]:
    """Contra cada campeón rival directo (misma posición, otro equipo), por cola y rol."""
    rivales = {}
    for m, team, pos, champ in db.execute("SELECT match_id, team_id, team_position, champion_id FROM participantes"):
        if pos:
            rivales[(m, 300 - team, pos)] = champ
    grupos = defaultdict(list)
    for f in filas:
        rc = rivales.get((f["match_id"], f.get("team_id"), f.get("team_position")))
        if rc is not None and f["cola"] in GRIETA and f["rol_ldh"]:
            for c in colas_de(f):
                grupos[(c, f["rol_ldh"], rc)].append(f)
    out = []
    for (cola, rol, rc), g in grupos.items():
        w = sum(f["win"] for f in g)
        out.append({"cola": cola, "rol": rol, "rival": rc, "n": len(g), "winrate": est.wilson(w, len(g)),
                    "wr_aj": round(_aj(w, len(g)), 3), "muestra_chica": len(g) < CFG["min_matchup"],
                    "dif_oro15": est.media([f.get("gold_diff_at_15") for f in g])})
    return sorted(out, key=lambda x: (x["muestra_chica"], -x["n"]))


# ------------------------------------------------------------------ heatmaps

def heatmaps(db: sqlite3.Connection, pid: str) -> dict:
    """Dónde morís y dónde matás (eventos de la timeline con posición), por lado, cola, rol y minuto."""
    q = """SELECT e.minuto, e.x, e.y, pt.lado, pa.cola, pt.rol, ? AS tipo
           FROM eventos e JOIN partidas pa USING(match_id)
           JOIN participantes pt ON pt.match_id = e.match_id AND pt.participant_id = e.{col}
           WHERE e.tipo = 'CHAMPION_KILL' AND pt.persona_id = ? AND e.x IS NOT NULL AND pa.cola IN ('solo','flex','normal')"""
    puntos = []
    for tipo, col in (("muerte", "victima"), ("kill", "actor")):
        for minuto, x, y, lado, cola, rol, t in db.execute(q.format(col=col), (tipo, pid)):
            puntos.append([round(minuto, 1), x, y, lado, cola, rol or "", t])
    return {"mapa": {"x_max": 14870, "y_max": 14980}, "campos": ["minuto", "x", "y", "lado", "cola", "rol", "tipo"],
            "puntos": puntos}


# ------------------------------------------------------------------ jungla

def _lado_inicio(tl: dict, pid: int) -> str | None:
    """Arriba o abajo en el minuto 1, cuando el jungla espera en su primer campamento (salen al 1:30).
    En las coordenadas de Grieta, y > x es la mitad de arriba para los dos equipos. Es el mismo criterio
    que Coach AI (arriba1); con el minuto 2 ya se había movido y daba al revés (rojo 17 % arriba)."""
    frames = tl["info"]["frames"]
    f = next((fr for fr in frames if fr["timestamp"] >= 60_000), None)
    pos = ((f or {}).get("participantFrames", {}).get(str(pid)) or {}).get("position")
    if not pos:
        return None
    return "arriba" if pos["y"] > pos["x"] else "abajo"


def jungla(db: sqlite3.Connection, pid: str) -> dict | None:
    """¿Qué tan predecible es tu jungla? De qué lado arrancás, separado por lado del mapa (regla 4),
    y si te cambia el resultado arrancar de un lado u otro."""
    ruta_cache = CACHE / "fase4_jungla.json.gz"
    cache = json.loads(gzip.decompress(ruta_cache.read_bytes())) if ruta_cache.exists() else {}
    filas = list(db.execute("""SELECT pa.match_id, pa.inicio_ms, pt.participant_id, pt.lado, pt.win
                               FROM partidas pa JOIN participantes pt USING(match_id)
                               WHERE pt.persona_id = ? AND pt.rol = 'Jungla' AND pa.cola IN ('solo','flex','normal')
                                 AND pa.tiene_timeline = 1""", (pid,)))
    if len(filas) < CFG["min_jungla"]:
        return None
    nuevas = False
    por_lado = defaultdict(list)
    for m, ini, part, lado, win in filas:
        clave = f"{m}:{part}"
        if clave not in cache:
            tl = json.loads(gzip.decompress(_ruta("timelines", m, ini).read_bytes()))
            cache[clave] = _lado_inicio(tl, part)
            nuevas = True
        if cache[clave]:
            por_lado[lado].append((cache[clave], win))
    if nuevas:
        ruta_cache.parent.mkdir(parents=True, exist_ok=True)
        ruta_cache.write_bytes(gzip.compress(json.dumps(cache).encode(), 6))
    out = {}
    for lado, g in por_lado.items():
        if len(g) < CFG["min_jungla_lado"]:
            continue
        arriba = [w for s, w in g if s == "arriba"]
        abajo = [w for s, w in g if s == "abajo"]
        p = est.fisher(sum(arriba), len(arriba) - sum(arriba), sum(abajo), len(abajo) - sum(abajo)) if arriba and abajo else None
        prop = est.wilson(len(arriba), len(g))
        mayor = max(prop["v"], 1 - prop["v"])
        lo_mayor = prop["lo"] if prop["v"] >= 0.5 else 1 - prop["hi"]
        out[lado] = {"n": len(g), "arriba": prop, "wr_arriba": est.wilson(sum(arriba), len(arriba)),
                     "wr_abajo": est.wilson(sum(abajo), len(abajo)), "p": None if p is None else round(p, 3),
                     # Predecible: el lado más usado, con todo su intervalo, pasa el umbral.
                     "predecible": lo_mayor > CFG["umbral_predecible"], "lado_habitual": "arriba" if prop["v"] >= 0.5 else "abajo",
                     "pct_habitual": round(mayor, 3),
                     # Arriba es el buff azul del lado azul y el rojo del lado rojo (y al revés abajo).
                     "buff_habitual": ("azul" if (lado == "azul") == (prop["v"] >= 0.5) else "rojo")}
    return {"umbral": CFG["umbral_predecible"], "lados": out} if out else None


def generar(db: sqlite3.Connection, filas_por: dict[str, list[dict]], nombres: dict, escribir: Callable) -> None:
    escribir("equipos.json", equipos(filas_por, nombres))
    for pid, filas in filas_por.items():
        escribir(f"matchups/{pid}.json", {"min": CFG["min_matchup"], "tabla": matchups(db, filas)})
        escribir(f"heatmap/{pid}.json", heatmaps(db, pid))
        escribir(f"jungla/{pid}.json", jungla(db, pid) or {})
