"""Arranque del bot. Cada cog carga aislado: si uno falla, el resto sigue."""

from __future__ import annotations

import logging
import os
import platform

import discord
from discord.ext import commands

from bot.services.datos import DATA_URL, Datos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ldh-lol")

COGS = ["bot.cogs.perfil", "bot.cogs.rankings", "bot.cogs.coaching", "bot.cogs.extra", "bot.cogs.feed", "bot.cogs.fase4"]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="-", intents=intents, help_command=None)
        self.datos = Datos()

    async def setup_hook(self):
        caidos = []
        for cog in COGS:
            try:
                await self.load_extension(cog)
            except Exception:
                logger.exception("No cargó %s", cog)
                caidos.append(cog)
        if caidos:
            logger.warning("Cogs sin cargar: %s", ", ".join(caidos))
        # Botones persistentes (DynamicItems): siguen andando después de un reinicio o un redeploy.
        from bot.ui.menu import MenuBoton
        from bot.ui.perfil_vista import PerfilBoton
        from bot.ui.rankings_vista import SelectorRanking
        self.add_dynamic_items(PerfilBoton, MenuBoton, SelectorRanking)
        await self._sincronizar()

    async def _sincronizar(self):
        """Sincroniza los slash commands solo si cambiaron: Discord limita las sincronizaciones y
        antes se hacía en cada reinicio de Railway. La huella queda en el volumen."""
        import hashlib
        import json

        from bot.services.storage import data_path

        huella = hashlib.sha256(json.dumps([c.to_dict(self.tree) for c in self.tree.get_commands()],
                                           sort_keys=True, default=str).encode()).hexdigest()
        ruta = data_path("slash_huella.txt")
        try:
            with open(ruta, encoding="utf-8") as f:
                if f.read().strip() == huella:
                    logger.info("Slash commands sin cambios: no se sincronizan")
                    return
        except OSError:
            pass
        try:
            await self.tree.sync()
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(huella)
            logger.info("Slash commands sincronizados")
        except discord.HTTPException:
            logger.exception("No se pudieron sincronizar los slash commands")

    async def close(self):
        await self.datos.close()
        await super().close()

    async def on_ready(self):
        logger.info("Conectado como %s · Python %s · discord.py %s · datos en %s",
                    self.user, platform.python_version(), discord.__version__, DATA_URL)


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Falta DISCORD_TOKEN")
    async with Bot() as bot:
        await bot.start(token)
