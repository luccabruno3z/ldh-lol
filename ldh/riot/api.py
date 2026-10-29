"""Cliente de la API de Riot con rate limiting y reintentos.

Adaptado de Coach AI (coach/riot_api.py) el 2026-10-29: la clave sale de
RIOT_API_KEY, el cliente no está atado a una sola cuenta y no hay caché de disco
(el crudo lo guarda ldh.almacen). Los reintentos y la ventana deslizante son los
mismos.
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Any
from urllib.parse import quote

import requests

from ..ajustes import AJUSTES
from .regions import platform_host, routing_host

MAX_RETRIES = 4


class RiotAPIError(RuntimeError):
    def __init__(self, status: int, url: str, detail: str = ""):
        self.status = status
        self.url = url
        super().__init__(f"HTTP {status} en {url}{': ' + detail if detail else ''}")


class _RateLimiter:
    """Ventanas deslizantes; bloquea hasta que quepa una petición más."""

    def __init__(self, limits):
        self._limits = [(n, window, deque()) for n, window in limits]

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            wait = 0.0
            for count, window, hits in self._limits:
                while hits and now - hits[0] > window:
                    hits.popleft()
                if len(hits) >= count:
                    wait = max(wait, window - (now - hits[0]) + 0.01)
            if wait <= 0:
                for _, _, hits in self._limits:
                    hits.append(now)
                return
            time.sleep(wait)


class RiotClient:
    """Un cliente para todas las cuentas: la plataforma va en cada llamada.

    Los límites de la clave son por región de ruteo, pero con un grupo casi
    todo en LAS alcanza con un solo limitador compartido (más conservador).
    """

    def __init__(self, api_key: str | None = None, verbose: bool = True):
        key = api_key or os.environ.get("RIOT_API_KEY", "")
        if not key.startswith("RGAPI-"):
            raise RiotAPIError(401, "-", "falta RIOT_API_KEY o no empieza con RGAPI-")
        self.verbose = verbose
        self.llamadas = 0
        self._limiter = _RateLimiter(AJUSTES["rate_limits"])
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Riot-Token": key,
                "Accept": "application/json",
                "User-Agent": "ldh-stats-lol/0.1 (estadisticas de un grupo de amigos)",
            }
        )

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def _get(self, url: str, params: dict | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._limiter.acquire()
            self.llamadas += 1
            try:
                resp = self._session.get(url, params=params, timeout=20)
            except requests.RequestException as exc:
                last_error = exc
                sleep = 2**attempt
                self._log(f"  falló la red ({exc}); reintento en {sleep}s")
                time.sleep(sleep)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                self._log(f"  rate limit; espero {retry_after}s")
                time.sleep(retry_after + 1)
                continue

            if resp.status_code in (500, 502, 503, 504):
                sleep = 2**attempt
                self._log(f"  Riot devolvió {resp.status_code}; reintento en {sleep}s")
                time.sleep(sleep)
                continue

            detail = ""
            try:
                detail = resp.json().get("status", {}).get("message", "")
            except ValueError:
                detail = resp.text[:200]
            raise RiotAPIError(resp.status_code, url, detail)

        raise RiotAPIError(0, url, f"sin éxito tras {MAX_RETRIES} intentos ({last_error})")

    # ------------------------------------------------------------------ cuentas

    def account_by_riot_id(self, game_name: str, tag_line: str) -> dict:
        """account-v1: Riot ID -> PUUID. Es global; americas lo sirve para todos."""
        ruta = f"/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}"
        ultimo: RiotAPIError | None = None
        for host in ("americas", "europe", "asia"):
            try:
                return self._get(f"https://{host}.api.riotgames.com{ruta}")
            except RiotAPIError as exc:
                if exc.status not in (403, 404):
                    raise
                ultimo = exc
        raise ultimo  # type: ignore[misc]

    def account_by_puuid(self, puuid: str) -> dict:
        return self._get(
            f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
        )

    def active_region(self, puuid: str) -> str | None:
        """Plataforma donde juega LoL (la2, br1…). Verificado el 2026-10-29."""
        data = self._get(
            "https://americas.api.riotgames.com/riot/account/v1/region/by-game/lol/"
            f"by-puuid/{puuid}"
        )
        return data.get("region")

    def ranked_entries(self, platform: str, puuid: str) -> list[dict]:
        """league-v4 by-puuid (verificado el 2026-10-29)."""
        return self._get(f"{platform_host(platform)}/lol/league/v4/entries/by-puuid/{puuid}")

    # ----------------------------------------------------------------- partidas

    def match_ids(self, platform: str, puuid: str, start_time: int | None = None,
                  maximo: int = 10_000) -> list[str]:
        """Todos los ids desde start_time (epoch en segundos), más recientes primero.

        count máximo por llamada: 100 (101 devuelve 400; verificado).
        """
        host = routing_host(platform)
        ids: list[str] = []
        cursor = 0
        while len(ids) < maximo:
            params: dict[str, Any] = {"start": cursor, "count": 100}
            if start_time is not None:
                params["startTime"] = start_time
            page = self._get(f"{host}/lol/match/v5/matches/by-puuid/{puuid}/ids", params)
            if not page:
                break
            ids.extend(page)
            cursor += len(page)
            if len(page) < 100:
                break
        return ids[:maximo]

    def match(self, match_id: str) -> dict:
        return self._get(f"{routing_host(_plataforma_de(match_id))}/lol/match/v5/matches/{match_id}")

    def timeline(self, match_id: str) -> dict:
        return self._get(
            f"{routing_host(_plataforma_de(match_id))}/lol/match/v5/matches/{match_id}/timeline"
        )


def _plataforma_de(match_id: str) -> str:
    """'LA2_1630650104' -> 'la2'."""
    return match_id.split("_", 1)[0].lower()
