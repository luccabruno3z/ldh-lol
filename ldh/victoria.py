"""Probabilidad de ganar minuto a minuto (la base de la tesis de xPetu): una regresión logística sobre el
estado de la partida, entrenada con las timelines del grupo.

El estado a un instante t, siempre como diferencia azul − rojo: oro, XP, kills, torres, inhibidores caídos
(vuelven a los 5 min), dragones, alma, larvas, Heraldo, Barón y Dragón Ancestral activos. El oro, la XP, las
kills y las torres van con un coeficiente por tramo de minuto: 1.000 de oro no pesan lo mismo a los 8 que a los 30.

Se valida antes de usarlo (partidas apartadas, no filas): Brier, log-loss, acierto a los 15 y la curva de
calibración por deciles, también por cola y por tramo. Si un decil se aleja más de 5 puntos, no se publica.
"""

from __future__ import annotations

import bisect
import gzip
import json
import sqlite3

import numpy as np

from .ajustes import AJUSTES, CACHE
from .almacen import _escribir_atomico, _json_compacto, _ruta

TRAMOS = (0, 10, 20, 30)  # minutos donde arranca cada tramo
POR_TRAMO = ("oro", "xp", "kills", "torres")
FIJAS = ("inhib", "dragones", "alma", "larvas", "heraldo", "baron", "ancestral")
BARON_MS, ANCESTRAL_MS, INHIB_MS = 180_000, 150_000, 300_000
VERSION = 1


def nombres() -> list[str]:
    return [f"{v}_{t}" for v in POR_TRAMO for t in TRAMOS] + list(FIJAS) + ["lado"]


def _equipo(pid: int) -> int:
    return 100 if pid <= 5 else 200


class Partida:
    """Las series de una timeline, listas para pedir el estado en cualquier instante."""

    def __init__(self, tl: dict):
        frames = tl["info"]["frames"]
        self.t_frames = [f["timestamp"] for f in frames]
        self.oro, self.xp = [], []
        for f in frames:
            pf = f["participantFrames"]
            d_oro = d_xp = 0
            for k, v in pf.items():
                s = 1 if int(k) <= 5 else -1
                d_oro += s * v.get("totalGold", 0)
                d_xp += s * v.get("xp", 0)
            self.oro.append(d_oro)
            self.xp.append(d_xp)
        self.eventos = []  # (t, tipo, equipo que suma, extra)
        for f in frames:
            for e in f["events"]:
                t, tipo = e.get("timestamp", 0), e["type"]
                if tipo == "CHAMPION_KILL" and e.get("killerId"):
                    self.eventos.append((t, "kill", _equipo(e["killerId"]) if e["killerId"] > 0 else
                                         300 - _equipo(e["victimId"]), e))
                elif tipo == "BUILDING_KILL":
                    gana = 300 - e["teamId"]
                    clase = "torre" if e.get("buildingType") == "TOWER_BUILDING" else "inhib"
                    self.eventos.append((t, clase, gana, e))
                elif tipo == "ELITE_MONSTER_KILL" and e.get("killerTeamId") in (100, 200):
                    m, sub = e.get("monsterType"), e.get("monsterSubType")
                    clase = {"BARON_NASHOR": "baron", "RIFTHERALD": "heraldo", "HORDE": "larva"}.get(m)
                    if m == "DRAGON":
                        clase = "ancestral" if sub == "ELDER_DRAGON" else "dragon"
                    if clase:
                        self.eventos.append((t, clase, e["killerTeamId"], e))
                elif tipo == "DRAGON_SOUL_GIVEN" and e.get("teamId") in (100, 200):
                    self.eventos.append((t, "alma", e["teamId"], e))
        self.eventos.sort(key=lambda x: x[0])
        self.t_eventos = [e[0] for e in self.eventos]
        self.fin = self.t_frames[-1]

    def estado(self, t: int, sin: frozenset = frozenset(), oro_extra: float = 0) -> dict:
        """Diferencias azul − rojo en el instante t. El oro y la XP salen del último frame (cada 60 s).
        sin: índices de self.eventos que se sacan y oro_extra: oro que se le suma al azul (negativo, al rojo),
        para medir cuánto pesó algo (el costo de una muerte)."""
        i = max(0, bisect.bisect_right(self.t_frames, t) - 1)
        s = {"oro": self.oro[i] + oro_extra, "xp": self.xp[i], "kills": 0, "torres": 0, "inhib": 0, "dragones": 0, "alma": 0,
             "larvas": 0, "heraldo": 0, "baron": 0, "ancestral": 0}
        for k, ev in enumerate(self.eventos[:bisect.bisect_right(self.t_eventos, t)]):
            te, clase, eq, e = ev
            if k in sin:
                continue
            sg = 1 if eq == 100 else -1
            if clase == "kill":
                s["kills"] += sg
            elif clase == "torre":
                s["torres"] += sg
            elif clase == "inhib" and t - te < INHIB_MS:
                s["inhib"] += sg
            elif clase == "dragon":
                s["dragones"] += sg
            elif clase == "alma":
                s["alma"] += sg
            elif clase == "larva":
                s["larvas"] += sg
            elif clase == "heraldo":
                s["heraldo"] += sg
            elif clase == "baron" and t - te < BARON_MS:
                s["baron"] += sg
            elif clase == "ancestral" and t - te < ANCESTRAL_MS:
                s["ancestral"] += sg
        s["minuto"] = t / 60_000
        return s


def vector(s: dict, lado: int = 1) -> np.ndarray:
    """Las variables del modelo para un estado (desde el lado azul; lado = 1 azul, −1 rojo es el término de
    lado que va con el signo del equipo que se mira)."""
    m = s["minuto"]
    tramo = max(i for i, a in enumerate(TRAMOS) if m >= a)
    x = []
    for v in POR_TRAMO:
        escala = 1000 if v in ("oro", "xp") else 1
        x += [s[v] / escala if i == tramo else 0.0 for i in range(len(TRAMOS))]
    x += [float(s[v]) for v in FIJAS]
    x.append(float(lado))
    return np.array(x)


def _filas(db: sqlite3.Connection) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """X, y (ganó azul), id de partida, minuto y cola, una fila por partida y minuto. Se cachea."""
    ruta = CACHE / "fase5_filas_modelo.npz"
    partidas = db.execute("""SELECT match_id, inicio_ms, ganador, cola FROM partidas
                             WHERE cola IN ('solo','flex','normal') AND tiene_timeline=1 ORDER BY match_id""").fetchall()
    clave = f"v{VERSION}:{len(partidas)}:{partidas[-1][0] if partidas else ''}"
    if ruta.exists():
        c = np.load(ruta, allow_pickle=False)
        if str(c["clave"]) == clave:
            return c["X"], c["y"], c["mid"], c["minuto"], c["cola"]
    X, y, mids, mins, colas = [], [], [], [], []
    for k, (mid, inicio, ganador, cola) in enumerate(partidas):
        tl = json.loads(gzip.decompress(_ruta("timelines", mid, inicio).read_bytes()))
        p = Partida(tl)
        for t in range(60_000, p.fin + 1, 60_000):
            s = p.estado(t)
            X.append(vector(s))
            y.append(1 if ganador == 100 else 0)
            mids.append(k)
            mins.append(s["minuto"])
            colas.append(cola)
    X, y = np.array(X), np.array(y)
    mids, mins, colas = np.array(mids), np.array(mins), np.array(colas)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(ruta, X=X, y=y, mid=mids, minuto=mins, cola=colas, clave=np.array(clave))
    return X, y, mids, mins, colas


def _simetrico(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cada estado también desde el lado rojo (variables con signo cambiado, resultado al revés). Así el
    modelo no se inclina hacia un lado por azar de la muestra, y el término de lado mide la ventaja real
    del azul. Antes de esto, la parte de prueba tenía 46 % de victorias azules contra 49 % y la
    calibración salía corrida 5 puntos solo por eso."""
    return np.vstack([X, -X]), np.concatenate([y, 1 - y])


def _calibracion(p: np.ndarray, y: np.ndarray, grupos: np.ndarray | None = None, reps: int = 300) -> list[dict]:
    """Predicho contra real por deciles. Con grupos (la partida de cada fila), el intervalo de la diferencia
    sale de remuestrear partidas: las ~30 filas de una partida no son independientes."""
    bordes = np.linspace(0, 1, 11)
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    remuestras = []
    if grupos is not None:
        unicos = np.unique(grupos)
        idx = {g: np.where(grupos == g)[0] for g in unicos}
        for _ in range(reps):
            ii = np.concatenate([idx[g] for g in rng.choice(unicos, size=len(unicos))])
            remuestras.append((p[ii], y[ii]))
    out = []
    for a, b in zip(bordes[:-1], bordes[1:]):
        en = lambda q: (q >= a) & (q < b if b < 1 else q <= b)  # noqa: E731
        m = en(p)
        if not m.sum():
            continue
        fila = {"desde": round(float(a), 1), "predicho": round(float(p[m].mean()), 3),
                "real": round(float(y[m].mean()), 3), "n": int(m.sum())}
        if remuestras:
            ds = [pp[en(pp)].mean() - yy[en(pp)].mean() for pp, yy in remuestras if en(pp).sum()]
            fila["dif_lo"], fila["dif_hi"] = (round(float(np.percentile(ds, q)), 3) for q in (2.5, 97.5))
        out.append(fila)
    return out


def entrenar(db: sqlite3.Connection) -> dict:
    """Entrena con el 80 % de las partidas, valida con el 20 % y, si pasa, reentrena con todo."""
    from sklearn.linear_model import LogisticRegression
    X, y, mids, mins, colas = _filas(db)
    rng = np.random.default_rng(AJUSTES["bootstrap_semilla"])
    unicas = np.unique(mids)
    prueba = set(rng.choice(unicas, size=len(unicas) // 5, replace=False).tolist())
    es_prueba = np.array([m in prueba for m in mids])
    modelo = LogisticRegression(C=1.0, max_iter=2000, fit_intercept=False).fit(*_simetrico(X[~es_prueba], y[~es_prueba]))
    Xt, yt = _simetrico(X[es_prueba], y[es_prueba])
    dup = lambda a: np.concatenate([a[es_prueba], a[es_prueba]])  # noqa: E731
    mt, mp, cp = dup(mids), dup(mins), dup(colas)
    p = modelo.predict_proba(Xt)[:, 1]
    eps = 1e-9
    cal = _calibracion(p, yt, mt)
    a15 = np.abs(mp - 15) < 0.5
    tramos = {f"{a}+" if b == 999 else f"{a}-{b}": (mp >= a) & (mp < b) for a, b in zip(TRAMOS, (*TRAMOS[1:], 999))}
    validacion = {
        "partidas_prueba": len(prueba), "filas_prueba": int(es_prueba.sum()),
        "brier": round(float(np.mean((p - yt) ** 2)), 4), "brier_base": 0.25,
        "logloss": round(float(-np.mean(yt * np.log(p + eps) + (1 - yt) * np.log(1 - p + eps))), 4),
        "acierto_15": round(float(np.mean((p[a15] > 0.5) == yt[a15])), 3),
        "calibracion": cal,
        "calibracion_cola": {c: _calibracion(p[cp == c], yt[cp == c], mt[cp == c]) for c in ("solo", "flex", "normal")},
        "calibracion_tramo": {k: _calibracion(p[m], yt[m], mt[m]) for k, m in tramos.items()},
    }
    peor = max((abs(c["predicho"] - c["real"]) for c in cal if c["n"] >= 200), default=0)
    validacion["peor_decil"] = round(peor, 3)
    validacion["aprobado"] = peor <= 0.05
    final = LogisticRegression(C=1.0, max_iter=2000, fit_intercept=False).fit(*_simetrico(X, y))
    return {"version": VERSION, "variables": nombres(), "coef": [round(float(c), 5) for c in final.coef_[0]],
            "intercepto": 0.0, "partidas": len(unicas), "filas": len(y), "validacion": validacion}


def prob(modelo: dict, s: dict, equipo: int = 100) -> float:
    """Probabilidad de que gane `equipo` en el estado s (diferencias azul − rojo)."""
    z = modelo["intercepto"] + float(np.dot(modelo["coef"], vector(s)))
    p = 1 / (1 + np.exp(-z))
    return float(p if equipo == 100 else 1 - p)


def cargar_modelo() -> dict | None:
    ruta = CACHE / "fase5_modelo.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def guardar_modelo(m: dict) -> None:
    _escribir_atomico(CACHE / "fase5_modelo.json", _json_compacto(m))
