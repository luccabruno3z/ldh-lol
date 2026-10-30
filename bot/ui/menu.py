"""-menu: un panel con botones para no tener que saberse los comandos. Basado en el menú del bot
de PR: los botones son DynamicItems (siguen andando después de un redeploy) y solo los usa quien
abrió el menú."""

from __future__ import annotations

import discord

from bot.cogs.perfil import AVISO_RIOT

ACCIONES = {"perfil": "Mi perfil", "grafico": "Mis gráficos", "buscar": "Buscar jugador", "top": "Rankings",
            "toprol": "Top por rol", "competencia": "Competencia del mes", "comparar": "Comparar",
            "tips": "Tips de mi rol", "glosario": "Glosario", "ayuda": "Ayuda", "inhouse": "Armar inhouse"}


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


class InhouseModal(discord.ui.Modal, title="Armar una inhouse"):
    jugadores = discord.ui.TextInput(label="Los 10 jugadores, separados por coma", style=discord.TextStyle.paragraph,
                                     placeholder="lucca, glarrex, mac55, cristoreyes, shiani, …", max_length=600)

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.fase4 import tarjeta_inhouse
        await interaction.response.defer(thinking=True)
        await interaction.followup.send(view=await tarjeta_inhouse(interaction.client, str(self.jugadores)))


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
        if self.accion == "inhouse":
            await interaction.response.send_modal(InhouseModal())
            return
        if self.accion == "ayuda":
            from bot.cogs.extra import AyudaVista
            await interaction.response.send_message(view=AyudaVista(), ephemeral=True)
            return
        if self.accion == "glosario":
            from bot.cogs.extra import GLOSARIO, _VistaTexto
            await interaction.response.send_message(view=_VistaTexto(GLOSARIO, "Glosario"), ephemeral=True)
            return
        if self.accion == "competencia":
            # Lo que va del mes en solo/dúo; otras fechas o colas con -competencia.
            from datetime import datetime, timedelta

            from bot.cogs.feed import ARG, tabla_competencia
            from bot.cogs.perfil import WEB, tarjeta_simple
            await interaction.response.defer(thinking=True)
            hoy = datetime.now(ARG)
            nombres = {p["id"]: p["nombre"] for p in await bot.datos.personas()}
            lineas = tabla_competencia(await bot.datos.partidas_resumen(), nombres, hoy.replace(day=1, hour=0, minute=0),
                                       hoy + timedelta(days=1), "solo", "## Competencia del mes · solo/dúo")
            lineas.append("-# Otras fechas o colas: `-competencia 1/11 30/11 flex`")
            await interaction.followup.send(view=tarjeta_simple(lineas, WEB))
            return
        if self.accion == "tips":
            pid = bot.get_cog("Perfil").vinculos.get(str(self.owner))
            d = await bot.datos.coaching_auto(pid) if pid else None
            rol = (d or {}).get("rol_con_referencia") or (d or {}).get("rol_principal")
            if not rol:
                await interaction.response.send_message(
                    "No sé tu rol principal (hace falta estar vinculado y tener 10+ partidas de solo/dúo en un rol). "
                    "Usá `-tips <rol>`.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True)
            from bot.cogs.extra import tarjeta_tips
            await interaction.followup.send(view=await tarjeta_tips(bot, rol))
            return
        if self.accion == "grafico":
            # La evolución siempre que haya 20+ partidas; el radar (la "rosa") cuando haya referencia.
            pid = bot.get_cog("Perfil").vinculos.get(str(self.owner))
            if not pid:
                await interaction.response.send_message(
                    "Primero vinculate con `-vincular <tu nombre o Riot ID>`, o usá `-grafico <jugador>`.", ephemeral=True)
                return
            from bot.cogs.extra import armar_grafico
            await interaction.response.defer(thinking=True)
            p = await bot.datos.perfil(pid)
            enviados = 0
            for tipo in ("tendencia", "evolucion", "radar"):
                view, png = await armar_grafico(bot, p, tipo, None)
                if png is not None:
                    await interaction.followup.send(view=view, file=discord.File(png, "grafico.png"))
                    enviados += 1
                elif tipo == "radar" or not enviados:
                    await interaction.followup.send(view, ephemeral=True)
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
                               "si algo dice **ruido**, con esas partidas no se puede sacar conclusiones.\n-# " + AVISO_RIOT),
        discord.ui.ActionRow(*[MenuBoton(a, owner) for a in ("perfil", "grafico", "buscar")]),
        discord.ui.ActionRow(*[MenuBoton(a, owner) for a in ("top", "toprol", "competencia", "comparar")]),
        discord.ui.ActionRow(*[MenuBoton(a, owner) for a in ("inhouse", "tips", "glosario", "ayuda")]),
        discord.ui.ActionRow(discord.ui.Button(label="Abrir la web", url="https://luccabruno3z.github.io/ldh-lol/")),
        accent_colour=0x00CCCC))
    return view
