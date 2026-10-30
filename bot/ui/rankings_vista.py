"""Rankings con menús desplegables en vez de argumentos (antes había que escribir `-top semana solo`).

Los menús son DynamicItems: el estado (período, cola, rol, ventana) viaja en el custom_id, así que
siguen andando después de 10 minutos y después de un redeploy, como los botones del perfil.
Solo los cambia quien abrió el ranking."""

from __future__ import annotations

import discord

from bot.cogs.perfil import WEB
from bot.cogs.rankings import PERIODOS, tarjeta_top, tarjeta_top_rol

COLAS = {"solo": "Ranked Solo/Dúo", "flex": "Ranked Flex", "normal": "Normales"}
ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")
VENTANAS = {"historico": "Temporada", "reciente": "Últimos 30 días"}
# Qué menús tiene cada ranking y en qué orden van los valores dentro del estado.
CLAVES = {"top": ("periodo", "cola"), "rol": ("rol", "cola", "ventana")}
OPCIONES = {"periodo": {k: v.capitalize() for k, v in PERIODOS.items()}, "cola": COLAS,
            "rol": {r: r for r in ROLES}, "ventana": VENTANAS}


def _texto(view: discord.ui.LayoutView) -> str:
    return "\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))


class SelectorRanking(discord.ui.DynamicItem[discord.ui.Select],
                      template=r"lk:(?P<tipo>top|rol):(?P<estado>[A-Za-z|]+):(?P<owner>\d+):(?P<clave>[a-z]+)"):
    def __init__(self, tipo: str, estado: dict, owner: int, clave: str):
        self.tipo, self.estado, self.owner, self.clave = tipo, estado, owner, clave
        cid = f"lk:{tipo}:{'|'.join(estado[k] for k in CLAVES[tipo])}:{owner}:{clave}"
        super().__init__(discord.ui.Select(custom_id=cid[:100], options=[
            discord.SelectOption(label=l, value=v, default=v == estado[clave]) for v, l in OPCIONES[clave].items()]))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        tipo = match["tipo"]
        estado = dict(zip(CLAVES[tipo], match["estado"].split("|")))
        return cls(tipo, estado, int(match["owner"]), match["clave"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message("Este ranking lo abrió otra persona. Abrí el tuyo con `-top`.", ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction):
        estado = {**self.estado, self.clave: self.item.values[0]}
        await interaction.response.defer()
        await interaction.edit_original_response(view=await vista_ranking(interaction.client, self.tipo, estado, self.owner))


async def vista_ranking(bot, tipo: str, estado: dict, owner: int) -> discord.ui.LayoutView:
    nombres = {p["id"]: p["nombre"] for p in await bot.datos.personas()}
    nc = (await bot.datos.ajustes()).get("nombres_cola", {})
    if tipo == "top":
        d = await bot.datos.ranking(estado["periodo"])
        texto, url = _texto(tarjeta_top(d, estado["cola"], nombres, nc)), f"{WEB}#/rankings/periodo"
    else:
        d = await bot.datos.ranking("roles")
        texto = _texto(tarjeta_top_rol(d[estado["ventana"]], estado["cola"], estado["rol"], nombres, nc))
        url = f"{WEB}#/rankings/roles"
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(texto[:3900]),
        *[discord.ui.ActionRow(SelectorRanking(tipo, estado, owner, k)) for k in CLAVES[tipo]],
        discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=url)),
        accent_colour=0x00CCCC))
    return view


class TopVista:
    """Compatibilidad con el menú y los comandos: arma la vista persistente de -top."""

    def __new__(cls, bot, owner: int, periodo: str = "mes", cola: str = "solo"):
        return _Pendiente(bot, "top", {"periodo": periodo, "cola": cola}, owner)


class TopRolVista:
    def __new__(cls, bot, owner: int, rol: str = "Top", cola: str = "solo", ventana: str = "historico"):
        return _Pendiente(bot, "rol", {"rol": rol, "cola": cola, "ventana": ventana}, owner)


class _Pendiente(discord.ui.LayoutView):
    """Se arma con `await vista.pintar()` (mismo uso que antes) y queda persistente."""

    def __init__(self, bot, tipo: str, estado: dict, owner: int):
        super().__init__(timeout=None)
        self._args = (bot, tipo, estado, owner)

    async def pintar(self):
        lista = await vista_ranking(*self._args)
        self.clear_items()
        for item in lista.children:
            self.add_item(item)
