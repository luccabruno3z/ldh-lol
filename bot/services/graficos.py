"""Gráficos PNG para Discord (-grafico), con matplotlib como el bot de PR y los colores del sitio.
Igual que en la web: la evolución lleva su banda de intervalo y el radar marca la mitad de la franja."""

from __future__ import annotations

import io
import math
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")  # sin pantalla; va antes de importar pyplot
import matplotlib.pyplot as plt  # noqa: E402

FONDO, PANEL, TEXTO, TENUE, GRILLA = "#0d1420", "#121a2a", "#e8ecf4", "#7a8296", "#263248"
ACENTO, SEGUNDO = "#00e5e5", "#ffa500"


def _figura(ancho=8, alto=4.2, polar=False):
    fig = plt.figure(figsize=(ancho, alto), dpi=110, facecolor=FONDO)
    ax = fig.add_subplot(111, polar=polar, facecolor=PANEL)
    ax.tick_params(colors=TENUE, labelsize=9)
    for s in getattr(ax, "spines", {}).values():
        s.set_color(GRILLA)
    return fig, ax


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def evolucion(evo: dict, cola: str, nombre_cola: str, titulo: str) -> io.BytesIO:
    """Winrate de las últimas N partidas en cada momento, con su banda de Wilson y el 50 % punteado."""
    pts = evo["colas"][cola]["puntos"]
    xs = [p["i"] for p in pts]
    fig, ax = _figura()
    ax.fill_between(xs, [p["lo"] * 100 for p in pts], [p["hi"] * 100 for p in pts], color=ACENTO, alpha=0.18, lw=0)
    ax.plot(xs, [p["v"] * 100 for p in pts], color=ACENTO, lw=2.4)
    ax.axhline(50, color=TENUE, lw=1, ls=(0, (4, 4)))
    ult = pts[-1]
    ax.scatter([ult["i"]], [ult["v"] * 100], color=ACENTO, zorder=3, s=30)
    ax.annotate(f"{round(ult['v'] * 100)} %", (ult["i"], ult["v"] * 100), xytext=(6, 6),
                textcoords="offset points", color=TEXTO, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_ylabel("winrate (%)", color=TENUE)
    fecha = datetime.fromtimestamp(ult["t"] / 1000, timezone.utc).strftime("%d/%m")
    ax.set_xlabel(f"partida número (última: {fecha})", color=TENUE)
    ax.grid(color=GRILLA, lw=0.6)
    ax.set_title(f"{titulo} · {nombre_cola} · últimas {evo['ventana']} partidas", color=TEXTO, fontsize=12, loc="left")
    return _png(fig)


def radar(comps: list[dict], titulo: str, segundo: list[dict] | None = None, etiquetas=("", "")) -> io.BytesIO:
    """Los 7 componentes (0–100) contra la franja; el anillo punteado es 50, la mitad de la franja."""
    n = len(comps)
    ang = [2 * math.pi * i / n for i in range(n)] + [0]
    val = lambda cs: [50 if c.get("sin_dato") or c.get("nivel") is None else c["nivel"] * 100 for c in cs]
    fig, ax = _figura(6.2, 6.2, polar=True)
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], color=TENUE, fontsize=8)
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels([c["nombre"] for c in comps], color=TEXTO, fontsize=10)
    ax.grid(color=GRILLA, lw=0.7)
    ax.plot(ang, [50] * (n + 1), color=TENUE, lw=1, ls=(0, (4, 4)))
    if segundo:
        v2 = val(segundo)
        ax.fill(ang, v2 + v2[:1], color=SEGUNDO, alpha=0.18)
        ax.plot(ang, v2 + v2[:1], color=SEGUNDO, lw=2, label=etiquetas[1])
    v1 = val(comps)
    ax.fill(ang, v1 + v1[:1], color=ACENTO, alpha=0.22)
    ax.plot(ang, v1 + v1[:1], color=ACENTO, lw=2.2, label=etiquetas[0])
    if segundo:
        ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.12), facecolor=PANEL, edgecolor=GRILLA, labelcolor=TEXTO)
    ax.set_title(titulo, color=TEXTO, fontsize=12, pad=24)
    return _png(fig)
