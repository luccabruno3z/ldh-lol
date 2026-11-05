"""-pool: la pool objetivo de cada rol, armada en el Pool Designer de Machine LoLing y traída acá.

No copiamos nada de Machine LoLing (sus términos lo prohíben): el botón lleva a su sitio, cada uno arma la
pool allá y elige esos campeones acá. Lo nuestro es el seguimiento con tus partidas.

Los menús son DynamicItems (siguen andando después de un redeploy). Solo edita su pool quien está
vinculado a ese jugador; los demás la ven sin menús."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import discord

from bot.services import formato as F

from bot.cogs.perfil import WEB
from bot.services.metas import MAX_CAMPEONES

POOL_DESIGNER = "https://pooldesigner.machineloling.com/"
ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")
EN_MODO = {"solo": "solo/dúo", "normal": "normales", "todo": "todas las colas"}


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def buscar_campeon(campeones: dict, texto: str) -> int | None:
    """Por nombre o key de Data Dragon, sin tildes ni espacios ("kai'sa", "kaisa", "mf" no)."""
    t = normalizar(texto)
    if not t:
        return None
    for criterio in (lambda n: n == t, lambda n: n.startswith(t)):
        for cid, c in campeones.items():
            if criterio(normalizar(c["nombre"])) or criterio(normalizar(c["key"])):
                return int(cid)
    return None


def _nombre(campeones: dict, cid: int) -> str:
    return (campeones.get(str(cid)) or {}).get("nombre", str(cid))


def _pct(x: dict | None) -> str:
    if not x or x.get("v") is None:
        return "—"
    if x.get("lo") is None:
        return f"{x['v'] * 100:.0f} %"
    return f"{x['v'] * 100:.0f} % ({x['lo'] * 100:.0f}–{x['hi'] * 100:.0f})"


def _seguimiento(seg: dict | None, decl: dict, campeones: dict) -> list[str]:
    """Lo publicado por el pipeline, solo si es la misma pool que está declarada ahora."""
    if not seg or sorted(seg.get("campeones") or []) != sorted(decl["campeones"]) or seg.get("desde") != decl["desde"]:
        return ["-# El seguimiento se calcula en la próxima actualización de los datos."]
    modos = seg.get("modos") or {}
    modo = max(modos, key=lambda m: (modos[m]["n_despues"] >= 10, m == "solo", modos[m]["n_despues"]), default=None)
    if not modo:
        return ["-# Todavía no hay partidas en este rol."]
    x = modos[modo]
    c, dd, ad = x["cumplimiento"], x["desde_que_la_declaraste"], x["antes_y_despues"]
    lin = [f"### Seguimiento en {EN_MODO.get(modo, modo)}",
           f"**Cumplimiento:** {c['v'] * 100:.0f} % de tus últimas {F.partidas(c['n'])} del rol "
           f"({c['lo'] * 100:.0f}–{c['hi'] * 100:.0f})" if c.get("v") is not None else "**Cumplimiento:** sin partidas"]
    if dd["dentro"]["n"] or dd["fuera"]["n"]:
        p = f" · p = {dd['p']:.3f}".replace(".", ",") if dd.get("p") is not None else ""
        lin.append(f"**Desde que la declaraste:** con la pool {_pct(dd['dentro'])} en {dd['dentro']['n']}, "
                   f"fuera {_pct(dd['fuera'])} en {dd['fuera']['n']}{p}"
                   + (" · muestra chica" if dd.get("muestra_chica") else ""))
    if ad["prop_antes"]["n"] and ad["prop_despues"]["n"]:
        lin.append(f"**Cuánto la jugás:** antes {_pct(ad['prop_antes'])} de {ad['prop_antes']['n']}, "
                   f"después {_pct(ad['prop_despues'])} de {ad['prop_despues']['n']}"
                   + (" · muestra chica" if ad.get("muestra_chica") else ""))
    filas = []
    for ch in x["campeones"]:
        idx = ch["indice"]
        filas.append(f"• {_nombre(campeones, ch['champ'])}: {F.partidas(ch['n'])} · {_pct(ch['winrate'])}"
                     + (f" · nota de partida {idx['v']:.0f}" if idx.get("v") is not None else "") + f" · {ch['estado']}")
    lin += filas
    lin.append("-# Son asociaciones: también pesan el parche, los rivales y tu práctica. Nota de partida: 50 = la mediana de tu franja.")
    return lin


class SelectorPool(discord.ui.DynamicItem[discord.ui.Select],
                   template=r"lp:(?P<pid>[A-Za-z0-9_-]+):(?P<rol>[A-Za-z]+):(?P<owner>\d+):(?P<clave>rol|champs)"):
    def __init__(self, pid: str, rol: str, owner: int, clave: str, opciones: list[discord.SelectOption] | None = None,
                 maximo: int = 1, minimo: int = 1, placeholder: str | None = None):
        self.pid, self.rol, self.owner, self.clave = pid, rol, owner, clave
        super().__init__(discord.ui.Select(custom_id=f"lp:{pid}:{rol}:{owner}:{clave}"[:100], placeholder=placeholder,
                                           min_values=minimo, max_values=maximo,
                                           options=opciones or [discord.SelectOption(label="-")]))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["pid"], match["rol"], int(match["owner"]), match["clave"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message("Esta tarjeta la abrió otra persona. Abrí la tuya con `-pool`.", ephemeral=True)
        return False

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        rol, aviso = self.rol, None
        if self.clave == "rol":
            rol = self.item.values[0]
        else:
            if not puede_editar(bot, interaction.user.id, self.pid):
                await interaction.response.send_message("Solo podés cambiar tu propia pool.", ephemeral=True)
                return
            await interaction.response.defer()
            ok = await bot.metas.guardar(self.pid, rol, [int(v) for v in self.item.values])
            aviso = None if ok else "No pude subirla a GitHub: quedó guardada en el bot y se reintenta en el próximo cambio."
        if not interaction.response.is_done():
            await interaction.response.defer()
        await interaction.edit_original_response(view=await tarjeta_pool(bot, self.pid, rol, self.owner, aviso))


class BorrarPool(discord.ui.DynamicItem[discord.ui.Button],
                 template=r"lpb:(?P<pid>[A-Za-z0-9_-]+):(?P<rol>[A-Za-z]+):(?P<owner>\d+)"):
    def __init__(self, pid: str, rol: str, owner: int):
        self.pid, self.rol, self.owner = pid, rol, owner
        super().__init__(discord.ui.Button(label=f"Borrar la pool de {rol}", style=discord.ButtonStyle.danger,
                                           custom_id=f"lpb:{pid}:{rol}:{owner}"[:100]))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["pid"], match["rol"], int(match["owner"]))

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        if interaction.user.id != self.owner or not puede_editar(bot, interaction.user.id, self.pid):
            await interaction.response.send_message("Solo podés cambiar tu propia pool.", ephemeral=True)
            return
        await interaction.response.defer()
        ok = await bot.metas.guardar(self.pid, self.rol, [])
        aviso = None if ok else "No pude subirlo a GitHub: quedó en el bot y se reintenta en el próximo cambio."
        await interaction.edit_original_response(view=await tarjeta_pool(bot, self.pid, self.rol, self.owner, aviso))


def puede_editar(bot, user_id: int, pid: str) -> bool:
    perfil = bot.get_cog("Perfil")
    return bool(perfil) and perfil.vinculos.get(str(user_id)) == pid


async def rol_por_defecto(bot, pid: str) -> str:
    """El primer rol con pool declarada; si no hay, el rol más jugado."""
    pools = bot.metas.pool(pid)
    for r in ROLES:
        if r in pools:
            return r
    roles = (await bot.datos.roles(pid) or {}).get("tabla") or []
    todo = [t for t in roles if t["cola"] == "todo"] or roles
    return max(todo, key=lambda t: t["n"])["rol"] if todo else "Mid"


async def tarjeta_pool(bot, pid: str, rol: str, owner: int, aviso: str | None = None) -> discord.ui.LayoutView:
    datos = bot.datos
    p = await datos.perfil(pid) or {"id": pid, "nombre": pid}
    campeones = await datos.campeones()
    decl = bot.metas.pool(pid).get(rol)
    editable = puede_editar(bot, owner, pid)
    nombre = discord.utils.escape_markdown(p["nombre"])

    lin = [f"## {nombre} · pool objetivo · {rol}"]
    if aviso:
        lin.append(f"⚠️ {aviso}")
    if decl:
        desde = datetime.fromisoformat(decl["desde"].replace("Z", "+00:00")).strftime("%d/%m/%Y")
        lin.append(f"**Tu pool:** {', '.join(_nombre(campeones, c) for c in decl['campeones'])} · desde el {desde}")
        seg = ((await datos.pool_objetivo(pid)) or {}).get("roles", {}).get(rol)
        lin += _seguimiento(seg, decl, campeones)
    else:
        lin.append("Todavía no declaraste una pool para este rol.")
    if editable:
        lin.append(f"-# Armala en el Pool Designer de Machine LoLing y elegí esos campeones en el menú (hasta "
                   f"{MAX_CAMPEONES}). Si alguno no aparece: `-pool agregar <campeón> {rol}`. Cambiar la pool reinicia "
                   "el seguimiento desde ese día.")

    items: list[discord.ui.Item] = [discord.ui.TextDisplay("\n".join(lin)), discord.ui.Separator()]
    items.append(discord.ui.ActionRow(SelectorPool(pid, rol, owner, "rol", [
        discord.SelectOption(label=r, value=r, default=r == rol,
                             description="con pool" if r in bot.metas.pool(pid) else None) for r in ROLES])))
    if editable:
        tabla = (await datos.campeones_de(pid) or {}).get("tabla") or []
        jugados = sorted((t for t in tabla if t["cola"] == "todo" and t["rol"] == rol), key=lambda t: -t["n"])
        ids = list(dict.fromkeys([*(decl or {}).get("campeones", []), *(t["champ"] for t in jugados)]))[:25]
        n_de = {t["champ"]: t["n"] for t in jugados}
        if ids:
            items.append(discord.ui.ActionRow(SelectorPool(
                pid, rol, owner, "champs", [discord.SelectOption(
                    label=_nombre(campeones, c), value=str(c), default=c in (decl or {}).get("campeones", []),
                    description=f"{n_de.get(c, 0)} partidas en {rol}") for c in ids],
                maximo=min(MAX_CAMPEONES, len(ids)), minimo=0, placeholder=f"Elegí tu pool de {rol}")))
    botones = [discord.ui.Button(label="Armala en Machine LoLing", url=POOL_DESIGNER),
               discord.ui.Button(label="Ver en la web", url=f"{WEB}#/jugadores/{pid}/campeones")]
    if editable and decl:
        botones.insert(1, BorrarPool(pid, rol, owner))
    items.append(discord.ui.ActionRow(*botones))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*items, accent_colour=0x00CCCC))
    return view
