"""-pool: tu pool objetivo por rol, armada en Machine LoLing, y su seguimiento con tus partidas."""

from __future__ import annotations

from discord.ext import commands

from bot.services.metas import MAX_CAMPEONES, Metas
from bot.ui.pool_vista import ROLES, buscar_campeon, puede_editar, rol_por_defecto, tarjeta_pool


def _separar_rol(texto: str) -> tuple[str, str | None]:
    """"Kai'Sa ADC" -> ("Kai'Sa", "ADC"). El rol va al final y es opcional."""
    partes = texto.strip().rsplit(" ", 1)
    if len(partes) == 2:
        rol = next((r for r in ROLES if r.lower() == partes[1].lower()), None)
        if rol:
            return partes[0], rol
    return texto.strip(), None


class Pool(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.metas = Metas()

    async def cog_unload(self):
        await self.bot.metas.close()

    @commands.hybrid_group(name="pool", fallback="ver", invoke_without_command=True,
                           description="Tu pool objetivo por rol (armala en Machine LoLing) y cómo la venís cumpliendo")
    async def pool(self, ctx: commands.Context, *, jugador: str | None = None):
        p = await self.bot.get_cog("Perfil")._persona(ctx, jugador, "pool")
        if not p:
            return
        await ctx.defer()
        rol = await rol_por_defecto(self.bot, p["id"])
        await ctx.reply(view=await tarjeta_pool(self.bot, p["id"], rol, ctx.author.id))

    async def _cambiar(self, ctx: commands.Context, texto: str, agregar: bool):
        pid = self.bot.get_cog("Perfil").vinculos.get(str(ctx.author.id))
        if not pid or not puede_editar(self.bot, ctx.author.id, pid):
            await ctx.reply("Para declarar tu pool primero vinculate con `-vincular <tu nombre o Riot ID>`.", ephemeral=True)
            return
        nombre, rol = _separar_rol(texto)
        cid = buscar_campeon(await self.bot.datos.campeones(), nombre)
        if cid is None:
            await ctx.reply(f"No encontré el campeón «{nombre}».", ephemeral=True)
            return
        pools = self.bot.metas.pool(pid)
        if not rol:  # sin rol: donde ya está (para sacar) o el que se ve por defecto
            rol = next((r for r in ROLES if cid in (pools.get(r) or {}).get("campeones", [])), None) \
                if not agregar else None
            rol = rol or await rol_por_defecto(self.bot, pid)
        actual = list((pools.get(rol) or {}).get("campeones", []))
        if agregar:
            if cid in actual:
                await ctx.reply(f"Ya está en tu pool de {rol}.", ephemeral=True)
                return
            if len(actual) >= MAX_CAMPEONES:
                await ctx.reply(f"Tu pool de {rol} ya tiene {MAX_CAMPEONES}: sacá uno primero.", ephemeral=True)
                return
            actual.append(cid)
        else:
            if cid not in actual:
                await ctx.reply(f"No está en tu pool de {rol}.", ephemeral=True)
                return
            actual.remove(cid)
        await ctx.defer()
        ok = await self.bot.metas.guardar(pid, rol, actual)
        aviso = None if ok else "No pude subirla a GitHub: quedó guardada en el bot y se reintenta en el próximo cambio."
        await ctx.reply(view=await tarjeta_pool(self.bot, pid, rol, ctx.author.id, aviso))

    @pool.command(name="agregar", description="Suma un campeón a tu pool objetivo (el rol al final es opcional)")
    async def agregar(self, ctx: commands.Context, *, campeon_y_rol: str):
        await self._cambiar(ctx, campeon_y_rol, True)

    @pool.command(name="sacar", description="Saca un campeón de tu pool objetivo (el rol al final es opcional)")
    async def sacar(self, ctx: commands.Context, *, campeon_y_rol: str):
        await self._cambiar(ctx, campeon_y_rol, False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Pool(bot))
