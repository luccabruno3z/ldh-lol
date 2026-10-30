"""Fase 2: roles, campeones (con pool), sinergia y rankings.

Todo se compara dentro de cada cola (regla 4) y contra el par correcto: el rival directo
de la misma partida o la mediana del grupo en el mismo rol (regla 8).
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

from . import estadistica as est
from .ajustes import AJUSTES, INICIO_HISTORIAL

MIN = AJUSTES["min_partidas"]
AJ = AJUSTES["ajuste_muestra"]
GRIETA = ("solo", "flex", "normal")
# "todo" junta las tres colas de la Grieta: para quien juega poco de cada una, es la única vista
# con muestra. Las colas por separado siguen siendo la comparación limpia (regla 4).
MODOS = (*GRIETA, "todo")
ROLES = ["Top", "Jungla", "Mid", "ADC", "Support"]
DIA_MS = 86_400_000


def colas_de(f: dict) -> list[str]:
    """Las colas en las que cuenta una fila: la suya y, si es de la Grieta, "todo"."""
    return [f["cola"], "todo"] if f["cola"] in GRIETA else [f["cola"]]


def en(f: dict, cola: str) -> bool:
    return f["cola"] == cola or (cola == "todo" and f["cola"] in GRIETA)

# Métrica propia de cada rol: (clave, etiqueta, campo de la fila). La primera es la del ranking.
METRICA_ROL = {
    "Top": [("dif_oro15", "Oro vs rival a los 15", "gold_diff_at_15"), ("dif_cs15", "CS vs rival a los 15", "cs_diff_at_15")],
    "Mid": [("dif_oro15", "Oro vs rival a los 15", "gold_diff_at_15"), ("dif_cs15", "CS vs rival a los 15", "cs_diff_at_15")],
    "ADC": [("dif_oro15", "Oro vs rival a los 15", "gold_diff_at_15"), ("dif_cs15", "CS vs rival a los 15", "cs_diff_at_15")],
    # La participación en dragones/Barón/Heraldo se probó y no discrimina: mediana 94 %, el jungla
    # está en casi todos los de su equipo (lección 1). Queda el oro contra el jungla rival.
    "Jungla": [("dif_oro15", "Oro vs rival a los 15", "gold_diff_at_15"), ("dif_cs15", "CS vs rival a los 15", "cs_diff_at_15")],
    "Support": [("dif_vision_min", "Visión/min vs rival", "dif_vision_min"), ("vision_min", "Visión/min", "vision_per_min")],
}


def _enriquecer(db: sqlite3.Connection, filas_por: dict[str, list[dict]]) -> None:
    """Agrega a cada fila: equipo, compañeros vinculados y visión contra el rival directo."""
    part = {}  # (match, participant_id) -> fila de participantes
    por_pos: dict[tuple, dict] = {}
    for r in db.execute("""SELECT pt.match_id, pt.participant_id, pt.puuid, pt.persona_id, pt.team_id,
                                  pt.team_position, pt.vision, pa.duracion_seg
                           FROM participantes pt JOIN partidas pa USING(match_id)"""):
        part[(r[0], r[1])] = r
        if r[5]:
            por_pos[(r[0], r[4], r[5])] = r
    equipo: dict[tuple, set] = defaultdict(set)
    pid_de: dict[tuple, tuple] = {}
    for (mid, _), r in part.items():
        if r[3]:
            equipo[(mid, r[4])].add(r[3])
            pid_de[(mid, r[2])] = (r[1], r[4], r[5], r[6], r[7])

    for filas in filas_por.values():
        for f in filas:
            info = pid_de.get((f["match_id"], f["puuid"]))
            if not info:
                continue
            _, team, pos, vision, dur = info
            f["team_id"] = team
            f["companeros"] = sorted(equipo[(f["match_id"], team)] - {f["persona_id"]})
            rival = por_pos.get((f["match_id"], 300 - team, pos)) if pos else None
            if rival and dur:
                f["dif_vision_min"] = (vision - rival[6]) / (dur / 60)


def _kda_crudo(g: list[dict]) -> float:
    return (sum(f["kills"] for f in g) + sum(f["assists"] for f in g)) / max(sum(f["deaths"] for f in g), 1)


def _medianas_kda(filas_por: dict[str, list[dict]], clave: Callable[[dict], tuple]) -> dict:
    """Mediana entre personas (con muestra) del KDA en cada grupo: la referencia del ajuste."""
    por = defaultdict(lambda: defaultdict(list))
    for pid, filas in filas_por.items():
        for f in filas:
            for k in clave(f):
                por[k][pid].append(f)
    out = {}
    for k, personas in por.items():
        vals = [_kda_crudo(g) for g in personas.values() if len(g) >= MIN] or \
               [_kda_crudo([f for g in personas.values() for f in g])]
        out[k] = statistics.median(vals)
    return out


def _resumen(g: list[dict], mediana_kda: float | None, rol: str | None) -> dict:
    """Bloque común de roles, campeones y rankings: crudo, ajustado, IC y confianza."""
    n, w = len(g), sum(f["win"] for f in g)
    k, d, a = (sum(f[c] for f in g) for c in ("kills", "deaths", "assists"))
    out = {
        "n": n,
        "winrate": est.wilson(w, n),
        "winrate_aj": est.ajustada_tasa(w, n),
        "kda": est.kda([f["kills"] for f in g], [f["deaths"] for f in g], [f["assists"] for f in g]),
        "kda_aj": est.ajustado_kda(k, d, a, mediana_kda),
        "confianza": est.confianza(n, [f["kills"] + f["assists"] for f in g]),
        "muestra_chica": n < MIN,
    }
    for clave, _, campo in METRICA_ROL.get(rol, []):
        out[clave] = est.media([f.get(campo) for f in g])
    return out


def _orden(t: dict) -> tuple:
    return (t["muestra_chica"], -(t["winrate_aj"] or 0), -t["n"])


def _medianas_rol(filas_por: dict[str, list[dict]]) -> dict:
    """Mediana del grupo por cola × rol para cada métrica, con cuántos jugadores aportan."""
    por = defaultdict(lambda: defaultdict(list))
    for pid, filas in filas_por.items():
        for f in filas:
            if f["rol_ldh"]:
                for c in colas_de(f):
                    por[(c, f["rol_ldh"])][pid].append(f)
    out = {}
    for (cola, rol), personas in por.items():
        con = {p: g for p, g in personas.items() if len(g) >= MIN}
        ref = {"jugadores": len(con)}
        if con:
            ref["winrate"] = est._r(statistics.median(sum(f["win"] for f in g) / len(g) for g in con.values()))
            ref["kda"] = est._r(statistics.median(_kda_crudo(g) for g in con.values()), 2)
            for clave, _, campo in METRICA_ROL.get(rol, []):
                vals = [statistics.fmean(v) for g in con.values()
                        if (v := [f[campo] for f in g if f.get(campo) is not None])]
                ref[clave] = est._r(statistics.median(vals)) if vals else None
        out[f"{cola}|{rol}"] = ref
    return out


def roles(filas: list[dict], med_kda: dict, med_rol: dict) -> dict:
    grupos = defaultdict(list)
    for f in filas:
        if f["cola"] in GRIETA and f["rol_ldh"]:
            for c in colas_de(f):
                grupos[(c, f["rol_ldh"])].append(f)
    tabla = []
    for (cola, rol), g in grupos.items():
        tabla.append({"cola": cola, "rol": rol, **_resumen(g, med_kda.get((cola, rol)), rol),
                      "referencia": med_rol.get(f"{cola}|{rol}")})
    tabla.sort(key=lambda t: (t["muestra_chica"], MODOS.index(t["cola"]), ROLES.index(t["rol"])))
    mejor = {}
    for cola in MODOS:
        cand = [t for t in tabla if t["cola"] == cola and t["confianza"] != "baja"]
        if cand:
            m = max(cand, key=lambda t: t["winrate_aj"])
            mejor[cola] = {"rol": m["rol"], "winrate_aj": m["winrate_aj"], "n": m["n"]}
    return {"tabla": tabla, "mejor": mejor,
            "metricas": {r: [{"clave": c, "nombre": n} for c, n, _ in ms] for r, ms in METRICA_ROL.items()}}


def campeones(filas: list[dict], med_kda: dict) -> list[dict]:
    """Por (campeón, posición) y cola: la experiencia que importa es la del par (regla 13)."""
    grupos = defaultdict(list)
    for f in filas:
        if f["cola"] in GRIETA:
            for c in colas_de(f):
                grupos[(c, f["champion_id"], f["rol_ldh"])].append(f)
    por_cola = defaultdict(int)
    for f in filas:
        for c in colas_de(f):
            por_cola[c] += 1
    tabla = []
    for (cola, champ, rol), g in grupos.items():
        g.sort(key=lambda f: f["inicio_ms"])
        tabla.append({"cola": cola, "champ": champ, "rol": rol, **_resumen(g, med_kda.get((cola, rol)), rol),
                      "popularidad": est._r(len(g) / por_cola[cola]), "ultimo_parche": g[-1].get("patch"),
                      "ultima": g[-1]["inicio_ms"]})
    return sorted(tabla, key=lambda t: (MODOS.index(t["cola"]), *_orden(t)))


def pool(filas: list[dict]) -> dict:
    """Dentro y fuera del pool, sin fuga: la experiencia se cuenta con las partidas anteriores."""
    cfg = AJUSTES["pool"]
    ventana = cfg["dias"] * DIA_MS
    previas: dict[tuple, list[int]] = defaultdict(list)
    marcadas = []
    for f in sorted((f for f in filas if f["cola"] in GRIETA), key=lambda f: f["inicio_ms"]):
        clave = (f["champion_id"], f["rol_ldh"])
        t = f["inicio_ms"]
        n_prev = sum(1 for x in previas[clave] if t - x <= ventana)
        marcadas.append((f, n_prev >= cfg["min_previas"]))
        previas[clave].append(t)
    completo = datetime.fromtimestamp(INICIO_HISTORIAL + cfg["dias"] * 86400, timezone.utc).strftime("%Y-%m")
    out = {}
    for cola in MODOS:
        de = [(f, dentro) for f, dentro in marcadas if en(f, cola)]
        if not de:
            continue
        dentro = [f for f, ok in de if ok]
        fuera = [f for f, ok in de if not ok]
        wd, wf = sum(f["win"] for f in dentro), sum(f["win"] for f in fuera)
        meses = defaultdict(lambda: [0, 0])
        for f, ok in de:
            m = datetime.fromtimestamp(f["inicio_ms"] / 1000, timezone.utc).strftime("%Y-%m")
            meses[m][0] += 1
            meses[m][1] += not ok
        out[cola] = {
            "dentro": est.wilson(wd, len(dentro)), "fuera": est.wilson(wf, len(fuera)),
            "dif": est.diferencia([float(f["win"]) for f in dentro], [float(f["win"]) for f in fuera]),
            "p": est._r(est.fisher(wd, len(dentro) - wd, wf, len(fuera) - wf), 4) if dentro and fuera else None,
            # El historial arranca el 8/1: hasta completar la primera ventana todo parece "fuera del pool".
            "por_mes": [{"mes": m, "n": v[0], "fuera": est.wilson(v[1], v[0]), "arranque": m < completo}
                        for m, v in sorted(meses.items())],
        }
    return {"regla": f"Del pool = ese campeón en esa posición ya tenía {cfg['min_previas']}+ partidas "
                     f"en los {cfg['dias']} días anteriores.", "colas": out}


def sinergia(filas_por: dict[str, list[dict]]) -> list[dict]:
    """Con cada compañero contra sin él, en la misma cola. p ajustado por Benjamini-Hochberg."""
    cfg = AJUSTES["sinergia"]
    filas_out = []
    for pid, filas in filas_por.items():
        for cola in GRIETA:
            de = [f for f in filas if f["cola"] == cola and "companeros" in f]
            comp = {c for f in de for c in f["companeros"]}
            for q in comp:
                con = [f for f in de if q in f["companeros"]]
                if len(con) < cfg["min_juntos"]:
                    continue
                sin = [f for f in de if q not in f["companeros"]]
                t0, t1 = con[0]["inicio_ms"], con[0]["inicio_ms"]
                for f in con:
                    t0, t1 = min(t0, f["inicio_ms"]), max(t1, f["inicio_ms"])
                sin_per = [f for f in sin if t0 <= f["inicio_ms"] <= t1]
                wc, ws = sum(f["win"] for f in con), sum(f["win"] for f in sin)
                kda_con = est.kda([f["kills"] for f in con], [f["deaths"] for f in con], [f["assists"] for f in con])
                kda_sin = est.kda([f["kills"] for f in sin], [f["deaths"] for f in sin], [f["assists"] for f in sin])
                filas_out.append({
                    "persona": pid, "companero": q, "cola": cola, "juntos": len(con),
                    "con": est.wilson(wc, len(con)), "sin": est.wilson(ws, len(sin)),
                    "sin_mismo_periodo": est.wilson(sum(f["win"] for f in sin_per), len(sin_per)),
                    "dif": est.diferencia([float(f["win"]) for f in con], [float(f["win"]) for f in sin]),
                    "kda_con": kda_con, "kda_sin": kda_sin,
                    "p": est.fisher(wc, len(con) - wc, ws, len(sin) - ws) if sin else 1.0,
                    "muestra_chica": len(con) < MIN,
                })
    ajust = est.benjamini_hochberg([r["p"] for r in filas_out])
    for r, pa in zip(filas_out, ajust):
        r["p"] = est._r(r["p"], 4)
        r["p_bh"] = est._r(pa, 4)
        r["senal"] = pa < AJ["alfa"]
    return sorted(filas_out, key=lambda r: (r["persona"], r["muestra_chica"], -r["juntos"]))


def mejor_companero(sin: list[dict], pid: str) -> dict | None:
    cand = [r for r in sin if r["persona"] == pid and r["juntos"] >= AJUSTES["sinergia"]["min_mejor"]
            and r["senal"] and r["dif"]["v"] and r["dif"]["v"] > 0]
    if not cand:
        return None
    m = max(cand, key=lambda r: r["dif"]["v"])
    return {"companero": m["companero"], "cola": m["cola"], "juntos": m["juntos"], "dif": m["dif"]}


def rankings(filas_por: dict[str, list[dict]], ahora_ms: int, med_kda_cola: dict) -> dict:
    cfg = AJUSTES["rankings"]
    out = {}
    for periodo, dias in cfg["periodos"].items():
        desde = ahora_ms - dias * DIA_MS if dias else 0
        por_cola = {}
        for cola in MODOS:
            filas = []
            for pid, fs in filas_por.items():
                g = [f for f in fs if en(f, cola) and f["inicio_ms"] >= desde]
                if g:
                    filas.append({"persona": pid, **_resumen(g, med_kda_cola.get(cola), None)})
            ok = sorted((r for r in filas if r["n"] >= cfg["min"][periodo]), key=_orden)
            for i, r in enumerate(ok):
                r["puesto"] = i + 1
            # Medalla solo con confianza media o alta y arriba del piso: con 3 habilitados, el
            # tercero podía ser un 22 % real y llevarse el bronce igual.
            podio = [r["persona"] for r in ok
                     if r["confianza"] != "baja" and (r["winrate_aj"] or 0) >= cfg["piso_podio"]][:3]
            por_cola[cola] = {"tabla": ok, "podio": podio,
                              "sin_muestra": sorted((r["persona"], r["n"]) for r in filas if r["n"] < cfg["min"][periodo])}
        out[periodo] = {"periodo": periodo, "dias": dias, "min": cfg["min"][periodo], "colas": por_cola}
    return out


def rankings_rol(filas_por: dict[str, list[dict]], ahora_ms: int) -> dict:
    cfg = AJUSTES["rankings"]
    out = {}
    for nombre, dias in (("historico", None), ("reciente", cfg["dias_rol_reciente"])):
        desde = ahora_ms - dias * DIA_MS if dias else 0
        por = {}
        for cola in MODOS:
            for rol in ROLES:
                clave, etiqueta, campo = METRICA_ROL[rol][0]
                filas = []
                for pid, fs in filas_por.items():
                    g = [f for f in fs if en(f, cola) and f["rol_ldh"] == rol and f["inicio_ms"] >= desde]
                    conf = est.confianza(len(g), [f["kills"] + f["assists"] for f in g])
                    if len(g) >= cfg["min_rol"] and conf != "baja":
                        m = est.media([f.get(campo) for f in g])
                        if m["v"] is not None:
                            filas.append({"persona": pid, "n": len(g), "valor": m, "confianza": conf,
                                          "winrate": est.wilson(sum(f["win"] for f in g), len(g))})
                filas.sort(key=lambda r: -r["valor"]["v"])
                por[f"{cola}|{rol}"] = {"metrica": clave, "nombre": etiqueta, "tabla": filas}
        out[nombre] = {"dias": dias, "min": cfg["min_rol"], "grupos": por}
    return out


# Medianas del grupo de la última corrida de generar(): la vista de una sola cuenta se compara
# contra el mismo grupo que la persona entera.
_MEDIANAS: dict = {}


def por_cuenta(filas: list[dict]) -> dict:
    """Roles, campeones y pool de una sola cuenta (las filas ya pasaron por _enriquecer)."""
    r = roles(filas, _MEDIANAS["kda"], _MEDIANAS["rol"])
    return {"roles": r, "campeones": {"tabla": campeones(filas, _MEDIANAS["kda"]), "pool": pool(filas)}}


def generar(db: sqlite3.Connection, filas_por: dict[str, list[dict]], escribir: Callable) -> dict:
    """Escribe roles/, campeones/, sinergia.json y rankings/. Devuelve lo que el perfil resume."""
    _enriquecer(db, filas_por)
    med_kda = _medianas_kda(filas_por, lambda f: [(c, f["rol_ldh"]) for c in colas_de(f)])
    med_kda_cola = _medianas_kda(filas_por, colas_de)
    med_rol = _medianas_rol(filas_por)
    _MEDIANAS.update(kda=med_kda, rol=med_rol)
    sin = sinergia(filas_por)
    escribir("sinergia.json", {"alfa": AJ["alfa"], "min_juntos": AJUSTES["sinergia"]["min_juntos"],
                               "nota": "Con contra sin el compañero, en la misma cola. 'señal' usa el p ajustado "
                                       "por Benjamini-Hochberg: con tantos pares, alguno sale por azar.",
                               "filas": sin})
    resumen = {}
    for pid, filas in filas_por.items():
        r = roles(filas, med_kda, med_rol)
        escribir(f"roles/{pid}.json", r)
        escribir(f"campeones/{pid}.json", {"tabla": campeones(filas, med_kda), "pool": pool(filas)})
        resumen[pid] = {"mejor_rol": r["mejor"], "mejor_companero": mejor_companero(sin, pid)}
    ahora = int(datetime.now(timezone.utc).timestamp() * 1000)
    for periodo, datos in rankings(filas_por, ahora, med_kda_cola).items():
        escribir(f"rankings/{periodo}.json", datos)
    escribir("rankings/roles.json", rankings_rol(filas_por, ahora))
    return resumen
