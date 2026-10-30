"""La rama `datos`: crudo inmutable por partida, rango y estado.

Una partida = un archivo que no se reescribe nunca. Que el archivo exista es
la marca de "ya procesada", así que no hace falta un processed.json.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .ajustes import DATOS, TIMELINES

ANON_CAMPOS = ("puuid", "riotIdGameName", "riotIdTagline", "riotIdName", "summonerName", "summonerId")


# ------------------------------------------------------------------ utilidades

def _escribir_atomico(ruta: Path, datos: bytes) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(datos)
    os.replace(tmp, ruta)


def _json_compacto(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def ahora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# -------------------------------------------------------------------- personas

def cargar_personas() -> list[dict]:
    return json.loads((DATOS / "personas.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------- estado

def cargar_estado() -> dict:
    ruta = DATOS / "estado.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return {"cuentas": {}, "cursores": {}, "salteadas": {}}


def guardar_estado(estado: dict) -> None:
    _escribir_atomico(
        DATOS / "estado.json",
        json.dumps(estado, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"),
    )


# ------------------------------------------------------------- anonimización

def anon_id(puuid: str) -> str:
    sal = os.environ.get("ANON_SALT", "")
    if not sal:
        raise RuntimeError("falta ANON_SALT: sin ella los ids anónimos no serían estables")
    return "anon_" + hashlib.sha256((sal + puuid).encode()).hexdigest()[:12]


def anonimizar_partida(match: dict, vinculados: set[str]) -> dict:
    """Saca la identidad de los que no se vincularon; deja campeón, rol y stats.

    El id anónimo es estable (hash con sal), así que si alguien se vincula
    después se lo reconoce en las partidas ya guardadas.
    """
    meta = match.get("metadata", {})
    meta["participants"] = [p if p in vinculados else anon_id(p) for p in meta.get("participants", [])]
    for p in match.get("info", {}).get("participants", []):
        puuid = p.get("puuid", "")
        if puuid in vinculados:
            continue
        for campo in ANON_CAMPOS:
            if campo in p:
                p[campo] = anon_id(puuid) if campo == "puuid" else ""
    return match


# ----------------------------------------------------------- timeline compacta

_PF_CAMPOS = ("position", "totalGold", "currentGold", "xp", "level",
              "minionsKilled", "jungleMinionsKilled")
_DANO_CAMPOS = ("totalDamageDoneToChampions", "totalDamageTaken")
_STATS_CAMPOS = ("power", "powerMax", "health", "healthMax")
_DANO_RECIBIDO = ("participantId", "name", "spellName", "type",
                  "magicDamage", "physicalDamage", "trueDamage", "basic")


def compactar_timeline(tl: dict, vinculados: set[str]) -> dict:
    """Misma forma que la timeline de Riot (el código de Coach AI la lee igual),
    con solo los campos que se usan. Pesa ~35 KB comprimida contra ~64 KB."""
    info = tl.get("info", {})
    frames = []
    for f in info.get("frames", []):
        pfs = {}
        for pid, pf in (f.get("participantFrames") or {}).items():
            c = {k: pf[k] for k in _PF_CAMPOS if k in pf}
            c["damageStats"] = {k: (pf.get("damageStats") or {}).get(k, 0) for k in _DANO_CAMPOS}
            c["championStats"] = {k: (pf.get("championStats") or {}).get(k, 0) for k in _STATS_CAMPOS}
            pfs[pid] = c
        eventos = []
        for e in f.get("events", []):
            e = dict(e)
            e.pop("victimDamageDealt", None)
            if "victimDamageReceived" in e:
                e["victimDamageReceived"] = [
                    {k: d[k] for k in _DANO_RECIBIDO if k in d} for d in e["victimDamageReceived"]
                ]
            eventos.append(e)
        frames.append({"timestamp": f.get("timestamp"), "participantFrames": pfs, "events": eventos})
    participantes = [
        {"participantId": p.get("participantId"),
         "puuid": p["puuid"] if p.get("puuid") in vinculados else anon_id(p.get("puuid", ""))}
        for p in info.get("participants", [])
    ]
    return {
        "metadata": {"matchId": tl.get("metadata", {}).get("matchId")},
        "info": {"frameInterval": info.get("frameInterval"), "frames": frames,
                 "participants": participantes},
    }


# ---------------------------------------------------------------------- crudo

def _ruta(tipo: str, match_id: str, inicio_ms: int) -> Path:
    plataforma = match_id.split("_", 1)[0].lower()
    mes = datetime.fromtimestamp(inicio_ms / 1000, timezone.utc).strftime("%Y-%m")
    base = TIMELINES if tipo == "timelines" else DATOS / tipo
    return base / plataforma / mes / f"{match_id}.json.gz"


def _indice_existentes() -> set[str]:
    return {p.name[: -len(".json.gz")] for p in (DATOS / "partidas").glob("*/*/*.json.gz")}


class Crudo:
    """Acceso al crudo con un índice en memoria de lo que ya está guardado."""

    def __init__(self) -> None:
        self.existentes = _indice_existentes()

    def tiene(self, match_id: str) -> bool:
        return match_id in self.existentes

    def guardar(self, match: dict, timeline: dict | None, vinculados: set[str]) -> None:
        match_id = match["metadata"]["matchId"]
        inicio = match["info"].get("gameStartTimestamp") or match["info"].get("gameCreation")
        if timeline is not None:
            _escribir_atomico(_ruta("timelines", match_id, inicio),
                              gzip.compress(_json_compacto(compactar_timeline(timeline, vinculados)), 9))
        # La partida se escribe al final: su archivo es la marca de "procesada".
        _escribir_atomico(_ruta("partidas", match_id, inicio),
                          gzip.compress(_json_compacto(anonimizar_partida(match, vinculados)), 9))
        self.existentes.add(match_id)


def iterar_partidas() -> Iterator[tuple[dict, dict | None]]:
    """(match, timeline o None) de todo el crudo, en orden de archivo."""
    for ruta in sorted((DATOS / "partidas").glob("*/*/*.json.gz")):
        match = json.loads(gzip.decompress(ruta.read_bytes()))
        rtl = TIMELINES / ruta.relative_to(DATOS / "partidas")
        tl = json.loads(gzip.decompress(rtl.read_bytes())) if rtl.exists() else None
        yield match, tl


# ----------------------------------------------------------------------- rango

def agregar_foto_rango(puuid: str, entradas: list[dict]) -> bool:
    """Anota el rango solo si cambió algo. Devuelve True si escribió."""
    ruta = DATOS / "rango" / f"{puuid}.jsonl"
    foto = {
        e["queueType"]: [e.get("tier"), e.get("rank"), e.get("leaguePoints"), e.get("wins"), e.get("losses")]
        for e in entradas
        if e.get("queueType") in ("RANKED_SOLO_5x5", "RANKED_FLEX_SR")
    }
    ultima = None
    if ruta.exists():
        lineas = ruta.read_text(encoding="utf-8").splitlines()
        if lineas:
            ultima = json.loads(lineas[-1])["colas"]
    if ultima == foto:
        return False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": ahora_iso(), "colas": foto}, ensure_ascii=False) + "\n")
    return True


def cargar_fotos_rango(puuid: str) -> list[dict]:
    ruta = DATOS / "rango" / f"{puuid}.jsonl"
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
