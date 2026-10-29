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


def pct(v: float | None) -> str:
    return "—" if v is None else f"{round(v * 100)} %"


def dec2(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}".replace(".", ",")


def _cola_principal(tabla: list[dict]) -> str | None:
    n: dict[str, int] = {}
    for t in tabla:
        n[t["cola"]] = n.get(t["cola"], 0) + t["n"]
    return max(n, key=n.get, default=None)


def tarjeta_simple(lineas: list[str], url: str) -> discord.ui.LayoutView:
    """Un Container con el texto (cortado al límite de Discord) y el botón a la web."""
    texto = "\n".join(lineas)
    if len(texto) > 3900:
        texto = texto[:3890] + "\n…"
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(texto),
                                       discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=url)),
                                       accent_colour=0x00CCCC))
    return view


def tarjeta_roles(p: dict, d: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    cola = _cola_principal(d["tabla"])
    nombre = discord.utils.escape_markdown(p["nombre"])
    if not cola:
        return tarjeta_simple([f"## {nombre}", "Todavía no hay partidas de Grieta."], f"{WEB}#/jugadores/{p['id']}")
    lineas = [f"## {nombre} · roles en {nombre_cola.get(cola, cola)}"]
    mejor = d["mejor"].get(cola)
    lineas.append(f"Mejor rol: **{mejor['rol']}** ({pct(mejor['winrate_aj'])} ajustado, n={mejor['n']})" if mejor
                  else 'Ningún rol llega a confianza media: no hay "mejor rol" todavía.')
    for t in (t for t in d["tabla"] if t["cola"] == cola):
        m = (d["metricas"].get(t["rol"]) or [None])[0]
        extra = f" · {m['nombre']} {ic(t.get(m['clave']), dec=0 if 'oro' in m['clave'] else 2)}" if m else ""
        chica = " · *muestra chica*" if t["muestra_chica"] else ""
        lineas.append(f"**{t['rol']}** (n={t['n']}, confianza {t['confianza']}{chica})\n"
                      f"WR {pct(t['winrate_aj'])} ajustado (real {ic(t['winrate'], 'pct')}) · KDA {dec2(t['kda_aj'])}{extra}")
    return tarjeta_simple(lineas, f"{WEB}#/jugadores/{p['id']}")


def tarjeta_campeones(p: dict, d: dict, champs: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    cola = _cola_principal(d["tabla"])
    nombre = discord.utils.escape_markdown(p["nombre"])
    if not cola:
        return tarjeta_simple([f"## {nombre}", "Todavía no hay partidas de Grieta."], f"{WEB}#/jugadores/{p['id']}")
    lineas = [f"## {nombre} · campeones en {nombre_cola.get(cola, cola)}"]
    for t in [t for t in d["tabla"] if t["cola"] == cola][:8]:
        champ = (champs.get(str(t["champ"])) or {}).get("nombre", t["champ"])
        chica = " · *muestra chica*" if t["muestra_chica"] else ""
        lineas.append(f"**{champ}** {t['rol'] or ''} (n={t['n']}{chica}) · WR {pct(t['winrate_aj'])} ajustado "
                      f"(real {ic(t['winrate'], 'pct')}) · KDA {dec2(t['kda_aj'])}")
    pool = d["pool"]["colas"].get(cola)
    if pool:
        lectura = "no discrimina" if pool["p"] is None or pool["p"] >= 0.05 else "hay señal"
        lineas.append(f"### Dentro y fuera del pool\nDentro {ic(pool['dentro'], 'pct')} (n={pool['dentro']['n']}) · "
                      f"fuera {ic(pool['fuera'], 'pct')} (n={pool['fuera']['n']}) → {lectura} (Fisher p = {pool['p']})")
    return tarjeta_simple(lineas, f"{WEB}#/jugadores/{p['id']}")


def tarjeta_sinergia(p: dict, d: dict, nombres: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    filas = [r for r in d["filas"] if r["persona"] == p["id"] and not r["muestra_chica"]][:8]
    lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · sinergia"]
    mc = p.get("mejor_companero")
    lineas.append(f"Mejor compañero: **{nombres.get(mc['companero'], mc['companero'])}** en {nombre_cola.get(mc['cola'], mc['cola'])}"
                  if mc else "Con ningún compañero rendís mejor más allá del ruido.")
    for r in filas:
        dif = r["dif"]["v"] or 0
        lineas.append(f"**{nombres.get(r['companero'], r['companero'])}** · {nombre_cola.get(r['cola'], r['cola'])} · "
                      f"{r['juntos']} juntos: {ic(r['con'], 'pct')} contra {ic(r['sin'], 'pct')} sin esa persona "
                      f"({'+' if dif > 0 else ''}{round(dif * 100)} pts, {'señal' if r['senal'] else 'ruido'})")
    if not filas:
        lineas.append(f"No hay compañeros con {d.get('min_juntos', 3)}+ partidas juntos fuera de la muestra chica.")
    lineas.append(f"-# {d.get('nota', '')}")
    return tarjeta_simple(lineas, f"{WEB}#/jugadores/{p['id']}")


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

    async def _persona(self, ctx: commands.Context, jugador: str | None, comando: str) -> dict | None:
        """El jugador nombrado o, sin nombre, el vinculado. Responde el error y devuelve None si no hay."""
        if jugador:
            p = await self.datos.buscar(jugador)
        else:
            pid = self.vinculos.get(str(ctx.author.id))
            if not pid:
                await ctx.reply(f"No estás vinculado. Usá `-vincular <tu nombre o Riot ID>` o `-{comando} <jugador>`.")
                return None
            p = {"id": pid}
        perfil = await self.datos.perfil(p["id"]) if p else None
        if not perfil:
            await ctx.reply("No encontré ese jugador. Solo aparecen las cuentas que se vincularon.")
        return perfil

    @commands.hybrid_command(name="perfil", description="Rango, KPIs, forma reciente y últimas partidas")
    async def perfil(self, ctx: commands.Context, *, jugador: str | None = None):
        if perfil := await self._persona(ctx, jugador, "perfil"):
            await ctx.reply(view=await self._tarjeta(perfil))

    @commands.hybrid_command(name="roles", description="Rendimiento por posición, ajustado por muestra")
    async def roles(self, ctx: commands.Context, *, jugador: str | None = None):
        if not (p := await self._persona(ctx, jugador, "roles")):
            return
        await ctx.reply(view=tarjeta_roles(p, await self.datos.roles(p["id"]),
                                           (await self.datos.ajustes()).get("nombres_cola", {})))

    @commands.hybrid_command(name="campeones", description="Campeón por posición, con el bloque dentro y fuera del pool")
    async def campeones(self, ctx: commands.Context, *, jugador: str | None = None):
        if not (p := await self._persona(ctx, jugador, "campeones")):
            return
        await ctx.reply(view=tarjeta_campeones(p, await self.datos.campeones_de(p["id"]), await self.datos.campeones(),
                                               (await self.datos.ajustes()).get("nombres_cola", {})))

    @commands.hybrid_command(name="sinergia", description="Con qué amigos rendís distinto")
    async def sinergia(self, ctx: commands.Context, *, jugador: str | None = None):
        if not (p := await self._persona(ctx, jugador, "sinergia")):
            return
        nombres = {x["id"]: x["nombre"] for x in await self.datos.personas()}
        await ctx.reply(view=tarjeta_sinergia(p, await self.datos.sinergia(), nombres,
                                              (await self.datos.ajustes()).get("nombres_cola", {})))

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
            "`-roles` · `-campeones` · `-sinergia` `[jugador]` rendimiento ajustado por muestra\n"
            "`-top [semana|mes|temporada] [solo|flex|normal]` · `-top_rol <rol> [cola]` rankings del grupo\n"
            "`-performance` · `-mejora` · `-temprano` `[jugador] [rol]` coaching contra tu franja de rango\n"
            f"Todo sale de la web: {WEB}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Perfil(bot))
