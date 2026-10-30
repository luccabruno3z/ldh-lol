"""Rankings del grupo: por período y por rol. Mismos JSON que la web (api/rankings/)."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.cogs.perfil import WEB, tarjeta_simple
from bot.services import formato as F

PERIODOS = {"semana": "últimos 7 días", "mes": "últimos 30 días", "temporada": "temporada"}
COLAS = {"solo": "solo", "soloq": "solo", "flex": "flex", "normal": "normal", "normales": "normal"}
ROLES = {"top": "Top", "jungla": "Jungla", "jg": "Jungla", "mid": "Mid", "adc": "ADC", "bot": "ADC",
         "support": "Support", "supp": "Support", "sup": "Support"}
MEDALLAS = ["🥇", "🥈", "🥉"]
MAX_FILAS = 8


def tarjeta_top(d: dict, cola: str, nombres: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    c = d["colas"][cola]
    lineas = [f"## Top · {nombre_cola.get(cola, cola)}",
              f"-# {PERIODOS[d['periodo']]} · winrate ajustado · mínimo {d['min']} partidas"]
    # La medalla va en la fila (antes había una línea aparte que repetía la tabla).
    for r in c["tabla"][:MAX_FILAS]:
        pid = r["persona"]
        marca = MEDALLAS[c["podio"].index(pid)] if pid in c["podio"] else f"`{r['puesto']}.`"
        lineas += [f"{marca} **{nombres.get(pid, pid)}** · {F.pct(r['winrate_aj'])} · {r['n']} partidas",
                   f"-# real {F.pct(r['winrate']['v'])} ({F.rango_pct(r['winrate'])}) · confianza {r['confianza']}"]
    if not c["tabla"]:
        lineas.append(f"Nadie tiene {d['min']}+ partidas en este período.")
    elif not c["podio"]:
        lineas.append("Sin podio: nadie llega a 50 % ajustado con confianza media o alta.")
    if c.get("sin_muestra"):
        lineas.append(f"-# Sin muestra suficiente: {len(c['sin_muestra'])} personas más.")
    lineas.append("-# Medalla solo con confianza media o alta y 50 % ajustado o más.")
    return tarjeta_simple(lineas, f"{WEB}#/rankings/periodo")


def tarjeta_top_rol(v: dict, cola: str, rol: str, nombres: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    g = v["grupos"][f"{cola}|{rol}"]
    dec = 0 if "oro" in g["metrica"] else 1 if "cs" in g["metrica"] else 2
    signo = g["metrica"].startswith("dif")
    lineas = [f"## {rol} · {nombre_cola.get(cola, cola)}", f"-# {g['nombre']}, contra el rival directo de la misma partida"]
    for i, r in enumerate(g["tabla"][:MAX_FILAS]):
        lineas += [f"`{i + 1}.` **{nombres.get(r['persona'], r['persona'])}**: {F.num(r['valor']['v'], dec, signo)} · {r['n']} partidas",
                   f"-# {F.rango(r['valor'], dec, signo)} · WR {F.pct(r['winrate']['v'])}"]
    if not g["tabla"]:
        lineas.append(f"Nadie tiene {v['min']}+ partidas de {rol} en esta cola.")
    lineas.append(f"-# Mínimo {v['min']} partidas en el rol y confianza media o alta.")
    return tarjeta_simple(lineas, f"{WEB}#/rankings/roles")


class Rankings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def datos(self):
        return self.bot.datos

    async def _contexto(self) -> tuple[dict, dict]:
        nombres = {p["id"]: p["nombre"] for p in await self.datos.personas()}
        return nombres, (await self.datos.ajustes()).get("nombres_cola", {})

    @commands.hybrid_command(name="top", description="Ranking del grupo por período y cola (winrate ajustado)")
    async def top(self, ctx: commands.Context, periodo: str = "mes", cola: str = "solo"):
        periodo, cola = periodo.lower(), COLAS.get(cola.lower())
        if periodo not in PERIODOS or not cola:
            await ctx.reply("Uso: `-top [semana|mes|temporada] [solo|flex|normal]`")
            return
        from bot.ui.rankings_vista import TopVista
        vista = TopVista(self.bot, ctx.author.id, periodo, cola)  # con menús para cambiar período y cola
        await vista.pintar()
        await ctx.reply(view=vista)

    @commands.hybrid_command(name="top_rol", description="Ranking por rol con la métrica de cada rol contra el rival directo")
    async def top_rol(self, ctx: commands.Context, rol: str = "top", cola: str = "solo", ventana: str = "temporada"):
        rol, cola = ROLES.get(rol.lower()), COLAS.get(cola.lower())
        if not rol or not cola:
            await ctx.reply("Uso: `-top_rol <top|jungla|mid|adc|support> [solo|flex|normal] [temporada|reciente]`")
            return
        from bot.ui.rankings_vista import TopRolVista
        vista = TopRolVista(self.bot, ctx.author.id, rol, cola, "reciente" if ventana.lower().startswith("rec") else "historico")
        await vista.pintar()
        await ctx.reply(view=vista)


async def setup(bot: commands.Bot):
    await bot.add_cog(Rankings(bot))
