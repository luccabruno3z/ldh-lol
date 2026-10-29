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
