"""Muestra de referencia por franja de rango y rol (fase 3).

Jugadores al azar de cada división de solo/dúo (league-v4 entries), con sus
partidas de la temporada en su rol principal. Sirve para percentiles entre
jugadores, que exigen 10+ partidas de cada uno.

- El crudo (partida anonimizada + timeline compacta) queda en .cache/referencia/,
  que no va a git (decisión del doc de lecciones: las timelines no van a git).
- `armar_filas()` reduce ese crudo a datos/referencia/filas.jsonl.gz, una fila
  por partida y jugador con las métricas que usa la fase 3 y el id anónimo.
- Se puede cortar y retomar: cada partida se guarda al bajarla y el estado de
  cada jugador queda en .cache/referencia/estado.json.
"""

from __future__ import annotations

import gzip
import json
import random
import time
from collections import Counter
from pathlib import Path

from .ajustes import AJUSTES, CACHE, DATOS, INICIO_HISTORIAL
from .almacen import (_escribir_atomico, _json_compacto, ahora_iso, anon_id, anonimizar_partida,
                      cargar_estado, compactar_timeline)
from .coach.analyze import extract_match_stats
from .riot.api import RiotAPIError, RiotClient, _RateLimiter
from .riot.regions import platform_host, routing_host

CONF = AJUSTES["referencia"]
DIR = CACHE / "referencia"
ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")
DIVISIONES = ("I", "II", "III", "IV")


def franja_de(tier: str | None) -> str | None:
    for nombre, tiers in CONF["franjas"].items():
        if tier in tiers:
            return nombre
    return None


# ------------------------------------------------------------------- crudo local

def _ruta(tipo: str, match_id: str) -> Path:
    return DIR / tipo / f"{match_id}.json.gz"


def _leer(tipo: str, match_id: str) -> dict | None:
    r = _ruta(tipo, match_id)
    return json.loads(gzip.decompress(r.read_bytes())) if r.exists() else None


def _cargar_estado() -> dict:
    r = DIR / "estado.json"
    if r.exists():
        return json.loads(r.read_text(encoding="utf-8"))
    return {"semillas": {}, "jugadores": {}}


def _guardar_estado(est: dict) -> None:
    _escribir_atomico(DIR / "estado.json", json.dumps(est, ensure_ascii=False).encode("utf-8"))


def _rol_en(match: dict, puuid: str) -> str | None:
    for p in match["info"]["participants"]:
        if p.get("puuid") == puuid:
            return CONF["roles_api"].get(p.get("teamPosition") or "")
    return None


def _remake(match: dict) -> bool:
    return any(p.get("gameEndedInEarlySurrender") for p in match["info"]["participants"])


# --------------------------------------------------------------------- scouteo

def _llenas(est: dict) -> Counter:
    c = Counter()
    for j in est["jugadores"].values():
        if j.get("listo"):
            c[(j["franja"], j["rol"])] += 1
    return c


def _semillas(api: RiotClient, est: dict, rng: random.Random) -> list[tuple[str, str, str]]:
    """(puuid, tier, división) de todas las divisiones de cada franja, mezclados por división."""
    vinculados = {c["puuid"] for c in cargar_estado()["cuentas"].values() if c.get("puuid")}
    por_div: list[list[tuple[str, str, str]]] = []
    for tiers in CONF["franjas"].values():
        for tier in tiers:
            for div in DIVISIONES:
                clave = f"{tier}|{div}"
                if clave not in est["semillas"]:
                    url = f"{platform_host('la2')}/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{div}"
                    est["semillas"][clave] = [e["puuid"] for e in api._get(url, {"page": 1}) if e.get("puuid")]
                    _guardar_estado(est)
                ps = [p for p in est["semillas"][clave] if p not in vinculados]
                rng.shuffle(ps)
                por_div.append([(p, tier, div) for p in ps])
    # Round-robin entre divisiones: cada franja se llena parejo con todas sus divisiones.
    salida = []
    for i in range(max(map(len, por_div))):
        for lista in por_div:
            if i < len(lista):
                salida.append(lista[i])
    return salida


def _bajar(api: RiotClient, match_id: str, puuid: str, con_timeline: bool) -> dict:
    m = _leer("partidas", match_id)
    if m is None:
        crudo = api._get(f"{routing_host('la2')}/lol/match/v5/matches/{match_id}")
        m = anonimizar_partida(crudo, {puuid})
        _escribir_atomico(_ruta("partidas", match_id), gzip.compress(_json_compacto(m), 6))
    if con_timeline and not _ruta("timelines", match_id).exists():
        tl = api._get(f"{routing_host('la2')}/lol/match/v5/matches/{match_id}/timeline")
        _escribir_atomico(_ruta("timelines", match_id),
                          gzip.compress(_json_compacto(compactar_timeline(tl, {puuid})), 6))
    return m


def _scoutear_jugador(api: RiotClient, est: dict, puuid: str, tier: str, div: str) -> None:
    franja = franja_de(tier)
    j = est["jugadores"].setdefault(puuid, {"tier": tier, "div": div, "franja": franja})
    if j.get("listo") or j.get("abandonado"):
        return
    if "ids" not in j:
        url = f"{routing_host('la2')}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        j["ids"] = api._get(url, {"queue": 420, "startTime": INICIO_HISTORIAL,
                                  "count": CONF["ids_por_jugador"]})
    roles: dict[str, str] = {}
    for mid in j["ids"]:
        m = _bajar(api, mid, puuid, con_timeline=False)
        if not _remake(m) and (rol := _rol_en(m, puuid)):
            roles[mid] = rol
        if len(roles) == CONF["partidas_para_decidir"]:
            break
    if not roles:
        j["abandonado"] = "sin partidas útiles"
        return
    rol = Counter(roles.values()).most_common(1)[0][0]
    j["rol"] = rol
    if _llenas(est)[(franja, rol)] >= CONF["meta_por_celda"]:
        j["abandonado"] = "celda llena"
        return
    # Primero solo partidas (un pedido cada una) hasta juntar las del rol; las timelines se bajan
    # recién cuando el jugador llega al mínimo, para no gastarlas en jugadores que se abandonan.
    usadas = []
    for i, mid in enumerate(j["ids"]):
        if len(usadas) >= CONF["partidas_por_jugador"]:
            break
        if len(usadas) + (len(j["ids"]) - i) < CONF["min_partidas"]:
            break
        m = _bajar(api, mid, puuid, con_timeline=False)
        if not _remake(m) and _rol_en(m, puuid) == rol:
            usadas.append(mid)
    if len(usadas) < CONF["min_partidas"]:
        j["abandonado"] = f"{len(usadas)} partidas en su rol"
        return
    for mid in usadas:
        _bajar(api, mid, puuid, con_timeline=True)
    j["usadas"] = usadas
    j["listo"] = ahora_iso()


def scoutear(hasta_epoch: float | None = None) -> None:
    api = RiotClient()
    # La clave es compartida con Coach AI: el scouteo usa solo una parte del límite.
    api._limiter = _RateLimiter(CONF["rate_limits"])
    est = _cargar_estado()
    rng = random.Random(23)
    semillas = _semillas(api, est, rng)
    meta = CONF["meta_por_celda"]
    print(f"{len(semillas)} semillas; meta {meta} jugadores por celda", flush=True)
    t0, hechos = time.time(), 0
    for puuid, tier, div in semillas:
        llenas = _llenas(est)
        if all(llenas[(f, r)] >= meta for f in CONF["franjas"] for r in ROLES):
            break
        if hasta_epoch and time.time() > hasta_epoch:
            print("Corte por horario.", flush=True)
            break
        try:
            _scoutear_jugador(api, est, puuid, tier, div)
        except RiotAPIError as exc:
            if exc.status in (401, 403):
                print(f"La clave no anda ({exc.status}); corto.", flush=True)
                _guardar_estado(est)
                break
            est["jugadores"].setdefault(puuid, {})["abandonado"] = f"error {exc.status}"
        _guardar_estado(est)
        hechos += 1
        if hechos % 10 == 0:
            llenas = _llenas(est)
            # "HB/Top=12": iniciales de la franja (Hierro–Bronce) y del rol.
            celdas = " ".join(f"{''.join(x[0] for x in f.split('–'))}/{r[:3]}={llenas[(f, r)]}"
                              for f in CONF["franjas"] for r in ROLES)
            print(f"[{(time.time() - t0) / 60:.0f} min, {api.llamadas} pedidos, {hechos} jugadores] {celdas}",
                  flush=True)
    _guardar_estado(est)


# ----------------------------------------------------------------------- filas

def participacion_objetivos(timeline: dict | None, match: dict, pid: int) -> float | None:
    """Parte de los dragones, Heraldos y Barones de su equipo donde estuvo (mató o asistió).

    Sin larvas ni estructuras: con ellas Lucca y Glarrex daban lo mismo (0,35 y 0,35) y la
    brecha conocida del coaching (63 % contra 42 %) desaparecía. Así da 0,68 contra 0,45 en
    ranked desde el 14/08, la ventana en que se midió.
    """
    if not timeline:
        return None
    equipo = next((p["teamId"] for p in match["info"]["participants"] if p["participantId"] == pid), None)
    total = estuvo = 0
    for f in timeline["info"]["frames"]:
        for e in f.get("events", []):
            if (e.get("type") != "ELITE_MONSTER_KILL" or e.get("monsterType") == "HORDE"
                    or e.get("killerTeamId") != equipo):
                continue
            total += 1
            if e.get("killerId") == pid or pid in (e.get("assistingParticipantIds") or []):
                estuvo += 1
    return estuvo / total if total else None


CAMPOS = ("match_id", "patch", "duration_min", "win", "role", "champion", "kills", "deaths", "assists",
          "kill_participation", "damage_share", "gold_per_min", "cs_per_min", "vision_per_min",
          "control_wards", "cs_at_10", "cs_at_15", "gold_at_10", "gold_at_15", "cs_diff_at_10",
          "cs_diff_at_15", "gold_diff_at_10", "gold_diff_at_15", "xp_diff_at_10", "xp_diff_at_15",
          "won_lane_gold_exp", "vision_advantage_vs_opp", "gold")


def fila_de(match: dict, timeline: dict | None, puuid: str) -> dict | None:
    """Las métricas de un jugador en una partida, igual para amigos, referencia y desconocidos."""
    s = extract_match_stats(match, puuid, timeline)
    if s is None:
        return None
    fila = {k: s.get(k) for k in CAMPOS}
    me = next(p for p in match["info"]["participants"] if p.get("puuid") == puuid)
    oro_equipo = sum(p.get("goldEarned", 0) for p in match["info"]["participants"] if p["teamId"] == me["teamId"])
    fila["oro_pct"] = me.get("goldEarned", 0) / oro_equipo if oro_equipo else None
    fila["champion_id"] = me.get("championId")
    fila["obj_part"] = participacion_objetivos(timeline, match, me["participantId"])
    rival = next((p for p in match["info"]["participants"] if p["teamId"] != me["teamId"]
                  and me.get("teamPosition") and p.get("teamPosition") == me.get("teamPosition")), None)
    minutos = (fila["duration_min"] or 0) or None
    fila["dif_vision_min"] = ((me.get("visionScore", 0) - rival.get("visionScore", 0)) / minutos
                              if rival and minutos else None)
    fila["rival"] = rival.get("puuid") if rival else None
    fila["muertes_min"] = fila["deaths"] / minutos if minutos else None
    return fila


def armar_filas() -> int:
    """Crudo local -> datos/referencia/filas.jsonl.gz (solo jugadores con 10+ partidas)."""
    est = _cargar_estado()
    lineas = []
    for puuid, j in est["jugadores"].items():
        if not j.get("listo"):
            continue
        for mid in j["usadas"]:
            m, tl = _leer("partidas", mid), _leer("timelines", mid)
            f = fila_de(m, tl, puuid)
            if f is None:
                continue
            f.update({"jugador": anon_id(puuid), "franja": j["franja"], "tier": j["tier"],
                      "div": j["div"], "bajada": j["listo"][:10]})
            lineas.append(json.dumps(f, ensure_ascii=False, separators=(",", ":")))
    _escribir_atomico(DATOS / "referencia" / "filas.jsonl.gz", gzip.compress("\n".join(lineas).encode("utf-8"), 9))
    print(f"referencia: {len(lineas)} filas", flush=True)
    return len(lineas)


def cargar_filas() -> list[dict]:
    r = DATOS / "referencia" / "filas.jsonl.gz"
    if not r.exists():
        return []
    return [json.loads(l) for l in gzip.decompress(r.read_bytes()).decode("utf-8").splitlines() if l]
