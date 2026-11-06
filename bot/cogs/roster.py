"""-roster: los rosters de la Virguhouse y de SRX (fase 7). Mismo JSON que la pestaña Rosters de Equipos en la web
(api/roster/). Ver y pedir informes puede cualquiera; crear y editar, solo Lucca (el dueño de la app del bot).

Los cambios se guardan en el volumen y en el repo ldh-lol-metas (rosters.json); la web y las métricas los toman
en la próxima corrida del pipeline."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.services import formato as F
from bot.ui.roster_vista import tarjeta_informe_roster, vista_roster

ROLES = ("Top", "Jungla", "Mid", "ADC", "Support")
ALIAS_ROL = {"top": "Top", "jungla": "Jungla", "jg": "Jungla", "jungle": "Jungla", "mid": "Mid", "adc": "ADC",
             "bot": "ADC", "support": "Support", "supp": "Support", "sup": "Support"}
CARPETAS = {"virguhouse": "virguhouse", "virgu": "virguhouse", "srx": "srx"}
ESTADOS = ("titular", "suplente")


def _slug(nombre: str) -> str:
    """'SRX 1' → 'srx-1': el id fijo del roster (minúsculas, sin tildes, guiones entre palabras)."""
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40] or "roster"


def _hoy() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Roster(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------------- ver

    async def _elegir(self, ctx: commands.Context, nombre_o_jugador: str | None) -> tuple[bool, str | None]:
        """(seguir, rid). Sin nombre: el roster de tu vínculo, o el primero. Responde si no encuentra."""
        idx = (await self.bot.datos.rosters()).get("rosters") or []
        if nombre_o_jugador:
            t = F.normalizar(nombre_o_jugador)
            r = next((r for r in idx if t in (F.normalizar(r["nombre"]), r["id"])), None) \
                or next((r for r in idx if t in F.normalizar(r["nombre"])), None)
            if not r:
                p = await self.bot.datos.buscar(nombre_o_jugador)
                r = next((r for r in idx if p and any(x["id"] == p["id"] for x in r["plantel"])), None)
                if not r:
                    nombres = ", ".join(f"**{x['nombre']}**" for x in idx) or "ninguno todavía"
                    await ctx.reply(f"No encontré un roster de **{nombre_o_jugador}**. Rosters: {nombres}.", ephemeral=True)
                    return False, None
            return True, r["id"]
        yo = self.bot.get_cog("Perfil").vinculos.get(str(ctx.author.id))
        return True, next((r["id"] for r in idx if any(x["id"] == yo for x in r["plantel"])), idx[0]["id"] if idx else None)

    @commands.hybrid_group(name="roster", aliases=["rosters"], fallback="ver", invoke_without_command=True,
                           description="Un roster: plantel, métricas del equipo y de cada jugador")
    async def roster(self, ctx: commands.Context, *, nombre_o_jugador: str | None = None):
        """-roster (el tuyo, o el primero), -roster srx-1, -roster ahitevan (el de ese jugador)."""
        seguir, rid = await self._elegir(ctx, nombre_o_jugador)
        if seguir:
            await ctx.reply(view=await vista_roster(self.bot, rid))

    @commands.hybrid_command(name="informe_roster", description="El último informe semanal de un roster")
    async def informe_roster(self, ctx: commands.Context, *, nombre_o_jugador: str | None = None):
        """-informe_roster (el de tu roster), -informe_roster ahitevan."""
        seguir, rid = await self._elegir(ctx, nombre_o_jugador)
        if not seguir:
            return
        d = await self.bot.datos.roster(rid) if rid else None
        if not d:
            await ctx.reply("Todavía no hay rosters publicados.", ephemeral=True)
            return
        informes = await self.bot.datos.informes_roster(rid)
        await ctx.reply(view=tarjeta_informe_roster(d, informes[0] if informes else None))

    @roster.command(name="sugerencias", description="Grupos que juegan juntos y todavía no son un roster")
    async def sugerencias(self, ctx: commands.Context):
        sug = (await self.bot.datos.rosters()).get("sugerencias") or []
        if not sug:
            await ctx.reply("No hay sugerencias: ningún grupo nuevo juega junto lo suficiente (10+ partidas con 4+ juntos).")
            return
        lin = ["## Grupos que juegan juntos", "-# Detectados por quién juega con quién en Flex y Normales. "
               "Lucca los declara con `-roster declarar <número> <nombre>`."]
        for i, s in enumerate(sug, 1):
            lin.append(f"**{i}. {discord.utils.escape_markdown(s['nombre'])}** · {F.partidas(s['partidas'])} juntos\n"
                       + " · ".join(f"{discord.utils.escape_markdown(p['nombre'])} ({p['rol'] or '—'}, {p['partidas']})"
                                    for p in s["plantel"]))
        await ctx.reply("\n".join(lin)[:1990])

    # ---------------------------------------------------------------- editar (solo Lucca)

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.command and ctx.command.name in ("crear", "sumar", "sacar", "borrar", "declarar", "renombrar"):
            if not await self.bot.is_owner(ctx.author):
                raise commands.CheckFailure("Solo Lucca puede crear y editar rosters.")
        return True

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            await ctx.reply(str(error) or "No podés usar este comando.", ephemeral=True)

    async def _rosters(self, ctx) -> dict | None:
        try:
            return {k: dict(v) for k, v in (await self.bot.metas.rosters_actuales()).items()}
        except RuntimeError:
            await ctx.reply("No pude leer los rosters guardados en GitHub, así que no toco nada (si guardara, "
                            "podría borrar los que ya hay). Probá de nuevo en un rato.", ephemeral=True)
            return None

    def _buscar_prefijo(self, rosters: dict, partes: list[str]) -> tuple[str | None, int]:
        """El roster nombrado al principio ('SRX 1 lucca' → srx-1, 2): el nombre más largo que coincida, dejando
        al menos una palabra para el jugador."""
        for k in range(len(partes) - 1, 0, -1):
            if rid := self._buscar(rosters, " ".join(partes[:k])):
                return rid, k
        return None, 0

    def _buscar(self, rosters: dict, texto: str) -> str | None:
        """Por id ('srx-1') o por nombre ('SRX 1'), sin tildes ni mayúsculas."""
        t = F.normalizar(texto)
        return next((rid for rid, r in rosters.items() if t in (F.normalizar(rid), F.normalizar(r.get("nombre", "")))), None)

    async def _guardar(self, ctx, rosters: dict, rid: str | None, mensaje: str, texto: str):
        ok = await self.bot.metas.guardar_rosters(rosters, mensaje)
        aviso = "" if ok else ("\n-# No pude subirlo a GitHub: quedó guardado en el bot y se reintenta en el próximo "
                               "cambio. Hasta que suba, la web no lo ve.")
        detalle = ""
        if rid and rid in rosters:
            r = rosters[rid]
            pl = r.get("plantel") or []
            detalle = "\n" + (" · ".join(f"{x['id']} ({x.get('rol') or '—'}{', suplente' if x.get('estado') == 'suplente' else ''})"
                                         for x in pl) or "Sin jugadores todavía.")
            faltan = [rol for rol in ROLES if not any(x.get("rol") == rol and x.get("estado") != "suplente" for x in pl)]
            if faltan:
                detalle += f"\n-# Sin titular: {', '.join(faltan)}."
        await ctx.reply(f"{texto}{detalle}\n-# La web y las métricas lo toman en la próxima corrida.{aviso}")

    @roster.command(name="crear", description="(Lucca) Crea un roster vacío: -roster crear <nombre> [srx|virguhouse]")
    async def crear(self, ctx: commands.Context, *, nombre_y_carpeta: str):
        partes = nombre_y_carpeta.split()
        carpeta = CARPETAS.get(F.normalizar(partes[-1])) if len(partes) > 1 else None
        nombre = " ".join(partes[:-1] if carpeta else partes)
        rosters = await self._rosters(ctx)
        if rosters is None:
            return
        rid = _slug(nombre)
        if rid in rosters:
            await ctx.reply(f"Ya existe un roster **{rosters[rid]['nombre']}** (`{rid}`).", ephemeral=True)
            return
        rosters[rid] = {"nombre": nombre, "carpeta": carpeta or "virguhouse", "plantel": [], "creado": _hoy()}
        await self._guardar(ctx, rosters, rid, f"Roster nuevo: {nombre}",
                            f"Listo: roster **{discord.utils.escape_markdown(nombre)}** (`{rid}`) en "
                            f"{'SRX' if carpeta == 'srx' else 'la Virguhouse'}. Sumá gente con "
                            f"`-roster sumar {rid} <jugador> <rol> [suplente]`.")

    @roster.command(name="sumar", description="(Lucca) -roster sumar <roster> <jugador> <rol> [suplente]")
    async def sumar(self, ctx: commands.Context, *, texto: str):
        partes = texto.split()
        estado = "suplente" if partes and F.normalizar(partes[-1]) in ("suplente", "sup") else "titular"
        if partes and F.normalizar(partes[-1]) in ESTADOS + ("sup",):
            partes = partes[:-1]
        rol = ALIAS_ROL.get(F.normalizar(partes[-1])) if partes else None
        if len(partes) < 3 or not rol:
            await ctx.reply("Uso: `-roster sumar <roster> <jugador> <rol> [suplente]`. Roles: Top, Jungla, Mid, ADC, Support.",
                            ephemeral=True)
            return
        rosters = await self._rosters(ctx)
        if rosters is None:
            return
        rid, k = self._buscar_prefijo(rosters, partes[:-1])
        if not rid:
            await ctx.reply(f"No encontré el roster. Rosters: {', '.join(f'`{k}`' for k in rosters) or 'ninguno'}.",
                            ephemeral=True)
            return
        jugador = " ".join(partes[k:-1])
        p = await self.bot.datos.buscar(jugador)
        if not p:
            await ctx.reply(await self.bot.datos.no_encontre(jugador), ephemeral=True)
            return
        plantel = [x for x in rosters[rid].get("plantel") or [] if x["id"] != p["id"]]
        previo = next((x for x in rosters[rid].get("plantel") or [] if x["id"] == p["id"]), None)
        plantel.append({"id": p["id"], "rol": rol, "estado": estado, "desde": (previo or {}).get("desde") or _hoy()})
        rosters[rid]["plantel"] = plantel
        otro = [x["id"] for x in plantel if x["rol"] == rol and x["estado"] == "titular" and x["id"] != p["id"]]
        aviso = f"\n-# Ojo: {', '.join(otro)} también es titular en {rol}." if estado == "titular" and otro else ""
        await self._guardar(ctx, rosters, rid, f"Roster {rid}: suma {p['id']}",
                            f"{'Actualicé' if previo else 'Sumé'} a **{discord.utils.escape_markdown(p['nombre'])}** en "
                            f"**{rosters[rid]['nombre']}** como {rol} {estado}.{aviso}")

    @roster.command(name="sacar", description="(Lucca) -roster sacar <roster> <jugador>")
    async def sacar(self, ctx: commands.Context, *, texto: str):
        partes = texto.split()
        rosters = await self._rosters(ctx)
        if rosters is None or len(partes) < 2:
            if rosters is not None:
                await ctx.reply("Uso: `-roster sacar <roster> <jugador>`.", ephemeral=True)
            return
        rid, k = self._buscar_prefijo(rosters, partes)
        p = await self.bot.datos.buscar(" ".join(partes[k:])) if rid else None
        if not rid or not p or not any(x["id"] == p["id"] for x in rosters[rid].get("plantel") or []):
            await ctx.reply("No encontré a ese jugador en ese roster.", ephemeral=True)
            return
        rosters[rid]["plantel"] = [x for x in rosters[rid]["plantel"] if x["id"] != p["id"]]
        await self._guardar(ctx, rosters, rid, f"Roster {rid}: saca {p['id']}",
                            f"Saqué a **{discord.utils.escape_markdown(p['nombre'])}** de **{rosters[rid]['nombre']}**.")

    @roster.command(name="borrar", description="(Lucca) -roster borrar <roster>")
    async def borrar(self, ctx: commands.Context, *, roster: str):
        rosters = await self._rosters(ctx)
        if rosters is None:
            return
        rid = self._buscar(rosters, roster)
        if not rid:
            await ctx.reply(f"No existe el roster `{roster}`.", ephemeral=True)
            return
        nombre = rosters.pop(rid)["nombre"]
        await self._guardar(ctx, rosters, None, f"Roster borrado: {rid}",
                            f"Borré el roster **{discord.utils.escape_markdown(nombre)}**. Sus informes viejos quedan en "
                            "`datos/informes_roster/` pero dejan de publicarse.")

    @roster.command(name="declarar", description="(Lucca) Declara una sugerencia: -roster declarar <número> <nombre>")
    async def declarar(self, ctx: commands.Context, *, numero_y_nombre: str):
        partes = numero_y_nombre.split()
        sug = (await self.bot.datos.rosters()).get("sugerencias") or []
        if not partes or not partes[0].isdigit() or not 1 <= int(partes[0]) <= len(sug):
            await ctx.reply(f"Uso: `-roster declarar <número> <nombre>`, con el número de `-roster sugerencias` "
                            f"(hay {len(sug)}).", ephemeral=True)
            return
        s = sug[int(partes[0]) - 1]
        nombre = " ".join(partes[1:]) or s["nombre"]
        rosters = await self._rosters(ctx)
        if rosters is None:
            return
        rid = _slug(nombre)
        if rid in rosters:
            await ctx.reply(f"Ya existe un roster `{rid}`: elegí otro nombre.", ephemeral=True)
            return
        # Titular de cada rol: el que más jugó en ese rol dentro del grupo; el resto, suplentes.
        plantel, usados = [], set()
        for rol in ROLES:
            t = next((p for p in s["plantel"] if p["rol"] == rol and p["id"] not in usados), None)
            if t:
                usados.add(t["id"])
                plantel.append({"id": t["id"], "rol": rol, "estado": "titular", "desde": _hoy()})
        plantel += [{"id": p["id"], "rol": p["rol"], "estado": "suplente", "desde": _hoy()}
                    for p in s["plantel"] if p["id"] not in usados]
        rosters[rid] = {"nombre": nombre, "carpeta": "virguhouse", "plantel": plantel, "creado": _hoy()}
        await self._guardar(ctx, rosters, rid, f"Roster declarado: {nombre}",
                            f"Declaré **{discord.utils.escape_markdown(nombre)}** (`{rid}`) en la Virguhouse. Titulares: "
                            "el que más jugó cada rol en el grupo. Ajustalo con `-roster sumar` y `-roster sacar`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Roster(bot))
