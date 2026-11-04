"""Formato único de números para todas las tarjetas del bot.

Reglas (pase de diseño del 2026-10-29):
- Coma decimal y signo menos de verdad (−), no el guión, para que "−116" no se lea "15-116".
- Rangos como "x a y", nunca "(x–y)": el guión se confundía con el signo.
- Etiqueta y valor separados por dos puntos cuando la etiqueta termina en número ("a los 15: −116").
- Cada bloque: una línea con los valores y abajo, en texto chico (-#), el detalle: real, intervalo y n.
- La muestra chica no se mezcla con el resto: va en una línea final.
"""

from __future__ import annotations

MENOS = "−"


def num(x: float | None, dec: int = 0, signo: bool = False, k: float = 1) -> str:
    if x is None:
        return "—"
    v = x * k
    # Miles con punto y decimales con coma, como la web (toLocaleString es-AR).
    s = f"{abs(v):,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if v < 0 and s.strip("0,."):
        return MENOS + s
    return ("+" if signo and v > 0 else "") + s


def pct(x: float | None, signo: bool = False) -> str:
    """0,483 → '48 %'."""
    return "—" if x is None else f"{num(x, 0, signo, 100)} %"


def pts(x: float | None) -> str:
    """Diferencia entre tasas: +0,15 → '+15 pts'."""
    return "—" if x is None else f"{num(x, 0, True, 100)} pts"


def rango(m: dict | None, dec: int = 0, signo: bool = False, k: float = 1, suf: str = "") -> str:
    """'40 a 57 %' a partir de {'lo':…, 'hi':…}. Vacío si no hay intervalo."""
    if not m or m.get("lo") is None:
        return ""
    return f"{num(m['lo'], dec, signo, k)} a {num(m['hi'], dec, signo, k)}{suf}"


def rango_pct(m: dict | None) -> str:
    return rango(m, 0, False, 100, " %")


def rango_pts(m: dict | None) -> str:
    return rango(m, 0, True, 100, " pts")


def se_separan(a: dict | None, b: dict | None) -> bool:
    """¿El intervalo del 95 % de la diferencia a − b deja afuera al cero? Aproximado desde el intervalo de cada uno
    (se = ancho / 3,92). Es menos exigente que pedir que los dos intervalos no se toquen, que se perdía diferencias
    reales. La misma cuenta que seSeparan en sitio/js/utils.js."""
    if not a or not b or None in (a.get("v"), a.get("lo"), a.get("hi"), b.get("v"), b.get("lo"), b.get("hi")):
        return False
    if a["lo"] > b["hi"] or b["lo"] > a["hi"]:  # si ni se tocan, se separan (cubre los intervalos asimétricos)
        return True
    se = (((a["hi"] - a["lo"]) / 3.92) ** 2 + ((b["hi"] - b["lo"]) / 3.92) ** 2) ** 0.5
    return se > 0 and abs(a["v"] - b["v"]) > 1.96 * se


def chica(items: list[str]) -> str | None:
    """'-# Muestra chica: Mid (2), ADC (6)' o None."""
    return f"-# Muestra chica, sin conclusiones: {', '.join(items)}" if items else None


def cambio(t: dict) -> dict:
    """El cambio de la tendencia a lo largo de las partidas jugadas. Si el JSON publicado es anterior a ese campo,
    se calcula desde la pendiente (puntos cada 100 partidas), así el bot no falla mientras se actualizan los datos."""
    if t.get("cambio"):
        return t["cambio"]
    k = (t.get("n", 1) - 1) / 100
    return {c: (t[c] * k if t.get(c) is not None else None) for c in ("v", "lo", "hi")} | (
        {"v": t["pendiente"] * k} if t.get("pendiente") is not None else {})
