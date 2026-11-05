"""Rankings del grupo: por período y por rol. Mismos JSON que la web (api/rankings/)."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.cogs.perfil import WEB, tarjeta_simple
from bot.services import formato as F

PERIODOS = {"semana": "últimos 7 días", "mes": "últimos 30 días", "temporada": "temporada"}
COLAS = F.COLAS  # el mismo diccionario en todos los comandos ("ranked", "todas"…)
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


def tarjeta_companeros(d: dict, nombres: dict, modo: str = "todo") -> discord.ui.LayoutView:
    """Mejores compañeros: cuántos puntos de winrate le suma cada uno a sus compañeros del grupo."""
    from bot.cogs.coaching import EN_MODO
    tabla = [r for r in (d.get("modos") or {}).get(modo, []) if not r["muestra_chica"]]
    lineas = ["## Mejores compañeros", f"-# Cuánto ganan tus compañeros con vos contra sin vos, en {EN_MODO.get(modo, modo)} · "
                                       "cada compañero contra sí mismo, mismo período"]
    for i, r in enumerate(tabla[:12], 1):
        s = r["suma"]
        tag = (" · **señal**" if r["senal"] else " · ruido" if s.get("ruido", True) else " · a confirmar")
        lineas += [f"`{i}.` **{nombres.get(r['persona'], r['persona'])}**: {F.num(s['v'] * 100, 1, True)} pts{tag}",
                   f"-# {F.num(s['lo'] * 100, 1, True)} a {F.num(s['hi'] * 100, 1, True)} · {r['companeros']} compañeros · "
                   f"{r['juntos']} partidas"]
    if not tabla:
        lineas.append("Todavía no hay suficientes partidas juntos en este modo.")
    lineas.append("-# 'Señal' con el p corregido por Benjamini–Hochberg (se compara a todos a la vez). No mide solo cómo "
                  "juega cada uno: también pesa con quién y en qué cola suele jugar.")
    return tarjeta_simple(lineas, f"{WEB}#/rankings/companeros")


def tarjeta_duos(d: dict, nombres: dict, modo: str = "todo", pid: str | None = None) -> discord.ui.LayoutView:
    """Dúos normalizados: juntos contra lo que daría cada uno por separado en el mismo período.
    Con pid, solo las parejas de esa persona."""
    from bot.cogs.coaching import EN_MODO
    todas = (d.get("modos") or {}).get(modo, [])
    if pid:
        todas = [r for r in todas if pid in (r["a"], r["b"])]
    tabla = [r for r in todas if not r["muestra_chica"]]
    lineas = ["## ¿Rinden juntos más que por separado?" + (f" · {nombres.get(pid, pid)}" if pid else ""),
              f"-# Dúos con {d.get('min_juntos', 15) * 2}+ partidas juntos en {EN_MODO.get(modo, modo)} · contra el winrate de "
              "cada uno sin el otro en el mismo período"]
    pct = lambda v: f"{F.num(v * 100, 0)} %"  # noqa: E731
    for i, r in enumerate(tabla[:12], 1):
        x = r["dif"]
        tag = (" · **señal**" if r["senal"] else " · a confirmar" if x["lo"] > 0 or x["hi"] < 0 else " · ruido")
        lineas += [f"`{i}.` **{nombres.get(r['a'], r['a'])} + {nombres.get(r['b'], r['b'])}**: "
                   f"{F.num(x['v'] * 100, 0, True)} pts{tag}",
                   f"-# {F.num(x['lo'] * 100, 0, True)} a {F.num(x['hi'] * 100, 0, True)} · juntos {pct(r['real']['v'])} "
                   f"en {r['juntos']} · esperado {pct(r['esperado'])} (por separado {pct(r['sin_a']['v'])} y {pct(r['sin_b']['v'])})"]
    if len(tabla) > 12:
        lineas.append(f"-# Y {len(tabla) - 12} dúos más en la web.")
    if not tabla:
        lineas.append("Todavía no hay dúos con suficientes partidas juntos en este modo."
                      + (f" Hay {len(todas)} con muestra chica en la web." if todas else ""))
    lineas.append("-# Esperado: lo que darían juntos si cada uno aporta lo suyo. 'Señal' con bootstrap y corrección BH "
                  "entre parejas. Es una asociación: también pesan la cola, el horario y contra quién juegan.")
    return tarjeta_simple(lineas, f"{WEB}#/rankings/duos")


def tarjeta_mejora(d: dict, nombres: dict, modo: str = "solo") -> discord.ui.LayoutView:
    from bot.cogs.coaching import EN_MODO
    tabla = (d.get("modos") or {}).get(modo, d["tabla"] if modo == "solo" else [])
    en = EN_MODO.get(modo, modo)
    lineas = ["## Quién más mejoró", f"-# Índice por partida contra su propia franja, en {en} · cambio a lo largo de sus partidas"]
    for i, x in enumerate(tabla[:10], 1):
        tag = {"mejorando": "**mejorando**", "empeorando": "empeorando"}.get(x["veredicto"], "sin tendencia clara")
        lineas += [f"`{i}.` **{nombres.get(x['persona'], x['persona'])}** · {x['rol']} · {F.num(x['inicio'], 0)} → {F.num(x['ahora'], 0)} · {tag}",
                   f"-# {F.num(F.cambio(x)['v'], 1, True)} puntos ({F.num(F.cambio(x)['lo'], 1, True)} a {F.num(F.cambio(x)['hi'], 1, True)}) en {x['n']} partidas"]
    if not tabla:
        lineas.append(f"Nadie tiene 30+ partidas de {en} en un rol con referencia.")
    lineas.append("-# Mejorando solo si todo el intervalo está arriba de cero. Cada uno contra su franja: se puede comparar entre rangos.")
    return tarjeta_simple(lineas, f"{WEB}#/rankings/mejora")


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
        periodo, cola = F.periodo(periodo), F.cola(cola)
        if periodo not in PERIODOS or not cola:
            await ctx.reply("Uso: `-top [semana|mes|temporada] [solo|flex|normal|todo]`", ephemeral=True)
            return
        from bot.ui.rankings_vista import TopVista
        await ctx.defer()
        vista = TopVista(self.bot, ctx.author.id, periodo, cola)  # con menús para cambiar período y cola
        await vista.pintar()
        await ctx.reply(view=vista)

    @commands.hybrid_command(name="top_rol", description="Ranking por rol con la métrica de cada rol contra el rival directo")
    async def top_rol(self, ctx: commands.Context, rol: str = "top", cola: str = "solo", ventana: str = "temporada"):
        rol, cola = ROLES.get(rol.lower()), F.cola(cola)
        if not rol or not cola:
            await ctx.reply("Uso: `-top_rol <top|jungla|mid|adc|support> [solo|flex|normal|todo] [temporada|reciente]`", ephemeral=True)
            return
        from bot.ui.rankings_vista import TopRolVista
        await ctx.defer()
        vista = TopRolVista(self.bot, ctx.author.id, rol, cola, "reciente" if ventana.lower().startswith("rec") else "historico")
        await vista.pintar()
        await ctx.reply(view=vista)


    @commands.hybrid_command(name="companeros", description="Mejores compañeros: quién hace ganar más a los demás")
    async def companeros(self, ctx: commands.Context, modo: str = "todo"):
        if (m := F.cola(modo, ("solo", "normal", "todo"))) is None:
            await ctx.reply("Uso: `-companeros [solo|normal|todo]`", ephemeral=True)
            return
        await ctx.defer()
        nombres, _ = await self._contexto()
        await ctx.reply(view=tarjeta_companeros(await self.datos.ranking("companeros") or {}, nombres, m))

    @commands.hybrid_command(name="duos", description="Dúos: si rinden juntos más que lo que da cada uno por separado")
    async def duos(self, ctx: commands.Context, *, texto: str | None = None):
        # -duos, -duos normal, -duos lucca, -duos lucca solo: el modo al final y opcional.
        partes = (texto or "").split()
        m = "todo"
        if partes and F.cola(partes[-1], ("solo", "normal", "todo")):
            m = F.cola(partes.pop(), ("solo", "normal", "todo"))
        elif partes and F.cola(partes[-1]):  # flex: los dúos no se separan por flex
            await ctx.reply("Uso: `-duos [jugador] [solo|normal|todo]` (Flex va dentro de \"todo\").", ephemeral=True)
            return
        pid = None
        if partes:
            p = await self.datos.buscar(" ".join(partes))
            if not p:
                await ctx.reply(await self.datos.no_encontre(" ".join(partes)), ephemeral=True)
                return
            pid = p["id"]
        await ctx.defer()
        nombres, _ = await self._contexto()
        await ctx.reply(view=tarjeta_duos(await self.datos.ranking("duos") or {}, nombres, m, pid))

    @commands.hybrid_command(name="mejoraron", description="Quién más mejoró: la tendencia de cada uno contra su franja")
    async def mejoraron(self, ctx: commands.Context, modo: str = "solo"):
        if (m := F.cola(modo, ("solo", "normal", "todo"))) is None:
            await ctx.reply("Uso: `-mejoraron [solo|normal|todo]`", ephemeral=True)
            return
        await ctx.defer()
        nombres, _ = await self._contexto()
        await ctx.reply(view=tarjeta_mejora(await self.datos.ranking("mejora") or {"tabla": []}, nombres, m))


async def setup(bot: commands.Bot):
    await bot.add_cog(Rankings(bot))
