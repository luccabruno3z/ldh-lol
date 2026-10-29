# Copiado sin cambios de Coach AI (coach/metrics.py) el 2026-10-29.
"""Metricas derivadas de coaching, calculadas siempre igual.

Todo lo que se fue descubriendo analizando partidas vive aca, en funciones puras
sobre las filas de `matches.jsonl`. El informe, el tablero y cualquier script
usan estas mismas funciones, asi que un numero no puede significar dos cosas
distintas segun quien lo calcule.

Tres decisiones de medicion que costaron encontrar y conviene no re-discutir:

1. Las muertes tardias se miden POR MINUTO DE VENTANA post-20, no en absoluto.
   Siete muertes en una partida de 39 minutos son menos graves que tres en una
   de 27, y el conteo absoluto castiga injustamente las partidas largas.

2. El dano se compara como PORCENTAJE DEL EQUIPO, no por minuto. El dano por
   minuto de un mago crece con los niveles y los objetos, asi que promediarlo
   sobre partidas de duracion distinta mide la duracion, no el juego.

3. La intensidad de combate se mide por TIEMPO HACIENDO DANO, no por muertes.
   Las muertes son una senal escasa y tardia: cuentan el resultado de las
   peleas, no cuanto se peleo.
"""

from __future__ import annotations

import datetime
import statistics as st
from typing import Callable, Iterable, Sequence

# --------------------------------------------------------------------------- #
# Basicos
# --------------------------------------------------------------------------- #


def played_at(row: dict) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(row["game_creation"] / 1000)


def winrate(rows: Sequence[dict]) -> float:
    return 100 * sum(1 for r in rows if r["win"]) / len(rows) if rows else 0.0


def mean_of(rows: Iterable[dict], f: Callable[[dict], float | None]) -> float | None:
    vals = []
    for r in rows:
        try:
            v = f(r)
        except (KeyError, TypeError, ZeroDivisionError):
            continue
        if v is not None:
            vals.append(v)
    return st.mean(vals) if vals else None


# --------------------------------------------------------------------------- #
# Las tres metricas propias
# --------------------------------------------------------------------------- #


def late_death_rate(row: dict) -> float:
    """Muertes despues del minuto 20 por minuto de ventana post-20."""
    window = max(row["duration_min"] - 20, 1.0)
    return row["deaths_by_phase"]["late_20_plus"] / window


def damage_share(row: dict) -> float:
    """Porcentaje del dano a campeones del equipo. Comparable entre partidas."""
    return row.get("damage_share", 0.0)


def damage_per_live_minute(row: dict) -> float:
    """Dano por minuto EN PIE, descontando el tiempo esperando en la fuente."""
    alive = row["duration_min"] * (1 - row.get("time_dead_pct", 0) / 100)
    return row["damage_to_champions"] / alive if alive > 0 else 0.0


def damage_per_cast(row: dict) -> float:
    casts = row["casts_q"] + row["casts_w"] + row["casts_e"] + row["casts_r"]
    return row["damage_to_champions"] / casts if casts else 0.0


def casts_per_minute(row: dict) -> float:
    casts = row["casts_q"] + row["casts_w"] + row["casts_e"] + row["casts_r"]
    return casts / row["duration_min"] if row["duration_min"] else 0.0


def dodges_per_min(row: dict) -> float | None:
    """Habilidades esquivadas por minuto.

    En absoluto no sirve: una partida de 40 minutos da mas esquivas que una de
    25 sin que nadie esquive mejor. Misma correccion que las muertes tardias.
    """
    d = row.get("skillshots_dodged")
    if d is None or not row.get("duration_min"):
        return None
    return d / row["duration_min"]


def combat_fraction(damage_series: Sequence[float], threshold: float = 400) -> float:
    """Fraccion de minutos con dano a campeones por encima del umbral.

    `damage_series` es el dano de cada minuto, que sale de la diferencia entre
    frames consecutivos de `damageStats.totalDamageDoneToChampions`.
    """
    if not damage_series:
        return 0.0
    return sum(1 for d in damage_series if d >= threshold) / len(damage_series)


# --------------------------------------------------------------------------- #
# Catalogo de metricas para tablas comparativas
# --------------------------------------------------------------------------- #

# (clave, etiqueta, funcion, "mas es mejor")
CATALOG: list[tuple[str, str, Callable[[dict], float | None], bool]] = [
    ("winrate", "Winrate %", lambda r: 100.0 if r["win"] else 0.0, True),
    ("duration", "Duración (min)", lambda r: r["duration_min"], False),
    ("deaths", "Muertes", lambda r: r["deaths"], False),
    ("late_deaths", "Muertes post-20 por min", late_death_rate, False),
    ("early_deaths", "Muertes 0-10", lambda r: r["deaths_by_phase"]["early_0_10"], False),
    ("time_dead", "% del tiempo muerto", lambda r: r.get("time_dead_pct"), False),
    ("kp", "Participación en kills %", lambda r: r["kill_participation"], True),
    ("assists", "Asistencias", lambda r: r["assists"], True),
    ("dmg_share", "% del daño del equipo", damage_share, True),
    ("dmg_live", "Daño por minuto vivo", damage_per_live_minute, True),
    ("casts_min", "Lanzamientos por minuto", casts_per_minute, True),
    ("gold_min", "Oro por minuto", lambda r: r["gold_per_min"], True),
    ("gold15", "Oro de carril @15", lambda r: r.get("gold_diff_at_15"), True),
    ("xp15", "XP de carril @15", lambda r: r.get("xp_diff_at_15"), True),
    ("vision", "Visión por minuto", lambda r: r["vision_per_min"], True),
    ("control_wards", "Wards de control", lambda r: r["control_wards"], True),
    ("wards", "Wards colocadas", lambda r: r["wards_placed"], True),
    ("wards_killed", "Wards enemigas destruidas", lambda r: r["wards_killed"], True),
    ("first_item", "Minuto del 1er ítem", lambda r: r.get("first_item_min"), False),
    ("items", "Ítems completados", lambda r: len(r.get("build_order") or []), True),
    ("picks", "Picks con aliado", lambda r: r.get("picks_with_ally"), True),
    ("dodges", "Habilidades esquivadas por min", dodges_per_min, True),
    # Depende del campeon: las de Sona casi no son skillshots y las de Xerath si.
    # Comparar este numero entre campeones distintos no significa nada.
    ("skillshot", "Precision de skillshots %", lambda r: r.get("skillshot_accuracy"), True),
]

BY_KEY = {k: (label, fn, higher) for k, label, fn, higher in CATALOG}


def summarize(rows: Sequence[dict], keys: Sequence[str] | None = None) -> dict[str, float | None]:
    """Promedio de las metricas del catalogo sobre un conjunto de partidas."""
    keys = keys or [k for k, _, _, _ in CATALOG]
    out: dict[str, float | None] = {"n": len(rows)}
    for k in keys:
        if k not in BY_KEY:
            continue
        out[k] = mean_of(rows, BY_KEY[k][1])
    return out


def compare_sets(named: dict[str, Sequence[dict]], keys: Sequence[str] | None = None) -> list[dict]:
    """Tabla comparativa entre varios conjuntos (vos, tu base, el espejo...)."""
    keys = keys or [k for k, _, _, _ in CATALOG]
    rows = []
    for k in keys:
        if k not in BY_KEY:
            continue
        label, fn, higher = BY_KEY[k]
        entry = {"key": k, "label": label, "higher_is_better": higher}
        for name, group in named.items():
            entry[name] = mean_of(group, fn)
        rows.append(entry)
    return rows


# --------------------------------------------------------------------------- #
# Sesiones
# --------------------------------------------------------------------------- #


def split_sessions(rows: Sequence[dict], gap_minutes: float = 180) -> list[list[dict]]:
    """Agrupa partidas en sesiones; un hueco de 3 horas abre una nueva."""
    ordered = sorted(rows, key=lambda r: r["game_creation"])
    sessions: list[list[dict]] = []
    current: list[dict] = []
    for r in ordered:
        if current and (r["game_creation"] - current[-1]["game_creation"]) / 60000 > gap_minutes:
            sessions.append(current)
            current = []
        current.append(r)
    if current:
        sessions.append(current)
    return sessions


def fatigue_curve(rows: Sequence[dict], cap: int = 6) -> list[dict]:
    """Winrate segun la posicion de la partida dentro de su sesion.

    Es la forma de ver el cansancio sin preguntarle nada al jugador.
    """
    buckets: dict[int, list[dict]] = {}
    for session in split_sessions(rows):
        for i, r in enumerate(session, 1):
            buckets.setdefault(min(i, cap), []).append(r)
    return [
        {"position": pos, "n": len(g), "winrate": winrate(g)}
        for pos, g in sorted(buckets.items())
    ]


def winrate_ci(rows: Sequence[dict], reps: int = 4000, seed: int = 23) -> dict:
    """Winrate con intervalo del 90% por bootstrap. Sin n, un winrate no dice nada."""
    import numpy as np

    if not rows:
        return {"n": 0, "winrate": None, "lo": None, "hi": None}
    w = np.array([1.0 if r["win"] else 0.0 for r in rows])
    bs = np.random.default_rng(seed).choice(w, (reps, len(w))).mean(axis=1)
    lo, hi = np.percentile(bs, [5, 95])
    return {"n": len(rows), "winrate": round(100 * float(w.mean()), 1),
            "lo": round(100 * float(lo), 1), "hi": round(100 * float(hi), 1)}


def winrate_por_campeon(rows: Sequence[dict], minimo: int = 5) -> list[dict]:
    """Winrate de cada campeon-rol que jugaste, con muestra e intervalo."""
    grupos: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        grupos.setdefault((r.get("champion", "?"), r.get("role", "?")), []).append(r)
    out = []
    for (champ, role), g in grupos.items():
        if len(g) < minimo:
            continue
        out.append({"champion": champ, "role": role, **winrate_ci(g)})
    return sorted(out, key=lambda d: -d["n"])


def discriminantes(rows: Sequence[dict], keys: Sequence[str] | None = None,
                   reps: int = 2000, seed: int = 7,
                   minimo: int = 4) -> list[dict]:
    """Que metricas separan tus victorias de tus derrotas en este campeon.

    Es la unica fuente disponible cuando no hay un pool de referencia: en vez
    de inventar un objetivo, se mira que hiciste distinto en las que ganaste.

    Ojo con leerlo como una regla. Con veinte partidas casi todo es ruido, asi
    que cada diferencia viene con su intervalo por bootstrap y se marca cuando
    cruza el cero: eso significa "no distingo esto del azar", no "no importa".
    """
    import numpy as np

    keys = keys or [k for k, _, _, _ in CATALOG if k != "winrate"]
    ganadas = [r for r in rows if r["win"]]
    perdidas = [r for r in rows if not r["win"]]
    rng = np.random.default_rng(seed)
    out = []
    for k in keys:
        if k not in BY_KEY:
            continue
        label, fn, higher = BY_KEY[k]
        g = np.array([v for v in (_safe(fn, r) for r in ganadas) if v is not None], dtype=float)
        p = np.array([v for v in (_safe(fn, r) for r in perdidas) if v is not None], dtype=float)
        if len(g) < minimo or len(p) < minimo:
            continue
        diff = float(g.mean() - p.mean())
        bs = (rng.choice(g, (reps, len(g))).mean(axis=1)
              - rng.choice(p, (reps, len(p))).mean(axis=1))
        lo, hi = (float(x) for x in np.percentile(bs, [5, 95]))
        sd = float(np.sqrt((g.var(ddof=1) + p.var(ddof=1)) / 2)) or 1e-9
        out.append({
            "key": k, "label": label, "higher_is_better": higher,
            "ganadas": float(g.mean()), "perdidas": float(p.mean()),
            "n_ganadas": int(len(g)), "n_perdidas": int(len(p)),
            "diff": diff, "lo": lo, "hi": hi,
            "efecto": abs(diff) / sd,
            "solido": (lo > 0) or (hi < 0),
            # si la diferencia apunta al lado que conviene
            "a_favor": (diff > 0) == higher,
        })
    out.sort(key=lambda d: (not d["solido"], -d["efecto"]))
    return out


def _safe(fn: Callable[[dict], float | None], row: dict) -> float | None:
    try:
        return fn(row)
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def current_session(rows: Sequence[dict], gap_minutes: float = 180,
                    cap: int = 6) -> dict:
    """En que punto de la sesion estas ahora mismo.

    Si la ultima partida quedo fuera de la ventana, la sesion se cerro sola y la
    proxima vuelve a contar desde la #1. `bucket` es el numero recortado al tope
    de la curva de cansancio, para poder marcar la fila que te toca.
    """
    vacia = {"jugadas": 0, "numero": 1, "bucket": 1, "activa": False,
             "minutos": None, "last_ms": None, "gap": gap_minutes, "cap": cap}
    if not rows:
        return vacia
    ultima = max(rows, key=lambda r: r["game_creation"])
    minutos = (datetime.datetime.now() - played_at(ultima)).total_seconds() / 60
    activa = minutos <= gap_minutes
    # `jugadas` vale para la sesion abierta; el tablero recalcula si vencio,
    # asi que se manda igual aunque ahora este cerrada.
    abierta = split_sessions(rows, gap_minutes)[-1]
    jugadas = len(abierta)
    victorias = sum(1 for r in abierta if r["win"])
    return {"jugadas": jugadas if activa else 0, "numero": (jugadas if activa else 0) + 1,
            "bucket": min((jugadas if activa else 0) + 1, cap),
            "activa": activa, "minutos": round(minutos),
            "abiertas": jugadas, "victorias": victorias,
            "derrotas": jugadas - victorias,
            "last_ms": ultima["game_creation"],
            "gap": gap_minutes, "cap": cap}


def rolling(rows: Sequence[dict], key: str, windows: Sequence[int] = (10, 20, 30, 50)) -> list[dict]:
    """La metrica en varias ventanas moviles hacia atras, de mas reciente a mas larga."""
    ordered = sorted(rows, key=lambda r: r["game_creation"])
    label, fn, higher = BY_KEY[key]
    out = []
    for n in windows:
        g = ordered[-n:]
        if len(g) < min(n, 5):
            continue
        out.append({"window": len(g), "value": mean_of(g, fn), "winrate": winrate(g)})
    return out


# --------------------------------------------------------------------------- #
# Progresion de rango
# --------------------------------------------------------------------------- #

DIVISIONS = {"IV": 3, "III": 2, "II": 1, "I": 0}


def lp_remaining(tier_rank: str, lp: int) -> int:
    """LP netos hasta el siguiente tier, desde 'EMERALD II' + 73."""
    parts = tier_rank.split()
    division = parts[-1] if parts and parts[-1] in DIVISIONS else "IV"
    return DIVISIONS[division] * 100 + (100 - lp)


def games_needed(remaining: int, win_rate: float, gain: float, loss: float) -> int | None:
    """Partidas para cubrir `remaining` LP. None si el winrate no alcanza."""
    net = gain * win_rate - loss * (1 - win_rate)
    if net <= 0:
        return None
    return int(-(-remaining // net))


def break_even(gain: float, loss: float) -> float:
    """Winrate a partir del cual se sube. Con 19/22 son 53,7%."""
    return loss / (gain + loss)
