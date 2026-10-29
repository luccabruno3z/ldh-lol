"""Arma salida/api/*.json desde ldh.sqlite. Solo personas vinculadas."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from . import estadistica as est
from .ajustes import AJUSTES, RAIZ, SALIDA
from .almacen import cargar_estado
from .base import RUTA_BASE, valor_rango
from .coach.static_data import get_static

API = SALIDA / "api"
COLAS_ORDEN = ["solo", "flex", "normal", "aram", "otra"]
ROLES_ORDEN = ["Top", "Jungla", "Mid", "ADC", "Support"]
MIN = AJUSTES["min_partidas"]

# (clave, campo de la fila de Coach AI). Todas son medias por partida con bootstrap.
METRICAS_MEDIA = [
    ("cs_min", "cs_per_min"),
    ("oro_min", "gold_per_min"),
    ("dano_min", "damage_per_min"),
    ("dano_pct", "damage_share"),
    ("vision_min", "vision_per_min"),
    ("kp", "kill_participation"),
]


def _escribir(rel: str, obj) -> None:
    ruta = API / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _bloque(filas: list[dict]) -> dict:
    """KPIs de un grupo de partidas, cada uno con n e intervalo."""
    out = {
        "n": len(filas),
        "winrate": est.wilson(sum(f["win"] for f in filas), len(filas)),
        "kda": est.kda([f["kills"] for f in filas], [f["deaths"] for f in filas],
                       [f["assists"] for f in filas]),
    }
    for clave, campo in METRICAS_MEDIA:
        out[clave] = est.media([f.get(campo) for f in filas])
    out["muestra_chica"] = len(filas) < MIN
    return out


def _tabla(filas: list[dict]) -> list[dict]:
    """Una fila por cola × rol. Las de poca muestra van al final aunque tengan el mejor número."""
    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in filas:
        grupos[(f["cola"], f["rol_ldh"] or "Sin rol")].append(f)
        grupos[(f["cola"], "Todos")].append(f)
    tabla = [{"cola": c, "rol": r, **_bloque(g)} for (c, r), g in grupos.items()]

    def orden(t):
        rol = ROLES_ORDEN.index(t["rol"]) if t["rol"] in ROLES_ORDEN else (-1 if t["rol"] == "Todos" else 9)
        return (COLAS_ORDEN.index(t["cola"]), t["muestra_chica"], rol)

    return sorted(tabla, key=orden)


def _forma(filas: list[dict]) -> dict | None:
    """Últimas N de la cola más jugada contra el resto de esa cola."""
    n_ult = AJUSTES["forma_reciente"]
    por_cola = defaultdict(list)
    for f in filas:
        if f["cola"] in ("solo", "flex", "normal"):
            por_cola[f["cola"]].append(f)
    if not por_cola:
        return None
    cola, del_cola = max(por_cola.items(), key=lambda kv: len(kv[1]))
    del_cola.sort(key=lambda f: f["inicio_ms"], reverse=True)
    ult, resto = del_cola[:n_ult], del_cola[n_ult:]
    comp = {}
    for clave, fn in [("winrate", lambda f: float(f["win"])),
                      ("kda", lambda f: (f["kills"] + f["assists"]) / max(f["deaths"], 1)),
                      ("cs_min", lambda f: f.get("cs_per_min")),
                      ("dano_min", lambda f: f.get("damage_per_min")),
                      ("kp", lambda f: f.get("kill_participation"))]:
        comp[clave] = {"ultimas": est.media([fn(f) for f in ult]), "resto": est.media([fn(f) for f in resto]),
                       "dif": est.diferencia([fn(f) for f in ult], [fn(f) for f in resto])}
    return {
        "cola": cola,
        "n_ultimas": len(ult),
        "n_resto": len(resto),
        "partidas": [{"win": f["win"], "k": f["kills"], "d": f["deaths"], "a": f["assists"],
                      "champ": f["champion_id"], "inicio": f["inicio_ms"]} for f in reversed(ult)],
        "comparacion": comp,
        "nota": "Comparación de una sola persona: la columna de jugadores distintos no aplica.",
    }


def _historial(f: dict, lp: dict | None) -> dict:
    return {
        "id": f["match_id"], "inicio": f["inicio_ms"], "cola": f["cola"], "cuenta": f["riot_id"],
        "champ": f["champion_id"], "rol": f["rol_ldh"], "lado": f["lado"], "win": f["win"],
        "k": f["kills"], "d": f["deaths"], "a": f["assists"], "cs_min": f.get("cs_per_min"),
        "oro": f.get("gold"), "dano": f.get("damage_to_champions"), "vision": f.get("vision_score"),
        "dur": f.get("duration_min"), "parche": f.get("patch"),
        "lp": None if not lp else {"delta": lp["delta"], "exacto": bool(lp["exacto"]),
                                   "tramo": lp["partidas_tramo"]},
    }


def publicar() -> dict:
    if API.exists():
        shutil.rmtree(API)
    db = sqlite3.connect(RUTA_BASE)
    db.row_factory = sqlite3.Row
    estado = cargar_estado()

    filas_por: dict[str, list[dict]] = defaultdict(list)
    for r in db.execute("""
        SELECT f.persona_id, f.datos, f.match_id, f.puuid, c.riot_id, pa.cola, pa.inicio_ms,
               pt.lado, pt.rol AS rol_ldh, pt.team_position, pt.champion_id
        FROM filas f JOIN partidas pa USING(match_id)
        JOIN participantes pt ON pt.match_id=f.match_id AND pt.puuid=f.puuid
        JOIN cuentas c ON c.puuid=f.puuid"""):
        fila = json.loads(r["datos"])
        fila.update({k: r[k] for k in ("persona_id", "match_id", "riot_id", "cola", "inicio_ms",
                                         "lado", "rol_ldh", "team_position", "champion_id")})
        filas_por[r["persona_id"]].append(fila)

    lp = {(r["match_id"], r["riot_id"]): dict(r) for r in db.execute(
        "SELECT l.*, c.riot_id FROM lp_partida l JOIN cuentas c USING(puuid)")}

    rangos: dict[str, dict] = defaultdict(dict)
    for r in db.execute("""SELECT c.persona_id, c.riot_id, r.* FROM rango_fotos r JOIN cuentas c USING(puuid)
                           ORDER BY r.t"""):
        rangos[r["persona_id"]].setdefault(r["riot_id"], {})[r["cola"]] = {
            "tier": r["tier"], "division": r["division"], "lp": r["lp"], "wins": r["wins"],
            "losses": r["losses"], "t": r["t"], "valor": r["valor"]}

    resumen_personas = []
    por_pag = AJUSTES["historial_por_pagina"]
    for p in db.execute("SELECT * FROM personas ORDER BY nombre COLLATE NOCASE"):
        pid = p["id"]
        cuentas = [dict(c) for c in db.execute(
            "SELECT riot_id, principal FROM cuentas WHERE persona_id=? ORDER BY principal DESC, riot_id", (pid,))]
        filas = sorted(filas_por.get(pid, []), key=lambda f: f["inicio_ms"], reverse=True)
        mejor = max(((rid, c["solo"]) for rid, c in rangos[pid].items() if "solo" in c),
                    key=lambda x: x[1]["valor"] or -1, default=None)
        paginas = max(1, -(-len(filas) // por_pag))
        perfil = {
            "id": pid, "nombre": p["nombre"],
            "cuentas": [{**c, "n": sum(f["riot_id"] == c["riot_id"] for f in filas)} for c in cuentas],
            "rango": rangos[pid],
            "n": len(filas),
            "ultima": filas[0]["inicio_ms"] if filas else None,
            "kpis": {"todas": _tabla(filas),
                     **{c["riot_id"]: _tabla([f for f in filas if f["riot_id"] == c["riot_id"]])
                        for c in cuentas if len(cuentas) > 1}},
            "forma": _forma(filas),
            "historial_paginas": paginas,
        }
        _escribir(f"perfil/{pid}.json", perfil)
        for i in range(paginas):
            _escribir(f"historial/{pid}/{i + 1}.json", {
                "pagina": i + 1, "paginas": paginas, "total": len(filas),
                "partidas": [_historial(f, lp.get((f["match_id"], f["riot_id"])))
                             for f in filas[i * por_pag:(i + 1) * por_pag]]})
        resumen_personas.append({
            "id": pid, "nombre": p["nombre"], "cuentas": [c["riot_id"] for c in cuentas], "n": len(filas),
            "ultima": perfil["ultima"],
            "solo": None if not mejor else {k: mejor[1][k] for k in ("tier", "division", "lp", "wins", "losses")},
        })
    _escribir("personas.json", resumen_personas)

    recientes = defaultdict(lambda: {"jugadores": []})
    for r in db.execute("""
        SELECT pa.match_id, pa.inicio_ms, pa.cola, pa.duracion_seg, pt.persona_id, pt.champion_id, pt.rol,
               pt.win, pt.kills, pt.deaths, pt.assists
        FROM partidas pa JOIN participantes pt USING(match_id)
        WHERE pt.persona_id IS NOT NULL AND pa.match_id IN
            (SELECT match_id FROM partidas ORDER BY inicio_ms DESC LIMIT 30)
        ORDER BY pa.inicio_ms DESC"""):
        m = recientes[r["match_id"]]
        m.update({"id": r["match_id"], "inicio": r["inicio_ms"], "cola": r["cola"],
                  "dur": round(r["duracion_seg"] / 60, 1)})
        m["jugadores"].append({"persona": r["persona_id"], "champ": r["champion_id"], "rol": r["rol"],
                               "win": r["win"], "k": r["kills"], "d": r["deaths"], "a": r["assists"]})
    _escribir("recientes.json", list(recientes.values()))

    static = get_static()
    _escribir("campeones.json", {"version": static.version,
                                 "campeones": {cid: {"key": k, "nombre": n} for cid, (k, n) in static.campeones().items()}})
    _escribir("ajustes.json", AJUSTES)
    n_partidas = db.execute("SELECT count(*) FROM partidas").fetchone()[0]
    meta = {
        "generado": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "ultima_ingesta": estado.get("ultima_ingesta"),
        "partidas": n_partidas,
        "personas": len(resumen_personas),
        "ddragon": static.version,
    }
    _escribir("meta.json", meta)
    db.close()

    for ruta in API.rglob("*.json"):  # nada se publica si un JSON no carga
        json.loads(ruta.read_text(encoding="utf-8"))
    print(f"Publicado: {len(resumen_personas)} personas, {n_partidas} partidas -> {API}")
    return meta
