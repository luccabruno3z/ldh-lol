"""Una corrida de ingesta: cuentas, rango y partidas nuevas hacia la rama `datos`."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .ajustes import AJUSTES, INICIO_HISTORIAL
from .almacen import (Crudo, agregar_foto_rango, ahora_iso, cargar_estado, cargar_personas,
                      guardar_estado)
from .riot.api import RiotAPIError, RiotClient


class SemillaCoachAI:
    """Lee partidas ya bajadas por Coach AI para no gastar API. Solo lectura.

    LDH_SEMILLA apunta a la carpeta data/ de Coach AI; se usa en local, nunca en Actions.
    """

    def __init__(self, carpeta: str | None):
        self.carpeta = Path(carpeta) if carpeta else None
        self.indice: dict = {}
        if self.carpeta and (self.carpeta / "raw" / "wp_cache_index.json").exists():
            self.indice = json.loads((self.carpeta / "raw" / "wp_cache_index.json").read_text(encoding="utf-8"))

    def leer(self, match_id: str, tipo: str) -> dict | None:
        nombre = (self.indice.get(match_id) or {}).get(tipo)
        if not nombre:
            return None
        ruta = self.carpeta / "cache" / nombre
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def resolver_cuentas(api: RiotClient, personas: list[dict], estado: dict) -> None:
    """Riot ID -> PUUID y plataforma. Lo resuelto queda en estado.json."""
    for persona in personas:
        for cuenta in persona["cuentas"]:
            rid = cuenta["riot_id"]
            ya = estado["cuentas"].get(rid)
            if ya and ya.get("puuid"):
                continue
            nombre, _, tag = rid.rpartition("#")
            try:
                acc = api.account_by_riot_id(nombre, tag)
                puuid = acc["puuid"]
                plataforma = cuenta.get("plataforma") or api.active_region(puuid) or "la2"
                estado["cuentas"][rid] = {"puuid": puuid, "plataforma": plataforma,
                                          "persona": persona["id"], "resuelta": ahora_iso()}
                print(f"  {rid}: resuelta ({plataforma})")
            except RiotAPIError as exc:
                estado["cuentas"][rid] = {"puuid": None, "persona": persona["id"], "error": str(exc),
                                          "intento": ahora_iso()}
                print(f"  {rid}: NO se pudo resolver ({exc.status})")


def correr(semilla: str | None = None) -> dict:
    t0 = time.monotonic()
    api = RiotClient()
    personas = cargar_personas()
    estado = cargar_estado()
    crudo = Crudo()
    sem = SemillaCoachAI(semilla or os.environ.get("LDH_SEMILLA"))

    print("Cuentas…")
    resolver_cuentas(api, personas, estado)
    guardar_estado(estado)
    # En el orden de personas.json (y solo las que siguen ahí: sacar a alguien lo deja de bajar).
    cuentas = [(c["riot_id"], estado["cuentas"][c["riot_id"]]) for p in personas for c in p["cuentas"]
               if (estado["cuentas"].get(c["riot_id"]) or {}).get("puuid")]
    vinculados = {c["puuid"] for _, c in cuentas}

    print("Rango…")
    for rid, c in cuentas:
        try:
            if agregar_foto_rango(c["puuid"], api.ranked_entries(c["plataforma"], c["puuid"])):
                print(f"  {rid}: rango nuevo")
        except RiotAPIError as exc:
            print(f"  {rid}: rango no disponible ({exc.status})")

    print("Partidas…")
    tope = int(os.environ.get("LDH_TOPE", AJUSTES["tope_partidas_por_corrida"]))
    tope_seg = int(os.environ.get("LDH_TOPE_SEG", AJUSTES["tope_segundos_por_corrida"]))
    inicio_corrida = int(time.time())
    nuevas = de_semilla = salteadas = 0
    pendientes_total = 0
    for rid, c in cuentas:
        puuid = c["puuid"]
        desde = max(estado["cursores"].get(puuid, 0), INICIO_HISTORIAL)
        try:
            ids = api.match_ids(c["plataforma"], puuid, start_time=desde)
        except RiotAPIError as exc:
            print(f"  {rid}: no pude listar partidas ({exc.status})")
            continue
        pendientes = [m for m in ids if not crudo.tiene(m) and m not in estado["salteadas"]]
        completas = True
        for match_id in pendientes:  # más recientes primero: lo útil llega antes
            if nuevas + salteadas >= tope or time.monotonic() - t0 > tope_seg:
                completas = False
                break
            match = sem.leer(match_id, "match")
            timeline = sem.leer(match_id, "timeline") if match else None
            if match:
                de_semilla += 1
            else:
                try:
                    match = api.match(match_id)
                    timeline = api.timeline(match_id)
                except RiotAPIError as exc:
                    if exc.status == 404:
                        estado["salteadas"][match_id] = "404"
                        salteadas += 1
                        continue
                    print(f"  {match_id}: error {exc.status}; queda para la próxima")
                    completas = False
                    continue
            info = match.get("info", {})
            remake = any(p.get("gameEndedInEarlySurrender") for p in info.get("participants", []))
            if remake:
                estado["salteadas"][match_id] = "remake"
                salteadas += 1
                continue
            crudo.guardar(match, timeline, vinculados)
            nuevas += 1
        if completas:
            # Margen de una hora por partidas que terminaron justo durante la corrida.
            estado["cursores"][puuid] = inicio_corrida - 3600
        else:
            pendientes_total += 1
        print(f"  {rid}: {len(ids)} listadas, {len(pendientes)} pendientes"
              f"{'' if completas else ' (sigue en la próxima corrida)'}")
        guardar_estado(estado)

    resumen = {"nuevas": nuevas, "de_semilla": de_semilla, "salteadas": salteadas,
               "cuentas_con_pendientes": pendientes_total, "llamadas_api": api.llamadas,
               "segundos": round(time.monotonic() - t0)}
    estado["ultima_ingesta"] = {"t": ahora_iso(), **resumen}
    guardar_estado(estado)
    print("Resumen:", resumen)
    return resumen
