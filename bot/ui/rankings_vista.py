"""Rankings con menús desplegables en vez de argumentos (antes había que escribir `-top semana solo`).
Como en el LeaderboardView del bot de PR: la vista vive 10 minutos y solo la cambia quien la abrió."""

from __future__ import annotations

import discord

from bot.cogs.perfil import WEB
from bot.cogs.rankings import PERIODOS, tarjeta_top, tarjeta_top_rol

COLAS = {"solo": "Ranked Solo/Dúo", "flex": "Ranked Flex", "normal": "Normales"}
ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")


def _texto(view: discord.ui.LayoutView) -> str:
    return "\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))


class _Selector(discord.ui.Select):
    def __init__(self, clave: str, opciones: dict, actual: str):
        self.clave = clave
        super().__init__(options=[discord.SelectOption(label=l, value=v, default=v == actual) for v, l in opciones.items()])

    async def callback(self, interaction: discord.Interaction):
        vista = self.view
        setattr(vista, self.clave, self.values[0])
        await interaction.response.defer()
        await vista.pintar()
        await interaction.edit_original_response(view=vista)


class _Base(discord.ui.LayoutView):
    url = WEB

    def __init__(self, bot, owner: int):
        super().__init__(timeout=600)
        self.bot, self.owner = bot, owner

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message("Este ranking lo abrió otra persona. Abrí el tuyo con `-top`.", ephemeral=True)
        return False

    async def _contexto(self):
        nombres = {p["id"]: p["nombre"] for p in await self.bot.datos.personas()}
        return nombres, (await self.bot.datos.ajustes()).get("nombres_cola", {})

    def _armar(self, texto: str, selectores: list[discord.ui.Select]):
        self.clear_items()
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(texto[:3900]),
            *[discord.ui.ActionRow(s) for s in selectores],
            discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=self.url)),
            accent_colour=0x00CCCC))


class TopVista(_Base):
    url = f"{WEB}#/rankings/periodo"

    def __init__(self, bot, owner: int, periodo: str = "mes", cola: str = "solo"):
        super().__init__(bot, owner)
        self.periodo, self.cola = periodo, cola

    async def pintar(self):
        d = await self.bot.datos.ranking(self.periodo)
        texto = _texto(tarjeta_top(d, self.cola, *await self._contexto()))
        self._armar(texto, [_Selector("periodo", {k: v.capitalize() for k, v in PERIODOS.items()}, self.periodo),
                            _Selector("cola", COLAS, self.cola)])


class TopRolVista(_Base):
    url = f"{WEB}#/rankings/roles"

    def __init__(self, bot, owner: int, rol: str = "Top", cola: str = "solo", ventana: str = "historico"):
        super().__init__(bot, owner)
        self.rol, self.cola, self.ventana = rol, cola, ventana

    async def pintar(self):
        d = await self.bot.datos.ranking("roles")
        texto = _texto(tarjeta_top_rol(d[self.ventana], self.cola, self.rol, *await self._contexto()))
        self._armar(texto, [_Selector("rol", {r: r for r in ROLES}, self.rol),
                            _Selector("cola", COLAS, self.cola),
                            _Selector("ventana", {"historico": "Temporada", "reciente": "Últimos 30 días"}, self.ventana)])
