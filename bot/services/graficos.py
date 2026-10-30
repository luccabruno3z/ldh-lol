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
    import matplotlib.dates as mdates

    c = evo["colas"][cola]
    pts = c["puntos"]
    fecha = lambda t: datetime.fromtimestamp(t / 1000, timezone.utc)
    xs = [fecha(p["t"]) for p in pts]
    fig, ax = _figura()
    ax.fill_between(xs, [p["lo"] * 100 for p in pts], [p["hi"] * 100 for p in pts], color=ACENTO, alpha=0.18, lw=0)
    ax.plot(xs, [p["v"] * 100 for p in pts], color=ACENTO, lw=2.4)
    ax.axhline(50, color=TENUE, lw=1, ls=(0, (4, 4)))
    # La referencia es tu propia temporada: la línea naranja es tu promedio.
    if c.get("temporada"):
        temp = c["temporada"]["v"] * 100
        ax.axhline(temp, color=SEGUNDO, lw=1.4, ls=(0, (6, 4)))
        # El rótulo va a la izquierda: a la derecha se pisaba con el de "hoy".
        ax.annotate(f"tu temporada {round(temp)} %", (xs[0], temp), xytext=(2, 5), textcoords="offset points",
                    color=SEGUNDO, fontsize=9, ha="left")
    for clave, rotulo, dy in (("mejor", "mejor tramo", 8), ("peor", "peor tramo", -14)):
        if c.get(clave):
            h = c[clave]
            ax.scatter([fecha(h["t"])], [h["v"] * 100], color=TENUE, s=14, zorder=3)
            ax.annotate(f"{rotulo} {round(h['v'] * 100)} %", (fecha(h["t"]), h["v"] * 100), xytext=(0, dy),
                        textcoords="offset points", color=TENUE, fontsize=8, ha="center")
    ult = pts[-1]
    ax.scatter([xs[-1]], [ult["v"] * 100], color=ACENTO, zorder=4, s=36)
    ax.annotate(f"hoy {round(ult['v'] * 100)} %", (xs[-1], ult["v"] * 100), xytext=(-8, 8),
                textcoords="offset points", color=ACENTO, fontsize=10, ha="right", fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_ylabel(f"winrate de las {evo['ventana']} anteriores (%)", color=TENUE)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.grid(color=GRILLA, lw=0.6)
    # El título contesta la pregunta del gráfico: ¿venís mejor o peor que antes?
    if c.get("ultimas"):
        veredicto = ("venís mejor" if c["ultimas"]["v"] > c["resto"]["v"] else "venís peor") if c.get("senal") \
            else "igual que siempre (ruido)"
        sub = (f"Últimas {evo['ventana']}: {round(c['ultimas']['v'] * 100)} % · antes: {round(c['resto']['v'] * 100)} % "
               f"→ {veredicto}")
    else:
        sub = ""
    ax.set_title(f"{titulo} · {nombre_cola}\n{sub}", color=TEXTO, fontsize=12, loc="left")
    return _png(fig)


def tendencia(t: dict, titulo: str, franja: str) -> io.BytesIO:
    """¿Estás mejorando? El índice por partida (promedio móvil) y la recta de toda la temporada."""
    # Eje = número de partida (la recta se ajusta por partida); los meses quedan como rótulos.
    MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    xs = [p["i"] for p in t["puntos"]]
    fig, ax = _figura()
    ax.axhline(50, color=TENUE, lw=1, ls=(0, (4, 4)))
    ax.annotate(f"mitad de {franja}", (0, 50), xytext=(2, 5), textcoords="offset points", color=TENUE, fontsize=9)
    ax.plot(xs, [p["v"] for p in t["puntos"]], color=ACENTO, lw=2.4)
    color = {"mejorando": "#00e07a", "empeorando": "#ff4466"}.get(t["veredicto"], TENUE)
    r = t["recta"]
    ax.plot([r["desde"]["i"], r["hasta"]["i"]], [r["desde"]["v"], r["hasta"]["v"]], color=color, lw=2.4, ls=(0, (8, 5)))
    ax.scatter([xs[-1]], [t["puntos"][-1]["v"]], color=ACENTO, s=36, zorder=4)
    vs = [p["v"] for p in t["puntos"]]
    ax.set_ylim(max(0, min(vs + [40]) - 8), min(100, max(vs + [60]) + 8))
    ax.set_xlim(0, t["n"] - 1)
    ax.set_ylabel(f"índice (promedio de {t['ventana']} partidas)", color=TENUE)
    ax.set_xlabel(f"partidas ({t['n']})", color=TENUE)
    marcas, ultimo = [], -1e9
    for mm in t.get("meses", []):
        if mm["i"] - ultimo > t["n"] / 14:  # sin rótulos pegados
            marcas.append(mm)
            ultimo = mm["i"]
    ax.set_xticks([mm["i"] for mm in marcas])
    ax.set_xticklabels([MESES[mm["mes"] - 1] for mm in marcas])
    ax.grid(color=GRILLA, lw=0.6)
    signo = lambda v: f"{'+' if v > 0 else ''}{v:.1f}".replace(".", ",")
    ax.set_title(f"{titulo}\nDe {t['inicio']:.0f} a {t['ahora']:.0f} → {t['veredicto']} "
                 f"({signo(t['pendiente'])} cada 100 partidas)", color=TEXTO, fontsize=12, loc="left")
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
