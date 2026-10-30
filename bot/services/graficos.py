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
COLOR_FRANJA = ["#c08457", "#c9ced8", "#3fbf9b"]  # bronce, plata, esmeralda


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
    ref = t.get("ref")
    if ref:
        # Dónde juegan de verdad los jugadores de la franja en este mismo índice: la mitad del medio y la mediana.
        ax.axhspan(ref["lo"], ref["hi"], color=TENUE, alpha=0.16, lw=0)
        ax.axhline(ref["mediana"], color=TENUE, lw=1.2, ls=(0, (4, 4)))
        ax.annotate(f"{franja}: mediana {ref['mediana']:.0f}, la mitad del medio entre {ref['lo']:.0f} y {ref['hi']:.0f}",
                    (0, ref["hi"]), xytext=(4, 4), textcoords="offset points", color=TEXTO, fontsize=8.5)
    else:
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


def radar(comps: list[dict], titulo: str, segundo: list[dict] | None = None, etiquetas=("", ""),
          franjas: dict | None = None) -> io.BytesIO:
    """Los 7 componentes (0–100) contra la franja. franjas: {franja: {componente: nivel}}, dónde cae el
    jugador mediano de cada franja en tu escala; va una línea punteada por franja."""
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
    if franjas:
        for j, (fr, niv) in enumerate(franjas.items()):
            vf = [(niv.get(c["clave"]) if niv.get(c["clave"]) is not None else 0.5) * 100 for c in comps]
            ax.plot(ang, vf + vf[:1], color=COLOR_FRANJA[j % 3], lw=1.6, ls=(0, (4, 3)), label=f"mediana {fr}")
    else:
        ax.plot(ang, [50] * (n + 1), color=TENUE, lw=1, ls=(0, (4, 4)))
    if segundo:
        v2 = val(segundo)
        ax.fill(ang, v2 + v2[:1], color=SEGUNDO, alpha=0.18)
        ax.plot(ang, v2 + v2[:1], color=SEGUNDO, lw=2, label=etiquetas[1])
    v1 = val(comps)
    ax.fill(ang, v1 + v1[:1], color=ACENTO, alpha=0.22)
    ax.plot(ang, v1 + v1[:1], color=ACENTO, lw=2.2, label=etiquetas[0])
    if segundo or franjas:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=2, facecolor=PANEL, edgecolor=GRILLA,
                  labelcolor=TEXTO, fontsize=9)
    ax.set_title(titulo, color=TEXTO, fontsize=12, pad=24)
    return _png(fig)


ABREV = {"Hierro–Bronce": "H–B", "Plata–Oro": "P–O", "Platino–Esmeralda": "P–E"}


def _fmt(x: float | None, dec: int, signo: bool = False) -> str:
    if x is None:
        return "—"
    t = f"{abs(x):,.{dec}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return ("+" if signo and x > 0 else "−" if x < 0 else "") + t


def franjas(filas: list[dict], titulo: str) -> io.BytesIO:
    """Contra cada franja: una fila por métrica con tu valor y la mediana de las tres franjas.
    Cada fila tiene su propia escala (son unidades distintas); los números van a la derecha."""
    nombres_fr = list(filas[0]["medianas"])
    n = len(filas)
    fig, ax = _figura(9, 0.62 * n + 1.3)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_xticks([])
    ax.set_yticks(range(n))
    ax.set_yticklabels([f["nombre"] + ("" if f["mejor"] else "  (menos es mejor)") for f in filas], color=TEXTO, fontsize=9.5)
    for s in ax.spines.values():
        s.set_visible(False)
    for i, f in enumerate(filas):
        vals = [f["v"], *f["medianas"].values()]
        # Cada fila tiene su escala, pero nunca menos de ±25 % de la mediana del medio: si no, 0,20 contra
        # 0,23 muertes por minuto ocupaba todo el ancho y parecía tan grande como 300 de oro.
        centro = (min(vals) + max(vals)) / 2
        medio = list(f["medianas"].values())[len(f["medianas"]) // 2]
        mitad = max((max(vals) - min(vals)) / 2 * 1.15, 0 if f["clave"].startswith("dif") else abs(medio) * 0.25, 1e-9)
        lo, hi = centro - mitad, centro + mitad
        x = lambda v: (v - lo) / (hi - lo)
        ax.plot([0, 1], [i, i], color=GRILLA, lw=1.2, zorder=1)
        for j, (fr, med) in enumerate(f["medianas"].items()):
            ax.scatter([x(med)], [i], marker="|", s=320, lw=3, color=COLOR_FRANJA[j], zorder=2)
        ax.scatter([x(f["v"])], [i], s=90, color=ACENTO, edgecolor=FONDO, lw=1.5, zorder=3)
        signo = f["clave"].startswith("dif")
        u = f" {f['unidad']}" if f["unidad"] else ""
        txt = f"vos {_fmt(f['v'], f['dec'], signo)}{u}   " + "   ".join(
            f"{ABREV.get(fr, fr)} {_fmt(m, f['dec'], signo)}" for fr, m in f["medianas"].items())
        ax.annotate(txt, (1.03, i), xycoords=("axes fraction", "data"), va="center", color=TENUE, fontsize=8.5)
    marcas = [plt.Line2D([], [], color=ACENTO, marker="o", ls="", ms=8, label="vos")] + [
        plt.Line2D([], [], color=COLOR_FRANJA[j], marker="|", ls="", ms=14, mew=3, label=f"mediana {fr}")
        for j, fr in enumerate(nombres_fr)]
    ax.legend(handles=marcas, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, frameon=False, labelcolor=TEXTO,
              fontsize=8.5, handletextpad=0.3, columnspacing=1.2)
    ax.set_title(titulo, color=TEXTO, fontsize=12, loc="left", pad=30)
    return _png(fig)
