"""-perfil con pestañas (Resumen, Roles, Campeones, Coaching, Partidas) y, para quien tiene varias
cuentas, botones para ver cada una por separado (pedido de Khaleevee).

Los botones son DynamicItems, como en el bot de PR: el estado viaja en el custom_id, así que siguen
andando después de un redeploy. Solo quien abrió el perfil puede cambiar de pestaña.
"""

from __future__ import annotations

import discord

PESTANAS = {"resumen": "Resumen", "roles": "Roles", "campeones": "Campeones", "coaching": "Coaching",
            "partidas": "Partidas"}
LIMITE = 3900


def _cid(tab: str, vista: str, owner: int, pid: str, cuentas: bool = False) -> str:
    # La fila de cuentas lleva ":c": si no, "Todas las cuentas" repetía el id de la pestaña activa
    # (misma pestaña, misma vista) y Discord rechazaba el mensaje entero (perfiles con 2+ cuentas).
    return f"lp:{tab}:{vista}:{owner}:{pid}{':c' if cuentas else ''}"[:100]


def _texto(view: discord.ui.LayoutView) -> str:
    """El texto de una tarjeta ya armada (se reusan las tarjetas de cada comando)."""
    return "\n\n".join(i.content for i in view.walk_children() if isinstance(i, discord.ui.TextDisplay))


class PerfilBoton(discord.ui.DynamicItem[discord.ui.Button],
                  template=r"lp:(?P<tab>[a-z]+):(?P<vista>[a-z0-9]+):(?P<owner>\d+):(?P<pid>[A-Za-z0-9_-]+)(?P<c>:c)?"):
    def __init__(self, tab: str, vista: str, owner: int, pid: str, *, label: str, activo: bool = False,
                 cuentas: bool = False):
        self.tab, self.vista, self.owner, self.pid = tab, vista, owner, pid
        super().__init__(discord.ui.Button(
            label=label[:80], custom_id=_cid(tab, vista, owner, pid, cuentas),
            style=discord.ButtonStyle.primary if activo else discord.ButtonStyle.secondary))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["tab"], match["vista"], int(match["owner"]), match["pid"], label=item.label or "",
                   cuentas=bool(match["c"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message("Este perfil lo abrió otra persona. Abrí el tuyo con `-perfil`.",
                                                ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = await render(interaction.client, self.pid, self.tab, self.vista, self.owner)
        await interaction.edit_original_response(view=view)


async def _cuerpo(bot, p: dict, tab: str, cuenta: dict | None) -> str:
    """El texto de la pestaña. Con cuenta, todo sale de las partidas de esa cuenta sola."""
    from bot.cogs import coaching as co
    from bot.cogs.perfil import tarjeta_campeones, tarjeta_roles

    datos = bot.datos
    nc = (await datos.ajustes()).get("nombres_cola", {})
    if tab == "resumen":
        hist = {"partidas": cuenta["historial"]} if cuenta else None
        return _texto(await bot.get_cog("Perfil")._tarjeta(p, hist=hist))
    if tab == "roles":
        d = cuenta["roles"] if cuenta else await datos.roles(p["id"])
        return _texto(tarjeta_roles(p, d, nc)) if d else "Sin datos de roles."
    if tab == "campeones":
        d = cuenta["campeones"] if cuenta else await datos.campeones_de(p["id"])
        return _texto(tarjeta_campeones(p, d, await datos.campeones(), nc)) if d else "Sin datos de campeones."
    if tab == "coaching":
        if cuenta:
            return ("## Coaching\nEl coaching necesita muestra y una franja por rango: se calcula con todas tus "
                    "cuentas juntas. Tocá **Todas las cuentas** para verlo.")
        d = await datos.coaching_auto(p["id"])
        if not d:
            return "Todavía no hay coaching publicado."
        perf, mejora = _texto(co.tarjeta_performance(p, d, None)), _texto(co.tarjeta_mejora(p, d, None))
        # Sin referencia, las dos tarjetas dicen lo mismo: se muestra una sola vez.
        pie = "\n\n-# Para elegir rol, modo (solo/dúo, normales o todo) y gráficos con menús: `-coaching`."
        return (perf if perf == mejora else f"{perf}\n\n{mejora}") + pie
    # partidas
    partidas = cuenta["historial"] if cuenta else ((await datos.historial(p["id"], 1)) or {}).get("partidas", [])
    champs = await datos.campeones()
    lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · últimas partidas"]
    for m in partidas[:12]:
        champ = (champs.get(str(m["champ"])) or {}).get("nombre", m["champ"])
        lp = m.get("lp") or {}
        lp_txt = f" · {'+' if (lp.get('delta') or 0) > 0 else ''}{lp['delta']} LP" if lp.get("exacto") else ""
        lineas.append(f"{'✅' if m['win'] else '❌'} **{champ}** {m['rol'] or ''} · {m['k']}/{m['d']}/{m['a']} · "
                      f"{nc.get(m['cola'], m['cola'])}{lp_txt}")
    if not partidas:
        lineas.append("Sin partidas todavía.")
    return "\n".join(lineas)


async def render(bot, pid: str, tab: str = "resumen", vista: str = "t", owner: int = 0) -> discord.ui.LayoutView:
    from bot.cogs.perfil import COLORES, WEB

    datos = bot.datos
    base = await datos.perfil(pid)
    p, cuenta = base, None
    if vista != "t":
        cuenta = await datos.cuenta(pid, int(vista))
        if cuenta:
            p = {**base, "cuentas": [{"riot_id": cuenta["riot_id"]}], "rango": cuenta["rango"], "n": cuenta["n"],
                 "kpis": {"todas": cuenta["kpis"]}, "forma": cuenta["forma"]}
        else:
            vista = "t"
    texto = await _cuerpo(bot, p, tab, cuenta)
    if len(texto) > LIMITE:
        texto = texto[:LIMITE - 10] + "\n…"

    items: list[discord.ui.Item] = [discord.ui.TextDisplay(texto), discord.ui.Separator()]
    items.append(discord.ui.ActionRow(*[PerfilBoton(t, vista, owner, pid, label=l, activo=t == tab)
                                        for t, l in PESTANAS.items()]))
    vistas = base.get("vistas_cuenta") or []
    if vistas:
        botones = [PerfilBoton(tab, "t", owner, pid, label="Todas las cuentas", activo=vista == "t", cuentas=True)]
        botones += [PerfilBoton(tab, str(v["indice"]), owner, pid, label=f"{v['riot_id']} ({v['n']})",
                                activo=vista == str(v["indice"]), cuentas=True) for v in vistas[:4]]
        items.append(discord.ui.ActionRow(*botones))
    items.append(discord.ui.ActionRow(discord.ui.Button(label="Ver en la web", url=f"{WEB}#/jugadores/{pid}")))

    rangos = [c.get("solo") for c in (p.get("rango") or {}).values() if c.get("solo")]
    mejor = max(rangos, key=lambda r: r.get("valor") or -1, default=None)
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=COLORES.get((mejor or {}).get("tier"), 0x00CCCC)))
    return view
