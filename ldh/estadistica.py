"""Intervalos y pruebas. Ninguna métrica se publica sin su n y su intervalo."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .ajustes import AJUSTES

REPS = AJUSTES["bootstrap_reps"]
SEMILLA = AJUSTES["bootstrap_semilla"]
CONF = AJUSTES["confianza"]
_Z = {0.90: 1.6449, 0.95: 1.96, 0.99: 2.5758}[CONF]
_Q = ((1 - CONF) / 2 * 100, (1 + CONF) / 2 * 100)


def _r(x: float | None, d: int = 3) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), d)


def wilson(ganadas: int, n: int) -> dict:
    """Winrate con intervalo de Wilson (se porta bien con n chico y con 0 % o 100 %)."""
    if n == 0:
        return {"v": None, "lo": None, "hi": None, "n": 0}
    p = ganadas / n
    den = 1 + _Z**2 / n
    centro = (p + _Z**2 / (2 * n)) / den
    margen = _Z * math.sqrt(p * (1 - p) / n + _Z**2 / (4 * n * n)) / den
    return {"v": _r(p), "lo": _r(centro - margen), "hi": _r(centro + margen), "n": n}


def media(valores: Sequence[float | None]) -> dict:
    """Media con intervalo bootstrap (percentil)."""
    x = np.array([v for v in valores if v is not None], dtype=float)
    if len(x) == 0:
        return {"v": None, "lo": None, "hi": None, "n": 0}
    if len(x) == 1:
        return {"v": _r(x[0]), "lo": None, "hi": None, "n": 1}
    rng = np.random.default_rng(SEMILLA)
    medias = x[rng.integers(0, len(x), (REPS, len(x)))].mean(axis=1)
    lo, hi = np.percentile(medias, _Q)
    return {"v": _r(x.mean()), "lo": _r(lo), "hi": _r(hi), "n": len(x)}


def kda(kills: Sequence[int], deaths: Sequence[int], assists: Sequence[int]) -> dict:
    """(K+A)/max(D,1) sobre las sumas, con bootstrap remuestreando partidas.
    Promediar el KDA de cada partida lo inflan las partidas con 0 muertes."""
    k, d, a = (np.array(v, dtype=float) for v in (kills, deaths, assists))
    n = len(k)
    if n == 0:
        return {"v": None, "lo": None, "hi": None, "n": 0}
    v = (k.sum() + a.sum()) / max(d.sum(), 1)
    if n == 1:
        return {"v": _r(v, 2), "lo": None, "hi": None, "n": 1}
    rng = np.random.default_rng(SEMILLA)
    idx = rng.integers(0, n, (REPS, n))
    boot = (k[idx].sum(1) + a[idx].sum(1)) / np.maximum(d[idx].sum(1), 1)
    lo, hi = np.percentile(boot, _Q)
    return {"v": _r(v, 2), "lo": _r(lo, 2), "hi": _r(hi, 2), "n": n}


def diferencia(a: Sequence[float], b: Sequence[float]) -> dict:
    """Diferencia de medias a − b con intervalo bootstrap. 'ruido' si cruza el cero."""
    xa = np.array([v for v in a if v is not None], dtype=float)
    xb = np.array([v for v in b if v is not None], dtype=float)
    if len(xa) < 2 or len(xb) < 2:
        return {"v": None, "lo": None, "hi": None, "na": len(xa), "nb": len(xb), "ruido": True}
    rng = np.random.default_rng(SEMILLA)
    da = xa[rng.integers(0, len(xa), (REPS, len(xa)))].mean(1)
    db = xb[rng.integers(0, len(xb), (REPS, len(xb)))].mean(1)
    lo, hi = np.percentile(da - db, _Q)
    return {"v": _r(xa.mean() - xb.mean()), "lo": _r(lo), "hi": _r(hi),
            "na": len(xa), "nb": len(xb), "ruido": bool(lo <= 0 <= hi)}


# ---- Fase 2: ajuste por muestra, confianza y pruebas entre grupos ----

AJ = AJUSTES["ajuste_muestra"]


def ajustada_tasa(ganadas: int, n: int, k: float = AJ["k_tasa"], centro: float = 0.5) -> float | None:
    """Winrate encogido hacia el centro: suma k partidas 'al centro'. 2 de 2 no es 100 %."""
    return None if n == 0 else _r((ganadas + k * centro) / (n + k))


def ajustado_kda(kills: int, deaths: int, assists: int, mediana: float | None,
                 k_muertes: float = AJ["k_muertes"]) -> float | None:
    """KDA con k muertes sumadas 'a la mediana' del mismo rol (el doc de funcionalidades usa 20)."""
    if mediana is None:
        return None
    return _r((kills + assists + k_muertes * mediana) / (max(deaths, 0) + k_muertes), 2)


def confianza(n: int, aportes: Sequence[float] | None = None) -> str:
    """alta con 15+; baja con menos de 8 o si una sola partida explica más del 40 % del resultado."""
    if aportes:
        total = sum(aportes)
        if total > 0 and max(aportes) / total > AJ["tope_peso_partida"]:
            return "baja"
    if n >= AJ["confianza_alta"]:
        return "alta"
    return "baja" if n < AJ["confianza_media"] else "media"


def fisher(a: int, b: int, c: int, d: int) -> float:
    """Prueba exacta de Fisher, bilateral, para [[a, b], [c, d]].
    Suma las tablas con los mismos márgenes y probabilidad <= la observada."""
    n1, n2, m1 = a + b, c + d, a + c
    n = n1 + n2

    def lp(x: int) -> float:
        return (math.lgamma(n1 + 1) - math.lgamma(x + 1) - math.lgamma(n1 - x + 1)
                + math.lgamma(n2 + 1) - math.lgamma(m1 - x + 1) - math.lgamma(n2 - m1 + x + 1)
                - math.lgamma(n + 1) + math.lgamma(m1 + 1) + math.lgamma(n - m1 + 1))

    obs = lp(a)
    p = sum(math.exp(lp(x)) for x in range(max(0, m1 - n2), min(n1, m1) + 1) if lp(x) <= obs + 1e-7)
    return min(1.0, p)


def benjamini_hochberg(ps: Sequence[float]) -> list[float]:
    """p ajustados por Benjamini-Hochberg: con muchas comparaciones alguna sale 'significativa' por azar."""
    m = len(ps)
    orden = sorted(range(m), key=lambda i: ps[i])
    ajust = [0.0] * m
    previo = 1.0
    for rango in range(m, 0, -1):
        i = orden[rango - 1]
        previo = min(previo, ps[i] * m / rango)
        ajust[i] = previo
    return ajust
