"""Reconstruye ldh.sqlite desde el crudo. Se tira y se arma de cero en cada corrida:
así cualquier corrección de lógica se aplica también hacia atrás."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from .ajustes import AJUSTES, SALIDA, cola_de
from .almacen import anon_id, cargar_estado, cargar_fotos_rango, cargar_personas, iterar_partidas
from .coach.analyze import extract_match_stats

EXTRACTOR_VERSION = 1
RUTA_BASE = SALIDA / "descargas" / "ldh.sqlite"

ESQUEMA = """
CREATE TABLE personas (id TEXT PRIMARY KEY, nombre TEXT NOT NULL);
CREATE TABLE cuentas (puuid TEXT PRIMARY KEY, persona_id TEXT NOT NULL REFERENCES personas(id),
    riot_id TEXT NOT NULL, plataforma TEXT, principal INTEGER NOT NULL DEFAULT 0);
CREATE TABLE partidas (match_id TEXT PRIMARY KEY, plataforma TEXT, queue_id INTEGER, cola TEXT,
    game_version TEXT, patch TEXT, inicio_ms INTEGER, fin_ms INTEGER, duracion_seg INTEGER,
    ganador INTEGER, tiene_timeline INTEGER);
CREATE TABLE participantes (match_id TEXT NOT NULL REFERENCES partidas(match_id),
    participant_id INTEGER, puuid TEXT, persona_id TEXT, team_id INTEGER, lado TEXT,
    team_position TEXT, rol TEXT, champion_id INTEGER, champion_key TEXT, win INTEGER,
    kills INTEGER, deaths INTEGER, assists INTEGER, cs INTEGER, oro INTEGER, dano_campeones INTEGER,
    dano_recibido INTEGER, vision INTEGER, wards INTEGER, wards_control INTEGER,
    kp REAL, dano_pct REAL, nivel INTEGER, items TEXT, keystone INTEGER, hechizos TEXT,
    PRIMARY KEY (match_id, participant_id));
CREATE TABLE filas (match_id TEXT NOT NULL, puuid TEXT NOT NULL, persona_id TEXT NOT NULL,
    extractor_version INTEGER, datos TEXT NOT NULL, PRIMARY KEY (match_id, puuid));
CREATE TABLE eventos (match_id TEXT NOT NULL, minuto REAL, tipo TEXT, subtipo TEXT,
    actor INTEGER, victima INTEGER, asistentes TEXT, equipo INTEGER, x INTEGER, y INTEGER);
CREATE TABLE rango_fotos (puuid TEXT NOT NULL, t TEXT NOT NULL, cola TEXT NOT NULL, tier TEXT,
    division TEXT, lp INTEGER, wins INTEGER, losses INTEGER, valor INTEGER);
CREATE TABLE lp_partida (match_id TEXT NOT NULL, puuid TEXT NOT NULL, cola TEXT, delta INTEGER,
    exacto INTEGER, partidas_tramo INTEGER, PRIMARY KEY (match_id, puuid));
CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT);
CREATE INDEX ix_part_persona ON participantes(persona_id);
CREATE INDEX ix_ev_match ON eventos(match_id);
"""

TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND",
         "MASTER", "GRANDMASTER", "CHALLENGER"]
DIVISIONES = {"IV": 0, "III": 1, "II": 2, "I": 3}
COLA_RANKED = {"RANKED_SOLO_5x5": "solo", "RANKED_FLEX_SR": "flex"}
EVENTOS = {"CHAMPION_KILL", "ELITE_MONSTER_KILL", "BUILDING_KILL", "TURRET_PLATE_DESTROYED",
           "WARD_PLACED", "WARD_KILL"}


def valor_rango(tier: str | None, division: str | None, lp: int | None) -> int | None:
    """Escala continua: un ascenso no se lee como una caída de 80 LP.
    Master+ no tiene divisiones: todos parten de la misma base y el LP sigue."""
    if tier not in TIERS:
        return None
    i = TIERS.index(tier)
    if i >= TIERS.index("MASTER"):
        return TIERS.index("MASTER") * 400 + (lp or 0)
    return i * 400 + DIVISIONES.get(division or "IV", 0) * 100 + (lp or 0)


def _validar(info: dict) -> str | None:
    """Rechaza valores imposibles (lección 2 del doc de funcionalidades)."""
    dur = info.get("gameDuration") or 0
    if not 60 <= dur <= 4 * 3600:
        return f"duración imposible ({dur} s)"
    if len(info.get("participants", [])) != 10 and cola_de(info.get("queueId")) != "otra":
        return "no hay 10 participantes"
    for p in info.get("participants", []):
        if not 0 <= (p.get("kills") or 0) <= 100 or not 0 <= (p.get("deaths") or 0) <= 100:
            return "K/D imposible"
    return None


def reconstruir() -> dict:
    personas = cargar_personas()
    estado = cargar_estado()
    RUTA_BASE.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUTA_BASE.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(ESQUEMA)

    # cuentas: puuid real y su id anónimo apuntan a la misma persona
    por_puuid: dict[str, str] = {}
    real_de: dict[str, str] = {}
    for p in personas:
        db.execute("INSERT INTO personas VALUES (?,?)", (p["id"], p["nombre"]))
        for k, c in enumerate(p["cuentas"]):
            e = estado["cuentas"].get(c["riot_id"]) or {}
            if not e.get("puuid"):
                continue
            db.execute("INSERT INTO cuentas VALUES (?,?,?,?,?)",
                       (e["puuid"], p["id"], c["riot_id"], e.get("plataforma"), int(bool(c.get("principal")))))
            por_puuid[e["puuid"]] = p["id"]
            real_de[e["puuid"]] = e["puuid"]
            real_de[anon_id(e["puuid"])] = e["puuid"]

    n = descartadas = 0
    for match, tl in iterar_partidas():
        info = match["info"]
        motivo = _validar(info)
        if motivo:
            descartadas += 1
            print(f"  {match['metadata']['matchId']}: descartada, {motivo}")
            continue
        mid = match["metadata"]["matchId"]
        ganador = next((t["teamId"] for t in info.get("teams", []) if t.get("win")), None)
        inicio = info.get("gameStartTimestamp") or info.get("gameCreation")
        db.execute("INSERT INTO partidas VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            mid, mid.split("_")[0].lower(), info.get("queueId"), cola_de(info.get("queueId")),
            info.get("gameVersion"), ".".join((info.get("gameVersion") or "").split(".")[:2]),
            inicio, info.get("gameEndTimestamp"), info.get("gameDuration"), ganador, int(tl is not None)))

        for p in info["participants"]:
            puuid = real_de.get(p.get("puuid"), p.get("puuid"))
            persona = por_puuid.get(puuid)
            ch = p.get("challenges") or {}
            db.execute("INSERT INTO participantes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                mid, p.get("participantId"), puuid, persona, p.get("teamId"),
                "azul" if p.get("teamId") == 100 else "rojo", p.get("teamPosition") or None,
                AJUSTES["roles"].get(p.get("teamPosition") or "", None),
                p.get("championId"), p.get("championName"), int(bool(p.get("win"))),
                p.get("kills"), p.get("deaths"), p.get("assists"),
                (p.get("totalMinionsKilled") or 0) + (p.get("neutralMinionsKilled") or 0),
                p.get("goldEarned"), p.get("totalDamageDealtToChampions"), p.get("totalDamageTaken"),
                p.get("visionScore"), p.get("wardsPlaced"), p.get("detectorWardsPlaced"),
                ch.get("killParticipation"), ch.get("teamDamagePercentage"), p.get("champLevel"),
                json.dumps([p.get(f"item{i}") or 0 for i in range(7)]),
                ((((p.get("perks") or {}).get("styles") or [{}])[0].get("selections") or [{}])[0]).get("perk"),
                json.dumps([p.get("summoner1Id"), p.get("summoner2Id")])))
            if persona:
                fila = extract_match_stats(match, p.get("puuid"), tl)
                if fila:
                    db.execute("INSERT INTO filas VALUES (?,?,?,?,?)",
                               (mid, puuid, persona, EXTRACTOR_VERSION, json.dumps(fila, ensure_ascii=False)))

        for frame in (tl or {}).get("info", {}).get("frames", []):
            for e in frame.get("events", []):
                if e.get("type") not in EVENTOS:
                    continue
                pos = e.get("position") or {}
                db.execute("INSERT INTO eventos VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    mid, round((e.get("timestamp") or 0) / 60000, 2), e["type"],
                    e.get("monsterType") or e.get("buildingType") or e.get("wardType"),
                    e.get("killerId") or e.get("creatorId"), e.get("victimId"),
                    json.dumps(e.get("assistingParticipantIds") or []) if e.get("assistingParticipantIds") else None,
                    e.get("killerTeamId") or e.get("teamId"), pos.get("x"), pos.get("y")))
        n += 1

    _cargar_rango(db, list(por_puuid))
    db.execute("INSERT INTO meta VALUES ('construida', ?)", (datetime.now().astimezone().isoformat(),))
    db.execute("INSERT INTO meta VALUES ('extractor_version', ?)", (str(EXTRACTOR_VERSION),))
    db.commit()
    db.execute("VACUUM")
    db.close()
    tmp.replace(RUTA_BASE)
    print(f"Base: {n} partidas, {descartadas} descartadas -> {RUTA_BASE}")
    return {"partidas": n, "descartadas": descartadas}


def _cargar_rango(db: sqlite3.Connection, puuids: list[str]) -> None:
    """Fotos de rango y LP por partida.

    Entre dos fotos consecutivas de una cola: si hubo exactamente una partida
    de esa cola, el cambio es de esa partida (exacto). Si hubo varias, cada una
    queda marcada como parte de un tramo y no se inventa su LP individual.
    """
    for puuid in puuids:
        previas: dict[str, tuple[str, int]] = {}
        for foto in cargar_fotos_rango(puuid):
            for qt, (tier, div, lp, w, l) in foto["colas"].items():
                cola = COLA_RANKED[qt]
                val = valor_rango(tier, div, lp)
                db.execute("INSERT INTO rango_fotos VALUES (?,?,?,?,?,?,?,?,?)",
                           (puuid, foto["t"], cola, tier, div, lp, w, l, val))
                if cola in previas and val is not None:
                    t0, v0 = previas[cola]
                    ms0 = int(datetime.fromisoformat(t0).timestamp() * 1000)
                    ms1 = int(datetime.fromisoformat(foto["t"]).timestamp() * 1000)
                    tramo = db.execute(
                        "SELECT pa.match_id FROM partidas pa JOIN participantes pt USING(match_id) "
                        "WHERE pt.puuid=? AND pa.cola=? AND pa.fin_ms>? AND pa.fin_ms<=?",
                        (puuid, cola, ms0, ms1)).fetchall()
                    for (mid,) in tramo:
                        db.execute("INSERT OR REPLACE INTO lp_partida VALUES (?,?,?,?,?,?)",
                                   (mid, puuid, cola, val - v0,  # con exacto=0 es el total del tramo
                                    int(len(tramo) == 1), len(tramo)))
                if val is not None:
                    previas[cola] = (foto["t"], val)
