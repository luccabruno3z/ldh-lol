"""Las pools objetivo que declara cada uno con -pool.

La copia del bot vive en el volumen (pools.json). Cada cambio se sube además al repo público
luccabruno3z/ldh-lol-metas (un solo pools.json) por la API de contenidos de GitHub, para que el pipeline
lo lea sin token. El token (GITHUB_TOKEN_METAS) es fine-grained y solo puede escribir en ese repo: si se
filtrara, no toca el repo principal ni los datos.

Si GitHub falla o falta el token, el cambio queda en el volumen marcado como pendiente y se vuelve a
subir en el siguiente guardado de cualquiera."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone

import aiohttp

from bot.services.storage import JSONStorage

logger = logging.getLogger(__name__)

REPO = os.getenv("METAS_REPO", "luccabruno3z/ldh-lol-metas")
API = f"https://api.github.com/repos/{REPO}/contents/pools.json"
MAX_CAMPEONES = 6


def ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Metas:
    def __init__(self):
        self.local = JSONStorage("pools.json")             # {pid: {rol: {campeones: [ids], desde: iso}}}
        self.pendientes = JSONStorage("pools_pendientes.json")  # {pid: true}
        self._lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None

    @property
    def token(self) -> str | None:
        return os.getenv("GITHUB_TOKEN_METAS") or None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def pool(self, pid: str) -> dict:
        return self.local.get(pid) or {}

    async def guardar(self, pid: str, rol: str, campeones: list[int]) -> bool:
        """Reemplaza la pool de un rol (lista vacía = la borra). Devuelve True si quedó subida a GitHub.
        Cambiar los campeones reinicia "desde": el seguimiento cuenta a partir de la nueva pool."""
        campeones = list(dict.fromkeys(int(c) for c in campeones))[:MAX_CAMPEONES]
        async with self._lock:
            d = dict(self.pool(pid))
            previa = d.get(rol) or {}
            if campeones:
                desde = previa.get("desde") if sorted(previa.get("campeones") or []) == sorted(campeones) else None
                d[rol] = {"campeones": campeones, "desde": desde or ahora_iso()}
            else:
                d.pop(rol, None)
            if d:
                self.local.set(pid, d)
            else:
                self.local.delete(pid)
            self.pendientes.set(pid, True)
            return await self._subir(f"Pool de {pid}: {rol}")

    async def _subir(self, mensaje: str) -> bool:
        """Sube los pendientes encima de lo que hay en GitHub (no pisa las pools de los demás)."""
        if not self.token:
            logger.warning("Falta GITHUB_TOKEN_METAS: la pool queda solo en el volumen")
            return False
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        cab = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ldh-lol-bot"}
        for _ in range(2):  # un reintento si otro guardado cambió el archivo en el medio (409)
            try:
                async with self._session.get(API, headers=cab) as r:
                    if r.status == 404:
                        remoto, sha = {}, None
                    else:
                        r.raise_for_status()
                        j = await r.json()
                        remoto, sha = json.loads(base64.b64decode(j["content"]) or b"{}"), j["sha"]
                pend = list(self.pendientes.all())
                for pid in pend:
                    if self.local.get(pid):
                        remoto[pid] = self.local.get(pid)
                    else:
                        remoto.pop(pid, None)
                cuerpo = {"message": mensaje, "content": base64.b64encode(
                    json.dumps(remoto, ensure_ascii=False, indent=1, sort_keys=True).encode()).decode()}
                if sha:
                    cuerpo["sha"] = sha
                async with self._session.put(API, headers=cab, json=cuerpo) as r:
                    if r.status == 409:
                        continue
                    r.raise_for_status()
                for pid in pend:
                    self.pendientes.delete(pid)
                return True
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
                logger.warning("No pude subir las pools a %s: %s", REPO, exc)
                return False
        return False
