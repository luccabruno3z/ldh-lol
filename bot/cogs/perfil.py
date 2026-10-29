"""Vincular y perfil. Todo lo que se muestra lleva su n y su intervalo, como en la web."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.services.storage import JSONStorage

logger = logging.getLogger(__name__)

TIERS = {"IRON": "Hierro", "BRONZE": "Bronce", "SILVER": "Plata", "GOLD": "Oro", "PLATINUM": "Platino",
         "EMERALD": "Esmeralda", "DIAMOND": "Diamante", "MASTER": "Maestro", "GRANDMASTER": "Gran Maestro",
         "CHALLENGER": "Retador"}
COLORES = {"IRON": 0x6b5a4e, "BRONZE": 0xa0703c, "SILVER": 0x8a96a8, "GOLD": 0xc99a1e, "PLATINUM": 0x2a9d8f,
           "EMERALD": 0x1fa65a, "DIAMOND": 0x4b7bec, "MASTER": 0xb05ce0, "GRANDMASTER": 0xd64545,
           "CHALLENGER": 0xf1c40f}
WEB = "https://luccabruno3z.github.io/ldh-lol/"


def rango(r: dict | None) -> str:
    if not r or not r.get("tier"):
        return "Sin clasificar"
    div = "" if r["tier"] in ("MASTER", "GRANDMASTER", "CHALLENGER") else f" {r['division']}"
    return f"{TIERS.get(r['tier'], r['tier'])}{div} · {r['lp']} LP ({r['wins']} V / {r['losses']} D)"


def ic(m: dict | None, tipo="dec", dec=1) -> str:
    """'52 % (45–59)' o '2,31 (2,05–2,60)'. Sin intervalo, solo el valor."""
    if not m or m.get("v") is None:
        return "—"
    k, suf = (100, " %") if tipo == "pct" else (1, " %") if tipo == "pct100" else (1, "")
    d = 0 if tipo in ("pct", "pct100") else dec
    f = lambda x: f"{x * k:.{d}f}".replace(".", ",")
    return f"{f(m['v'])}{suf}" + (f" ({f(m['lo'])}–{f(m['hi'])})" if m.get("lo") is not None else "")


class Perfil(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.vinculos = JSONStorage("vinculos.json")  # {discord_id: persona_id}

    @property
    def datos(self):
        return self.bot.datos

    @commands.hybrid_command(name="vincular", description="Une tu usuario de Discord con tu jugador del grupo")
    async def vincular(self, ctx: commands.Context, *, jugador: str):
        p = await self.datos.buscar(jugador)
        if not p:
            await ctx.reply(f"No encontré a **{discord.utils.escape_markdown(jugador)}** entre los jugadores publicados. "
                            "Solo aparecen las cuentas que se vincularon: pedile a Lucca que te sume.")
            return
        self.vinculos.set(str(ctx.author.id), p["id"])
        await ctx.reply(f"Listo: quedaste vinculado a **{discord.utils.escape_markdown(p['nombre'])}**. "
                        "Ahora `-perfil` sin nombre muestra el tuyo.")

    @commands.hybrid_command(name="desvincular", description="Borra tu vínculo")
    async def desvincular(self, ctx: commands.Context):
        self.vinculos.delete(str(ctx.author.id))
        await ctx.reply("Listo, ya no estás vinculado.")

    @commands.hybrid_command(name="perfil", description="Rango, KPIs, forma reciente y últimas partidas")
    async def perfil(self, ctx: commands.Context, *, jugador: str | None = None):
        if jugador:
            p = await self.datos.buscar(jugador)
        else:
            pid = self.vinculos.get(str(ctx.author.id))
            p = {"id": pid} if pid else None
            if not p:
                await ctx.reply("No estás vinculado. Usá `-vincular <tu nombre o Riot ID>` o `-perfil <jugador>`.")
                return
        perfil = await self.datos.perfil(p["id"]) if p else None
        if not perfil:
            await ctx.reply("No encontré ese jugador. Solo aparecen las cuentas que se vincularon.")
            return
        await ctx.reply(view=await self._tarjeta(perfil))

    async def _tarjeta(self, p: dict) -> discord.ui.LayoutView:
        campeones = await self.datos.campeones()
        nombre_cola = (await self.datos.ajustes()).get("nombres_cola", {})
        mejor = max((c.get("solo") for c in p["rango"].values() if c.get("solo")),
                    key=lambda r: r.get("valor") or -1, default=None)

        cuentas = "\n".join(
            f"`{discord.utils.escape_markdown(c['riot_id'])}` — Solo: {rango((p['rango'].get(c['riot_id']) or {}).get('solo'))}"
            for c in p["cuentas"])
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## {discord.utils.escape_markdown(p['nombre'])}\n{cuentas}\n-# {p['n']} partidas desde el 8/1/2026"),
            discord.ui.Separator(),
        ]

        # KPIs: la cola más jugada, fila "Todos" y los roles con muestra suficiente.
        tabla = [f for f in p["kpis"]["todas"]]
        if tabla:
            cola = max({f["cola"] for f in tabla}, key=lambda c: next(f["n"] for f in tabla if f["cola"] == c and f["rol"] == "Todos"))
            filas = [f for f in tabla if f["cola"] == cola][:6]
            lineas = [f"### KPIs · {nombre_cola.get(cola, cola)}"]
            for f in filas:
                chica = " · *muestra chica*" if f["muestra_chica"] else ""
                lineas.append(f"**{f['rol']}** (n={f['n']}{chica})\nWR {ic(f['winrate'], 'pct')} · KDA {ic(f['kda'], dec=2)} · "
                              f"CS/min {ic(f['cs_min'])} · Part. kills {ic(f['kp'], 'pct100')}")
            items += [discord.ui.TextDisplay("\n".join(lineas)), discord.ui.Separator()]

        forma = p.get("forma")
        if forma:
            dif = forma["comparacion"]["winrate"]["dif"]
            lectura = "ruido: no se puede decir que cambió" if dif.get("ruido") else ("mejor que su resto" if dif["v"] > 0 else "peor que su resto")
            racha = "".join("🟩" if x["win"] else "🟥" for x in forma["partidas"])
            items += [discord.ui.TextDisplay(
                f"### Forma reciente · {nombre_cola.get(forma['cola'], forma['cola'])}\n{racha}\n"
                f"Últimas {forma['n_ultimas']}: WR {ic(forma['comparacion']['winrate']['ultimas'], 'pct')} · "
                f"resto ({forma['n_resto']}): {ic(forma['comparacion']['winrate']['resto'], 'pct')} → {lectura}"),
                discord.ui.Separator()]

        hist = await self.datos.historial(p["id"], 1)
        if hist and hist["partidas"]:
            lineas = ["### Últimas partidas"]
            for m in hist["partidas"][:5]:
                champ = (campeones.get(str(m["champ"])) or {}).get("nombre", m["champ"])
                lineas.append(f"{'✅' if m['win'] else '❌'} {champ} · {m['rol'] or '—'} · {m['k']}/{m['d']}/{m['a']} · "
                              f"{nombre_cola.get(m['cola'], m['cola'])}")
            items.append(discord.ui.TextDisplay("\n".join(lineas)))

        items.append(discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=f"{WEB}#/jugadores/{p['id']}")))
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(*items, accent_colour=COLORES.get((mejor or {}).get("tier"), 0x00cccc)))
        return view

    @commands.hybrid_command(name="ayuda", description="Qué hace el bot")
    async def ayuda(self, ctx: commands.Context):
        await ctx.reply(
            "**LDH Stats LoL**\n"
            "`-vincular <nombre o Riot ID>` une tu Discord con tu jugador\n"
            "`-desvincular` borra el vínculo\n"
            "`-perfil [jugador]` rango, KPIs con su intervalo, forma reciente y últimas partidas\n"
            f"Todo sale de la web: {WEB}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Perfil(bot))
