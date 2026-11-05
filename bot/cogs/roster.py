"""-roster: los rosters premade de Flex y Normales (fase 7), con sus métricas de proceso. Mismo JSON que la
pestaña Rosters de Equipos en la web (api/roster/)."""

from __future__ import annotations

from discord.ext import commands

from bot.services import formato as F
from bot.ui.roster_vista import tarjeta_informe_roster, vista_roster


class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _elegir(self, ctx: commands.Context, nombre_o_jugador: str | None) -> tuple[bool, str | None]:
        """(seguir, rid). Sin nombre: el roster de tu vínculo, o None (el más grande). Responde si no encuentra."""
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
                    return False, None
            return True, r["id"]
        yo = self.bot.get_cog("Perfil").vinculos.get(str(ctx.author.id))
        return True, next((r["id"] for r in idx if any(x["id"] == yo for x in r["plantel"])), idx[0]["id"] if idx else None)

    @commands.hybrid_command(name="roster", aliases=["rosters"],
                             description="El roster premade: quiénes juegan juntos y sus métricas de proceso")
    async def roster(self, ctx: commands.Context, *, nombre_o_jugador: str | None = None):
        """-roster (el tuyo, o el más grande), -roster ahitevan (el de ese jugador)."""
        seguir, rid = await self._elegir(ctx, nombre_o_jugador)
        if seguir:
            await ctx.reply(view=await vista_roster(self.bot, rid))

    @commands.hybrid_command(name="informe_roster", description="El último informe semanal de un roster premade")
    async def informe_roster(self, ctx: commands.Context, *, nombre_o_jugador: str | None = None):
        """-informe_roster (el de tu roster), -informe_roster ahitevan."""
        seguir, rid = await self._elegir(ctx, nombre_o_jugador)
        if not seguir:
            return
        d = await self.bot.datos.roster(rid) if rid else None
        if not d:
            await ctx.reply("Todavía no hay rosters publicados.", ephemeral=True)
            return
        informes = await self.bot.datos.informes_roster(rid)
        await ctx.reply(view=tarjeta_informe_roster(d, informes[0] if informes else None))


async def setup(bot: commands.Bot):
    await bot.add_cog(Roster(bot))
