"""Lee los JSON publicados (api/) por HTTP, con caché TTL y dato viejo si falla la red.
El bot nunca llama a Riot: solo lee lo que publicó el pipeline."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

# En Railway: https://luccabruno3z.github.io/ldh-lol/api ; en local: http://127.0.0.1:8010/api
DATA_URL = os.getenv("LDH_DATA_URL", "https://luccabruno3z.github.io/ldh-lol/api").rstrip("/")


class Datos:
    def __init__(self, ttl: int = 300, timeout: int = 10, max_retries: int = 3):
        self.ttl = ttl
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self._cache: dict[str, tuple[float, object]] = {}
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _json(self, ruta: str):
        url = f"{DATA_URL}/{ruta}"
        cached = self._cache.get(url)
        if cached and time.monotonic() - cached[0] < self.ttl:
            return cached[1]
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        ultimo: Exception | None = None
        for intento in range(self.max_retries):
            try:
                async with self._session.get(url) as resp:
                    if resp.status == 404:
                        return None
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
                    self._cache[url] = (time.monotonic(), data)
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                # ValueError: JSON a medio publicar. Se reintenta igual que un error de red.
                ultimo = exc
                await asyncio.sleep(2**intento)
        if cached:
            logger.warning("Uso datos viejos de %s: %s", url, ultimo)
            return cached[1]
        raise RuntimeError(f"No pude leer {url}: {ultimo}")

    async def personas(self) -> list[dict]:
        return await self._json("personas.json") or []

    async def perfil(self, persona_id: str) -> dict | None:
        return await self._json(f"perfil/{quote(persona_id)}.json")

    async def historial(self, persona_id: str, pagina: int = 1) -> dict | None:
        return await self._json(f"historial/{quote(persona_id)}/{pagina}.json")

    async def roles(self, persona_id: str) -> dict | None:
        return await self._json(f"roles/{quote(persona_id)}.json")

    async def campeones_de(self, persona_id: str) -> dict | None:
        return await self._json(f"campeones/{quote(persona_id)}.json")

    async def cuenta(self, persona_id: str, indice: int) -> dict | None:
        """Vista de una sola cuenta de alguien con varias (cuenta/<persona>/<i>.json)."""
        return await self._json(f"cuenta/{quote(persona_id)}/{indice}.json")

    async def equipos(self) -> dict:
        return await self._json("equipos.json") or {}

    async def matchups(self, persona_id: str) -> dict | None:
        return await self._json(f"matchups/{quote(persona_id)}.json")

    async def heatmap(self, persona_id: str) -> dict | None:
        return await self._json(f"heatmap/{quote(persona_id)}.json")

    async def jungla(self, persona_id: str) -> dict | None:
        return await self._json(f"jungla/{quote(persona_id)}.json")

    async def recientes(self) -> list[dict]:
        return await self._json("recientes.json") or []

    async def partidas_resumen(self) -> list[dict]:
        """Una fila mínima por partida de cada persona (p, t, c, w, ch, lp): semanal y competencias."""
        return await self._json("partidas_resumen.json") or []

    async def consejos(self) -> dict:
        return await self._json("consejos.json") or {}

    async def coaching(self, persona_id: str, modo: str = "solo") -> dict | None:
        """modo: solo, normal o todo (solo/dúo, flex y normales juntas)."""
        sub = "" if modo == "solo" else f"{modo}/"
        return await self._json(f"coaching/{sub}{quote(persona_id)}.json")

    async def coaching_auto(self, persona_id: str, modo: str | None = None) -> dict | None:
        """El modo pedido; sin pedido, solo/dúo si algún rol tiene referencia, si no todo junto."""
        if modo:
            return await self.coaching(persona_id, modo)
        d = await self.coaching(persona_id, "solo")
        if d and d.get("rol_con_referencia"):
            return d
        return await self.coaching(persona_id, "todo") or d

    async def sinergia(self) -> dict:
        return await self._json("sinergia.json") or {"filas": []}

    async def rachas(self, persona_id: str) -> dict | None:
        return await self._json(f"rachas/{quote(persona_id)}.json")

    async def rachas_grupo(self) -> dict | None:
        return await self._json("rachas/grupo.json")

    async def ranking(self, nombre: str) -> dict | None:
        """semana, mes, temporada o roles."""
        return await self._json(f"rankings/{nombre}.json")

    async def campeones(self) -> dict:
        return (await self._json("campeones.json") or {}).get("campeones", {})

    async def ajustes(self) -> dict:
        return await self._json("ajustes.json") or {}

    async def buscar(self, texto: str) -> dict | None:
        """Por id, nombre o Riot ID (con o sin #TAG). Solo personas vinculadas."""
        t = texto.strip().lower()
        personas = await self.personas()
        for criterio in (
            lambda p: p["id"] == t or p["nombre"].lower() == t,
            lambda p: any(c.lower() == t or c.lower().split("#")[0] == t for c in p["cuentas"]),
            lambda p: t in p["nombre"].lower() or any(t in c.lower() for c in p["cuentas"]),
        ):
            hallado = next((p for p in personas if criterio(p)), None)
            if hallado:
                return hallado
        return None
