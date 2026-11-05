"""-roster: los rosters premade de Flex y Normales (fase 7), con sus métricas de proceso. Mismo JSON que la
pestaña Rosters de Equipos en la web (api/roster/)."""

from __future__ import annotations

from discord.ext import commands

from bot.services import formato as F
from bot.ui.roster_vista import vista_roster


class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="roster", aliases=["rosters"],
                             description="El roster premade: quiénes juegan juntos y sus métricas de proceso")
    async def roster(self, ctx: commands.Context, *, nombre_o_jugador: str | None = None):
        """-roster (el tuyo, o el más grande), -roster ahitevan (el de ese jugador)."""
        idx = (await self.bot.datos.rosters()).get("rosters") or []
        rid = None
        if nombre_o_jugador:
            t = F.normalizar(nombre_o_jugador)
            r = next((r for r in idx if t in F.normalizar(r["nombre"])), None)
            if not r:
                p = await self.bot.datos.buscar(nombre_o_jugador)
                r = next((r for r in idx if p and any(x["id"] == p["id"] for x in r["plantel"])), None)
                if not r:
                    nombres = ", ".join(f"**{x['nombre']}**" for x in idx) or "ninguno todavía"
                    await ctx.reply(f"No encontré un roster de **{nombre_o_jugador}**. Rosters: {nombres}.", ephemeral=True)
                    return
            rid = r["id"]
        else:
            yo = self.bot.get_cog("Perfil").vinculos.get(str(ctx.author.id))
            rid = next((r["id"] for r in idx if any(x["id"] == yo for x in r["plantel"])), None)
        await ctx.reply(view=await vista_roster(self.bot, rid))


async def setup(bot: commands.Bot):
    await bot.add_cog(Roster(bot))
