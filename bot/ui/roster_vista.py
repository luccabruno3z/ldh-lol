"""-roster: la tarjeta de un roster premade (fase 7) con sus métricas de proceso y menús de roster y período.
Los menús son DynamicItems (el estado viaja en el custom_id), así que siguen andando después de un redeploy.
Es información del grupo: cualquiera puede usar los menús."""

from __future__ import annotations

import discord

from bot.cogs.perfil import WEB
from bot.services import formato as F

VENTANAS = {"semana": "Última semana", "mes": "Últimas 4 semanas", "temporada": "Temporada"}
MIN = 10  # el umbral de muestra chica de todo el sitio
COLA = {"flex": "Flex", "normal": "Normal"}


def _valor(k: str, x: dict | None, meta: dict) -> str:
    if not x or x.get("v") is None:
        return "—"
    if meta["tipo"] == "prop" or k == "objetivos":
        v, r = F.pct(x["v"]), F.rango_pct(x)
    else:
        dec = 2 if k == "vision" else 0 if k == "oro14" else 1
        v, r = F.num(x["v"], dec, k != "vision"), F.rango(x, dec, k != "vision")
    return f"{v} ({r})" if r else v


def _dif(k: str, x: dict | None, meta: dict) -> str:
    if not x or x.get("v") is None:
        return ""
    if x.get("nivel") == "muestra chica":
        return " · muestra chica"
    if meta["tipo"] == "prop" or k == "objetivos":
        txt = f"{F.pts(x['v'])} ({F.rango_pts(x)})"
    else:
        dec = 2 if k == "vision" else 0 if k == "oro14" else 1
        txt = f"{F.num(x['v'], dec, True)} ({F.rango(x, dec, True)})"
    nivel = x.get("nivel") or "ruido"
    return f" · en la temporada, contra la referencia {txt}, {'**señal**' if nivel == 'señal' else nivel}"


def texto_roster(d: dict, ventana: str) -> str:
    v = d["ventanas"][ventana]
    nombre = discord.utils.escape_markdown(d["nombre"])
    lin = [f"## {nombre}", f"-# {F.partidas(d['partidas'])} juntos en Flex y Normales · {VENTANAS[ventana].lower()}: "
                           f"{F.partidas(v['n'])}"]
    plantel = " · ".join(f"{'**' if p['nucleo'] else ''}{discord.utils.escape_markdown(p['nombre'])}{'**' if p['nucleo'] else ''}"
                         f" ({p['rol'] or '—'}, {p['partidas']})" for p in d["plantel"])
    lin.append(f"**Plantel:** {plantel}")
    if v["n"] < MIN:
        cuantas = "Sin partidas en este período." if not v["n"] else f"Solo {F.partidas(v['n'])}:"
        lin.append(f"-# {cuantas} con menos de {MIN} los números cambian mucho.")
    for k, meta in d["metricas"].items():
        if k == "winrate":
            continue
        x = v["metricas"].get(k)
        lin.append(f"**{meta['nombre']}** ({meta['unidad']}): {_valor(k, x, meta)}"
                   + (f", n = {x['n']}" if x and x.get("n") else "")
                   + _dif(k, d["contra_referencia"].get(k), meta))
    w = v["metricas"].get("winrate")
    if w and w.get("n"):
        lin.append(f"-# Winrate, solo como contexto: {_valor('winrate', w, d['metricas']['winrate'])}, n = {w['n']}.")
    fuera = [(k, x) for k, x in d["contra_referencia"].items() if x.get("nivel") in ("señal", "a confirmar")]
    if fuera:
        lin.append("**Para mirar:** " + "; ".join(
            f"{d['metricas'][k]['nombre'].lower()} {'más alto' if x['v'] > 0 else 'más bajo'} que la referencia ({x['nivel']})"
            for k, x in fuera) + ". Es una comparación, no la causa.")
    else:
        lin.append("**Para mirar:** en la temporada ninguna métrica se separa de la referencia.")
    lin.append(f"-# Referencia: las demás partidas de Flex y Normales del grupo ({d['referencia']['n']}). La comparación es "
               "siempre de la temporada, con BH sobre todos los rosters. Placas: solo antes del 14.")
    return "\n".join(lin)


class SelectorRoster(discord.ui.DynamicItem[discord.ui.Select],
                     template=r"lr:(?P<rid>[A-Za-z0-9_-]+):(?P<ventana>[a-z]+):(?P<clave>rid|ventana)"):
    def __init__(self, rid: str, ventana: str, clave: str, opciones: list[discord.SelectOption] | None = None):
        self.rid, self.ventana, self.clave = rid, ventana, clave
        super().__init__(discord.ui.Select(custom_id=f"lr:{rid}:{ventana}:{clave}"[:100],
                                           options=opciones or [discord.SelectOption(label="-")]))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["rid"], match["ventana"], match["clave"])

    async def callback(self, interaction: discord.Interaction):
        estado = {"rid": self.rid, "ventana": self.ventana, self.clave: self.item.values[0]}
        await interaction.response.defer()
        await interaction.edit_original_response(view=await vista_roster(interaction.client, estado["rid"], estado["ventana"]))


async def vista_roster(bot, rid: str | None, ventana: str = "temporada") -> discord.ui.LayoutView:
    idx = (await bot.datos.rosters()).get("rosters") or []
    view = discord.ui.LayoutView(timeout=None)
    if not idx:
        view.add_item(discord.ui.Container(discord.ui.TextDisplay(
            "Todavía no hay rosters: hacen falta 10 partidas de Flex o Normales con 4 o más del mismo grupo juntos."),
            accent_colour=0x00CCCC))
        return view
    rid = rid if any(r["id"] == rid for r in idx) else idx[0]["id"]
    ventana = ventana if ventana in VENTANAS else "temporada"
    d = await bot.datos.roster(rid)
    texto = texto_roster(d, ventana) if d else "No encontré ese roster."
    items: list[discord.ui.Item] = [discord.ui.TextDisplay(texto[:3900]), discord.ui.Separator()]
    if len(idx) > 1:
        items.append(discord.ui.ActionRow(SelectorRoster(rid, ventana, "rid", [
            discord.SelectOption(label=r["nombre"][:100], value=r["id"], description=F.partidas(r["partidas"]),
                                 default=r["id"] == rid) for r in idx[:25]])))
    items.append(discord.ui.ActionRow(SelectorRoster(rid, ventana, "ventana", [
        discord.SelectOption(label=l, value=k, default=k == ventana,
                             description=F.partidas(d["ventanas"][k]["n"]) if d else None) for k, l in VENTANAS.items()])))
    items.append(discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=f"{WEB}#/equipos/rosters")))
    view.add_item(discord.ui.Container(*items, accent_colour=0x00CCCC))
    return view
