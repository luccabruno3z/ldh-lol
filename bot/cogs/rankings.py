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
    # La medalla sigue al orden de la tabla: si el 1.º no la tiene (confianza baja), se aclara abajo.
    medallas = iter(MEDALLAS)
    for r in c["tabla"][:MAX_FILAS]:
        pid = r["persona"]
        if pid in c["podio"]:
            marca = next(medallas, f"`{r['puesto']}.`")
        else:
            marca = f"`{r['puesto']}.`"
        lineas += [f"{marca} **{nombres.get(pid, pid)}** · {F.pct(r['winrate_aj'])} · {F.partidas(r['n'])}",
                   f"-# real {F.pct(r['winrate']['v'])} ({F.rango_pct(r['winrate'])}) · confianza {r['confianza']}"]
    if not c["tabla"]:
        lineas.append(f"Nadie tiene {d['min']}+ partidas en este período.")
    elif not c["podio"]:
        lineas.append("Sin podio: nadie llega a 50 % ajustado con confianza media o alta.")
    if c.get("sin_muestra"):
        lineas.append(f"-# Sin muestra suficiente: {len(c['sin_muestra'])} personas más.")
    primero_sin = c["tabla"] and c["tabla"][0]["persona"] not in c["podio"] and c["podio"]
    lineas.append("-# Medalla solo con confianza media o alta y 50 % ajustado o más"
                  + (": por eso alguien de arriba puede no tenerla." if primero_sin else "."))
    return tarjeta_simple(lineas, f"{WEB}#/rankings/periodo")


# Unidad y por qué de cada métrica de -top_rol (el nombre viene del pipeline).
UNIDAD_ROL = {"oro": "de oro", "cs": "de CS", "xp": "de XP", "vision": "de visión/min", "dano": "de daño/min", "kp": "pts de KP"}
POR_QUE_ROL = {"oro": "La ventaja de oro a los 15 resume cómo salís de la línea: es lo que más se asocia con ganar en ese rol.",
               "vision": "En Support la visión es lo propio del rol: es lo que más depende de vos y no del tirador.",
               "cs": "El farmeo es la base del oro del rol.", "xp": "La experiencia marca quién llega antes a los niveles clave."}


def tarjeta_top_rol(v: dict, cola: str, rol: str, nombres: dict, nombre_cola: dict) -> discord.ui.LayoutView:
    g = v["grupos"][f"{cola}|{rol}"]
    dec = 0 if "oro" in g["metrica"] else 1 if "cs" in g["metrica"] else 2
    signo = g["metrica"].startswith("dif")
    clave = next((k for k in UNIDAD_ROL if k in g["metrica"]), None)
    u = f" {UNIDAD_ROL[clave]}" if clave else ""
    lineas = [f"## {rol} · {nombre_cola.get(cola, cola)}", f"-# {g['nombre']}, contra el rival directo de la misma partida"]
    if clave in POR_QUE_ROL:
        lineas.append(f"-# Por qué esta métrica: {POR_QUE_ROL[clave]}")
    for i, r in enumerate(g["tabla"][:MAX_FILAS]):
        lineas += [f"`{i + 1}.` **{nombres.get(r['persona'], r['persona'])}**: {F.num(r['valor']['v'], dec, signo)}{u} · {F.partidas(r['n'])}",
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
        tag = " · " + F.etiqueta_senal(r["senal"], None if s.get("ruido", True) else s)
        lineas += [f"`{i}.` **{nombres.get(r['persona'], r['persona'])}**: {F.num(s['v'] * 100, 1, True)} pts{tag}",
                   f"-# {F.num(s['lo'] * 100, 1, True)} a {F.num(s['hi'] * 100, 1, True)} · {r['companeros']} compañeros · "
                   f"{F.partidas(r['juntos'])}"]
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
        tag = " · " + F.etiqueta_senal(r["senal"], x)
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
    todas = (d.get("modos") or {}).get(modo, d["tabla"] if modo == "solo" else [])
    # Una fila por persona (su rol con más cambio) y ordenadas por cuánto cambiaron.
    mejor = {}
    for x in todas:
        if x["persona"] not in mejor or F.cambio(x)["v"] > F.cambio(mejor[x["persona"]])["v"]:
            mejor[x["persona"]] = x
    tabla = sorted(mejor.values(), key=lambda x: -F.cambio(x)["v"])
    en = EN_MODO.get(modo, modo)
    lineas = ["## Quién más mejoró", f"-# Nota de partida contra su propia franja, en {en} · ordenado por cuánto cambió "
                                     "a lo largo de sus partidas · una fila por persona (su rol con más cambio)"]
    for i, x in enumerate(tabla[:10], 1):
        tag = {"mejorando": "**mejorando**", "empeorando": "empeorando"}.get(x["veredicto"], "sin tendencia clara")
        lineas += [f"`{i}.` **{nombres.get(x['persona'], x['persona'])}** · {x['rol']} · {F.num(x['inicio'], 0)} → {F.num(x['ahora'], 0)} · {tag}",
                   f"-# {F.num(F.cambio(x)['v'], 1, True)} puntos ({F.num(F.cambio(x)['lo'], 1, True)} a {F.num(F.cambio(x)['hi'], 1, True)}) en {F.partidas(x['n'])}"]
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
    async def top_rol(self, ctx: commands.Context, rol: str | None = None, cola: str = "solo", ventana: str = "temporada"):
        if rol is None or (F.cola(rol) and not ROLES.get(rol.lower())):  # -top_rol, -top_rol flex
            if rol is not None:
                cola = rol
            pid = self.bot.get_cog("Perfil").vinculos.get(str(ctx.author.id))
            d = await self.datos.coaching_auto(pid) if pid else None
            rol = ((d or {}).get("rol_principal") or "top").lower()
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
