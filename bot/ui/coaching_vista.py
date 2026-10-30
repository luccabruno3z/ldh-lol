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
    "perf": ("Performance", "Tu índice y sus 7 componentes contra tu franja"),
    "mejora": ("Plan de mejora", "Las brechas más grandes como metas en números"),
    "temp": ("Primeros 15 minutos", "CS, oro y XP a los 10 y 15 contra tu rival"),
    "gfra": ("Gráfico: contra cada franja", "Tus números al lado de la mediana de cada elo"),
    "grad": ("Gráfico: radar", "Tus 7 componentes con la mediana de cada franja"),
    "gten": ("Gráfico: ¿estás mejorando?", "Tu índice por partida y su tendencia"),
    "gevo": ("Gráfico: winrate en el tiempo", "Tus últimas 20 contra tu temporada"),
    "grac": ("Gráfico: ¿te conviene seguir?", "Tu winrate según cómo venías: rachas y pausas"),
    "gmue": ("Gráfico: lo que te cuestan las muertes", "Dónde morís y cuánta probabilidad de ganar perdés"),
}
GRAFICO = {"gfra": "franjas", "grad": "radar", "gten": "tendencia", "gevo": "evolucion", "grac": "rachas",
           "gmue": "muertes"}
SIN_ROL = ("gevo", "grac", "gmue")  # no dependen del rol
MODOS = {"solo": "Solo/Dúo", "normal": "Normales", "todo": "Todo (solo, flex y normales)"}
ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")


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
    elif not d:
        texto = "Todavía no hay coaching publicado para este jugador."
    else:
        fn = {"perf": co.tarjeta_performance, "mejora": co.tarjeta_mejora, "temp": co.tarjeta_temprano}[vista]
        texto = _texto(fn(p, d, rol))
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
            description=f"{d['roles'][r]['n']} partidas" + (" · sin referencia" if d["roles"][r].get("sin_referencia") else ""))
            for r in ROLES if r in roles]))
    items.append(sel("modo", [discord.SelectOption(
        label=l, value=m, default=m == modo,
        description=f"{n_modo[m]} partidas" if n_modo.get(m) is not None else None) for m, l in MODOS.items()]))
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
