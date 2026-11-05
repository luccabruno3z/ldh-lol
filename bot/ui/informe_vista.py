"""-informe: el informe de coaching que escribe Claude a pedido (datos/informes/<pid>.json, publicado en api/informes).

Las cifras no están en el texto: salen de las evidencias citadas, cada una con su intervalo y n. El botón
"Ver evidencia" es un DynamicItem (sigue andando después de un redeploy) y responde en privado; cualquiera puede
mirarla, porque es la misma que está en la web."""

from __future__ import annotations

import discord

from bot.cogs.perfil import WEB

TIPO = {"observacion": "observación", "asociacion": "asociación", "estimacion_modelo": "estimación del modelo",
        "contexto": "contexto"}
FASE = {"temprana": "antes del 14", "media": "del 14 al 25", "tardia": "después del 25"}
EN_MODO = {"solo": "solo/dúo", "normal": "normales", "todo": "todas las colas"}


def _ev(e: dict) -> str:
    extra = f" · {e['prueba']}" if e.get("prueba") else ""
    fases = " · ".join(f"{FASE.get(k, k)}: {v}" for k, v in (e.get("fases_fmt") or {}).items())
    mas = " · ".join(x for x in (e.get("por_partida_fmt"), e.get("con_objetivo_fmt"), fases) if x)
    return f"• {e['que']}: **{e.get('fmt') or '—'}**{extra}" + (f"\n  {mas}" if mas else "") + f"\n-# {TIPO.get(e['tipo'], e['tipo'])}" + (
        f" · {' '.join(x for x in e.get('limitaciones') or [] if x)}" if any(e.get("limitaciones") or []) else "")


class InformeBoton(discord.ui.DynamicItem[discord.ui.Button], template=r"li:(?P<pid>[A-Za-z0-9_-]+)"):
    def __init__(self, pid: str):
        self.pid = pid
        super().__init__(discord.ui.Button(label="Ver evidencia", custom_id=f"li:{pid}"[:100],
                                           style=discord.ButtonStyle.secondary))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["pid"])

    async def callback(self, interaction: discord.Interaction):
        d = await interaction.client.datos.informe(self.pid)
        if not d:
            await interaction.response.send_message("Ese informe ya no está publicado.", ephemeral=True)
            return
        ev = {e["id"]: e for e in d.get("evidencias") or []}
        partes = []
        for i, p in enumerate(d["prioridades"], 1):
            partes.append(f"### {i}. {p['titulo']}\n" + "\n".join(_ev(ev[x]) for x in p["evidencias"] if x in ev))
        for t in d.get("mantener") or []:
            if t.get("evidencias"):
                partes.append(f"### Mantener: {t['texto']}\n" + "\n".join(_ev(ev[x]) for x in t["evidencias"] if x in ev))
        texto = "\n".join(partes)
        await interaction.response.send_message(texto[:1990] + ("…" if len(texto) > 1990 else ""), ephemeral=True)


def tarjeta_informe(p: dict, d: dict | None) -> discord.ui.LayoutView:
    nombre = discord.utils.escape_markdown(p["nombre"])
    url = f"{WEB}#/jugadores/{p['id']}/coaching"
    view = discord.ui.LayoutView(timeout=None)
    if not d or not d.get("prioridades"):
        texto = (f"## {nombre} · informe\nTodavía no hay un informe de coaching. Lo escribe Claude a pedido: "
                 "pedíselo a Lucca. Mientras tanto, `-coaching` tiene tus números.")
        view.add_item(discord.ui.Container(discord.ui.TextDisplay(texto), discord.ui.ActionRow(
            discord.ui.Button(label="Ver en la web", url=url)), accent_colour=0x00CCCC))
        return view
    lineas = [f"## {nombre} · tu informe", f"-# {d['fecha']} · {EN_MODO.get(d['modo'], d['modo'])} · escrito por {d.get('autor', 'Claude')}",
              d.get("resumen", "")]
    for i, x in enumerate(d["prioridades"], 1):
        lineas += [f"### {i}. {x['titulo']}", x["observacion"],
                   f"**Puede ser porque** {x['posible_explicacion']}",
                   f"-# Falta ver: {x['falta_verificar']}",
                   f"**Para practicar:** {x['ejercicio']}",
                   f"-# Cómo revisarlo: {x['como_revisar']}"]
        ev = {e["id"]: e for e in d.get("evidencias") or []}
        lineas += [f"-# 🎬 {ev[m]['que']}" for m in x.get("momentos") or [] if m in ev]
    if d.get("mantener"):
        lineas.append("### Mantené\n" + "\n".join(f"• {t['texto']}" for t in d["mantener"]))
    if d.get("proxima_revision"):
        lineas.append(f"-# Próxima revisión: {d['proxima_revision']}")
    lineas.append("-# Las cifras están en **Ver evidencia**, cada una con su intervalo y n. Lo que dice \"puede ser\" "
                  "es una hipótesis para revisar en tus partidas, no un diagnóstico.")
    texto = "\n".join(l for l in lineas if l)
    if len(texto) > 3900:
        texto = texto[:3890] + "\n…"
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(texto), discord.ui.ActionRow(
        InformeBoton(p["id"]), discord.ui.Button(label="Ver en la web", url=url)), accent_colour=0x00CCCC))
    return view
