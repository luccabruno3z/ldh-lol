"""Coaching y gráficos con menús: qué ver, rol y modo (solo/dúo, normales o todo), en vez de escribirlos
en el comando. Los menús son DynamicItems: el estado viaja en el custom_id, así que siguen andando
después de 10 minutos y de un redeploy, como los del perfil y los rankings. Solo los usa quien abrió
la tarjeta; cada cambio edita el mismo mensaje (con el gráfico nuevo si es un gráfico)."""

from __future__ import annotations

import io

import discord

from bot.cogs.perfil import WEB
from bot.services import formato as F

# Qué se puede ver: (etiqueta, descripción). Las que empiezan con "g" son gráficos.
VISTAS = {
    "perf": ("Performance", "Tu Performance y sus 7 componentes contra tu franja"),
    "mejora": ("Plan de mejora", "Las brechas más grandes como metas en números"),
    "temp": ("Primeros 15 minutos", "CS, oro y XP a los 10 y 15 contra tu rival"),
    "conv": ("¿Cerrás las que ibas ganando?", "Ganadas contra esperadas según cómo iba tu equipo al 15"),
    "gfra": ("Gráfico: contra cada franja", "Tus números al lado de la mediana de cada elo"),
    "grad": ("Gráfico: radar", "Tus 7 componentes con la mediana de cada franja"),
    "gten": ("Gráfico: ¿estás mejorando?", "Tu nota de partida y su tendencia"),
    "gevo": ("Gráfico: winrate en el tiempo", "Tus últimas 20 contra tu temporada"),
    "grac": ("Gráfico: ¿cómo te va después de perder?", "Tu winrate según cómo venías: rachas y pausas"),
    "gmue": ("Gráfico: tus chances al morir", "Dónde morís y cuánto estima el modelo que bajan tus chances"),
    "gcur": ("Gráfico: curva de aprendizaje", "Cuánto te lleva aprender un campeón, con tus más jugados del rol"),
}
GRAFICO = {"gfra": "franjas", "grad": "radar", "gten": "tendencia", "gevo": "evolucion", "grac": "rachas",
           "gmue": "muertes", "gcur": "curva"}
SIN_ROL = ("gevo", "grac", "conv")  # no se filtran por rol: la tarjeta lo dice
MODOS = {"solo": "Solo/Dúo", "normal": "Normales", "todo": "Todo (solo, flex y normales)"}
ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")


CONV = {"ventaja": "Ibas arriba al 15 (60 % o más)", "pareja": "Pareja al 15", "desventaja": "Ibas abajo al 15 (40 % o menos)"}
EN_MODO = {"solo": "solo/dúo", "normal": "normales", "todo": "todas las colas"}


def texto_conversion(p: dict, d: dict | None, modo: str) -> str:
    """Ganadas contra esperadas por el modelo al minuto 15, contra el grupo."""
    nombre = discord.utils.escape_markdown(p.get("nombre", p.get("id", "")))
    m = ((d or {}).get("modos") or {}).get(modo)
    lin = [f"## {nombre} · ¿cerrás las que ibas ganando? · {EN_MODO.get(modo, modo)}"]
    if not m or not any(x.get("n") for x in m.values()):
        return "\n".join(lin + ["Todavía no hay partidas de 16 minutos o más con timeline en este modo."])
    pts = lambda v: F.num(v * 100, 1, True)  # noqa: E731
    for k, nombre_t in CONV.items():
        x = m.get(k) or {}
        if not x.get("n"):
            lin.append(f"**{nombre_t}:** sin partidas")
            continue
        if x.get("muestra_chica"):
            lin.append(f"**{nombre_t}:** {x['ganadas']} ganadas en {x['n']} · muestra chica")
            continue
        if x.get("senal"):
            lectura = ("más" if x["contra_grupo"] > 0 else "menos") + " que el grupo"
        else:
            lectura = "como el grupo (" + F.etiqueta_senal(False, None).strip("*") + ")"
        p_bh = f" · p = {x['p_bh']:.2f}".replace(".", ",") if x.get("p_bh") is not None else ""
        lin.append(f"**{nombre_t}:** {x['ganadas']} ganadas de {x['esperadas']:.0f} esperadas en {x['n']} · "
                   f"{pts(x['v'])} pts por partida ({pts(x['lo'])} a {pts(x['hi'])}) · {lectura}{p_bh}")
    lin.append("-# Probabilidad del modelo al minuto 15. El modelo se entrenó con estas partidas: el grupo da cerca de "
               "cero por construcción, por eso se compara cada uno contra el grupo (BH entre personas). Es del equipo, "
               "no solo tuyo, y es una asociación.")
    return "\n".join(lin)


def _texto(view) -> str:
    return "\n\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))


class SelectorCoaching(discord.ui.DynamicItem[discord.ui.Select],
                       template=r"lc:(?P<vista>[a-z]+):(?P<pid>[A-Za-z0-9_-]+):(?P<rol>[A-Za-z]+):"
                                r"(?P<modo>[a-z]+):(?P<owner>\d+):(?P<clave>vista|rol|modo)"):
    def __init__(self, vista: str, pid: str, rol: str, modo: str, owner: int, clave: str,
                 opciones: list[discord.SelectOption] | None = None):
        self.vista, self.pid, self.rol, self.modo, self.owner, self.clave = vista, pid, rol, modo, owner, clave
        cid = f"lc:{vista}:{pid}:{rol}:{modo}:{owner}:{clave}"[:100]
        # Al reconstruirse desde el custom_id, Discord no manda las opciones: alcanza con una de relleno,
        # el callback solo lee el valor elegido.
        super().__init__(discord.ui.Select(custom_id=cid, options=opciones or [discord.SelectOption(label="-")]))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["vista"], match["pid"], match["rol"], match["modo"], int(match["owner"]), match["clave"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message(
            "Esta tarjeta la abrió otra persona. Abrí la tuya con `-performance`, `-grafico` o el `-menu`.", ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction):
        estado = {"vista": self.vista, "rol": self.rol, "modo": self.modo, self.clave: self.item.values[0]}
        await interaction.response.defer()
        view, png = await vista_coaching(interaction.client, estado["vista"], self.pid, estado["rol"], estado["modo"], self.owner)
        archivos = [discord.File(png, "grafico.png")] if png else []
        await interaction.edit_original_response(view=view, attachments=archivos)


async def vista_coaching(bot, vista: str, pid: str, rol: str | None, modo: str | None,
                         owner: int) -> tuple[discord.ui.LayoutView, io.BytesIO | None]:
    """La tarjeta pedida con sus tres menús. rol y modo: None o "auto" = el de siempre (solo/dúo si
    alcanza, si no todo; el rol con más partidas con referencia)."""
    from bot.cogs import coaching as co
    from bot.cogs.extra import armar_grafico

    rol = None if rol in (None, "auto") else rol
    modo = None if modo in (None, "auto") else modo
    datos = bot.datos
    p = await datos.perfil(pid) or {"id": pid, "nombre": pid}
    d = await datos.coaching_auto(pid, modo) or {}
    modo = d.get("modo") or modo or "solo"
    roles = list(d.get("roles") or {})
    if rol and rol not in roles and vista not in SIN_ROL:
        rol = None  # el rol elegido no tiene muestra en este modo: se vuelve al de siempre
    rol = rol or d.get("rol_con_referencia") or d.get("rol_principal")

    png = None
    if vista in GRAFICO:
        res, png = await armar_grafico(bot, p, GRAFICO[vista], rol, modo)
        texto = res if png is None else _texto(res)
    elif vista == "conv":
        texto = texto_conversion(p, await datos.conversion(pid), modo)
    elif not d:
        texto = "Todavía no hay coaching publicado para este jugador."
    else:
        fn = {"perf": co.tarjeta_performance, "mejora": co.tarjeta_mejora, "temp": co.tarjeta_temprano}[vista]
        texto = _texto(fn(p, d, rol))
    if vista in SIN_ROL and (png is not None or vista == "conv"):
        texto += "\n-# Usa todas tus partidas del modo, sin filtrar por rol."
    if len(texto) > 3500:
        texto = texto[:3490] + "\n…"

    # Cuántas partidas tiene cada modo, para elegir sabiendo (los JSON quedan en caché).
    n_modo = {}
    for m in MODOS:
        dm = d if m == modo else await datos.coaching(pid, m)
        n_modo[m] = (dm or {}).get("n_modo")

    estado = {"vista": vista, "rol": rol or "auto", "modo": modo}
    sel = lambda clave, opciones: discord.ui.ActionRow(  # noqa: E731
        SelectorCoaching(estado["vista"], pid, estado["rol"], estado["modo"], owner, clave, opciones))
    items: list[discord.ui.Item] = [discord.ui.TextDisplay(texto)]
    if png:
        items.append(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://grafico.png")))
    items.append(discord.ui.Separator())
    items.append(sel("vista", [discord.SelectOption(label=l, value=v, description=desc, default=v == vista)
                               for v, (l, desc) in VISTAS.items()]))
    if roles and vista not in SIN_ROL:
        items.append(sel("rol", [discord.SelectOption(
            label=r, value=r, default=r == rol,
            description=f"{F.partidas(d['roles'][r]['n'])}" + (" · sin referencia" if d["roles"][r].get("sin_referencia") else ""))
            for r in ROLES if r in roles]))
    items.append(sel("modo", [discord.SelectOption(
        label=l, value=m, default=m == modo,
        description=f"{F.partidas(n_modo[m])}" if n_modo.get(m) is not None else None) for m, l in MODOS.items()]))
    items.append(discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=f"{WEB}#/jugadores/{pid}/coaching")))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=0x00CCCC))
    return view, png


async def responder(ctx, bot, vista: str, pid: str, rol: str | None, modo: str | None) -> None:
    """Contesta un comando con la tarjeta y sus menús."""
    view, png = await vista_coaching(bot, vista, pid, rol, modo, ctx.author.id)
    if png:
        await ctx.reply(view=view, file=discord.File(png, "grafico.png"))
    else:
        await ctx.reply(view=view)


__all__ = ["SelectorCoaching", "vista_coaching", "responder", "VISTAS", "F"]
