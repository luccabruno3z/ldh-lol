"""-partida: el gráfico de la probabilidad de ganar de una partida, con ◀ ▶ para recorrer el historial.
Los botones son DynamicItems (el número de partida viaja en el custom_id), así que siguen andando después
de un redeploy. Solo los usa quien abrió la tarjeta."""

from __future__ import annotations

import io

import discord

from bot.cogs.perfil import WEB
from bot.services import formato as F

OBJ = {"baron": "el Barón", "ancestral": "el Ancestral", "dragon": "un dragón", "heraldo": "el Heraldo",
       "larva": "larvas", "torre": "una torre", "inhib": "un inhibidor"}
POR_PAGINA = 15  # historial_por_pagina de config/ajustes.json


class PartidaBoton(discord.ui.DynamicItem[discord.ui.Button],
                   template=r"lq:(?P<pid>[A-Za-z0-9_-]+):(?P<i>\d+):(?P<owner>\d+):(?P<dir>[ab])"):
    def __init__(self, pid: str, i: int, owner: int, dir: str, *, disabled: bool = False):
        self.pid, self.i, self.owner = pid, i, owner
        super().__init__(discord.ui.Button(label="◀ Anterior" if dir == "a" else "Siguiente ▶",
                                           custom_id=f"lq:{pid}:{i}:{owner}:{dir}"[:100], disabled=disabled,
                                           style=discord.ButtonStyle.secondary))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["pid"], int(match["i"]), int(match["owner"]), match["dir"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message("Esta tarjeta la abrió otra persona. Abrí la tuya con `-partida`.",
                                                ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view, png = await vista_partida(interaction.client, self.pid, self.i, self.owner)
        await interaction.edit_original_response(view=view, attachments=[discord.File(png, "partida.png")] if png else [])


def _perdidos(xs) -> str:
    u = list(dict.fromkeys(xs or []))
    return f", el rival tomó {', '.join(OBJ.get(x, x) for x in u)}" if u else ""


async def vista_partida(bot, pid: str, i: int, owner: int) -> tuple[discord.ui.LayoutView, io.BytesIO | None]:
    """La partida i (0 = la última) de la persona: la curva, sus muertes con lo que costaron y el momento clave."""
    from bot.services import graficos
    datos = bot.datos
    h = await datos.historial(pid, i // POR_PAGINA + 1) or {}
    lista = h.get("partidas") or []
    total = (h.get("paginas") or 1) * POR_PAGINA
    m = lista[i % POR_PAGINA] if i % POR_PAGINA < len(lista) else None
    perfil = await datos.perfil(pid) or {"nombre": pid}
    nombre = discord.utils.escape_markdown(perfil["nombre"])
    png = None
    if not m:
        texto = f"## {nombre}\nNo encontré esa partida en el historial."
    else:
        champs = await datos.campeones()
        champ = (champs.get(str(m["champ"])) or {}).get("nombre", m["champ"])
        cab = (f"## {nombre} · {'✅ Victoria' if m['win'] else '❌ Derrota'} con {champ}\n"
               f"-# {m['rol'] or ''} · {m['k']}/{m['d']}/{m['a']} · {F.num(m.get('dur'), 0)} min · partida {i + 1} del historial")
        d = await datos.partida(m["id"])
        if not d:
            texto = cab + "\nEsta partida no tiene timeline: no hay gráfico."
        else:
            lado = d["lados"].get(pid, "azul")
            eq = 100 if lado == "azul" else 200
            lineas = [cab]
            k = d.get("clave")
            if k:
                dv = k["delta"] if lado == "azul" else -k["delta"]
                ev = [e for e in d["eventos"] if k["min"] - 1 < e["min"] <= k["min"] and (e["tipo"] in OBJ or e["tipo"] == "muerte")]
                que = ", ".join("tu muerte" if e["tipo"] == "muerte" and e.get("persona") == pid else
                                "una muerte de alguien del grupo" if e["tipo"] == "muerte" else
                                f"{'tu equipo tomó' if e.get('equipo') == eq else 'el rival tomó'} {OBJ.get(e['tipo'], e['tipo'])}"
                                for e in ev) or "peleas y oro"
                lineas.append(f"El minuto que más pesó fue el **{k['min']}**: **{'+' if dv > 0 else '−'}"
                              f"{F.num(abs(dv) * 100, 0)} pts** ({que}).")
            muertes = sorted((e for e in d["eventos"] if e["tipo"] == "muerte" and e.get("persona") == pid),
                             key=lambda e: -e["costo"])
            if muertes:
                lineas.append("**Tus muertes más caras:** " + " · ".join(
                    f"min {F.num(e['min'], 0)}: −{F.num(e['costo'] * 100, 0)} pts{_perdidos(e.get('perdidos'))}"
                    for e in muertes[:3]))
            lineas.append("-# Probabilidad de ganar de tu equipo minuto a minuto (modelo de la web, Guías). "
                          "Rojo: tus muertes, más grande = más costó.")
            texto = "\n".join(lineas)
            png = graficos.curva_partida(d, pid, f"{perfil['nombre']} · {champ} · {'victoria' if m['win'] else 'derrota'}")
    items: list[discord.ui.Item] = [discord.ui.TextDisplay(texto[:3900])]
    if png:
        items.append(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://partida.png")))
    items.append(discord.ui.ActionRow(
        PartidaBoton(pid, i + 1, owner, "a", disabled=i + 1 >= total),
        PartidaBoton(pid, max(i - 1, 0), owner, "b", disabled=i == 0),
        discord.ui.Button(label="Ver en la web", url=f"{WEB}#/jugadores/{pid}/partidas")))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=0x00CCCC))
    return view, png
