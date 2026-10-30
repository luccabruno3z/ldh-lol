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

COGS = ["bot.cogs.perfil", "bot.cogs.rankings", "bot.cogs.coaching", "bot.cogs.extra"]


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
        self.add_dynamic_items(PerfilBoton, MenuBoton)
        try:
            await self.tree.sync()
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
