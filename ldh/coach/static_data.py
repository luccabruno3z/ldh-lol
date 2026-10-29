"""Datos estáticos de Data Dragon: nombres de campeones, ítems, runas y hechizos.

Adaptado de Coach AI (coach/static_data.py) el 2026-10-29:
- idioma es_MX (el cliente de los jugadores), configurable en ajustes.json;
- caché por versión: la de Coach AI guardaba versions.json sin vencimiento y
  quedó trabada en 16.16.1 mientras las partidas ya eran 16.20.
Se agrupa siempre por id; el nombre es solo para mostrar.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from ..ajustes import AJUSTES, CACHE

STATIC_DIR = CACHE / "ddragon"
DDRAGON = "https://ddragon.leagueoflegends.com"
LOCALE = AJUSTES["ddragon_idioma"]
VERSIONES_TTL = 6 * 3600


def _get_json(url: str) -> Any | None:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError):
        return None


def _fetch_json(url: str, cache_name: str, ttl: float | None = None) -> Any | None:
    cache_file = STATIC_DIR / cache_name
    if cache_file.exists() and (ttl is None or time.time() - cache_file.stat().st_mtime < ttl):
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    data = _get_json(url)
    if data is None:
        # Sin red: mejor un dato viejo que ninguno.
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        return None
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


class StaticData:
    def __init__(self) -> None:
        self._version: str | None = None
        self._items: dict[str, dict] | None = None
        self._runes: dict[int, str] | None = None
        self._styles: dict[int, str] | None = None
        self._spells: dict[int, str] | None = None
        self._champ_key: dict[int, str] | None = None
        self._champ_name: dict[int, str] | None = None

    @property
    def version(self) -> str | None:
        if self._version is None:
            versions = _fetch_json(f"{DDRAGON}/api/versions.json", "versions.json", VERSIONES_TTL)
            self._version = versions[0] if versions else None
        return self._version

    def _data(self, archivo: str) -> Any | None:
        if not self.version:
            return None
        return _fetch_json(
            f"{DDRAGON}/cdn/{self.version}/data/{LOCALE}/{archivo}",
            f"{self.version}/{LOCALE}/{archivo}",
        )

    def _load_items(self) -> dict[str, dict]:
        if self._items is None:
            self._items = (self._data("item.json") or {}).get("data", {})
        return self._items

    def _load_runes(self) -> None:
        if self._runes is not None:
            return
        self._runes, self._styles = {}, {}
        for style in self._data("runesReforged.json") or []:
            self._styles[style["id"]] = style["name"]
            for slot in style.get("slots", []):
                for rune in slot.get("runes", []):
                    self._runes[rune["id"]] = rune["name"]

    def _load_spells(self) -> dict[int, str]:
        if self._spells is None:
            self._spells = {}
            for spell in ((self._data("summoner.json") or {}).get("data") or {}).values():
                self._spells[int(spell["key"])] = spell["name"]
        return self._spells

    def _load_champions(self) -> None:
        if self._champ_key is not None:
            return
        self._champ_key, self._champ_name = {}, {}
        for internal, champ in ((self._data("champion.json") or {}).get("data") or {}).items():
            try:
                cid = int(champ["key"])
            except (KeyError, ValueError):
                continue
            self._champ_key[cid] = internal
            self._champ_name[cid] = champ.get("name", internal)

    def champion_key(self, champion_id: int) -> str:
        self._load_champions()
        return self._champ_key.get(champion_id, "")

    def champion_name(self, champion_id: int) -> str:
        self._load_champions()
        return self._champ_name.get(champion_id, "")

    def campeones(self) -> dict[int, tuple[str, str]]:
        """id -> (clave interna, nombre en es_MX). Para publicar a la web."""
        self._load_champions()
        return {cid: (self._champ_key[cid], self._champ_name[cid]) for cid in self._champ_key}

    def item_name(self, item_id: int) -> str:
        item = self._load_items().get(str(item_id))
        return item["name"] if item else f"Ítem {item_id}"

    def item_gold(self, item_id: int) -> int:
        item = self._load_items().get(str(item_id))
        return (item.get("gold") or {}).get("total", 0) if item else 0

    def is_completed_item(self, item_id: int) -> bool:
        """Legendario/completo: cuesta 2000+ de oro total."""
        return self.item_gold(item_id) >= 2000

    def rune_name(self, rune_id: int) -> str:
        self._load_runes()
        return self._runes.get(rune_id, f"Runa {rune_id}")

    def style_name(self, style_id: int) -> str:
        self._load_runes()
        return self._styles.get(style_id, f"Estilo {style_id}")

    def spell_name(self, spell_id: int) -> str:
        return self._load_spells().get(spell_id, f"Hechizo {spell_id}")


_instance: StaticData | None = None


def get_static() -> StaticData:
    global _instance
    if _instance is None:
        _instance = StaticData()
    return _instance
