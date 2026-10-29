"""Rankings del grupo: por período y por rol. Mismos JSON que la web (api/rankings/)."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.cogs.perfil import WEB, ic, pct, tarjeta_simple

PERIODOS = {"semana": "últimos 7 días", "mes": "últimos 30 días", "temporada": "temporada"}
COLAS = {"solo": "solo", "soloq": "solo", "flex": "flex", "normal": "normal", "normales": "normal"}
ROLES = {"top": "Top", "jungla": "Jungla", "jg": "Jungla", "mid": "Mid", "adc": "ADC", "bot": "ADC",
         "support": "Support", "supp": "Support", "sup": "Support"}
MEDALLAS = ["🥇", "🥈", "🥉"]


def tarjeta_top(d: dict, cola: str, nombres: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    c = d["colas"][cola]
    lineas = [f"## Top · {nombre_cola.get(cola, cola)} · {PERIODOS[d['periodo']]}"]
    if c["podio"]:
        lineas.append(" ".join(f"{MEDALLAS[i]} **{nombres.get(pid, pid)}**" for i, pid in enumerate(c["podio"])))
    for r in c["tabla"][:10]:
        lineas.append(f"`{r['puesto']:>2}` **{nombres.get(r['persona'], r['persona'])}** · {pct(r['winrate_aj'])} ajustado "
                      f"(real {ic(r['winrate'], 'pct')}, n={r['n']}) · confianza {r['confianza']}")
    if not c["tabla"]:
        lineas.append(f"Nadie tiene {d['min']}+ partidas en este período.")
    lineas.append(f"-# Mínimo {d['min']} partidas. El podio exige confianza media o alta.")
    return tarjeta_simple(lineas, f"{WEB}#/rankings/periodo")


def tarjeta_top_rol(v: dict, cola: str, rol: str, nombres: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    g = v["grupos"][f"{cola}|{rol}"]
    dec = 0 if "oro" in g["metrica"] else 2
    lineas = [f"## {rol} · {nombre_cola.get(cola, cola)} · {g['nombre']}"]
    for i, r in enumerate(g["tabla"][:10]):
        lineas.append(f"`{i + 1:>2}` **{nombres.get(r['persona'], r['persona'])}** · {ic(r['valor'], dec=dec)} (n={r['n']})")
    if not g["tabla"]:
        lineas.append(f"Nadie tiene {v['min']}+ partidas de {rol} en esta cola.")
    lineas.append(f"-# Contra el rival directo de la misma partida. Mínimo {v['min']} partidas y confianza media o alta.")
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
        await ctx.reply(view=tarjeta_top(await self.datos.ranking(periodo), cola, *await self._contexto()))

    @commands.hybrid_command(name="top_rol", description="Ranking por rol con la métrica de cada rol contra el rival directo")
    async def top_rol(self, ctx: commands.Context, rol: str, cola: str = "solo", ventana: str = "temporada"):
        rol, cola = ROLES.get(rol.lower()), COLAS.get(cola.lower())
        if not rol or not cola:
            await ctx.reply("Uso: `-top_rol <top|jungla|mid|adc|support> [solo|flex|normal] [temporada|reciente]`")
            return
        d = await self.datos.ranking("roles")
        v = d["reciente" if ventana.lower().startswith("rec") else "historico"]
        await ctx.reply(view=tarjeta_top_rol(v, cola, rol, *await self._contexto()))


async def setup(bot: commands.Bot):
    await bot.add_cog(Rankings(bot))
