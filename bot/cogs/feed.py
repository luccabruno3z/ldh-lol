"""Lo que más usan los bots de LoL para grupos de amigos (Scout, LP Tracker, Blitzcrank):

- Feed de partidas: cuando termina una partida de alguien del grupo, el resultado con su KDA y LP.
- Ascensos y descensos de división en solo/dúo.
- Competencias por fecha (-competencia) y el resumen del lunes con lo destacado de la semana.

El bot sigue sin llamar a Riot: lee recientes.json y personas.json, que publica la actualización.
Por eso el feed llega cuando corre la actualización, no en el momento exacto en que termina la partida.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from bot.cogs.perfil import TIERS, WEB, tarjeta_simple
from bot.services import formato as F
from bot.services.storage import JSONStorage

logger = logging.getLogger(__name__)
ARG = timezone(timedelta(hours=-3))
ORDEN_TIER = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"]
ORDEN_DIV = {"IV": 0, "III": 1, "II": 2, "I": 3}
COLAS = {"solo": "solo", "soloq": "solo", "flex": "flex", "normal": "normal", "normales": "normal", "todas": None}


def _valor(r: dict | None) -> int | None:
    if not r or r.get("tier") not in ORDEN_TIER:
        return None
    return ORDEN_TIER.index(r["tier"]) * 4 + ORDEN_DIV.get(r.get("division") or "IV", 0)


def _rango(r: dict) -> str:
    div = "" if r["tier"] in ("MASTER", "GRANDMASTER", "CHALLENGER") else f" {r['division']}"
    return f"{TIERS.get(r['tier'], r['tier'])}{div}"


def _fecha(texto: str, hoy: datetime) -> datetime | None:
    """'1/11', '01/11' o '1/11/2026' (hora argentina)."""
    try:
        partes = [int(x) for x in texto.replace("-", "/").split("/")]
        anio = partes[2] if len(partes) > 2 else hoy.year
        return datetime(anio, partes[1], partes[0], tzinfo=ARG)
    except (ValueError, IndexError):
        return None


def tabla_competencia(filas: list[dict], nombres: dict, desde: datetime, hasta: datetime, cola: str | None,
                      titulo: str, minimo: int = 5) -> list[str]:
    """Una línea por persona: partidas, winrate con su intervalo y LP. Con menos de `minimo`, al final."""
    d_ms, h_ms = desde.timestamp() * 1000, hasta.timestamp() * 1000
    por = defaultdict(list)
    for f in filas:
        if d_ms <= f["t"] < h_ms and (cola is None or f["c"] == cola):
            por[f["p"]].append(f)
    if not por:
        return [titulo, "Nadie jugó en esas fechas."]
    filas_t = []
    for pid, g in por.items():
        n, w = len(g), sum(x["w"] for x in g)
        lps = [x["lp"] for x in g if x["lp"] is not None]
        filas_t.append({"pid": pid, "n": n, "w": w, "wr": (w + 5) / (n + 10), "lp": sum(lps) if lps else None,
                        "n_lp": len(lps)})
    # Ordenado por winrate ajustado (como los rankings); la muestra chica va al final.
    grandes = sorted((x for x in filas_t if x["n"] >= minimo), key=lambda x: -x["wr"])
    chicas = sorted((x for x in filas_t if x["n"] < minimo), key=lambda x: -x["n"])
    lineas = [titulo, f"-# {desde:%d/%m} al {(hasta - timedelta(days=1)):%d/%m} · winrate ajustado · mínimo {minimo} partidas"]
    for i, x in enumerate(grandes[:10], 1):
        lp = f" · {F.num(x['lp'], 0, True)} LP en {x['n_lp']}" if x["lp"] is not None else ""
        lineas.append(f"`{i}.` **{nombres.get(x['pid'], x['pid'])}** · {F.pct(x['wr'])} · {x['w']}V {x['n'] - x['w']}D{lp}")
    if chicas:
        lineas.append("-# Muestra chica: " + ", ".join(f"{nombres.get(x['pid'], x['pid'])} ({x['n']})" for x in chicas))
    lineas.append("-# El LP solo cuenta las partidas con LP exacto (una partida entre dos actualizaciones).")
    return lineas


class Feed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.estado = JSONStorage("feed.json")  # {"vistos": [...], "rangos": {pid: valor}}
        self.vigilar.start()

    def cog_unload(self):
        self.vigilar.cancel()

    @property
    def datos(self):
        return self.bot.datos

    def _canales(self, clave: str) -> list[discord.abc.Messageable]:
        extra = self.bot.get_cog("Extra")
        if not extra:
            return []
        ids = [c.get(clave) for c in extra.canales.all().values() if c.get(clave)]
        return [ch for ch in (self.bot.get_channel(i) for i in ids) if ch]

    @commands.hybrid_command(name="canal_feed", description="Canal donde se publican las partidas del grupo y los ascensos")
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    async def canal_feed(self, ctx: commands.Context, canal: discord.TextChannel | None = None):
        self.bot.get_cog("Extra")._config(ctx.guild.id, "feed", canal.id if canal else None)
        await ctx.reply(f"Listo: las partidas del grupo y los ascensos se publican en {canal.mention}." if canal
                        else "Listo: ya no se publica el feed.")

    @commands.hybrid_command(name="competencia", description="Quién rindió mejor entre dos fechas: -competencia 1/11 30/11 solo")
    async def competencia(self, ctx: commands.Context, desde: str, hasta: str | None = None, cola: str = "solo"):
        hoy = datetime.now(ARG)
        d = _fecha(desde, hoy)
        h = (_fecha(hasta, hoy) + timedelta(days=1)) if hasta else hoy + timedelta(days=1)
        if not d or not h or h <= d or cola.lower() not in COLAS:
            await ctx.reply("Uso: `-competencia <desde dd/mm> [hasta dd/mm] [solo|flex|normal|todas]`", ephemeral=True)
            return
        await ctx.defer()
        nombres = {p["id"]: p["nombre"] for p in await self.datos.personas()}
        c = COLAS[cola.lower()]
        nc = (await self.datos.ajustes()).get("nombres_cola", {})
        lineas = tabla_competencia(await self.datos.partidas_resumen(), nombres, d, h, c,
                                   f"## Competencia · {nc.get(c, 'todas las colas') if c else 'todas las colas'}")
        await ctx.reply(view=tarjeta_simple(lineas, WEB))

    async def destacados_semana(self) -> list[str]:
        """Para el resumen del lunes: quién más LP sumó, quién más jugó y la mejor racha de la semana."""
        hasta = datetime.now(ARG)
        desde = hasta - timedelta(days=7)
        filas = [f for f in await self.datos.partidas_resumen()
                 if f["t"] >= desde.timestamp() * 1000 and f["c"] == "solo"]
        if not filas:
            return []
        nombres = {p["id"]: p["nombre"] for p in await self.datos.personas()}
        por = defaultdict(list)
        for f in sorted(filas, key=lambda x: x["t"]):
            por[f["p"]].append(f)
        lineas = ["### Lo de la semana"]
        mas = max(por.items(), key=lambda kv: len(kv[1]))
        lineas.append(f"🎮 Más partidas: **{nombres.get(mas[0], mas[0])}** ({len(mas[1])})")
        racha = {pid: max((len(s) for s in "".join("V" if x["w"] else "D" for x in g).split("D")), default=0)
                 for pid, g in por.items()}
        mejor = max(racha.items(), key=lambda kv: kv[1])
        if mejor[1] >= 3:
            lineas.append(f"🔥 Mejor racha: **{nombres.get(mejor[0], mejor[0])}**, {mejor[1]} victorias seguidas")
        lp = {pid: sum(x["lp"] for x in g if x["lp"] is not None) for pid, g in por.items()
              if any(x["lp"] is not None for x in g)}
        if lp:
            sube = max(lp.items(), key=lambda kv: kv[1])
            lineas.append(f"📈 Más LP: **{nombres.get(sube[0], sube[0])}** ({F.num(sube[1], 0, True)} LP en las partidas con LP exacto)")
        return lineas

    @tasks.loop(minutes=5)
    async def vigilar(self):
        """Publica las partidas nuevas del grupo y los cambios de división en el canal de feed."""
        canales = self._canales("feed")
        try:
            recientes = await self.datos.recientes()
            personas = await self.datos.personas()
        except Exception:
            logger.exception("Feed: no pude leer los datos")
            return
        vistos = set(self.estado.get("vistos", []))
        rangos = self.estado.get("rangos", {})
        primera = not vistos and not rangos
        nuevos = [m for m in sorted(recientes, key=lambda m: m["inicio"]) if m["id"] not in vistos]
        cambios = []
        for p in personas:
            v = _valor(p.get("solo"))
            antes = rangos.get(p["id"])
            if v is not None and antes is not None and v != antes:
                cambios.append((p, v > antes))
            if v is not None:
                rangos[p["id"]] = v
        # La primera vez solo se anota lo que hay, para no inundar el canal con partidas viejas.
        if not primera and canales and (nuevos or cambios):
            nombres = {p["id"]: p["nombre"] for p in personas}
            champs = await self.datos.campeones()
            nc = (await self.datos.ajustes()).get("nombres_cola", {})
            for m in nuevos[-10:]:
                lineas = [f"### {'✅ Victoria' if all(j['win'] for j in m['jugadores']) else '❌ Derrota' if not any(j['win'] for j in m['jugadores']) else '⚔️ Enfrentados'} · {nc.get(m['cola'], m['cola'])} · {F.num(m['dur'], 0)} min"]
                for j in m["jugadores"]:
                    champ = (champs.get(str(j["champ"])) or {}).get("nombre", j["champ"])
                    lp = f" · **{F.num(j['lp'], 0, True)} LP**" if j.get("lp") is not None else ""
                    lineas.append(f"{'✅' if j['win'] else '❌'} **{nombres.get(j['persona'], j['persona'])}** · {champ} "
                                  f"{j['rol'] or ''} · {j['k']}/{j['d']}/{j['a']}{lp}")
                lineas += await self._momento_clave(m)
                vista = tarjeta_simple(lineas, f"{WEB}#/jugadores/{m['jugadores'][0]['persona']}")
                for ch in canales:
                    try:
                        await ch.send(view=vista)
                    except discord.HTTPException:
                        logger.exception("Feed: no pude publicar en %s", ch)
            for p, sube in cambios:
                txt = (f"📈 **{p['nombre']}** subió a **{_rango(p['solo'])}** en solo/dúo" if sube
                       else f"📉 **{p['nombre']}** bajó a **{_rango(p['solo'])}** en solo/dúo")
                for ch in canales:
                    try:
                        await ch.send(view=tarjeta_simple([txt], f"{WEB}#/jugadores/{p['id']}"))
                    except discord.HTTPException:
                        logger.exception("Feed: no pude publicar en %s", ch)
        vistos.update(m["id"] for m in recientes)
        self.estado.set("vistos", sorted(vistos)[-500:])
        self.estado.set("rangos", rangos)

    async def _momento_clave(self, m: dict) -> list[str]:
        """La jugada que más movió la probabilidad de ganar (fase 5), desde el equipo del primer jugador."""
        try:
            d = await self.datos.partida(m["id"])
        except Exception:
            return []
        k = (d or {}).get("clave")
        if not k:
            return []
        lado = d["lados"].get(m["jugadores"][0]["persona"], "azul")
        dv = k["delta"] if lado == "azul" else -k["delta"]
        nombres = {"baron": "Barón", "ancestral": "Ancestral", "dragon": "dragón", "heraldo": "Heraldo", "inhib": "inhibidor"}
        eq = 100 if lado == "azul" else 200
        ev = [e for e in d["eventos"] if k["min"] - 1 < e["min"] <= k["min"] and e["tipo"] in nombres]
        que = ", ".join(f"{nombres[e['tipo']]} {'propio' if e.get('equipo') == eq else 'rival'}" for e in ev) or "peleas y oro"
        return [f"-# Momento clave: minuto {k['min']}, {'+' if dv > 0 else '−'}{F.num(abs(dv) * 100, 0)} pts ({que})"]

    @vigilar.before_loop
    async def _esperar(self):
        await self.bot.wait_until_ready()

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.MissingPermissions, commands.NoPrivateMessage)):
            await ctx.reply("Eso lo puede configurar alguien con permiso de **Gestionar servidor**, dentro del servidor.",
                            ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Feed(bot))
