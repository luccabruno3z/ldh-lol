"""Vincular y perfil. Todo lo que se muestra lleva su n y su intervalo, como en la web."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.services import formato as F
from bot.services.storage import JSONStorage

logger = logging.getLogger(__name__)

TIERS = {"IRON": "Hierro", "BRONZE": "Bronce", "SILVER": "Plata", "GOLD": "Oro", "PLATINUM": "Platino",
         "EMERALD": "Esmeralda", "DIAMOND": "Diamante", "MASTER": "Maestro", "GRANDMASTER": "Gran Maestro",
         "CHALLENGER": "Retador"}
COLORES = {"IRON": 0x6b5a4e, "BRONZE": 0xa0703c, "SILVER": 0x8a96a8, "GOLD": 0xc99a1e, "PLATINUM": 0x2a9d8f,
           "EMERALD": 0x1fa65a, "DIAMOND": 0x4b7bec, "MASTER": 0xb05ce0, "GRANDMASTER": 0xd64545,
           "CHALLENGER": 0xf1c40f}
WEB = "https://luccabruno3z.github.io/ldh-lol/"
# La política de Riot pide este aviso donde los jugadores lo vean (la web lo tiene en el pie).
AVISO_RIOT = ("LDH Stats LoL no está respaldado por Riot Games y no refleja la opinión de Riot Games ni de nadie "
              "involucrado oficialmente en la producción o gestión de League of Legends. League of Legends y "
              "Riot Games son marcas registradas de Riot Games, Inc.")


async def autocompletar_jugador(interaction: discord.Interaction, actual: str) -> list[app_commands.Choice[str]]:
    """Sugerencias de jugador en los slash commands: evita los "no encontré ese jugador"."""
    t = actual.strip().lower()
    personas = await interaction.client.datos.personas()
    hallados = [p for p in personas if not t or t in p["nombre"].lower() or any(t in c.lower() for c in p["cuentas"])]
    return [app_commands.Choice(name=p["nombre"], value=p["id"]) for p in hallados[:25]]


def rango(r: dict | None) -> str:
    if not r or not r.get("tier"):
        return "Sin clasificar"
    div = "" if r["tier"] in ("MASTER", "GRANDMASTER", "CHALLENGER") else f" {r['division']}"
    return f"{TIERS.get(r['tier'], r['tier'])}{div} · {r['lp']} LP ({r['wins']} V / {r['losses']} D)"


def ic(m: dict | None, tipo="dec", dec=1) -> str:
    """'52 % (45 a 59 %)' o '2,31 (2,05 a 2,60)'. Sin intervalo, solo el valor."""
    if not m or m.get("v") is None:
        return "—"
    if tipo == "pct":
        return f"{F.pct(m['v'])}" + (f" ({F.rango_pct(m)})" if m.get("lo") is not None else "")
    k, suf = (1, " %") if tipo == "pct100" else (1, "")
    d = 0 if tipo == "pct100" else dec
    return f"{F.num(m['v'], d)}{suf}" + (f" ({F.rango(m, d, suf=suf)})" if m.get("lo") is not None else "")


pct = F.pct


def dec2(v: float | None) -> str:
    return F.num(v, 2)


def _cola_principal(tabla: list[dict]) -> str | None:
    n: dict[str, int] = {}
    for t in tabla:
        n[t["cola"]] = n.get(t["cola"], 0) + t["n"]
    return max(n, key=n.get, default=None)


def tarjeta_simple(lineas: list[str], url: str) -> discord.ui.LayoutView:
    """Un Container con el texto (cortado al límite de Discord) y el botón a la web."""
    texto = "\n".join(l for l in lineas if l)
    if len(texto) > 3900:
        texto = texto[:3890] + "\n…"
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(texto),
                                       discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=url)),
                                       accent_colour=0x00CCCC))
    return view


def _dec_metrica(clave: str) -> int:
    return 0 if "oro" in clave else 1 if "cs" in clave else 2


def tarjeta_roles(p: dict, d: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    cola = _cola_principal(d["tabla"])
    nombre = discord.utils.escape_markdown(p["nombre"])
    url = f"{WEB}#/jugadores/{p['id']}"
    if not cola:
        return tarjeta_simple([f"## {nombre}", "Todavía no hay partidas de Grieta."], url)
    lineas = [f"## {nombre} · roles", f"-# {nombre_cola.get(cola, cola)} · valores ajustados por muestra"]
    mejor = d["mejor"].get(cola)
    lineas.append(f"Mejor rol: **{mejor['rol']}**, {F.pct(mejor['winrate_aj'])} ajustado en {mejor['n']} partidas" if mejor
                  else 'Ningún rol llega a confianza media: todavía no hay "mejor rol".')
    filas = [t for t in d["tabla"] if t["cola"] == cola]
    for t in (t for t in filas if not t["muestra_chica"]):
        m = (d["metricas"].get(t["rol"]) or [None])[0]
        val = t.get(m["clave"]) if m else None
        dec = _dec_metrica(m["clave"]) if m else 0
        extra = f" · {m['nombre']}: {F.num(val['v'], dec, True)}" if m and val and val.get("v") is not None else ""
        det = f" · {m['nombre'].split(' ')[0].lower()} {F.rango(val, dec, True)}" if extra and val.get("lo") is not None else ""
        lineas += [f"\n**{t['rol']}** · {t['n']} partidas · confianza {t['confianza']}",
                   f"WR {F.pct(t['winrate_aj'])} · KDA {F.num(t['kda_aj'], 2)}{extra}",
                   f"-# WR real {F.pct(t['winrate']['v'])} ({F.rango_pct(t['winrate'])}) · "
                   f"KDA real {F.num(t['kda']['v'], 2)} ({F.rango(t['kda'], 2)}){det}"]
    lineas.append(F.chica([f"{t['rol']} ({t['n']})" for t in filas if t["muestra_chica"]]))
    return tarjeta_simple(lineas, url)


def tarjeta_campeones(p: dict, d: dict, champs: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    cola = _cola_principal(d["tabla"])
    nombre = discord.utils.escape_markdown(p["nombre"])
    url = f"{WEB}#/jugadores/{p['id']}"
    if not cola:
        return tarjeta_simple([f"## {nombre}", "Todavía no hay partidas de Grieta."], url)
    lineas = [f"## {nombre} · campeones", f"-# {nombre_cola.get(cola, cola)} · ordenados por winrate ajustado"]
    filas = [t for t in d["tabla"] if t["cola"] == cola]
    nombre_c = lambda t: (champs.get(str(t["champ"])) or {}).get("nombre", t["champ"])
    for t in [t for t in filas if not t["muestra_chica"]][:6]:
        lineas += [f"\n**{nombre_c(t)}** {t['rol'] or ''} · {t['n']} partidas",
                   f"WR {F.pct(t['winrate_aj'])} · KDA {F.num(t['kda_aj'], 2)}",
                   f"-# real {F.pct(t['winrate']['v'])} ({F.rango_pct(t['winrate'])}) · confianza {t['confianza']}"]
    resto = [t for t in filas if t["muestra_chica"]]
    if resto:
        lineas.append(f"-# Muestra chica, sin conclusiones: {len(resto)} campeones más")
    pool = d["pool"]["colas"].get(cola)
    if pool and pool["p"] is not None:
        senal = pool["p"] < 0.05
        lineas += ["### Dentro y fuera de tu pool",
                   f"Dentro: **{F.pct(pool['dentro']['v'])}** ({pool['dentro']['n']}) · "
                   f"fuera: **{F.pct(pool['fuera']['v'])}** ({pool['fuera']['n']}) → {'hay señal' if senal else 'no discrimina'}",
                   f"-# {F.rango_pct(pool['dentro'])} · {F.rango_pct(pool['fuera'])} · Fisher p = {F.num(pool['p'], 3)}"]
    return tarjeta_simple(lineas, url)


def tarjeta_sinergia(p: dict, d: dict, nombres: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    todas = [r for r in d["filas"] if r["persona"] == p["id"] and not r["muestra_chica"]]
    # Lo que tiene señal arriba; después, los compañeros con más partidas juntos.
    filas = sorted(todas, key=lambda r: (not r["senal"], -r["juntos"]))[:7]
    lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · sinergia"]
    mc = p.get("mejor_companero")
    lineas.append(f"Mejor compañero: **{nombres.get(mc['companero'], mc['companero'])}** en {nombre_cola.get(mc['cola'], mc['cola'])}"
                  if mc else "Con ningún compañero rendís mejor más allá del ruido.")
    for r in filas:
        # Un intervalo que no cruza el cero puede no pasar la corrección por tantos pares: se dice así.
        tag = ("**señal**" if r["senal"] else "ruido" if r["dif"].get("ruido")
               else "no pasa la corrección por comparaciones múltiples")
        lineas += [f"\n**{nombres.get(r['companero'], r['companero'])}** · {nombre_cola.get(r['cola'], r['cola'])} · {r['juntos']} juntos",
                   f"Juntos {F.pct(r['con']['v'])} · sin esa persona {F.pct(r['sin']['v'])} → {F.pts(r['dif']['v'])}, {tag}",
                   f"-# diferencia {F.rango_pts(r['dif'])} · p ajustado {F.num(r['p_bh'], 2)}"]
    if not filas:
        lineas.append(f"No hay compañeros con {d.get('min_juntos', 3)}+ partidas juntos fuera de la muestra chica.")
    elif len(todas) > len(filas):
        lineas.append(f"-# {len(todas) - len(filas)} compañeros más en la web.")
    lineas.append("-# Misma cola, con contra sin. La señal usa el p ajustado por Benjamini-Hochberg: con tantos pares, alguno sale por azar.")
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
                            "Solo aparecen las cuentas que se vincularon: pedile a Lucca que te sume.", ephemeral=True)
            return
        self.vinculos.set(str(ctx.author.id), p["id"])
        await ctx.reply(f"Listo: quedaste vinculado a **{discord.utils.escape_markdown(p['nombre'])}**. "
                        "Ahora `-perfil` sin nombre muestra el tuyo.\n"
                        "-# Tus estadísticas son públicas en la web y en el bot porque te sumaste al grupo. "
                        "Si querés dejar de aparecer, pedíselo a Lucca y se saca tu cuenta.")

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
                await ctx.reply(f"No estás vinculado. Usá `-vincular <tu nombre o Riot ID>` o `-{comando} <jugador>`.", ephemeral=True)
                return None
            p = {"id": pid}
        perfil = await self.datos.perfil(p["id"]) if p else None
        if not perfil:
            await ctx.reply("No encontré ese jugador. Solo aparecen las cuentas que se vincularon.", ephemeral=True)
        return perfil

    async def _abrir(self, ctx: commands.Context, jugador: str | None, comando: str, tab: str):
        """El perfil con pestañas, abierto en la pestaña pedida."""
        from bot.ui.perfil_vista import render
        if p := await self._persona(ctx, jugador, comando):
            await ctx.defer()  # armar la tarjeta lee varios JSON: Discord corta a los 3 s
            await ctx.reply(view=await render(self.bot, p["id"], tab, "t", ctx.author.id))

    @commands.hybrid_command(name="perfil", description="Tu perfil con pestañas: resumen, roles, campeones, coaching y partidas")
    @app_commands.autocomplete(jugador=autocompletar_jugador)
    async def perfil(self, ctx: commands.Context, *, jugador: str | None = None):
        await self._abrir(ctx, jugador, "perfil", "resumen")

    @commands.hybrid_command(name="roles", description="Rendimiento por posición, ajustado por muestra")
    @app_commands.autocomplete(jugador=autocompletar_jugador)
    async def roles(self, ctx: commands.Context, *, jugador: str | None = None):
        await self._abrir(ctx, jugador, "roles", "roles")

    @commands.hybrid_command(name="campeones", description="Campeón por posición, con el bloque dentro y fuera del pool")
    @app_commands.autocomplete(jugador=autocompletar_jugador)
    async def campeones(self, ctx: commands.Context, *, jugador: str | None = None):
        await self._abrir(ctx, jugador, "campeones", "campeones")

    @commands.hybrid_command(name="sinergia", description="Con qué amigos rendís distinto")
    @app_commands.autocomplete(jugador=autocompletar_jugador)
    async def sinergia(self, ctx: commands.Context, *, jugador: str | None = None):
        if not (p := await self._persona(ctx, jugador, "sinergia")):
            return
        nombres = {x["id"]: x["nombre"] for x in await self.datos.personas()}
        await ctx.reply(view=tarjeta_sinergia(p, await self.datos.sinergia(), nombres,
                                              (await self.datos.ajustes()).get("nombres_cola", {})))

    async def _tarjeta(self, p: dict, hist: dict | None = None) -> discord.ui.LayoutView:
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

        # KPIs: la cola más jugada, "Todos" y hasta 3 roles con muestra; lo chico va a una línea final.
        tabla = [f for f in p["kpis"]["todas"]]
        if tabla:
            cola = max({f["cola"] for f in tabla}, key=lambda c: next(f["n"] for f in tabla if f["cola"] == c and f["rol"] == "Todos"))
            filas = [f for f in tabla if f["cola"] == cola]
            grandes = [f for f in filas if not f["muestra_chica"]][:4]
            lineas = [f"### KPIs · {nombre_cola.get(cola, cola)}"]
            for f in grandes:
                lineas += [f"**{f['rol']}** · {f['n']} partidas",
                           f"WR {F.pct(f['winrate']['v'])} · KDA {F.num(f['kda']['v'], 2)} · "
                           f"CS/min {F.num(f['cs_min']['v'], 1)} · KP {F.num(f['kp']['v'], 0)} %",
                           f"-# WR {F.rango_pct(f['winrate'])} · KDA {F.rango(f['kda'], 2)} · "
                           f"CS {F.rango(f['cs_min'], 1)} · KP {F.rango(f['kp'], 0)} %"]
            resto = [f"{f['rol']} ({f['n']})" for f in filas if f not in grandes]
            if resto:
                lineas.append(f"-# En la web: {', '.join(resto)}")
            items += [discord.ui.TextDisplay("\n".join(lineas)), discord.ui.Separator()]

        forma = p.get("forma")
        if forma:
            c = forma["comparacion"]["winrate"]
            dif = c["dif"]
            lectura = "ruido, no se puede decir que cambió" if dif.get("ruido") else ("mejor que tu resto" if dif["v"] > 0 else "peor que tu resto")
            racha = "".join("🟩" if x["win"] else "🟥" for x in forma["partidas"])
            items += [discord.ui.TextDisplay(
                f"### Forma reciente · {nombre_cola.get(forma['cola'], forma['cola'])}\n{racha}\n"
                f"Últimas {forma['n_ultimas']}: **{F.pct(c['ultimas']['v'])}** · resto: {F.pct(c['resto']['v'])} → {lectura}\n"
                f"-# {F.rango_pct(c['ultimas'])} · resto ({forma['n_resto']} partidas) {F.rango_pct(c['resto'])}"),
                discord.ui.Separator()]

        hist = hist or await self.datos.historial(p["id"], 1)
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Perfil(bot))
