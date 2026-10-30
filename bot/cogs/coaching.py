"""Coaching (fase 3): Performance, plan de mejora y primeros 15 minutos. Mismos JSON que la web
(api/coaching/[modo/]<id>.json). Los percentiles son contra ranked solo/dúo de la franja y el rol; el modo
(solo, normal o todo) elige qué partidas de la persona entran."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.cogs.perfil import WEB, tarjeta_simple
from bot.cogs.rankings import ROLES
from bot.services import formato as F


def _num(x: float | None, dec: int = 0, signo: bool = False) -> str:
    return F.num(x, dec, signo)


def _val(m: dict, x: float | None) -> str:
    return _num(x, m.get("dec", 2), signo=m.get("clave", "").startswith("dif")) + (f" {m['unidad']}" if m.get("unidad") else "")


MODOS = {"solo": "solo", "soloq": "solo", "normal": "normal", "normales": "normal", "todo": "todo", "todas": "todo"}
EN_MODO = {"solo": "solo/dúo", "normal": "normales", "todo": "todas las colas"}


def _jugador_rol_modo(texto: str | None) -> tuple[str | None, str | None, str | None]:
    """'-mejora seagranda jungla normal' → ('seagranda', 'Jungla', 'normal'). Rol y modo van al final,
    en cualquier orden, y son opcionales."""
    partes = (texto or "").split()
    rol = modo = None
    while partes:
        w = partes[-1].lower()
        if not rol and ROLES.get(w):
            rol = ROLES[w]
        elif not modo and w in MODOS:
            modo = MODOS[w]
        else:
            break
        partes.pop()
    return (" ".join(partes) or None), rol, modo


def _en(d: dict) -> str:
    return EN_MODO.get(d.get("modo") or "solo", "solo/dúo")


def _pie_modo(d: dict) -> list[str]:
    return [f"-# {d['nota_modo']}"] if d.get("nota_modo") else []


def _rol(d: dict, pedido: str | None) -> tuple[str | None, dict | None]:
    rol = pedido or d.get("rol_con_referencia") or d.get("rol_principal")
    return rol, (d.get("roles") or {}).get(rol)


def _sin_dato(p: dict, d: dict, rol: str | None, r: dict | None) -> list[str] | None:
    nombre = discord.utils.escape_markdown(p["nombre"])
    if not d.get("franja"):
        return [f"## {nombre}", "Sin rango de solo/dúo: no hay franja contra la cual compararte."]
    if r is None:
        roles = ", ".join(d.get("roles") or {}) or "ninguno"
        otro = "" if d.get("modo") == "todo" else " Probá con `todo` al final: junta solo/dúo, flex y normales."
        return [f"## {nombre}", f"No tenés 10+ partidas de {_en(d)} en {rol or 'ningún rol'}. Roles con muestra: {roles}.{otro}"]
    if r.get("sin_referencia"):
        return [f"## {nombre} · {rol}",
                f"La referencia de {d['franja']} en {rol} tiene {r['n_ref']} jugadores; hacen falta 20 para dar percentiles."]
    return None


def tarjeta_performance(p: dict, d: dict, pedido: str | None) -> discord.ui.LayoutView:
    rol, r = _rol(d, pedido)
    url = f"{WEB}#/jugadores/{p['id']}"
    if (aviso := _sin_dato(p, d, rol, r)):
        return tarjeta_simple(aviso, url)
    pf = r["performance"]
    lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · Performance",
              f"-# {rol} en {_en(d)} · {r['n']} partidas · contra {d['franja']}",
              f"# {_num(pf['v'] * 100)}/100",
              f"-# {F.rango(pf, 0, k=100)} · confianza {r['confianza']}"]
    # Solo contra la propia franja: "rendís como un X" sería estimar un rango (Riot prohíbe MMR/ELO).
    lado = ("por encima de" if pf["lo"] > 0.5 else "por debajo de" if pf["hi"] < 0.5 else "a la par de")
    lineas.append(f"Estás {lado} la mitad de los jugadores de {d['franja']} en {rol}.")
    lineas.append("### Componentes")
    for c in r["componentes"]:
        if c["sin_dato"]:
            lineas.append(f"**{c['nombre']}**: sin dato, cuenta como 50")
            continue
        lineas += [f"**{c['nombre']}**: {_num(c['nivel'] * 100)} · puede sumar {_num(c['margen'] * 100, 1)}",
                   f"-# {F.rango(c, 0, k=100)} · peso {_num(c['peso'] * 100)}"]
    lineas.append(f"-# Percentiles contra {r['n_ref']} jugadores de {d['franja']} en {rol}. 50 = la mitad de tu franja.")
    return tarjeta_simple(lineas + _pie_modo(d), url)


def tarjeta_mejora(p: dict, d: dict, pedido: str | None) -> discord.ui.LayoutView:
    rol, r = _rol(d, pedido)
    url = f"{WEB}#/jugadores/{p['id']}"
    if (aviso := _sin_dato(p, d, rol, r)):
        return tarjeta_simple(aviso, url)
    lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · plan de mejora", f"-# {rol} en {_en(d)} · contra {d['franja']}"]
    # Las 3 brechas más grandes contra la franja: las métricas con el percentil más bajo y su intervalo entero abajo.
    for i, m in enumerate(r["mejorar"][:3], 1):
        lineas += [f"\n**{i}. {m['nombre']}**: de {_val(m, m['v'])} a {_val(m, m['mediana'])}",
                   f"-# la meta es la mediana de {d['franja']} · hoy mejor que el {round(m['pct'] * 100)} %"]
        if m.get("consejo"):
            lineas.append(f"> {m['consejo']}")
        if m.get("nota"):
            lineas.append(f"-# {m['nota']}")
    if not r["mejorar"]:
        lineas.append("Ninguna métrica queda claramente abajo de tu franja. Lo que más puede sumar:")
        for s in r["sumar"]:
            meta = s.get("meta")
            if meta:
                lineas.append(f"**{s['nombre']}**: {meta['nombre'].lower()} de {_val(meta, meta['desde'])} a "
                              f"{_val(meta, meta['hasta'])} (mediana de {meta['franja']})")
            lineas.append(f"> {s['consejo']}")
    lineas.append("-# Solo entra una métrica si todo su intervalo de percentil queda abajo de 40.")
    return tarjeta_simple(lineas + _pie_modo(d), url)


def tarjeta_temprano(p: dict, d: dict, pedido: str | None) -> discord.ui.LayoutView:
    url = f"{WEB}#/jugadores/{p['id']}"
    del_modo = (d.get("temprano") or {}).get(d.get("modo") or "solo") or {}
    rol = pedido or d.get("rol_principal") or max(del_modo, key=lambda k: del_modo[k]["n"], default=None)
    t = del_modo.get(rol)
    nombre = discord.utils.escape_markdown(p["nombre"])
    if not t:
        return tarjeta_simple([f"## {nombre}", f"Menos de 10 partidas de {_en(d)} en {rol or 'ningún rol'}."], url)
    ref = ((d.get("roles") or {}).get(rol) or {}).get("metricas") or {}
    lineas = [f"## {nombre} · primeros 15 minutos", f"-# {rol} en {_en(d)} · {t['n']} partidas · contra el rival directo"]
    lin = t["linea"]
    if lin["gana"]["n"] and lin["pierde"]["n"]:
        # Lo más útil primero: si la partida se pierde en la línea o después.
        veredicto = "se separa del ruido" if lin["senal"] else "no se separa del ruido"
        lineas += [f"Vas arriba a los 15 en **{F.pct(lin['pct_gana']['v'])}** de las partidas.",
                   f"Arriba ganás **{F.pct(lin['gana']['v'])}** · abajo, **{F.pct(lin['pierde']['v'])}** ({veredicto})",
                   f"-# arriba {F.rango_pct(lin['gana'])} en {lin['gana']['n']} · abajo {F.rango_pct(lin['pierde'])} "
                   f"en {lin['pierde']['n']} · Fisher p = {_num(lin['p'], 3)}"]
    lineas.append("### Tus números")
    for k, m in t["metricas"].items():
        mm = {**m, "clave": k}
        extra = f" · mejor que el {round(ref[k]['pct'] * 100)} % de {d['franja']}" if k in ref else ""
        lineas += [f"**{m['nombre']}**: {_val(mm, m['v'])}{extra}",
                   f"-# {F.rango(m, m.get('dec', 0), k.startswith('dif'))}" if m.get("lo") is not None else None]
    return tarjeta_simple(lineas + _pie_modo(d), url)


class Coaching(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _abrir(self, ctx: commands.Context, texto: str | None, comando: str, vista: str):
        """La tarjeta con sus menús (qué ver, rol y modo): rol y modo escritos son solo el arranque."""
        from bot.ui.coaching_vista import responder
        jugador, rol, modo = _jugador_rol_modo(texto)
        p = await self.bot.get_cog("Perfil")._persona(ctx, jugador, comando)
        if not p:
            return
        await ctx.defer()
        await responder(ctx, self.bot, vista, p["id"], rol, modo)

    @commands.hybrid_command(name="performance", description="Performance y sus 7 componentes contra tu franja (con menús de rol y modo)")
    async def performance(self, ctx: commands.Context, *, jugador_rol_y_modo: str | None = None):
        await self._abrir(ctx, jugador_rol_y_modo, "performance", "perf")

    @commands.hybrid_command(name="mejora", description="Las brechas más grandes contra tu franja, como metas en números")
    async def mejora(self, ctx: commands.Context, *, jugador_rol_y_modo: str | None = None):
        await self._abrir(ctx, jugador_rol_y_modo, "mejora", "mejora")

    @commands.hybrid_command(name="temprano", description="CS, oro y XP a los 10 y 15 contra tu rival directo")
    async def temprano(self, ctx: commands.Context, *, jugador_rol_y_modo: str | None = None):
        await self._abrir(ctx, jugador_rol_y_modo, "temprano", "temp")

    @commands.hybrid_command(name="coaching", description="Todo tu coaching en una tarjeta: elegí qué ver, el rol y el modo con los menús")
    async def coaching(self, ctx: commands.Context, *, jugador_rol_y_modo: str | None = None):
        await self._abrir(ctx, jugador_rol_y_modo, "coaching", "perf")


async def setup(bot: commands.Bot):
    await bot.add_cog(Coaching(bot))
