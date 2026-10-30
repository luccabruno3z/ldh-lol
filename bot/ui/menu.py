"""-menu: un panel con botones para no tener que saberse los comandos. Basado en el menú del bot
de PR: los botones son DynamicItems (siguen andando después de un redeploy) y solo los usa quien
abrió el menú."""

from __future__ import annotations

import discord

ACCIONES = {"perfil": "Mi perfil", "buscar": "Buscar jugador", "top": "Rankings", "toprol": "Top por rol",
            "comparar": "Comparar", "ayuda": "Ayuda"}


class BuscarModal(discord.ui.Modal, title="Buscar jugador"):
    jugador = discord.ui.TextInput(label="Nombre o Riot ID", placeholder="LuccaBruno#LAS o lucca", max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        from bot.ui.perfil_vista import render
        p = await interaction.client.datos.buscar(str(self.jugador))
        if not p:
            await interaction.response.send_message("No encontré a nadie con ese nombre en el grupo.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        await interaction.followup.send(view=await render(interaction.client, p["id"], "resumen", "t", interaction.user.id))


class CompararModal(discord.ui.Modal, title="Comparar dos jugadores"):
    a = discord.ui.TextInput(label="Jugador", placeholder="lucca", max_length=60)
    b = discord.ui.TextInput(label="Contra", placeholder="glarrex", max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.extra import tarjeta_comparar
        datos = interaction.client.datos
        pa, pb = await datos.buscar(str(self.a)), await datos.buscar(str(self.b))
        if not pa or not pb:
            await interaction.response.send_message("No encontré a alguno de los dos en el grupo.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        await interaction.followup.send(view=await tarjeta_comparar(interaction.client, pa["id"], pb["id"], None, None))


class MenuBoton(discord.ui.DynamicItem[discord.ui.Button], template=r"lm:(?P<accion>[a-z]+):(?P<owner>\d+)"):
    def __init__(self, accion: str, owner: int):
        self.accion, self.owner = accion, owner
        super().__init__(discord.ui.Button(
            label=ACCIONES.get(accion, accion), custom_id=f"lm:{accion}:{owner}",
            style=discord.ButtonStyle.primary if accion == "perfil" else discord.ButtonStyle.secondary))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["accion"], int(match["owner"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message("Este menú es de otra persona. Abrí el tuyo con `-menu`.", ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        if self.accion == "buscar":
            await interaction.response.send_modal(BuscarModal())
            return
        if self.accion == "comparar":
            await interaction.response.send_modal(CompararModal())
            return
        if self.accion == "ayuda":
            from bot.cogs.extra import AyudaVista
            await interaction.response.send_message(view=AyudaVista(), ephemeral=True)
            return
        if self.accion == "perfil":
            pid = bot.get_cog("Perfil").vinculos.get(str(self.owner))
            if not pid:
                await interaction.response.send_message(
                    "Primero vinculate con `-vincular <tu nombre o Riot ID>`, o usá **Buscar jugador**.", ephemeral=True)
                return
            from bot.ui.perfil_vista import render
            await interaction.response.defer(thinking=True)
            await interaction.followup.send(view=await render(bot, pid, "resumen", "t", self.owner))
            return
        from bot.ui.rankings_vista import TopRolVista, TopVista
        await interaction.response.defer(thinking=True)
        vista = TopVista(bot, self.owner) if self.accion == "top" else TopRolVista(bot, self.owner)
        await vista.pintar()
        await interaction.followup.send(view=vista)


def menu(owner: int) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("## LDH Stats LoL\nElegí qué querés ver. Los números llevan su intervalo y su n; "
                               "si algo dice **ruido**, con esas partidas no se puede sacar conclusiones."),
        discord.ui.ActionRow(*[MenuBoton(a, owner) for a in ("perfil", "buscar", "top")]),
        discord.ui.ActionRow(*[MenuBoton(a, owner) for a in ("toprol", "comparar", "ayuda")]),
        discord.ui.ActionRow(discord.ui.Button(label="Abrir la web", url="https://luccabruno3z.github.io/ldh-lol/")),
        accent_colour=0x00CCCC))
    return view
