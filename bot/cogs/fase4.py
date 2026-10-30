"""Fase 4 en el bot: -ideal, -inhouse, -matchups, -jungla y -mapa. Mismos JSON que la web
(equipos.json, matchups/, jungla/, heatmap/) y la misma lógica del balanceador que sitio/js/equipos.js."""

from __future__ import annotations

import io
import itertools
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.perfil import WEB, autocompletar_jugador, tarjeta_simple
from bot.services import formato as F

ROLES = ["Top", "Jungla", "Mid", "ADC", "Support"]
PERMS = list(itertools.permutations(range(5)))


def _mejor_asignacion(eq: dict, pids: list[str]) -> dict:
    """Primero cuántos cumplen el mínimo de partidas en su rol, después la fuerza."""
    mejor = None
    for perm in PERMS:
        asig, cumplen, suma = [], 0, 0.0
        for k, rol in enumerate(ROLES):
            pid = pids[perm[k]]
            r = eq["jugadores"].get(pid, {}).get("roles", {}).get(rol)
            n = r["n"] if r else 0
            cumplen += n >= eq["min_rol"]
            suma += r["wr_aj"] if r else 0.45
            asig.append({"rol": rol, "pid": pid, "n": n, "wr_aj": r["wr_aj"] if r else None})
        cand = {"asig": asig, "cumplen": cumplen, "fuerza": suma / 5}
        if not mejor or (cand["cumplen"], cand["fuerza"]) > (mejor["cumplen"], mejor["fuerza"]):
            mejor = cand
    return mejor


def balancear(eq: dict, pids: list[str]) -> dict:
    """Las 126 particiones 5v5: la que más cumple el mínimo y, entre esas, la más pareja."""
    primero, resto = pids[0], pids[1:]
    mejor = None
    for c in itertools.combinations(resto, 4):
        a = _mejor_asignacion(eq, [primero, *c])
        b = _mejor_asignacion(eq, [p for p in resto if p not in c])
        cand = {"a": a, "b": b, "cumplen": a["cumplen"] + b["cumplen"], "dif": abs(a["fuerza"] - b["fuerza"])}
        if not mejor or (cand["cumplen"], -cand["dif"]) > (mejor["cumplen"], -mejor["dif"]):
            mejor = cand
    # Un campeón por jugador sin repetir entre equipos; primero los que tienen menos opciones.
    usados, champs = set(), {}
    filas = [x for e in (mejor["a"], mejor["b"]) for x in e["asig"]]
    for x in sorted(filas, key=lambda x: len(eq["jugadores"][x["pid"]]["roles"].get(x["rol"], {}).get("campeones", []))):
        ops = eq["jugadores"][x["pid"]]["roles"].get(x["rol"], {}).get("campeones", [])
        c = next((o for o in ops if o["id"] not in usados), None)
        if c:
            usados.add(c["id"])
        champs[(x["pid"], x["rol"])] = c
    mejor["champs"] = champs
    return mejor


class Fase4(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mapa: bytes | None = None

    @property
    def datos(self):
        return self.bot.datos

    async def _persona(self, ctx, jugador, comando):
        return await self.bot.get_cog("Perfil")._persona(ctx, jugador, comando)

    @commands.hybrid_command(name="ideal", description="El 5 ideal del grupo: una persona por rol con 10+ partidas ahí")
    async def ideal(self, ctx: commands.Context):
        eq = await self.datos.equipos()
        if not eq.get("ideal"):
            await ctx.reply("No hay cinco personas distintas con 10+ partidas en cada rol.", ephemeral=True)
            return
        op = eq["ideal"][0]
        lineas = ["## El 5 ideal del grupo", f"-# Fuerza {F.pct(op['fuerza'])} · winrate ajustado en el rol, todas las colas de Grieta"]
        for x in op["equipo"]:
            lineas.append(f"**{x['rol']}** · {eq['jugadores'][x['persona']]['nombre']} · {F.pct(x['wr_aj'])} en {x['n']} partidas")
        if len(eq["ideal"]) > 1:
            alt = eq["ideal"][1]
            cambios = [f"{x['rol']}: {eq['jugadores'][x['persona']]['nombre']}" for x, y in zip(alt["equipo"], op["equipo"])
                       if x["persona"] != y["persona"]]
            lineas.append(f"-# Casi igual de fuerte ({F.pct(alt['fuerza'])}) cambiando {', '.join(cambios)}.")
        await ctx.reply(view=tarjeta_simple(lineas, f"{WEB}#/equipos"))

    @commands.hybrid_command(name="inhouse", description="Arma dos equipos parejos con 10 jugadores (separados por coma)")
    async def inhouse(self, ctx: commands.Context, *, jugadores: str):
        await ctx.reply(view=await tarjeta_inhouse(self.bot, jugadores))

    @commands.hybrid_command(name="matchups", description="Cómo te va contra cada campeón rival directo")
    @app_commands.autocomplete(jugador=autocompletar_jugador)
    async def matchups(self, ctx: commands.Context, jugador: str | None = None, cola: str = "solo"):
        if not (p := await self._persona(ctx, jugador, "matchups")):
            return
        d = await self.datos.matchups(p["id"]) or {"tabla": []}
        champs = await self.datos.campeones()
        nc = (await self.datos.ajustes()).get("nombres_cola", {})
        filas = [f for f in d["tabla"] if f["cola"] == cola and not f["muestra_chica"]]
        nombre_c = lambda c: (champs.get(str(c)) or {}).get("nombre", c)
        lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · contra quién", f"-# {nc.get(cola, cola)} · rival directo · {d.get('min', 5)}+ partidas"]
        for f in sorted(filas, key=lambda f: -f["n"])[:10]:
            lineas += [f"**{nombre_c(f['rival'])}** ({f['rol']}) · {F.pct(f['winrate']['v'])} en {f['n']}",
                       f"-# {F.rango_pct(f['winrate'])} · ajustado {F.pct(f['wr_aj'])}"]
        if not filas:
            lineas.append(f"Ningún rival se repite {d.get('min', 5)} veces o más en esta cola.")
        await ctx.reply(view=tarjeta_simple(lineas, f"{WEB}#/jugadores/{p['id']}"))

    @commands.hybrid_command(name="jungla", description="¿Qué tan predecible es tu jungla? De qué buff arrancás, por lado")
    @app_commands.autocomplete(jugador=autocompletar_jugador)
    async def jungla(self, ctx: commands.Context, *, jugador: str | None = None):
        if not (p := await self._persona(ctx, jugador, "jungla")):
            return
        d = await self.datos.jungla(p["id"])
        if not d or not d.get("lados"):
            await ctx.reply(f"{p['nombre']} no tiene 20+ partidas de jungla con timeline.", ephemeral=True)
            return
        lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · arranque de jungla"]
        for lado in ("azul", "rojo"):
            x = d["lados"].get(lado)
            if not x:
                continue
            tag = "**predecible**" if x["predecible"] else "variás"
            lineas += [f"**Lado {lado}** ({x['n']} partidas): arrancás en el buff {x['buff_habitual']} el "
                       f"{F.pct(x['pct_habitual'])} → {tag}",
                       f"-# arriba {F.rango_pct(x['arriba'])} · Fisher p sobre el winrate = {F.num(x['p'], 2) if x['p'] is not None else '—'}"]
        lineas.append(f"-# Posición en el minuto 1. Predecible si todo el intervalo pasa el {F.pct(d['umbral'])}.")
        await ctx.reply(view=tarjeta_simple(lineas, f"{WEB}#/jugadores/{p['id']}"))

    async def _imagen_mapa(self) -> bytes | None:
        if self._mapa is None:
            version = (await self.datos._json("campeones.json") or {}).get("version")
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"https://ddragon.leagueoflegends.com/cdn/{version}/img/map/map11.png") as r:
                        if r.status == 200:
                            self._mapa = await r.read()
            except aiohttp.ClientError:
                return None
        return self._mapa

    @commands.hybrid_command(name="mapa", description="Dónde morís o matás, sobre el minimapa (por lado)")
    @app_commands.autocomplete(jugador=autocompletar_jugador)
    async def mapa(self, ctx: commands.Context, jugador: str | None = None, tipo: str = "muertes", lado: str = "azul"):
        if jugador and jugador.lower() in ("muertes", "kills", "azul", "rojo"):
            jugador, tipo, lado = None, jugador if jugador.lower() in ("muertes", "kills") else tipo, \
                jugador if jugador.lower() in ("azul", "rojo") else lado
        if not (p := await self._persona(ctx, jugador, "mapa")):
            return
        await ctx.defer()
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.image as mpimg
        import matplotlib.pyplot as plt

        d = await self.datos.heatmap(p["id"]) or {"puntos": []}
        t = "muerte" if tipo.lower().startswith("m") else "kill"
        lado = "rojo" if lado.lower().startswith("r") else "azul"
        pts = [q for q in d["puntos"] if q[6] == t and q[3] == lado]
        if len(pts) < 10:
            await ctx.reply(f"Muy pocos puntos para {p['nombre']} del lado {lado} ({len(pts)}).")
            return
        X0, Y0, X1, Y1, S = -120, -120, 14870, 14980, 512
        fig, ax = plt.subplots(figsize=(6, 6), dpi=100, facecolor="#0d1420")
        img = await self._imagen_mapa()
        if img:
            ax.imshow(mpimg.imread(io.BytesIO(img), format="png"), extent=(0, S, S, 0), alpha=0.55)
        xs = [(q[1] - X0) / (X1 - X0) * S for q in pts]
        ys = [S - (q[2] - Y0) / (Y1 - Y0) * S for q in pts]
        # Celdas de 16 px; las que están por debajo de la mediana quedan transparentes para que se vea
        # dónde se repite de verdad (con todas pintadas, el mapa entero quedaba de un color).
        import numpy as np
        H, _, _ = np.histogram2d(xs, ys, bins=32, range=[[0, S], [0, S]])
        umbral = np.percentile(H[H > 0], 50) if (H > 0).any() else 1
        H = np.where(H >= umbral, H, np.nan)
        ax.imshow(H.T, extent=(0, S, S, 0), cmap="Reds" if t == "muerte" else "Greens", alpha=0.8,
                  interpolation="nearest", vmin=umbral)
        ax.set_xlim(0, S); ax.set_ylim(S, 0); ax.axis("off")
        ax.set_title(f"{p['nombre']} · {'muertes' if t == 'muerte' else 'kills'} · lado {lado} ({len(pts)})", color="#e8ecf4")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"## {discord.utils.escape_markdown(p['nombre'])} · mapa\n-# Cuanto más fuerte el color, más se repite. "
                                   "Va por lado: desde cada base el mapa es distinto."),
            discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://mapa.png")),
            discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=f"{WEB}#/jugadores/{p['id']}")),
            accent_colour=0x00CCCC))
        await ctx.reply(view=view, file=discord.File(buf, "mapa.png"))


async def tarjeta_inhouse(bot, texto: str) -> discord.ui.LayoutView:
    """Compartida por -inhouse y el botón del menú."""
    partes = [x.strip() for x in re.split(r"[,\n;]+", texto) if x.strip()]
    if len(partes) != 10:
        partes = [x for x in texto.split() if x]
    pids, faltan = [], []
    for x in partes:
        p = await bot.datos.buscar(x)
        (pids.append(p["id"]) if p and p["id"] not in pids else faltan.append(x))
    if len(pids) != 10:
        return tarjeta_simple(["## Inhouse", f"Necesito 10 jugadores distintos del grupo; encontré {len(pids)}.",
                               f"-# No encontré o repetidos: {', '.join(faltan) or '—'}. Separalos con coma: "
                               "`-inhouse lucca, glarrex, mac55, …`"], f"{WEB}#/equipos")
    eq = await bot.datos.equipos()
    champs_nombre = await bot.datos.campeones()
    r = balancear(eq, pids)
    pA = r["a"]["fuerza"] / (r["a"]["fuerza"] + r["b"]["fuerza"])
    lineas = ["## Inhouse"]
    if r["cumplen"] < 10:
        lineas.append(f"⚠️ No hay forma de que los 10 tengan {eq['min_rol']}+ partidas en su rol. "
                      f"Mejor compromiso: {r['cumplen']} de 10 cumplen.")
    lineas.append(f"Equipo A **{F.pct(pA)}** · Equipo B **{F.pct(1 - pA)}**" + (" → parejo" if abs(pA - 0.5) < 0.02 else ""))
    for nombre, e in (("A", r["a"]), ("B", r["b"])):
        lineas.append(f"### Equipo {nombre}")
        for x in e["asig"]:
            c = r["champs"].get((x["pid"], x["rol"]))
            cn = (champs_nombre.get(str(c["id"])) or {}).get("nombre", c["id"]) if c else "—"
            falta = " ⚠️" if x["n"] < eq["min_rol"] else ""
            lineas.append(f"**{x['rol']}** · {eq['jugadores'][x['pid']]['nombre']}{falta} · {F.pct(x['wr_aj'])} en {x['n']} · {cn}")
    lineas.append("-# Probabilidad = fuerza A / (A + B), sin calibrar: no hay inhouses registradas para medir si acierta.")
    return tarjeta_simple(lineas, f"{WEB}#/equipos")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fase4(bot))
