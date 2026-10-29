"""Coaching (fase 3): Performance, plan de mejora y primeros 15 minutos. Mismos JSON que la web
(api/coaching/<id>.json); los percentiles son contra la franja de rango y el rol en solo/dúo."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.cogs.perfil import WEB, tarjeta_simple
from bot.cogs.rankings import ROLES


def _num(x: float | None, dec: int = 0, signo: bool = False) -> str:
    if x is None:
        return "—"
    s = f"{x:+.{dec}f}" if signo else f"{x:.{dec}f}"
    return s.replace(".", ",")


def _val(m: dict, x: float | None) -> str:
    return _num(x, m.get("dec", 2), signo=m.get("clave", "").startswith("dif")) + (f" {m['unidad']}" if m.get("unidad") else "")


def _jugador_y_rol(texto: str | None) -> tuple[str | None, str | None]:
    """'-mejora seagranda jungla' → ('seagranda', 'Jungla'). El rol va al final y es opcional."""
    if not texto:
        return None, None
    partes = texto.split()
    if ROLES.get(partes[-1].lower()):
        return (" ".join(partes[:-1]) or None), ROLES[partes[-1].lower()]
    return texto, None


def _rol(d: dict, pedido: str | None) -> tuple[str | None, dict | None]:
    rol = pedido or d.get("rol_principal")
    return rol, (d.get("roles") or {}).get(rol)


def _sin_dato(p: dict, d: dict, rol: str | None, r: dict | None) -> list[str] | None:
    nombre = discord.utils.escape_markdown(p["nombre"])
    if not d.get("franja"):
        return [f"## {nombre}", "Sin rango de solo/dúo: no hay franja contra la cual compararte."]
    if r is None:
        roles = ", ".join(d.get("roles") or {}) or "ninguno"
        return [f"## {nombre}", f"No tenés 10+ partidas de solo/dúo en {rol or 'ningún rol'}. Roles con muestra: {roles}."]
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
    lineas = [f"## {discord.utils.escape_markdown(p['nombre'])} · {rol} en solo/dúo",
              f"Performance **{_num(pf['v'] * 100)}**/100 ({_num(pf['lo'] * 100)}–{_num(pf['hi'] * 100)}) "
              f"contra {d['franja']} · n={r['n']}, confianza {r['confianza']}"]
    if pf.get("como"):
        lineas.append(f"Rendís como un **{pf['como']}** típico" +
                      (f" (también podría ser {' o '.join(pf['pisan'])})" if pf["pisan"] else "") + ".")
    for c in r["componentes"]:
        nivel = "sin dato" if c["sin_dato"] else f"{_num(c['nivel'] * 100)} ({_num(c['lo'] * 100)}–{_num(c['hi'] * 100)})"
        lineas.append(f"**{c['nombre']}** {nivel} · peso {_num(c['peso'] * 100)} · puede sumar {_num(c['margen'] * 100, 1)}")
    lineas.append(f"-# Percentiles contra {r['n_ref']} jugadores de {d['franja']} en {rol}. 50 = la mitad de tu franja.")
    return tarjeta_simple(lineas, url)


def tarjeta_mejora(p: dict, d: dict, pedido: str | None) -> discord.ui.LayoutView:
    rol, r = _rol(d, pedido)
    url = f"{WEB}#/jugadores/{p['id']}"
    if (aviso := _sin_dato(p, d, rol, r)):
        return tarjeta_simple(aviso, url)
    lineas = [f"## Plan de mejora · {discord.utils.escape_markdown(p['nombre'])} · {rol}"]
    # Las 3 brechas más grandes contra la franja: las métricas con el percentil más bajo y su intervalo entero abajo.
    for i, m in enumerate(r["mejorar"][:3], 1):
        lineas.append(f"**{i}. {m['nombre']}**: subir de {_val(m, m['v'])} a {_val(m, m['mediana'])} "
                      f"(mediana de {d['franja']}; hoy mejor que el {round(m['pct'] * 100)} %)")
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
    return tarjeta_simple(lineas, url)


def tarjeta_temprano(p: dict, d: dict, pedido: str | None) -> discord.ui.LayoutView:
    url = f"{WEB}#/jugadores/{p['id']}"
    solo = (d.get("temprano") or {}).get("solo") or {}
    rol = pedido or d.get("rol_principal") or max(solo, key=lambda k: solo[k]["n"], default=None)
    t = solo.get(rol)
    nombre = discord.utils.escape_markdown(p["nombre"])
    if not t:
        return tarjeta_simple([f"## {nombre}", f"Menos de 10 partidas de solo/dúo en {rol or 'ningún rol'}."], url)
    ref = ((d.get("roles") or {}).get(rol) or {}).get("metricas") or {}
    lineas = [f"## {nombre} · primeros 15 minutos · {rol} en solo/dúo (n={t['n']})"]
    for k, m in t["metricas"].items():
        mm = {**m, "clave": k}
        extra = f" · mejor que el {round(ref[k]['pct'] * 100)} % de {d['franja']}" if k in ref else ""
        ic = f" ({_val(mm, m['lo'])} a {_val(mm, m['hi'])})" if m.get("lo") is not None else ""
        lineas.append(f"**{m['nombre']}** {_val(mm, m['v'])}{ic}{extra}")
    lin = t["linea"]
    if lin["gana"]["n"] and lin["pierde"]["n"]:
        lineas.append(f"Vas arriba a los 15 en {round(lin['pct_gana']['v'] * 100)} % de las partidas. "
                      f"Arriba ganás {round(lin['gana']['v'] * 100)} % (n={lin['gana']['n']}); "
                      f"abajo, {round(lin['pierde']['v'] * 100)} % (n={lin['pierde']['n']}). Fisher p = {_num(lin['p'], 3)}")
    lineas.append("-# Diferencias contra el rival directo de la misma partida.")
    return tarjeta_simple(lineas, url)


class Coaching(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _cargar(self, ctx: commands.Context, texto: str | None, comando: str):
        jugador, rol = _jugador_y_rol(texto)
        p = await self.bot.get_cog("Perfil")._persona(ctx, jugador, comando)
        if not p:
            return None, None, None
        d = await self.bot.datos.coaching(p["id"])
        if not d:
            await ctx.reply("Todavía no hay coaching publicado para este jugador.")
            return None, None, None
        return p, d, rol

    @commands.hybrid_command(name="performance", description="Performance y sus 7 componentes contra tu franja de rango")
    async def performance(self, ctx: commands.Context, *, jugador_y_rol: str | None = None):
        p, d, rol = await self._cargar(ctx, jugador_y_rol, "performance")
        if p:
            await ctx.reply(view=tarjeta_performance(p, d, rol))

    @commands.hybrid_command(name="mejora", description="Las 3 brechas más grandes contra tu franja, como metas en números")
    async def mejora(self, ctx: commands.Context, *, jugador_y_rol: str | None = None):
        p, d, rol = await self._cargar(ctx, jugador_y_rol, "mejora")
        if p:
            await ctx.reply(view=tarjeta_mejora(p, d, rol))

    @commands.hybrid_command(name="temprano", description="CS, oro y XP a los 10 y 15 contra tu rival directo")
    async def temprano(self, ctx: commands.Context, *, jugador_y_rol: str | None = None):
        p, d, rol = await self._cargar(ctx, jugador_y_rol, "temprano")
        if p:
            await ctx.reply(view=tarjeta_temprano(p, d, rol))


async def setup(bot: commands.Bot):
    await bot.add_cog(Coaching(bot))
