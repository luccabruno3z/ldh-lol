"""Simulador del bot sin Discord: corre un comando o toca un botón/menú y muestra lo que vería el usuario.

Sirve para probar tarjetas y para que alguien recorra el bot como usuario sin escribir en un servidor real.
Lee los datos de LDH_DATA_URL (por defecto el sitio local en http://127.0.0.1:8010/api).

    python scripts/simular_bot.py "-perfil glarrex"
    python scripts/simular_bot.py "-coaching" --como lucca          # como si fueras lucca (vinculado)
    python scripts/simular_bot.py --tocar "lc:gmue:lucca:auto:solo:1:vista" --valor gcur --como lucca
    python scripts/simular_bot.py --tocar "lp:..."                  # un botón (sin --valor)

Cada respuesta se imprime como texto: los TextDisplay, y por cada botón y menú su custom_id (para tocarlo
después con --tocar) y sus opciones. Los PNG se guardan en --salida y se imprime la ruta.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import sys
import tempfile
from types import SimpleNamespace

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("LDH_DATA_URL", "http://127.0.0.1:8010/api")

USUARIO = 1  # id de Discord del usuario simulado


def _preparar_volumen(como: str | None) -> None:
    # Un volumen por usuario simulado: si dos pruebas corren a la vez como personas distintas, no se pisan el vínculo.
    d = os.path.join(tempfile.gettempdir(), "ldh-simular-bot", como or "sin-vincular")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "vinculos.json"), "w", encoding="utf-8") as f:
        json.dump({str(USUARIO): como} if como else {}, f)
    for extra in ("canales.json", "feed.json", "sugerencias.json", "pools_pendientes.json"):
        p = os.path.join(d, extra)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write("{}")
    os.environ["BOT_DATA_DIR"] = d
    os.environ.pop("GITHUB_TOKEN_METAS", None)  # nunca escribir en el repo de metas desde el simulador


class Captura:
    def __init__(self, salida: str):
        self.salida, self.n = salida, 0
        self.bloques: list[str] = []

    def _archivos(self, file=None, files=None, attachments=None):
        rutas = []
        for f in [*(files or []), *(attachments or []), *([file] if file else [])]:
            fp = getattr(f, "fp", None)
            if fp is None:
                continue
            self.n += 1
            ruta = os.path.join(self.salida, f"{self.n:02d}-{getattr(f, 'filename', 'archivo.png')}")
            fp.seek(0)
            with open(ruta, "wb") as out:
                out.write(fp.read())
            rutas.append(ruta)
        return rutas

    def registrar(self, origen: str, content=None, view=None, embed=None, embeds=None, file=None, files=None,
                  attachments=None, ephemeral=False, **_):
        lin = [f"=== {origen}{' (solo vos la ves)' if ephemeral else ''} ==="]
        if content:
            lin.append(content)
        for e in [*(embeds or []), *([embed] if embed else [])]:
            lin.append(f"[embed] {e.title or ''}\n{e.description or ''}")
            for fld in e.fields:
                lin.append(f"  {fld.name}: {fld.value}")
        if view is not None:
            lin += _describir_vista(view)
        for r in self._archivos(file, files, attachments):
            lin.append(f"[imagen guardada] {r}")
        self.bloques.append("\n".join(lin))


def _describir_vista(view) -> list[str]:
    import discord
    lin = []
    for it in view.walk_children():
        if isinstance(it, discord.ui.DynamicItem):
            it = it.item
        if isinstance(it, discord.ui.TextDisplay):
            lin.append(it.content)
        elif isinstance(it, discord.ui.MediaGallery):
            lin.append("[galería: el PNG adjunto]")
        elif isinstance(it, discord.ui.Separator):
            lin.append("────")
        elif isinstance(it, discord.ui.Button):
            dest = f"link → {it.url}" if it.url else f"custom_id={it.custom_id}"
            lin.append(f"[botón] «{it.label}»{' (desactivado)' if it.disabled else ''} · {dest}")
        elif isinstance(it, discord.ui.Select):
            ops = " | ".join(f"{o.label}={o.value}{' ✓' if o.default else ''}"
                             + (f" ({o.description})" if o.description else "") for o in it.options)
            lin.append(f"[menú] {it.placeholder or ''} · custom_id={it.custom_id} · elegí hasta {it.max_values}: {ops}")
    return lin


def _ctx_falso(bot, cap: Captura, contenido: str):
    from discord.ext import commands
    from discord.ext.commands.view import StringView

    autor = SimpleNamespace(id=USUARIO, name="usuario", display_name="usuario", mention="@usuario", bot=False,
                            guild_permissions=SimpleNamespace(manage_guild=False, administrator=False))
    canal = SimpleNamespace(id=10, send=None, typing=None)
    msg = SimpleNamespace(id=100, author=autor, channel=canal, guild=None, content=contenido, attachments=[],
                          mentions=[], role_mentions=[], channel_mentions=[], _state=None)
    view = StringView(contenido)
    view.skip_string("-")
    nombre = view.get_word()
    ctx = commands.Context(message=msg, bot=bot, view=view, prefix="-")
    ctx.invoked_with = nombre
    ctx.command = bot.all_commands.get(nombre)

    async def reply(content=None, **kw):
        cap.registrar("respuesta", content, **kw)
    ctx.reply = reply
    ctx.send = reply

    async def defer(**_):
        return None
    ctx.defer = defer
    return ctx


class _Respuesta:
    def __init__(self, cap: Captura):
        self.cap, self._hecho = cap, False

    def is_done(self):
        return self._hecho

    async def defer(self, **_):
        self._hecho = True

    async def send_message(self, content=None, **kw):
        self._hecho = True
        self.cap.registrar("respuesta al tocar", content, **kw)

    async def edit_message(self, content=None, **kw):
        self._hecho = True
        self.cap.registrar("mensaje editado", content, **kw)

    async def send_modal(self, modal):
        self._hecho = True
        campos = [f"  campo «{c.label}»" for c in modal.children]
        self.cap.bloques.append("\n".join([f"=== ventana «{modal.title}» (formulario) ==="] + campos))


def _interaccion_falsa(bot, cap: Captura):
    async def editar(content=None, **kw):
        cap.registrar("mensaje editado", content, **kw)

    async def seguir(content=None, **kw):
        cap.registrar("respuesta extra", content, **kw)
    return SimpleNamespace(client=bot, user=SimpleNamespace(id=USUARIO, mention="@usuario"), guild=None,
                           response=_Respuesta(cap), edit_original_response=editar,
                           followup=SimpleNamespace(send=seguir), message=None)


async def _tocar(bot, cap: Captura, custom_id: str, valores: list[str]):
    import discord
    for cls in bot._connection._dynamic_items.values() if hasattr(bot._connection, "_dynamic_items") else []:
        pass
    clases = getattr(bot, "_simular_dinamicos", [])
    for cls in clases:
        m = cls.__discord_ui_compiled_template__.fullmatch(custom_id)
        if not m:
            continue
        inter = _interaccion_falsa(bot, cap)
        # Discord le pasa el componente que se tocó (con su etiqueta); acá uno de mentira con lo mínimo.
        falso = SimpleNamespace(label="", custom_id=custom_id, values=valores, emoji=None, style=None, disabled=False)
        item = await cls.from_custom_id(inter, falso, m)
        if isinstance(item.item, discord.ui.Select):
            item.item._values = valores
        if hasattr(item, "interaction_check") and not await item.interaction_check(inter):
            return
        await item.callback(inter)
        return
    cap.bloques.append(f"=== nada responde a {custom_id} (no es un botón persistente) ===")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("comando", nargs="?", help='p. ej. "-perfil glarrex"')
    ap.add_argument("--como", help="id del jugador vinculado al usuario simulado (p. ej. lucca)")
    ap.add_argument("--tocar", help="custom_id de un botón o menú")
    ap.add_argument("--valor", action="append", default=[], help="opción elegida en el menú (se puede repetir)")
    ap.add_argument("--salida", default=os.path.join(tempfile.gettempdir(), "ldh-simular-bot", "png"))
    # "-coaching" empieza con guion: argparse lo tomaría como una opción, así que se separa a mano.
    argv = sys.argv[1:]
    cmd = next((x for x in argv if x.startswith("-") and not x.startswith("--")), None)
    if cmd:
        argv.remove(cmd)
    a = ap.parse_args(argv)
    if cmd:
        a.comando = cmd
    os.makedirs(a.salida, exist_ok=True)
    _preparar_volumen(a.como)
    sys.stdout.reconfigure(encoding="utf-8")

    from discord.ext import tasks
    tasks.Loop.start = lambda self, *x, **k: None  # sin tareas periódicas (feed, ranking semanal)
    from bot.main import COGS, Bot

    bot = Bot()
    for cog in COGS:
        await bot.load_extension(cog)
    from bot.ui.coaching_vista import SelectorCoaching
    from bot.ui.informe_vista import InformeBoton
    from bot.ui.menu import MenuBoton
    from bot.ui.partida_vista import PartidaBoton
    from bot.ui.perfil_vista import PerfilBoton
    from bot.ui.pool_vista import BorrarPool, SelectorPool
    from bot.ui.rankings_vista import SelectorRanking
    from bot.cogs.extra import SelectorTexto
    bot._simular_dinamicos = [PerfilBoton, MenuBoton, SelectorRanking, SelectorCoaching, PartidaBoton, InformeBoton,
                              SelectorPool, BorrarPool, SelectorTexto]
    # Guardar una pool no sube nada: queda solo en el volumen temporal.
    if hasattr(bot, "metas"):
        async def _sin_subir(*_a, **_k):
            return False
        bot.metas._subir = _sin_subir
    cap = Captura(a.salida)
    try:
        if a.tocar:
            await _tocar(bot, cap, a.tocar, a.valor)
        elif a.comando:
            ctx = _ctx_falso(bot, cap, a.comando)
            if ctx.command is None:
                from discord.ext import commands as _c
                await bot.on_command_error(ctx, _c.CommandNotFound(f'Command "{ctx.invoked_with}" is not found'))
                if not cap.bloques:
                    cap.bloques.append(f"=== el bot no tiene el comando «{ctx.invoked_with}» (no contesta nada) ===")
            else:
                try:
                    await ctx.command.invoke(ctx)
                except Exception as e:  # lo que en Discord sería un error del comando
                    from discord.ext import commands as _c
                    if isinstance(e, _c.UserInputError):
                        await bot.on_command_error(ctx, e)  # el bot contesta el modo de uso
                    else:
                        cap.bloques.append(f"=== error del comando: {type(e).__name__}: {e} ===")
        else:
            ap.error("pasá un comando o --tocar")
    finally:
        await bot.datos.close()
    print("\n\n".join(cap.bloques) or "(sin respuesta)")


if __name__ == "__main__":
    asyncio.run(main())
