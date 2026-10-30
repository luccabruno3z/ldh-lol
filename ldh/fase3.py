"""Fase 3: coaching. Percentiles contra la muestra de referencia, Performance, fortalezas,
"cómo sumar", los primeros 15 minutos y la comparación contra tu campeón.

Referencias que se usan (regla 8, siempre el par correcto):
- Percentiles: jugadores de referencia de la misma franja de rango y el mismo rol, cada uno
  con 10+ partidas de solo/dúo (ldh.referencia). Se compara el promedio de la persona con
  los promedios de esos jugadores, nunca con partidas sueltas.
- Contra tu campeón: los desconocidos que jugaron el mismo campeón en el mismo rol en las
  partidas del grupo en el mismo modo. Es por partida (casi todos aparecen una vez), así que se
  compara media contra media con su intervalo y la columna de jugadores distintos (regla 2).
"""

from __future__ import annotations

import gzip
import json
import math
import sqlite3
import warnings
from datetime import datetime, timezone
from collections import defaultdict
from typing import Callable

import numpy as np

from . import estadistica as est
from .ajustes import AJUSTES, CACHE, DATOS, RAIZ
from .almacen import _escribir_atomico, _json_compacto, _ruta, anon_id
from .fase2 import GRIETA, colas_de
from .referencia import CONF as REF, ROLES, cargar_filas, fila_de, franja_de

MIN = AJUSTES["min_partidas"]
PERF = AJUSTES["performance"]
REPS = AJUSTES["bootstrap_reps"]
SEMILLA = AJUSTES["bootstrap_semilla"]
FRANJAS = list(REF["franjas"])
CONSEJOS = json.loads((RAIZ / "config" / "consejos.json").read_text(encoding="utf-8"))
VERSION_FILAS = 4  # 4: recalcular sin la cuenta que pasó a privada

# clave: (etiqueta, función por partida, más es mejor, decimales, unidad)
METRICAS: dict[str, tuple] = {
    "kda": ("KDA", None, True, 2, ""),
    "kp": ("Participación en kills", lambda f: f.get("kill_participation"), True, 1, "%"),
    "dano": ("% del daño del equipo", lambda f: f.get("damage_share"), True, 1, "%"),
    "oro_min": ("Oro por minuto", lambda f: f.get("gold_per_min"), True, 0, ""),
    "cs_min": ("CS por minuto", lambda f: f.get("cs_per_min"), True, 2, ""),
    "vision_min": ("Visión por minuto", lambda f: f.get("vision_per_min"), True, 2, ""),
    "control": ("Wards de control por partida", lambda f: f.get("control_wards"), True, 2, ""),
    "obj": ("Participación en dragones, Heraldo y Barón", lambda f: None if f.get("obj_part") is None else f["obj_part"] * 100, True, 1, "%"),
    "muertes_min": ("Muertes por minuto", lambda f: f.get("muertes_min"), False, 3, ""),
    "cs10": ("CS a los 10", lambda f: f.get("cs_at_10"), True, 1, ""),
    "cs15": ("CS a los 15", lambda f: f.get("cs_at_15"), True, 1, ""),
    "dif_oro10": ("Oro vs rival a los 10", lambda f: f.get("gold_diff_at_10"), True, 0, ""),
    "dif_oro15": ("Oro vs rival a los 15", lambda f: f.get("gold_diff_at_15"), True, 0, ""),
    "dif_cs10": ("CS vs rival a los 10", lambda f: f.get("cs_diff_at_10"), True, 1, ""),
    "dif_cs15": ("CS vs rival a los 15", lambda f: f.get("cs_diff_at_15"), True, 1, ""),
    "dif_xp15": ("XP vs rival a los 15", lambda f: f.get("xp_diff_at_15"), True, 0, ""),
    "dif_vision_min": ("Visión/min vs rival", lambda f: f.get("dif_vision_min"), True, 2, ""),
    "winrate": ("Winrate ajustado a tu franja", None, True, 3, ""),
}
# El CS no es tarea del support: sus métricas de CS no entran en sus fortalezas ni debilidades.
# La participación en dragones, Heraldo y Barón no distingue junglas: mediana de 96 % en la
# referencia (el jungla está en casi todos). Se probó y se saca, como en la fase 2.
NO_APLICA = {"Support": {"cs_min", "cs10", "cs15", "dif_cs10", "dif_cs15"}, "Jungla": {"obj"}}
# Las métricas que forman la "nota" por partida que mide la consistencia.
NOTA = ("kp", "dano", "oro_min", "vision_min")
# Índice por partida para la tendencia: lo que depende de cómo jugaste, no del resultado (el winrate
# depende de los compañeros y tiene demasiado ruido para ver una tendencia). Muertes cuentan al revés.
# Las del gráfico "contra cada franja": tu valor al lado de la mediana de las tres franjas. Solo pone
# las medianas al lado; no dice a qué franja te parecés (eso sería estimar un rango, y Riot no lo permite).
POR_FRANJA = ("kp", "dano", "oro_min", "cs_min", "vision_min", "control", "muertes_min", "dif_oro15", "dif_vision_min")
INDICE = {
    "_": ("kp", "dano", "oro_min", "vision_min", "dif_oro15", "muertes_min"),
    "Support": ("kp", "dano", "oro_min", "vision_min", "dif_vision_min", "muertes_min"),
}


def _componentes(rol: str) -> list[tuple[str, str, list[str]]]:
    sup = rol == "Support"
    return [
        ("combate", "Combate", ["kda"]),
        ("efectividad", "Efectividad", ["kp", "dano"]),
        ("economia", "Economía", ["oro_min"] if sup else ["oro_min", "cs_min"]),
        ("linea", "Línea", ["dif_vision_min"] if sup else ["dif_oro15", "dif_cs15"]),
        ("winrate", "Winrate", ["winrate"]),
        ("equipo", "Equipo", ["vision_min"] if rol == "Jungla" else ["vision_min", "obj"]),
        ("consistencia", "Consistencia", ["consistencia"]),
    ]


# ------------------------------------------------------------------ las filas

def _filas_grieta(db: sqlite3.Connection) -> list[dict]:
    """Una fila por jugador y partida de la Grieta guardada (solo, flex y normales; amigos y desconocidos).

    Se cachean por partida: recalcular las ~35.000 filas tarda un minuto y medio.
    """
    ruta = CACHE / "fase3_filas.json.gz"
    cache = {}
    if ruta.exists():
        c = json.loads(gzip.decompress(ruta.read_bytes()))
        if c.get("version") == VERSION_FILAS:
            cache = c["partidas"]
    # Las partidas guardadas antes de que alguien se vinculara lo tienen anonimizado: se lo reconoce
    # por su anon_id (como en base.reconstruir), si no esas partidas no contaban como suyas.
    vinc, real = {}, {}
    for puuid, pid in db.execute("SELECT puuid, persona_id FROM cuentas"):
        vinc[puuid] = vinc[anon_id(puuid)] = pid
        real[anon_id(puuid)] = puuid
    salida, nuevas = [], 0
    for mid, inicio, cola in db.execute("SELECT match_id, inicio_ms, cola FROM partidas "
                                        "WHERE cola IN ('solo','flex','normal') AND tiene_timeline=1"):
        if mid not in cache:
            m = json.loads(gzip.decompress(_ruta("partidas", mid, inicio).read_bytes()))
            tl = json.loads(gzip.decompress(_ruta("timelines", mid, inicio).read_bytes()))
            filas = []
            for p in m["info"]["participants"]:
                f = fila_de(m, tl, p["puuid"])
                if f:
                    f["puuid"] = p["puuid"]
                    filas.append(f)
            cache[mid] = filas
            nuevas += 1
        for f in cache[mid]:
            salida.append({**f, "puuid": real.get(f["puuid"], f["puuid"]), "persona": vinc.get(f["puuid"]),
                           "rival_vinculado": f.get("rival") in vinc,
                           "inicio_ms": inicio, "cola": cola})
    if nuevas:
        _escribir_atomico(ruta, gzip.compress(_json_compacto({"version": VERSION_FILAS, "partidas": cache}), 6))
    return salida


def _matriz(filas: list[dict]) -> dict[str, np.ndarray]:
    """Valores por partida de cada métrica (NaN sin dato) más k, d, a y win."""
    out = {}
    for k, (_, fn, *_r) in METRICAS.items():
        if fn:
            out[k] = np.array([np.nan if fn(f) is None else float(fn(f)) for f in filas])
    for k, campo in (("_k", "kills"), ("_d", "deaths"), ("_a", "assists"), ("_w", "win")):
        out[k] = np.array([float(f[campo]) for f in filas])
    return out


def _valores(m: dict[str, np.ndarray], idx: np.ndarray, peso: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Valor de cada métrica de jugador para cada fila de índices (bootstrap: idx de REPS × n).

    peso: uno por partida (solo la referencia lo usa, para llevar victorias y derrotas al 50 %)."""
    v = {}
    w = np.ones(len(m["_w"])) if peso is None else peso
    with np.errstate(invalid="ignore", divide="ignore"):
        for k in METRICAS:
            if k == "kda":
                v[k] = ((m["_k"] * w)[idx].sum(-1) + (m["_a"] * w)[idx].sum(-1)) / np.maximum((m["_d"] * w)[idx].sum(-1), 1)
            elif k == "winrate":
                n = idx.shape[-1]
                v[k] = (m["_w"][idx].sum(-1) + AJUSTES["ajuste_muestra"]["k_tasa"] * 0.5) / (n + AJUSTES["ajuste_muestra"]["k_tasa"])
            else:
                x, wx = m[k][idx], w[idx]
                # Un jugador sin dato en más de la mitad de sus partidas no tiene valor.
                ok = ~np.isnan(x)
                media = np.nansum(x * wx, -1) / np.where(ok, wx, 0).sum(-1)
                v[k] = np.where(ok.sum(-1) * 2 >= idx.shape[-1], media, np.nan)
    return v


def _pct(x: np.ndarray | float, ref: np.ndarray) -> np.ndarray:
    """Percentil (0–1) de x entre los valores de referencia, contando la mitad de los empates.

    Con N jugadores de referencia, nadie queda en 0 ni en 100 exactos: estar debajo de los 22 no
    dice "peor que todos los de la franja". Se usa (rango + 0,5) / (N + 1), que va de ~2 a ~98
    con 22 jugadores (lo de AhiTeVan: daba 0 de consistencia con 15 partidas)."""
    x = np.asarray(x, dtype=float)
    rango = (np.searchsorted(ref, x, "left") + np.searchsorted(ref, x, "right")) / 2
    p = (rango + 0.5) / (len(ref) + 1)
    return np.where(np.isnan(x), np.nan, p)


# ------------------------------------------------------------- la referencia

class Celda:
    """Referencia de una franja y un rol: promedios por jugador y distribución por partida."""

    def __init__(self, filas: list[dict]):
        por_jug = defaultdict(list)
        for f in filas:
            por_jug[f["jugador"]].append(f)
        jugadores = [g for g in por_jug.values() if len(g) >= REF["min_partidas"]]
        self.n_jugadores = len(jugadores)
        todas = [f for g in jugadores for f in g]
        mt = _matriz(todas)
        # Sesgo de selección: cada jugador entra por su rango actual, y sus últimas partidas son las
        # que lo dejaron ahí (en Hierro–Bronce ganaron el 39 %: vienen de bajar). El emparejamiento
        # apunta al 50 %, así que victorias y derrotas se ponderan para pesar como un 50 % cada una.
        self.winrate_crudo = float(mt["_w"].mean()) if len(todas) else None
        p = min(max(self.winrate_crudo or 0.5, 0.05), 0.95)
        # Por partida: base de la "nota" de consistencia.
        self.partida = {k: np.sort(mt[k][~np.isnan(mt[k])]) for k in {*NOTA, *[k for ks in INDICE.values() for k in ks]}}
        vals = defaultdict(list)
        for g in jugadores:
            m = _matriz(g)
            peso = np.where(m["_w"] > 0, 0.5 / p, 0.5 / (1 - p))
            v = _valores(m, np.arange(len(g))[None, :], peso)
            for k, x in v.items():
                vals[k].append(x[0])
            vals["consistencia"].append(-self.dispersion(m, np.arange(len(g))[None, :])[0])
            vals["_oro_pct"].append(np.mean([f["oro_pct"] for f in g if f["oro_pct"] is not None]))
        self.por_jugador = {k: np.sort(np.array([x for x in xs if not np.isnan(x)])) for k, xs in vals.items()}
        # Winrate: con 10 partidas por jugador casi toda la dispersión es azar. Se estima cuánto
        # varía de verdad entre jugadores (varianza observada menos la binomial esperada) y el
        # componente compara contra esa dispersión, no contra los winrates crudos de 10 partidas.
        crudos = np.array([np.mean([f["win"] for f in g]) for g in jugadores]) if jugadores else np.array([])
        ns = np.array([len(g) for g in jugadores])
        self.tau2 = max(float(crudos.var(ddof=1) - np.mean(crudos * (1 - crudos) / ns)), 1e-4) if len(crudos) > 2 else None
        # El mismo índice de la tendencia, promediado por jugador de referencia: dónde juega la franja
        # en ese gráfico (mediana y la mitad del medio), para no comparar solo contra un 50 teórico.
        rol = filas[0]["role"] if filas else None
        self.indice_jugadores = np.sort(np.array([x for g in jugadores
                                                  if not np.isnan(x := float(np.nanmean(self.indice(_matriz(g), rol))))]))

    def indice(self, m: dict, rol: str | None) -> np.ndarray:
        """Índice por partida (0–100): percentil promedio en las métricas de INDICE, muertes al revés."""
        ps = []
        for k in INDICE.get(rol, INDICE["_"]):
            if k in self.partida and len(self.partida[k]):
                p = _pct(m[k], self.partida[k])
                ps.append(1 - p if not METRICAS[k][2] else p)
        if not ps:
            return np.full(len(m["_w"]), np.nan)
        with warnings.catch_warnings():  # partidas sin ninguna métrica: NaN, sin aviso
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(np.stack(ps), axis=0) * 100

    def dispersion(self, m: dict, idx: np.ndarray) -> np.ndarray:
        """Desvío de la nota por partida: el promedio de los percentiles por partida de NOTA."""
        notas = np.nanmean(np.stack([_pct(m[k], self.partida[k]) for k in NOTA]), axis=0)
        return np.nanstd(notas[idx], axis=-1)

    def disponible(self, k: str) -> bool:
        return len(self.por_jugador.get(k, [])) >= REF["min_jugadores"]

    def mediana(self, k: str) -> float | None:
        r = self.por_jugador.get(k)
        return float(np.median(r)) if r is not None and len(r) else None


# Sin rango en solo ni en flex no hay franja: se compara contra toda la referencia del rol junta.
TODAS = "Hierro a Esmeralda"


def _celdas() -> dict[tuple[str, str], Celda]:
    por = defaultdict(list)
    for f in cargar_filas():
        por[(f["franja"], f["role"])].append(f)
        por[(TODAS, f["role"])].append(f)
    return {k: Celda(v) for k, v in por.items()}


# --------------------------------------------------------------- por persona

def _sigmoide(n: int) -> float:
    return 1 / (1 + math.exp(-(n - PERF["penalizacion_centro"]) / PERF["penalizacion_escala"]))


def _r(x, d=3):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), d)


def _ic(boot: np.ndarray) -> tuple[float | None, float | None]:
    b = boot[~np.isnan(boot)]
    if len(b) < REPS / 2:
        return None, None
    lo, hi = np.percentile(b, (2.5, 97.5))
    return _r(lo), _r(hi)


def _evaluar(filas: list[dict], celda: Celda, rol: str, idx: np.ndarray) -> dict:
    """Percentiles por métrica y Performance para el original (fila 0 de idx) y el bootstrap."""
    m = _matriz(filas)
    v = _valores(m, idx)
    v["consistencia"] = -celda.dispersion(m, idx)
    pct = {k: _pct(x, celda.por_jugador[k]) if celda.disponible(k) else np.full(len(idx), np.nan)
           for k, x in v.items()}
    if celda.tau2 and celda.disponible("winrate"):
        # Bayes empírico: el winrate crudo se encoge según la dispersión real de la franja y se
        # ubica en una normal con esa dispersión. 0,5 = la mitad de la franja.
        n = idx.shape[-1]
        crudo = m["_w"][idx].mean(-1)
        encogido = 0.5 + (crudo - 0.5) * celda.tau2 / (celda.tau2 + 0.25 / n)
        v["winrate"] = encogido
        pct["winrate"] = 0.5 * (1 + np.vectorize(math.erf)((encogido - 0.5) / math.sqrt(2 * celda.tau2)))
    comps, total = {}, np.zeros(len(idx))
    for clave, _, metricas in _componentes(rol):
        ps = [pct[k] for k in metricas if celda.disponible(k)]
        nivel = np.nanmean(np.stack(ps), axis=0) if ps else np.full(len(idx), np.nan)
        comps[clave] = nivel
        total += PERF["pesos"][clave] * np.where(np.isnan(nivel), 0.5, nivel)
    s = _sigmoide(len(filas))
    return {"valores": v, "pct": pct, "comps": comps, "perf": 0.5 + (total - 0.5) * s}


def _consejo(clave: str, rol: str) -> str:
    c = CONSEJOS.get(clave, {})
    return c.get(rol) or c.get("_", "")


def tendencia(filas: list[dict], celda: "Celda", rol: str) -> dict | None:
    """¿Estás mejorando? El índice de cada partida (0–100, percentil promedio contra tu franja y rol)
    a lo largo del tiempo, con su recta de tendencia. La pendiente va en puntos cada 100 partidas,
    con intervalo bootstrap (se remuestrean partidas manteniendo su orden en el tiempo)."""
    cfg = PERF["tendencia"]
    if len(filas) < cfg["min_partidas"]:
        return None
    y = celda.indice(_matriz(filas), rol)
    if np.isnan(y).all():
        return None
    ok = ~np.isnan(y)
    y, t = y[ok], np.array([f["inicio_ms"] for f, o in zip(filas, ok) if o])
    n = len(y)
    if n < cfg["min_partidas"]:
        return None
    x = np.arange(n, dtype=float)
    pendiente = float(np.polyfit(x, y, 1)[0])
    rng = np.random.default_rng(SEMILLA)
    boot = []
    for idx in rng.integers(0, n, (REPS, n)):
        xs = x[idx]
        if xs.std() > 0:
            boot.append(np.polyfit(xs, y[idx], 1)[0])
    lo, hi = np.percentile(boot, (2.5, 97.5))
    v = cfg["ventana"]
    movil = np.convolve(y, np.ones(v) / v, mode="valid")
    paso = max(1, len(movil) // 60)  # unos 60 puntos alcanzan para la línea
    # El eje es el número de partida (la recta se ajusta por partida): con fechas, los días de muchas
    # partidas se apretaban y la línea daba saltos. Las fechas quedan como rótulos, una por mes.
    puntos = [{"i": i + v - 1, "t": int(t[i + v - 1]), "v": _r(movil[i], 1)} for i in range(0, len(movil), paso)]
    if puntos[-1]["i"] != n - 1:
        puntos.append({"i": n - 1, "t": int(t[-1]), "v": _r(movil[-1], 1)})
    meses, visto = [], None
    for i, ts in enumerate(t):
        m_ = datetime.fromtimestamp(ts / 1000, timezone.utc).month
        if m_ != visto:
            meses.append({"i": i, "mes": m_})
            visto = m_
    a, b = np.polyfit(x, y, 1)
    return {"n": n, "ventana": v, "puntos": puntos, "meses": meses,
            "recta": {"desde": {"i": 0, "t": int(t[0]), "v": _r(b, 1)},
                      "hasta": {"i": n - 1, "t": int(t[-1]), "v": _r(a * (n - 1) + b, 1)}},
            "pendiente": _r(pendiente * 100, 1), "lo": _r(lo * 100, 1), "hi": _r(hi * 100, 1),
            "veredicto": "mejorando" if lo > 0 else "empeorando" if hi < 0 else "sin tendencia clara",
            "inicio": _r(float(np.mean(y[:v])), 1), "ahora": _r(float(np.mean(y[-v:])), 1),
            "metricas": [METRICAS[k][0] for k in INDICE.get(rol, INDICE["_"])],
            "ref": None if len(celda.indice_jugadores) < REF["min_jugadores"] else {
                "mediana": _r(float(np.median(celda.indice_jugadores)), 1),
                "lo": _r(float(np.percentile(celda.indice_jugadores, 25)), 1),
                "hi": _r(float(np.percentile(celda.indice_jugadores, 75)), 1),
                "jugadores": len(celda.indice_jugadores)}}


def _rol(filas: list[dict], rol: str, franja: str, celdas: dict) -> dict | None:
    celda = celdas.get((franja, rol))
    if celda is None or celda.n_jugadores < REF["min_jugadores"]:
        return {"n": len(filas), "sin_referencia": True,
                "n_ref": 0 if celda is None else celda.n_jugadores}
    n = len(filas)
    rng = np.random.default_rng(SEMILLA)
    idx = np.vstack([np.arange(n)[None, :], rng.integers(0, n, (REPS, n))])
    ev = _evaluar(filas, celda, rol, idx)

    metricas = {}
    for k, (nombre, _, mejor, dec, unidad) in [*METRICAS.items(), ("consistencia", ("Consistencia", None, True, 3, ""))]:
        if k in NO_APLICA.get(rol, ()) or not celda.disponible(k):
            continue
        val, p = ev["valores"][k], ev["pct"][k]
        if np.isnan(val[0]):
            continue
        lo, hi = _ic(val[1:])
        plo, phi = _ic(p[1:])
        # Para las métricas donde menos es mejor, el percentil se da vuelta: "mejor que el X %".
        inv = (lambda x: None if x is None else _r(1 - x)) if not mejor else (lambda x: x)
        pv, plo, phi = inv(_r(p[0])), inv(plo), inv(phi)
        if not mejor:
            plo, phi = phi, plo
        metricas[k] = {"nombre": nombre, "v": _r(val[0], dec + 1), "lo": lo, "hi": hi, "dec": dec, "unidad": unidad,
                       "pct": pv, "pct_lo": plo, "pct_hi": phi, "mediana": _r(celda.mediana(k), dec + 1),
                       "n_ref": len(celda.por_jugador[k])}

    por_franja = []
    for k in POR_FRANJA:
        if k not in metricas or (k == "dif_oro15" and rol == "Support") or (k == "dif_vision_min" and rol != "Support"):
            continue
        x = metricas[k]
        meds = {fr: _r(c.mediana(k), x["dec"] + 1) for fr in FRANJAS
                if (c := celdas.get((fr, rol))) is not None and c.n_jugadores >= REF["min_jugadores"] and c.disponible(k)}
        if len(meds) == len(FRANJAS):
            por_franja.append({"clave": k, "mejor": METRICAS[k][2], "medianas": meds,
                               **{c: x[c] for c in ("nombre", "v", "lo", "hi", "dec", "unidad")}})

    # Las otras franjas en el radar: dónde caería el jugador mediano de cada franja dentro de la tuya
    # (su mediana de cada métrica, en percentil de tu referencia). Winrate y consistencia no se comparan
    # entre franjas (el winrate es 50 % por construcción; la consistencia se mide contra el reparto de
    # cada franja): van en 50.
    radar_franjas = {}
    for fr in FRANJAS:
        c = celdas.get((fr, rol))
        if c is None or c.n_jugadores < REF["min_jugadores"]:
            continue
        niveles = {}
        for clave, _, ms in _componentes(rol):
            ps = [float(_pct(c.mediana(k), celda.por_jugador[k])) for k in ms
                  if clave not in ("winrate", "consistencia") and celda.disponible(k) and c.disponible(k)]
            niveles[clave] = _r(float(np.mean(ps))) if ps else 0.5
        radar_franjas[fr] = niveles

    comps = []
    for clave, nombre, ms in _componentes(rol):
        nivel = ev["comps"][clave]
        lo, hi = _ic(nivel[1:])
        sin = bool(np.isnan(nivel[0]))
        nv = 0.5 if sin else float(nivel[0])
        w = PERF["pesos"][clave]
        comps.append({"clave": clave, "nombre": nombre, "metricas": ms, "nivel": _r(nv), "lo": lo, "hi": hi,
                      "peso": w, "aporte": _r(w * nv), "margen": _r(w * (1 - nv)), "sin_dato": sin})

    # Antes se calculaba el Performance contra cada franja ("rendís como un Plata–Oro"). Se sacó:
    # mapear el rendimiento a un rango es una estimación de ELO, y la política de Riot prohíbe
    # las alternativas al sistema de rangos oficial (calculadoras de MMR/ELO).
    lo, hi = _ic(ev["perf"][1:])

    # Fortalezas y a mejorar: el intervalo del percentil entero de un lado.
    cand = [(k, x) for k, x in metricas.items() if k != "winrate" and x["pct_lo"] is not None]
    fort = sorted([(k, x) for k, x in cand if x["pct_lo"] > PERF["umbral_fortaleza"]], key=lambda t: -t[1]["pct"])[:3]
    debil = sorted([(k, x) for k, x in cand if x["pct_hi"] < PERF["umbral_debilidad"]], key=lambda t: t[1]["pct"])[:3]
    oro_pct = np.nanmean([f["oro_pct"] for f in filas if f["oro_pct"] is not None])
    oro_pct_pct = _r(_pct(oro_pct, celda.por_jugador["_oro_pct"]))

    def item(k, x, con_consejo):
        d = {"clave": k, **{c: x[c] for c in ("nombre", "v", "lo", "hi", "dec", "unidad", "pct", "pct_lo", "pct_hi", "mediana", "n_ref")}}
        if con_consejo:
            d["consejo"] = _consejo(k, rol)
            # Regla 9: morir cuesta más cuando uno lleva más oro del equipo. Se aclara, no se reta.
            if k == "muertes_min" and oro_pct_pct is not None and oro_pct_pct > 0.5:
                d["nota"] = (f"Llevás más oro de tu equipo que el {round(oro_pct_pct * 100)} % de tu franja: "
                             "parte de esas muertes vienen de ser el que hace las jugadas. Lo que cuenta es "
                             "morir sin que el equipo saque nada a cambio.")
        return d

    # Cómo sumar: los dos componentes con más margen, con una meta en números.
    sumar = []
    # El winrate es el resultado, no algo que se practique: no entra como "cómo sumar".
    for c in sorted([c for c in comps if not c["sin_dato"] and c["clave"] != "winrate"], key=lambda c: -c["margen"])[:2]:
        k = next((k for k in c["metricas"] if k in metricas), None)
        meta = None
        if k:
            x = metricas[k]
            mejor = METRICAS.get(k, (None, None, True))[2]
            objetivo, franja_meta = x["mediana"], franja
            ya = x["v"] >= objetivo if mejor else x["v"] <= objetivo
            if ya and franja in FRANJAS and FRANJAS.index(franja) + 1 < len(FRANJAS):
                arriba = celdas.get((FRANJAS[FRANJAS.index(franja) + 1], rol))
                if arriba and arriba.disponible(k):
                    objetivo, franja_meta = _r(arriba.mediana(k), x["dec"] + 1), FRANJAS[FRANJAS.index(franja) + 1]
            meta = {"metrica": k, "nombre": x["nombre"], "desde": x["v"], "hasta": objetivo, "franja": franja_meta,
                    "dec": x["dec"], "unidad": x["unidad"], "ya_supera": (x["v"] >= objetivo) if mejor else (x["v"] <= objetivo)}
        sumar.append({"componente": c["clave"], "nombre": c["nombre"], "nivel": c["nivel"], "margen": c["margen"],
                      "meta": meta, "consejo": _consejo(c["clave"], rol)})

    return {"n": n, "confianza": est.confianza(n), "franja": franja, "n_ref": celda.n_jugadores,
            "ref_winrate_crudo": _r(celda.winrate_crudo),
            "performance": {"v": _r(ev["perf"][0]), "lo": lo, "hi": hi},
            "componentes": comps, "metricas": metricas,
            "fortalezas": [item(k, x, False) for k, x in fort],
            "mejorar": [item(k, x, True) for k, x in debil],
            "sumar": sumar, "por_franja": por_franja, "radar_franjas": radar_franjas,
            "tendencia": tendencia(filas, celda, rol)}


def temprano(filas: list[dict]) -> dict:
    """Los primeros 15 minutos por cola y rol, más ganar o perder la línea contra el resultado."""
    out = defaultdict(dict)
    grupos = defaultdict(list)
    for f in filas:
        if f["cola"] in GRIETA and f.get("rol_ldh") in ROLES:
            for c in colas_de(f):
                grupos[(c, f["rol_ldh"])].append(f)
    for (cola, rol), g in grupos.items():
        if len(g) < MIN:
            continue
        claves = ["cs10", "cs15", "dif_oro10", "dif_oro15", "dif_cs10", "dif_cs15", "dif_xp15"]
        if rol == "Support":
            claves = ["dif_oro10", "dif_oro15", "dif_xp15"]
        met = {}
        for k in claves:
            nombre, fn, _, dec, _u = METRICAS[k]
            met[k] = {"nombre": nombre, "dec": dec, **est.media([fn(f) for f in g])}
        gana = [f for f in g if (f.get("gold_diff_at_15") or 0) > 0 and f.get("gold_diff_at_15") is not None]
        pierde = [f for f in g if f.get("gold_diff_at_15") is not None and f["gold_diff_at_15"] < 0]
        a, b = sum(f["win"] for f in gana), sum(f["win"] for f in pierde)
        p = est.fisher(a, len(gana) - a, b, len(pierde) - b) if gana and pierde else None
        out[cola][rol] = {"n": len(g), "metricas": met,
                          "linea": {"gana": est.wilson(a, len(gana)), "pierde": est.wilson(b, len(pierde)),
                                    "pct_gana": est.wilson(len(gana), len(gana) + len(pierde)),
                                    "p": _r(p), "senal": p is not None and p < AJUSTES["ajuste_muestra"]["alfa"]}}
    return dict(out)


def contra_campeon(mias: list[dict], otros: list[dict]) -> list[dict]:
    """Tus pares (campeón, rol) del modo con 10+ partidas contra los desconocidos que jugaron
    lo mismo en las partidas del grupo. Se sacan los que tenían a alguien del grupo de rival directo."""
    por = defaultdict(list)
    for f in otros:
        if f["persona"] is None and not f["rival_vinculado"]:
            por[(f["champion"], f["role"])].append(f)
    mios = defaultdict(list)
    for f in mias:
        mios[(f["champion"], f["role"])].append(f)
    salida = []
    claves = ["dif_oro15", "cs_min", "kp", "dano", "muertes_min", "vision_min"]
    for (champ, rol), g in mios.items():
        ref = por.get((champ, rol), [])
        if len(g) < MIN or len(ref) < PERF["min_partidas_campeon"]:
            continue
        filas = []
        for k in claves:
            if k in NO_APLICA.get(rol, ()):
                continue
            nombre, fn, mejor, dec, unidad = METRICAS[k]
            d = est.diferencia([fn(f) for f in g], [fn(f) for f in ref])
            if d["v"] is None:
                continue
            filas.append({"clave": k, "nombre": nombre, "dec": dec, "unidad": unidad, "mejor": mejor,
                          "tuyo": est.media([fn(f) for f in g])["v"], "ellos": est.media([fn(f) for f in ref])["v"], **d})
        wins = est.diferencia([float(f["win"]) for f in g], [float(f["win"]) for f in ref])
        salida.append({"campeon": champ, "campeon_id": g[0]["champion_id"], "rol": rol, "n": len(g), "n_ref": len(ref),
                       "jugadores_ref": len({f["puuid"] for f in ref}), "winrate": wins,
                       "winrate_tuyo": _r(np.mean([f["win"] for f in g])), "winrate_ellos": _r(np.mean([f["win"] for f in ref])),
                       "filas": filas})
    return sorted(salida, key=lambda x: -x["n"])


# -------------------------------------------------------------------- generar

# Los tres modos del sitio. Fuera de solo/dúo la referencia sigue siendo de ranked solo/dúo de tu
# franja (la única que hay): en normales el emparejamiento es otro, así que es una orientación.
MODOS = {"solo": ("solo",), "normal": ("normal",), "todo": GRIETA}
NOTA_MODO = {
    "solo": None,
    "normal": "En normales te comparo igual contra jugadores de ranked solo/dúo de tu franja: el emparejamiento "
              "de normales es otro y se juega más suelto, así que tomalo como orientación.",
    "todo": "Junta solo/dúo, flex y normales. La referencia es ranked solo/dúo de tu franja: con normales en la "
            "mezcla, tomalo como orientación.",
}


def ruta_coaching(pid: str, modo: str) -> str:
    return f"coaching/{pid}.json" if modo == "solo" else f"coaching/{modo}/{pid}.json"


def _franja_persona(cuentas: dict) -> tuple[str, dict | None, str]:
    """Franja por el mejor rango de solo/dúo; si no tiene, el de flex; si tampoco, toda la referencia."""
    for cola in ("solo", "flex"):
        mejor = max((c[cola] for c in cuentas.values() if cola in c), key=lambda r: r["valor"] or -1, default=None)
        if mejor and franja_de(mejor["tier"]):
            return franja_de(mejor["tier"]), mejor, cola
    return TODAS, None, "sin_rango"


def generar(db: sqlite3.Connection, filas_por: dict[str, list[dict]], rangos: dict, escribir: Callable) -> None:
    celdas = _celdas()
    grieta = _filas_grieta(db)
    por_persona = defaultdict(list)
    franja_partida = defaultdict(set)  # match -> franjas del grupo en esa partida
    franja_persona = {pid: _franja_persona(cuentas) for pid, cuentas in rangos.items()}
    for f in grieta:
        if f["persona"]:
            por_persona[f["persona"]].append(f)
            if f["persona"] in franja_persona:
                franja_partida[f["match_id"]].add(franja_persona[f["persona"]][0])

    escribir("referencia.json", {
        "franjas": REF["franjas"], "min_jugadores": REF["min_jugadores"], "min_partidas": REF["min_partidas"],
        "celdas": [{"franja": fr, "rol": rol, "jugadores": c.n_jugadores,
                    "medianas": {k: _r(c.mediana(k), 4) for k in c.por_jugador if not k.startswith("_")}}
                   for (fr, rol), c in sorted(celdas.items()) if fr != TODAS],
        "bajada": max((f.get("bajada", "") for f in cargar_filas()), default=None)})

    mejora = {m: [] for m in MODOS}
    for pid, filas in filas_por.items():
        franja, rango, fuente = franja_persona.get(pid, (TODAS, None, "sin_rango"))
        early = temprano(filas)
        for modo, colas in MODOS.items():
            mias = sorted((f for f in por_persona.get(pid, []) if f["cola"] in colas), key=lambda f: f["inicio_ms"])
            por_rol = defaultdict(list)
            for f in mias:
                por_rol[f["role"]].append(f)
            roles = {rol: _rol(g, rol, franja, celdas) for rol, g in por_rol.items() if rol in ROLES and len(g) >= MIN}
            otros = [f for f in grieta if f["cola"] in colas
                     and (franja == TODAS or franja in franja_partida.get(f["match_id"], ()))]
            escribir(ruta_coaching(pid, modo), {
                "modo": modo, "nota_modo": NOTA_MODO[modo],
                "franja": franja, "fuente_franja": fuente,
                "rango": rango and {k: rango[k] for k in ("tier", "division", "lp")},
                "n_modo": len(mias),
                "roles": roles,
                "rol_principal": max(roles, key=lambda r: roles[r]["n"]) if roles else None,
                # El que se muestra por defecto: el de más partidas entre los que tienen referencia. Si el
                # principal cae en una celda sin referencia, se ve el siguiente en vez de "no hay datos".
                "rol_con_referencia": max((r for r in roles if not roles[r].get("sin_referencia")),
                                          key=lambda r: roles[r]["n"], default=None),
                "temprano": early,
                "campeones": contra_campeon(mias, otros),
            })
            for rol, r in roles.items():
                if (t := r.get("tendencia")):
                    mejora[modo].append({"persona": pid, "rol": rol, "franja": franja, "n": t["n"],
                                         "pendiente": t["pendiente"], "lo": t["lo"], "hi": t["hi"],
                                         "veredicto": t["veredicto"], "inicio": t["inicio"], "ahora": t["ahora"]})
    # Quién más mejoró: por la pendiente de la tendencia (puntos cada 100 partidas contra su propia
    # franja), así no se comparan winrates de franjas distintas. Primero los que se separan del ruido.
    orden = {m: sorted(t, key=lambda x: (x["veredicto"] != "mejorando", -x["lo"])) for m, t in mejora.items()}
    escribir("rankings/mejora.json", {
        "nota": "Pendiente del índice por partida (0–100, contra la propia franja y rol), en puntos "
                "cada 100 partidas. 'Mejorando' solo si todo el intervalo está arriba de cero.",
        "tabla": orden["solo"], "modos": orden})
