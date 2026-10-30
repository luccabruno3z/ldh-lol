"""Lo que se trajo del bot de PR: -menu, -grafico, -comparar, -glosario, -ayuda con categorías,
-tips, -sugerencia y el ranking semanal publicado solo en un canal."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.perfil import AVISO_RIOT, WEB, autocompletar_jugador, tarjeta_simple
from bot.cogs.rankings import COLAS, ROLES, tarjeta_top
from bot.services import formato as F
from bot.services.storage import JSONStorage

logger = logging.getLogger(__name__)
ARG = timezone(timedelta(hours=-3))

METRICAS = [("winrate", "Winrate", "pct"), ("kda", "KDA", 2), ("cs_min", "CS/min", 1), ("oro_min", "Oro/min", 0),
            ("dano_min", "Daño/min", 0), ("dano_pct", "% del daño", "pct100"), ("vision_min", "Visión/min", 2),
            ("kp", "Part. kills", "pct100")]

GLOSARIO = {
    "Ajustado": "Con pocas partidas, el winrate y el KDA se acercan al promedio. Así nadie queda primero con 2 de 2. "
                "El valor **real** va al lado.",
    "Intervalo": "El rango donde está el valor real (en gris, \"x a y\"). Si es ancho, todavía hay pocas partidas.",
    "Confianza": "**alta** 15 partidas o más · **media** de 8 a 14 · **baja** menos de 8. "
                 "Con confianza baja algo no puede ser \"tu mejor\" nada.",
    "Ruido": "La diferencia existe en los números pero, con estas partidas, podría ser azar. No se puede decir que cambió.",
    "Muestra chica": "Menos de 10 partidas: va al final o plegado, y no se sacan conclusiones.",
    "Franja y percentil": "Te comparamos con jugadores de tu rango (Hierro–Bronce, Plata–Oro o Platino–Esmeralda) "
                          "en tu rol. \"Mejor que el 70 %\" es contra ellos, no contra el grupo.",
    "Performance": "Índice de 0 a 100 con 7 componentes, cada uno es tu percentil contra tu franja. 50 = la mitad de tu franja.",
    "Pool": "Una partida es \"de tu pool\" si ya tenías 5+ partidas con ese campeón en ese rol en los 90 días anteriores.",
    "Privacidad": "Solo aparecen las cuentas de quienes se sumaron al grupo, y sus estadísticas son públicas en la web "
                  "y el bot. Los demás jugadores de las partidas quedan anónimos. Para dejar de aparecer, pedíselo a Lucca.",
    "Señal": "En sinergia y en el pool: la diferencia pasa la prueba (Fisher, y con tantos pares, ajustada por "
             "Benjamini-Hochberg). Si no, es ruido.",
}

AYUDA = {
    "Empezar": "`-menu` panel con botones para todo\n`-vincular <tu nombre o Riot ID>` así los comandos sin nombre muestran el tuyo\n"
               "`-desvincular` borra el vínculo\n"
               "`-ayuda` esta guía, por tema · `-glosario [término]` qué significa ajustado, intervalo, ruido, franja…\n"
               "`-sugerencia <texto>` una idea o un error para mejorar el bot o la web",
    "Perfil": "`-perfil [jugador]` perfil con pestañas: resumen, roles, campeones, coaching y partidas. "
              "Si tenés varias cuentas, hay botones para ver cada una\n`-roles` · `-campeones` · `-sinergia` `[jugador]` "
              "abren esa pestaña directo",
    "Coaching": "`-coaching [jugador]` todo en una tarjeta: elegís qué ver, el rol y el modo con menús\n"
                "`-performance [jugador] [rol] [solo|normal|todo]` tu índice y sus 7 componentes contra tu franja\n"
                "`-mejora [jugador] [rol] [solo|normal|todo]` las 3 brechas más grandes como metas en números\n"
                "`-temprano [jugador] [rol] [solo|normal|todo]` CS, oro y XP a los 10 y 15 contra tu rival directo\n"
                "-# Sin modo: solo/dúo si te alcanza, si no `todo` (solo/dúo, flex y normales juntas).\n"
                "`-tips <rol>` consejos del rol",
    "Gráficos": "`-grafico [jugador] tendencia [rol] [modo]` ¿estás mejorando? Tu índice por partida contra tu franja y su tendencia\n"
                "`-grafico [jugador] evolucion [modo]` ¿venís mejor o peor? Tu winrate de las últimas 20 contra tu temporada\n"
                "`-grafico [jugador] radar [rol] [modo]` la rosa de tus 7 componentes contra tu franja\n"
                "`-grafico [jugador] franjas [rol] [modo]` tus números al lado de la mediana de cada franja de elo\n"
                "-# Todos traen menús para cambiar de gráfico, rol y modo sin volver a escribir el comando.\n"
                "-# En `-menu`, **Mis gráficos** manda los tres.",
    "Equipos y mapa": "`-ideal` el 5 ideal del grupo: una persona por rol con 10+ partidas ahí\n"
                      "`-inhouse <10 jugadores separados por coma>` dos equipos parejos, cada uno en un rol que conoce\n"
                      "`-matchups [jugador] [cola]` cómo te va contra cada campeón rival directo\n"
                      "`-jungla [jugador]` de qué buff arrancás y qué tan predecible sos, por lado\n"
                      "`-mapa [jugador] [muertes|kills] [azul|rojo]` dónde morís o matás, sobre el minimapa",
    "Rankings": "`-top [semana|mes|temporada] [solo|flex|normal|todo]` con menús para cambiar período y cola\n"
                "`-top_rol [rol] [cola]` la métrica de cada rol contra el rival directo\n"
                "`-comparar <jugador> <otro> [cola] [rol]` métrica por métrica\n"
                "`-competencia <desde dd/mm> [hasta dd/mm] [cola]` quién rindió mejor entre dos fechas\n"
                "`-mejoraron [solo|normal|todo]` quién más mejoró, cada uno contra su propia franja",
    "Servidor": "`-canal_feed #canal` publica cada partida del grupo (resultado, KDA y LP) y los ascensos y descensos\n"
                "`-canal_ranking #canal` publica el top de la semana y lo destacado cada lunes\n"
                "`-canal_sugerencias #canal` adónde llegan las `-sugerencia <texto>`\n"
                "-# Los tres necesitan el permiso Gestionar servidor.",
}


def _tipo_num(m: dict | None, tipo) -> str:
    if not m or m.get("v") is None:
        return "—"
    if tipo == "pct":
        return F.pct(m["v"])
    if tipo == "pct100":
        return f"{F.num(m['v'], 0)} %"
    return F.num(m["v"], tipo)


def _rango(m: dict | None, tipo) -> str:
    if not m or m.get("lo") is None:
        return ""
    if tipo == "pct":
        return F.rango_pct(m)
    return F.rango(m, 0 if tipo == "pct100" else tipo, suf=" %" if tipo == "pct100" else "")


async def tarjeta_comparar(bot, a: str, b: str, cola: str | None, rol: str | None) -> discord.ui.LayoutView:
    """Dos jugadores en la misma cola y el mismo rol. 'Se separan' solo si los intervalos no se tocan."""
    datos = bot.datos
    pa, pb = await datos.perfil(a), await datos.perfil(b)
    nc = (await datos.ajustes()).get("nombres_cola", {})
    ta, tb = pa["kpis"]["todas"], pb["kpis"]["todas"]
    comunes = [c for c in ("solo", "flex", "normal") if any(f["cola"] == c for f in ta) and any(f["cola"] == c for f in tb)]
    url = f"{WEB}#/comparar/{a}/{b}"
    if not comunes:
        return tarjeta_simple([f"## {pa['nombre']} contra {pb['nombre']}", "No tienen ninguna cola de Grieta en común."], url)
    if cola not in comunes:
        cola = max(comunes, key=lambda c: sum(f["n"] for f in ta + tb if f["cola"] == c and f["rol"] == "Todos"))
    rol = rol or "Todos"
    fa = next((f for f in ta if f["cola"] == cola and f["rol"] == rol), None)
    fb = next((f for f in tb if f["cola"] == cola and f["rol"] == rol), None)
    na, nb = discord.utils.escape_markdown(pa["nombre"]), discord.utils.escape_markdown(pb["nombre"])
    lineas = [f"## {na} contra {nb}", f"-# {nc.get(cola, cola)} · {rol} · {fa['n'] if fa else 0} y {fb['n'] if fb else 0} partidas"]
    if not fa or not fb:
        lineas.append(f"Alguno de los dos no tiene partidas de {rol} en esta cola.")
        return tarjeta_simple(lineas, url)
    for k, nombre, tipo in METRICAS:
        ma, mb = fa.get(k), fb.get(k)
        if not ma or not mb or ma.get("v") is None or mb.get("v") is None:
            continue
        separan = ma.get("lo") is not None and mb.get("lo") is not None and (ma["lo"] > mb["hi"] or mb["lo"] > ma["hi"])
        quien = (na if ma["v"] > mb["v"] else nb) if separan else None
        lineas += [f"**{nombre}**: {_tipo_num(ma, tipo)} contra {_tipo_num(mb, tipo)}"
                   + (f" → **{quien}** se separa" if quien else " → se pisan"),
                   f"-# {_rango(ma, tipo)} · {_rango(mb, tipo)}"]
    if rol == "Todos":
        lineas.append("-# \"Todos\" mezcla los roles de cada uno: para comparar a igualdad, pasá un rol (`-comparar a b solo jungla`).")
    if fa["muestra_chica"] or fb["muestra_chica"]:
        lineas.append("-# Alguno tiene menos de 10 partidas acá: muestra chica, sin conclusiones.")
    lineas.append("-# \"Se separa\" solo cuando los dos intervalos no se tocan; si se pisan, no se puede decir quién rinde más.")
    return tarjeta_simple(lineas, url)


def autocompletar_opciones(*opciones: str):
    """Autocompletado de una lista fija (tipo de gráfico, rol, lado) para los slash commands."""
    async def _auto(interaction: discord.Interaction, actual: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=o, value=o) for o in opciones if actual.lower() in o][:25]
    return _auto


async def tarjeta_tips(bot, rol: str) -> discord.ui.LayoutView:
    """Los consejos de config/consejos.json para un rol (compartido por -tips y el menú)."""
    consejos = await bot.datos.consejos()
    nombres = {"combate": "Combate", "efectividad": "Efectividad", "economia": "Economía", "linea": "Línea",
               "equipo": "Equipo", "consistencia": "Consistencia"}
    lineas = [f"## Tips · {rol}", "-# Los que te tocan a vos salen en `-mejora`, según tus números."]
    for k, n in nombres.items():
        c = consejos.get(k, {})
        if txt := c.get(rol) or c.get("_"):
            lineas.append(f"**{n}**\n> {txt}")
    return tarjeta_simple(lineas, WEB)


async def armar_grafico(bot, p: dict, tipo: str, rol: str | None, modo: str | None = None):
    """(vista, png) del gráfico pedido, o (mensaje, None) si todavía no se puede dibujar.
    modo: solo, normal o todo; sin modo, solo/dúo si alcanza y si no todo junto."""
    from bot.services import graficos
    from bot.cogs.coaching import EN_MODO
    nombre = p["nombre"]
    if tipo.lower().startswith("ten"):
        d = await bot.datos.coaching_auto(p["id"], modo)
        en = EN_MODO.get((d or {}).get("modo") or "solo")
        rol_n = ROLES.get((rol or "").lower()) or (d or {}).get("rol_con_referencia") or (d or {}).get("rol_principal")
        r = ((d or {}).get("roles") or {}).get(rol_n) or {}
        t = r.get("tendencia")
        if not t:
            return (f"Todavía no se puede medir la tendencia de {nombre} en {rol_n or 'ningún rol'}: hacen falta 30 "
                    f"partidas de {en} en el rol y referencia en su franja."), None
        png = graficos.tendencia(t, f"{nombre} · {rol_n} en {en} contra {d['franja']}", d["franja"])
        signo = lambda v: f"{'+' if v > 0 else ''}{F.num(v, 1)}"
        texto = (f"## {discord.utils.escape_markdown(nombre)} · ¿estás mejorando?\n"
                 f"De **{F.num(t['inicio'], 0)}** a **{F.num(t['ahora'], 0)}** → **{t['veredicto']}** "
                 f"({signo(t['pendiente'])} puntos cada 100 partidas, {signo(t['lo'])} a {signo(t['hi'])})\n"
                 f"-# Índice de 0 a 100 por partida: tus percentiles en {', '.join(t['metricas']).lower()} contra "
                 f"{d['franja']} en {rol_n}. Mide cómo jugás, no si ganaste. 50 = la mitad de tu franja.")
    elif tipo.lower().startswith("fra"):
        d = await bot.datos.coaching_auto(p["id"], modo)
        en = EN_MODO.get((d or {}).get("modo") or "solo")
        rol_n = ROLES.get((rol or "").lower()) or (d or {}).get("rol_con_referencia") or (d or {}).get("rol_principal")
        r = ((d or {}).get("roles") or {}).get(rol_n) or {}
        filas = r.get("por_franja")
        if not filas:
            return (f"Todavía no hay comparación por franja para {nombre} en {rol_n or 'ningún rol'}: hacen falta "
                    f"10+ partidas de {en} en el rol."), None
        png = graficos.franjas(filas, f"{nombre} · {rol_n} en {en} · tus números y la mediana de cada franja",
                               d.get("franja"))
        texto = (f"## {discord.utils.escape_markdown(nombre)} · contra cada franja\n"
                 f"-# Tu promedio al lado de la mediana de los jugadores de referencia de cada franja en {rol_n} "
                 "(ranked solo/dúo de LAS). Mejor siempre a la derecha; la barra va de la mediana de tu franja a tu punto "
                 "(verde arriba, roja abajo). No dice a qué franja te parecés: Riot no permite estimar rangos.")
    elif tipo.lower().startswith("rad"):
        d = await bot.datos.coaching_auto(p["id"], modo)
        en = EN_MODO.get((d or {}).get("modo") or "solo")
        rol_n = ROLES.get((rol or "").lower()) or (d or {}).get("rol_con_referencia") or (d or {}).get("rol_principal")
        r = ((d or {}).get("roles") or {}).get(rol_n)
        if not r or r.get("sin_referencia"):
            return (f"Todavía no hay referencia para el radar de {nombre} en {rol_n or 'ningún rol'}: hacen falta "
                    f"10+ partidas de {en} en el rol y 20 jugadores de referencia en su franja."), None
        png = graficos.radar(r["componentes"], f"{nombre} · {rol_n} en {en} contra {d['franja']}",
                             etiquetas=(nombre, ""), franjas=r.get("radar_franjas"))
        texto = (f"## {discord.utils.escape_markdown(nombre)} · radar\n-# Performance {round(r['performance']['v'] * 100)}/100 "
                 f"contra {d['franja']}. Cada línea punteada es dónde cae el jugador mediano de esa franja en la escala "
                 "de la tuya. Winrate y consistencia no se comparan entre franjas: van en 50. Detalle en `-performance`.")
    else:
        evo = p.get("evolucion") or {}
        colas = evo.get("colas") or {}
        if not colas:
            return f"{nombre} todavía no tiene {evo.get('ventana', 20)} partidas en ninguna cola de Grieta.", None
        if modo and modo not in colas:
            return f"{nombre} todavía no tiene {evo.get('ventana', 20)} partidas en {EN_MODO.get(modo, modo)}.", None
        # Sin modo, la cola más jugada (no "todo", que siempre sería la más grande).
        cola = modo or max((c for c in colas if c != "todo"), key=lambda c: colas[c]["n"], default="todo")
        nc = (await bot.datos.ajustes()).get("nombres_cola", {})
        png = graficos.evolucion(evo, cola, nc.get(cola, cola), nombre)
        c = colas[cola]
        if c.get("ultimas"):
            veredicto = (("**venís mejor**" if c["ultimas"]["v"] > c["resto"]["v"] else "**venís peor**")
                         if c.get("senal") else "igual que siempre (ruido)")
            resp = (f"En tus últimas {evo['ventana']} ganás **{F.pct(c['ultimas']['v'])}**; antes, "
                    f"{F.pct(c['resto']['v'])} → {veredicto} · Fisher p = {F.num(c['p'], 2)}")
        else:
            resp = ""
        texto = (f"## {discord.utils.escape_markdown(nombre)} · ¿venís mejor o peor?\n{resp}\n"
                 f"-# Cada punto es tu winrate en las {evo['ventana']} partidas anteriores a esa fecha. "
                 "La banda es el margen de error; la línea naranja, tu promedio de la temporada.")
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(texto),
        discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://grafico.png")),
        discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=f"{WEB}#/jugadores/{p['id']}")),
        accent_colour=0x00CCCC))
    return view, png


class _SelectorTexto(discord.ui.Select):
    def __init__(self, textos: dict, titulo: str):
        self.textos, self.titulo = textos, titulo
        super().__init__(placeholder="Elegí un tema", options=[discord.SelectOption(label=k) for k in textos])

    async def callback(self, interaction: discord.Interaction):
        # La vista se guarda antes de rearmarla: mostrar() saca este selector y self.view pasa a None,
        # y editar con view=None en un mensaje de Components V2 da "Cannot send an empty message".
        vista = self.view
        vista.mostrar(self.values[0])
        await interaction.response.defer()
        await interaction.edit_original_response(view=vista)


class _VistaTexto(discord.ui.LayoutView):
    def __init__(self, textos: dict, titulo: str, inicial: str | None = None):
        super().__init__(timeout=600)
        self.textos, self.titulo = textos, titulo
        self.mostrar(inicial or next(iter(textos)))

    def mostrar(self, k: str):
        self.clear_items()
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"## {self.titulo} · {k}\n{self.textos[k]}\n\n-# {AVISO_RIOT}"),
            discord.ui.ActionRow(_SelectorTexto(self.textos, self.titulo)),
            discord.ui.ActionRow(discord.ui.Button(label="Abrir la web", url=WEB)),
            accent_colour=0x00CCCC))


class AyudaVista(_VistaTexto):
    def __init__(self):
        super().__init__(AYUDA, "Ayuda")


class Extra(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.canales = JSONStorage("canales.json")  # {guild_id: {"ranking": id, "sugerencias": id, "ultimo_ranking": "2026-W44"}}
        self.sugerencias = JSONStorage("sugerencias.json")
        self.ranking_semanal.start()

    def cog_unload(self):
        self.ranking_semanal.cancel()

    @property
    def datos(self):
        return self.bot.datos

    async def _persona(self, ctx, jugador, comando):
        return await self.bot.get_cog("Perfil")._persona(ctx, jugador, comando)

    @commands.hybrid_command(name="menu", description="Panel con botones: tu perfil, buscar, rankings, comparar y ayuda")
    async def menu(self, ctx: commands.Context):
        from bot.ui.menu import menu
        await ctx.reply(view=menu(ctx.author.id))

    @commands.hybrid_command(name="ayuda", description="Qué hace el bot, por tema")
    async def ayuda(self, ctx: commands.Context):
        await ctx.reply(view=AyudaVista())

    @commands.hybrid_command(name="glosario", description="Qué significa cada término (ajustado, intervalo, ruido…)")
    async def glosario(self, ctx: commands.Context, *, termino: str | None = None):
        inicial = next((k for k in GLOSARIO if termino and termino.lower() in k.lower()), None)
        await ctx.reply(view=_VistaTexto(GLOSARIO, "Glosario", inicial))

    @commands.hybrid_command(name="tips", description="Consejos de juego para un rol")
    async def tips(self, ctx: commands.Context, rol: str = "top"):
        rol_n = ROLES.get(rol.lower())
        if not rol_n:
            await ctx.reply("Uso: `-tips <top|jungla|mid|adc|support>`", ephemeral=True)
            return
        await ctx.reply(view=await tarjeta_tips(self.bot, rol_n))

    @commands.hybrid_command(name="comparar", description="Dos jugadores, métrica por métrica, en la misma cola y rol")
    @app_commands.autocomplete(jugador=autocompletar_jugador, otro=autocompletar_jugador)
    async def comparar(self, ctx: commands.Context, jugador: str, otro: str, cola: str | None = None, rol: str | None = None):
        pa, pb = await self.datos.buscar(jugador), await self.datos.buscar(otro)
        if not pa or not pb:
            await ctx.reply("No encontré a alguno de los dos. Uso: `-comparar <jugador> <otro> [solo|flex|normal|todo] [rol]`", ephemeral=True)
            return
        await ctx.defer()
        await ctx.reply(view=await tarjeta_comparar(self.bot, pa["id"], pb["id"],
                                                    COLAS.get((cola or "").lower()), ROLES.get((rol or "").lower())))

    @commands.hybrid_command(name="grafico", description="Evolución del winrate, tendencia de mejora o radar de tus componentes")
    @app_commands.autocomplete(jugador=autocompletar_jugador, tipo=autocompletar_opciones("tendencia", "evolucion", "radar", "franjas"),
                               rol=autocompletar_opciones("top", "jungla", "mid", "adc", "support"),
                               modo=autocompletar_opciones("solo", "normal", "todo"))
    async def grafico(self, ctx: commands.Context, jugador: str | None = None, tipo: str = "evolucion", rol: str | None = None,
                      modo: str | None = None):
        if jugador and jugador.lower() in ("evolucion", "evolución", "radar", "tendencia", "franjas"):  # -grafico radar
            jugador, tipo = None, jugador
        if not (p := await self._persona(ctx, jugador, "grafico")):
            return
        await ctx.defer()  # dibujar el PNG puede pasar los 3 s
        from bot.cogs.coaching import MODOS
        from bot.ui.coaching_vista import responder
        if rol and rol.lower() in MODOS and not modo:  # -grafico lucca radar todo
            rol, modo = None, rol
        vista = {"ten": "gten", "rad": "grad", "fra": "gfra"}.get(tipo.lower()[:3], "gevo")
        # Con menús para cambiar de gráfico, rol y modo sin volver a escribir el comando.
        await responder(ctx, self.bot, vista, p["id"], ROLES.get((rol or "").lower()), MODOS.get((modo or "").lower()))

    @commands.hybrid_command(name="sugerencia", description="Dejá una idea o un error para mejorar el bot o la web")
    async def sugerencia(self, ctx: commands.Context, *, texto: str):
        lista = self.sugerencias.get("lista", [])
        lista.append({"autor": str(ctx.author), "texto": texto[:1000], "t": datetime.now(timezone.utc).isoformat()})
        self.sugerencias.set("lista", lista[-500:])
        canal_id = (self.canales.get(str(ctx.guild.id)) or {}).get("sugerencias") if ctx.guild else None
        canal = self.bot.get_channel(canal_id) if canal_id else None
        if canal:
            await canal.send(f"💡 **Sugerencia de {discord.utils.escape_markdown(ctx.author.display_name)}**\n> {texto[:1500]}")
        await ctx.reply("¡Gracias! La sugerencia quedó anotada.")

    def _config(self, guild_id: int, clave: str, valor):
        c = self.canales.get(str(guild_id)) or {}
        c[clave] = valor
        self.canales.set(str(guild_id), c)

    @commands.hybrid_command(name="canal_ranking", description="Canal donde se publica el top de la semana cada lunes")
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    async def canal_ranking(self, ctx: commands.Context, canal: discord.TextChannel | None = None):
        self._config(ctx.guild.id, "ranking", canal.id if canal else None)
        await ctx.reply(f"Listo: el top semanal se publica en {canal.mention} los lunes a las 12." if canal
                        else "Listo: ya no se publica el top semanal.")

    @commands.hybrid_command(name="canal_sugerencias", description="Canal adonde llegan las -sugerencia")
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    async def canal_sugerencias(self, ctx: commands.Context, canal: discord.TextChannel | None = None):
        self._config(ctx.guild.id, "sugerencias", canal.id if canal else None)
        await ctx.reply(f"Listo: las sugerencias llegan a {canal.mention}." if canal else "Listo: las sugerencias solo se guardan.")

    @tasks.loop(minutes=30)
    async def ranking_semanal(self):
        """Lunes desde las 12 (hora argentina): el top de la semana en solo/dúo, una vez por semana y servidor."""
        ahora = datetime.now(ARG)
        if ahora.weekday() != 0 or ahora.hour < 12:
            return
        semana = f"{ahora.isocalendar().year}-W{ahora.isocalendar().week:02d}"
        pendientes = [(gid, c) for gid, c in self.canales.all().items()
                      if c.get("ranking") and c.get("ultimo_ranking") != semana]
        if not pendientes:
            return
        try:
            d = await self.datos.ranking("semana")
            nombres = {p["id"]: p["nombre"] for p in await self.datos.personas()}
            nc = (await self.datos.ajustes()).get("nombres_cola", {})
            feed = self.bot.get_cog("Feed")
            destacados = await feed.destacados_semana() if feed else []
        except Exception:
            logger.exception("No pude leer el ranking semanal")
            return
        for gid, c in pendientes:
            canal = self.bot.get_channel(c["ranking"])
            if not canal:
                continue
            try:
                await canal.send(view=tarjeta_top(d, "solo", nombres, nc))
                if destacados:
                    await canal.send(view=tarjeta_simple(destacados, WEB))
                self._config(int(gid), "ultimo_ranking", semana)
            except discord.HTTPException:
                logger.exception("No pude publicar el ranking semanal en %s", gid)

    @ranking_semanal.before_loop
    async def _esperar(self):
        await self.bot.wait_until_ready()

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.MissingPermissions, commands.NoPrivateMessage)):
            await ctx.reply("Eso lo puede configurar alguien con permiso de **Gestionar servidor**, dentro del servidor.")
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Extra(bot))
