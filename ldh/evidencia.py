"""Paquete de evidencia para un informe de coaching: lo que ya publicó el pipeline, en piezas citables.

No recalcula nada: lee salida/api. Cada evidencia tiene un id estable, su tipo (qué tan fuerte es lo que dice),
su alcance (modo, rol, cuentas), el valor con intervalo y n, un texto ya formateado y sus limitaciones.
El informe cita ids; los números los pinta la web y el bot desde acá, nunca desde el texto del informe.

    python -m ldh evidencia <persona> [solo|normal|todo]
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .ajustes import AJUSTES, RAIZ, SALIDA

API = SALIDA / "api"
CACHE = RAIZ / ".cache" / "evidencia"
AJUSTES_MIN = AJUSTES["min_partidas"]
TIPOS = ("observacion", "asociacion", "estimacion_modelo", "contexto")


def _leer(rel: str) -> dict | None:
    ruta = API / rel
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def _n(x: float | None, dec: int = 0, signo: bool = False, k: float = 1) -> str:
    if x is None:
        return "—"
    v = x * k
    s = f"{abs(v):,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("−" if v < 0 and s.strip("0,.") else "+" if signo and v > 0 else "") + s


def _fmt(v, lo, hi, n=None, dec=0, signo=False, k=1, suf="") -> str:
    base = f"{_n(v, dec, signo, k)}{suf}"
    if lo is not None and hi is not None:
        base += f" ({_n(lo, dec, signo, k)} a {_n(hi, dec, signo, k)}{suf})"
    if isinstance(n, (tuple, list)):
        return base + f", n = {' y '.join(str(x) for x in n)}"
    return base + (f", n = {n}" if n is not None else "")


class Paquete:
    def __init__(self, persona: str, nombre: str, modo: str, extra: dict | None = None):
        self.persona, self.nombre, self.modo = persona, nombre, modo
        self.extra = extra or {}  # el paquete de un roster suma tipo, semana y plantel
        self.items: list[dict] = []

    def add(self, id_: str, tipo: str, que: str, rol: str | None, v=None, lo=None, hi=None, n=None, *,
            dec=0, signo=False, k=1, suf="", prueba: str | None = None, limitaciones: list[str] | None = None,
            extra: dict | None = None) -> None:
        assert tipo in TIPOS
        if tipo != "contexto" and (lo is None or hi is None):
            tipo = "contexto"  # sin intervalo no puede ser prioridad (regla de Sol)
        self.items.append({
            "id": id_, "tipo": tipo, "que": que,
            "alcance": {"modo": self.modo, "rol": rol, "cuentas": "todas"},
            "v": v, "lo": lo, "hi": hi, "n": n,
            "fmt": _fmt(v, lo, hi, n, dec, signo, k, suf) if v is not None else None,
            "prueba": prueba, "limitaciones": limitaciones or [], **(extra or {})})

    def json(self) -> dict:
        cuerpo = {"persona": self.persona, "nombre": self.nombre, "modo": self.modo, **self.extra, "evidencias": self.items}
        h = hashlib.sha256(json.dumps(cuerpo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        meta = _leer("meta.json") or {}
        return {**cuerpo, "hash": h, "datos_al": meta.get("generado") or meta.get("actualizado")}


def _coaching(pk: Paquete, d: dict) -> None:
    franja = d.get("franja")
    for rol, r in (d.get("roles") or {}).items():
        if r.get("sin_referencia") or not r.get("performance"):
            continue
        p = r["performance"]
        pk.add(f"perf.{rol}", "estimacion_modelo", f"Performance en {rol} contra {franja}", rol, p["v"], p["lo"], p["hi"],
               r.get("n"), k=100, limitaciones=["Pesos fijos por componente; mide cómo jugás contra tu franja, no si ganás."])
        for c in r.get("componentes") or []:
            if c.get("sin_dato"):
                continue
            pk.add(f"comp.{rol}.{c['clave']}", "observacion", f"{c['nombre']} (percentil contra {franja})", rol,
                   c["nivel"], c["lo"], c["hi"], r.get("n"), k=100)
        for lado, lista in (("fuerte", r.get("fortalezas")), ("mejorar", r.get("mejorar"))):
            for m in lista or []:
                pk.add(f"met.{rol}.{m['clave']}", "observacion",
                       f"{m['nombre']}: percentil {_n(m['pct'], 0, k=100)} de {franja} (mediana {_n(m['mediana'], m['dec'])})",
                       rol, m["v"], m["lo"], m["hi"], r.get("n"), dec=m["dec"], suf=m.get("unidad") and f" {m['unidad']}" or "",
                       extra={"lado": lado, "consejo_publicado": m.get("consejo"), "nota_publicada": m.get("nota")})
        t = r.get("tendencia")
        if t and t.get("pendiente") is not None:
            pk.add(f"tend.{rol}", "asociacion", f"Tendencia del índice en {rol}, puntos cada 100 partidas ({t.get('veredicto')})",
                   rol, t["pendiente"], t["lo"], t["hi"], t.get("n"), dec=1, signo=True,
                   limitaciones=["El rol está fijo; el campeón no: un cambio de campeones también mueve la tendencia."])
    for modo, por_rol in (d.get("temprano") or {}).items():
        if modo != pk.modo:
            continue
        for rol, t in por_rol.items():
            for clave, m in (t.get("metricas") or {}).items():
                pk.add(f"temp.{rol}.{clave}", "observacion", m["nombre"], rol, m["v"], m["lo"], m["hi"], m.get("n"),
                       dec=m.get("dec", 0), signo=True, limitaciones=["Contra el rival directo de la misma partida."])
            for clave, nombre in (("gana", "Winrate cuando ganás la línea a los 15"), ("pierde", "Winrate cuando la perdés")):
                m = (t.get("linea") or {}).get(clave)
                if m and m.get("v") is not None:
                    pk.add(f"temp.{rol}.linea_{clave}", "asociacion", nombre, rol, m["v"], m["lo"], m["hi"], m.get("n"),
                           k=100, suf=" %")
    for c in d.get("campeones") or []:
        w = c.get("winrate") or {}
        if w.get("v") is None:
            continue
        pk.add(f"camp.{c['campeon_id']}.{c['rol']}", "asociacion",
               f"{c['campeon']} en {c['rol']}: tu winrate menos el de la referencia con ese campeón", c["rol"],
               w["v"], w["lo"], w["hi"], c.get("n"), k=100, signo=True, suf=" pts",
               prueba="ruido" if w.get("ruido") else "señal",
               limitaciones=[f"Referencia: {c.get('jugadores_ref')} jugadores distintos."])


def _pool(pk: Paquete, d: dict) -> None:
    p = ((d or {}).get("pool") or {}).get("colas", {}).get(pk.modo)
    if not p or not p.get("dif"):
        return
    x = p["dif"]
    pk.add("pool.dentro_fuera", "asociacion", "Winrate dentro del pool menos fuera del pool", None, x["v"], x["lo"], x["hi"],
           (p["dentro"]["n"], p["fuera"]["n"]), k=100, signo=True, suf=" pts", prueba=f"Fisher p = {_n(p.get('p'), 3)}",
           limitaciones=[d["pool"].get("regla", ""), "No demuestra que cambiar de campeón cause la diferencia."])


def _rachas(pk: Paquete, d: dict | None) -> None:
    m = ((d or {}).get("modos") or {}).get(pk.modo)
    if not m:
        return
    nombres = {"corta_vs_sigue": "Después de 2 derrotas: cortar menos seguir enseguida",
               "racha_vs_victoria": "Después de 2+ derrotas menos después de ganar",
               "largas_vs_cortas": "Partidas largas de la sesión menos las primeras"}
    for clave, c in (m.get("comparaciones") or {}).items():
        x = c.get("dif") or {}
        if x.get("v") is None:
            continue
        pk.add(f"rachas.{clave}", "asociacion", nombres.get(clave, clave), None, x["v"], x["lo"], x["hi"],
               (x.get("na"), x.get("nb")), k=100, signo=True, suf=" pts",
               prueba=("muestra chica" if c.get("muestra_chica") else "señal" if c.get("senal") else "ruido") + f", p = {_n(c.get('p'), 3)}",
               limitaciones=["Asociación: no mide tilt ni asegura que una pausa lo arregle."])


def _muertes(pk: Paquete, d: dict | None) -> None:
    m = ((d or {}).get("modos") or {}).get(pk.modo)
    if not m:
        return
    for rol, r in (m.get("roles") or {}).items():
        if not r.get("n"):
            continue
        x = r["por_muerte"]
        med = (d.get("mediana_grupo") or {}).get(f"{pk.modo}|{rol}")
        pk.add(f"muertes.{rol}", "estimacion_modelo", "Caída estimada de probabilidad de ganar por muerte", rol,
               x["v"], x["lo"], x["hi"], r["n"], dec=1, k=100, suf=" pts",
               limitaciones=["Estimación del modelo con y sin la muerte; no es la causa demostrada."],
               extra={"por_partida_fmt": f"{_n(r['por_partida'], 0, k=100)} pts por partida"
                                         + (f" (mediana del grupo {_n(med, 0, k=100)})" if med is not None else ""),
                      "con_objetivo_fmt": f"{_n(r['con_objetivo'], 0, k=100)} % con objetivo rival en el minuto siguiente",
                      "fases_fmt": {f: f"{_n(v.get('costo'), 1, k=100)} pts, n = {v['n']}" for f, v in r["fases"].items()}})


def _conversion(pk: Paquete, d: dict | None) -> None:
    m = ((d or {}).get("modos") or {}).get(pk.modo) or {}
    nombres = {"ventaja": "Con ventaja al minuto 15 (60 % o más): victorias reales menos esperadas por partida",
               "desventaja": "Con desventaja al minuto 15 (40 % o menos): victorias reales menos esperadas por partida"}
    for tramo, que in nombres.items():
        x = m.get(tramo) or {}
        if not x.get("n") or x.get("muestra_chica"):
            continue
        pk.add(f"conversion.{tramo}", "estimacion_modelo", que, None, x["v"], x["lo"], x["hi"], x["n"],
               dec=1, k=100, signo=True, suf=" pts",
               prueba=("señal" if x.get("senal") else "ruido") + f" contra el grupo, p BH = {_n(x.get('p_bh'), 3)}",
               limitaciones=["El modelo se entrenó con estas partidas: el grupo da cerca de cero por construcción.",
                             "Es del equipo, no solo de la persona; es una asociación."],
               extra={"ganadas": x["ganadas"], "esperadas": x["esperadas"], "contra_grupo": x.get("contra_grupo")})


def _curvas(pk: Paquete, d: dict | None, nombres: dict) -> None:
    m = ((d or {}).get("modos") or {}).get(pk.modo) or {}
    for c in (m.get("campeones") or [])[:6]:
        a = c.get("ahora") or {}
        if a.get("v") is None:
            continue
        pk.add(f"curva.{c['champ']}.{c['rol']}", "observacion",
               f"{nombres.get(str(c['champ']), c['champ'])} en {c['rol']}: últimas partidas contra tu nivel normal ({c.get('estado')})",
               c["rol"], a["v"], a["lo"], a["hi"], a.get("n"), dec=1, signo=True,
               extra={"partidas_total": c.get("n")})


VOD_PARTIDAS = 5
OBJ_VOD = {"baron": "el Barón", "ancestral": "el Ancestral", "dragon": "un dragón", "heraldo": "el Heraldo",
           "larva": "larvas", "torre": "una torre", "inhib": "un inhibidor"}


def _mmss(t: int) -> str:
    return f"{t // 60000}:{t // 1000 % 60:02d}"


def _vod(pk: Paquete, historial: dict | None) -> None:
    """Los momentos para el VOD de las últimas partidas con timeline, como contexto (no como prioridad):
    sirven para que el «cómo revisar» del informe cite un minuto concreto."""
    hechas = 0
    for h in (historial or {}).get("partidas") or []:
        if hechas >= VOD_PARTIDAS:
            break
        if pk.modo != "todo" and h.get("cola") != pk.modo:
            continue
        d = _leer(f"partida/{h['id']}.json")
        if not d or not d.get("momentos") or pk.persona not in d.get("lados", {}):
            continue
        hechas += 1
        eq = 100 if d["lados"][pk.persona] == "azul" else 200
        for i, x in enumerate(d["momentos"], 1):
            if x["tipo"] == "muerte":
                if x["persona"] != pk.persona:
                    continue
                u = list(dict.fromkeys(x.get("perdidos") or []))
                que = f"{_mmss(x['t'])}: muerte propia" + (f", después el rival tomó {', '.join(OBJ_VOD.get(o, o) for o in u)}" if u else "")
                v = -x["costo"]
            else:
                v = x["delta"] if eq == 100 else -x["delta"]
                k = x["kills"]
                nos, ellos = (k["azul"], k["rojo"]) if eq == 100 else (k["rojo"], k["azul"])
                obj = [f"{'propio' if o['equipo'] == eq else 'rival'}: {OBJ_VOD.get(o['tipo'], o['tipo'])}" for o in x.get("objetivos") or []]
                propia = any(m["persona"] == pk.persona for m in x.get("muertes") or [])
                que = (f"{_mmss(x['desde'])} a {_mmss(x['hasta'])}: la chance del equipo {'sube' if v > 0 else 'baja'}; "
                       f"kills {nos} a {ellos}" + (f"; objetivos {', '.join(obj)}" if obj else "")
                       + ("; incluye una muerte propia" if propia else ""))
            pk.add(f"vod.{h['id']}.{i}", "contexto", f"Momento para el VOD ({'victoria' if h.get('win') else 'derrota'}, "
                   f"{h.get('cola', '')}) · {que}", h.get("rol"), v, dec=0, signo=True, k=100, suf=" pts",
                   limitaciones=["Estimación del modelo; sirve para elegir qué mirar, no es la causa."],
                   extra={"match": h["id"], "t": x["t"]})


def armar(persona: str, modo: str = "solo") -> dict:
    personas = {p["id"]: p for p in (_leer("personas.json") or [])}
    if persona not in personas:
        raise SystemExit(f"No existe la persona {persona!r}. Opciones: {', '.join(sorted(personas))}")
    pk = Paquete(persona, personas[persona]["nombre"], modo)
    ruta = f"coaching/{persona}.json" if modo == "solo" else f"coaching/{modo}/{persona}.json"
    if (c := _leer(ruta)):
        pk.add("contexto.franja", "contexto", f"Franja de referencia: {c.get('franja')} (desde {c.get('fuente_franja')}); "
               f"{c.get('n_modo')} partidas en el modo; rol principal {c.get('rol_principal')}", None)
        _coaching(pk, c)
    _pool(pk, _leer(f"campeones/{persona}.json"))
    _rachas(pk, _leer(f"rachas/{persona}.json"))
    _muertes(pk, _leer(f"muertes/{persona}.json"))
    _conversion(pk, _leer(f"conversion/{persona}.json"))
    champs = {k: v.get("nombre", k) for k, v in ((_leer("campeones.json") or {}).get("campeones") or {}).items()}
    _curvas(pk, _leer(f"curvas/{persona}.json"), champs)
    _vod(pk, _leer(f"historial/{persona}/1.json"))
    return pk.json()


# ---------------------------------------------------------------- informe semanal por roster (fase 7)

def _formato_metrica(k: str, meta: dict, diferencia: bool = False) -> dict:
    """Cómo se escribe cada métrica del roster: proporciones en % (o en pts si es una diferencia)."""
    if meta["tipo"] == "prop" or k == "objetivos":
        return {"dec": 0, "k": 100, "suf": " pts" if diferencia else " %", "signo": diferencia}
    return {"dec": 2 if k == "vision" else 0 if k == "oro14" else 1, "signo": k != "vision" or diferencia}


def _vod_roster(pk: Paquete, sem: dict, nombres: dict) -> None:
    """Los momentos para el VOD de las partidas de la semana, desde el lado del roster (contexto)."""
    for h in sem["partidas"]:
        d = _leer(f"partida/{h['match']}.json")
        if not d or not d.get("momentos"):
            continue
        eq = 100 if h["lado"] == "azul" else 200
        for i, x in enumerate(d["momentos"], 1):
            if x["tipo"] == "muerte":
                if d["lados"].get(x["persona"]) != h["lado"]:
                    continue
                u = list(dict.fromkeys(x.get("perdidos") or []))
                que = (f"{_mmss(x['t'])}: muerte de {nombres.get(x['persona'], x['persona'])}"
                       + (f", después el rival tomó {', '.join(OBJ_VOD.get(o, o) for o in u)}" if u else ""))
                v = -x["costo"]
            else:
                v = x["delta"] if eq == 100 else -x["delta"]
                k = x["kills"]
                nos, ellos = (k["azul"], k["rojo"]) if eq == 100 else (k["rojo"], k["azul"])
                obj = [f"{'propio' if o['equipo'] == eq else 'rival'}: {OBJ_VOD.get(o['tipo'], o['tipo'])}"
                       for o in x.get("objetivos") or []]
                muertos = [nombres.get(m["persona"], m["persona"]) for m in x.get("muertes") or []
                           if d["lados"].get(m["persona"]) == h["lado"]]
                que = (f"{_mmss(x['desde'])} a {_mmss(x['hasta'])}: la chance del equipo {'sube' if v > 0 else 'baja'}; "
                       f"kills {nos} a {ellos}" + (f"; objetivos {', '.join(obj)}" if obj else "")
                       + (f"; {'mueren' if len(muertos) > 1 else 'muere'} {' y '.join(muertos)}" if muertos else ""))
            pk.add(f"vod.{h['match']}.{i}", "contexto", f"Momento para el VOD ({'victoria' if h['win'] else 'derrota'}, "
                   f"{h['cola']}) · {que}", None, v, dec=0, signo=True, k=100, suf=" pts",
                   limitaciones=["Estimación del modelo; sirve para elegir qué mirar, no es la causa."],
                   extra={"match": h["match"], "t": x["t"]})


def armar_roster(rid: str, semana: str | None = None) -> dict:
    """El paquete de un roster para una semana ISO (por defecto, la última con partidas)."""
    d = _leer(f"roster/{rid}.json")
    if not d:
        opciones = ", ".join(f"{r['id']} ({r['nombre']})" for r in (_leer("roster/index.json") or {}).get("rosters", []))
        raise SystemExit(f"No existe el roster {rid!r}. Opciones: {opciones or 'ninguno'}")
    semanas = d.get("semanas") or {}
    semana = semana or next(iter(semanas), None)
    if semana not in semanas:
        raise SystemExit(f"El roster no tiene partidas en la semana {semana!r}. Semanas: {', '.join(semanas) or 'ninguna'}")
    sem = semanas[semana]
    # Nombres de todos los vinculados: en una partida del roster puede jugar alguien de afuera del plantel.
    nombres = {p["id"]: p["nombre"] for p in (_leer("personas.json") or [])} | {p["id"]: p["nombre"] for p in d["plantel"]}
    pk = Paquete(rid, d["nombre"], "roster", {"tipo": "roster", "semana": semana,
                                               "plantel": [p["nombre"] for p in d["plantel"]]})
    ganadas = sum(h["win"] for h in sem["partidas"])
    pk.add("contexto.roster", "contexto", f"Roster {d['nombre']}: {len(d['plantel'])} en el plantel; en la semana "
           f"{semana} jugaron {sem['n']} partidas juntos ({ganadas} ganadas); {d['partidas']} en la temporada", None)
    for k, meta in d["metricas"].items():
        f = _formato_metrica(k, meta)
        if k == "winrate":
            w = sem["metricas"][k]
            pk.add("contexto.winrate", "contexto", "Winrate de la semana (solo contexto: con esta muestra casi siempre es ruido)",
                   None, w["v"], n=w["n"], **f)
            continue
        x = sem["metricas"][k]
        if x.get("n"):
            pk.add(f"semana.{k}", "observacion", f"{meta['nombre']} en la semana ({meta['unidad']})", None,
                   x["v"], x["lo"], x["hi"], x["n"], **f,
                   limitaciones=[f"Muestra chica: menos de {AJUSTES_MIN} partidas."] if x["n"] < AJUSTES_MIN else [])
        t = d["ventanas"]["temporada"]["metricas"][k]
        if t.get("n"):
            pk.add(f"temporada.{k}", "observacion", f"{meta['nombre']} en la temporada ({meta['unidad']})", None,
                   t["v"], t["lo"], t["hi"], t["n"], **f)
        c = d["contra_referencia"].get(k) or {}
        if c.get("v") is not None and c.get("nivel") != "muestra chica":
            pk.add(f"referencia.{k}", "asociacion", f"{meta['nombre']}: temporada del roster menos la referencia "
                   "(las demás partidas de Flex y Normales del grupo)", None, c["v"], c["lo"], c["hi"], (c["n"], c["n_ref"]),
                   **_formato_metrica(k, meta, True), prueba=f"{c['nivel']}, p BH = {_n(c.get('p_bh'), 3)}",
                   limitaciones=["Descriptivo: el roster juega contra otros rivales y en otros horarios que la referencia."])
    _vod_roster(pk, sem, nombres)
    return pk.json()


def guardar_roster(rid: str, semana: str | None = None) -> Path:
    d = armar_roster(rid, semana)
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta = CACHE / f"roster-{rid}-{d['semana']}.json"
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def guardar(persona: str, modo: str = "solo") -> Path:
    d = armar(persona, modo)
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta = CACHE / f"{persona}-{modo}.json"
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def resumen(d: dict) -> str:
    """Una línea por evidencia, para leer rápido sin gastar contexto."""
    lineas = [f"{d['nombre']} · {d.get('semana') or d['modo']} · hash {d['hash']} · {len(d['evidencias'])} evidencias"]
    for e in d["evidencias"]:
        extra = " · ".join(str(e[k]) for k in ("prueba",) if e.get(k))
        lineas.append(f"[{e['tipo'][:5]}] {e['id']}: {e['que']} = {e['fmt'] or '—'}" + (f" · {extra}" if extra else ""))
    return "\n".join(lineas)
