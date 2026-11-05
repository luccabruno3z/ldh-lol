"""Informe de coaching: esquema, validador y armado del JSON publicable.

Lo escribe Claude a pedido de Lucca, desde el paquete de evidencia (ldh/evidencia.py). Las reglas están en
docs/REGLAS_EVIDENCIA.md. El texto no lleva cifras: las cifras salen de las evidencias citadas, que se copian
al informe para que la web y el bot no dependan del paquete.

    python -m ldh validar_informe <borrador.json>     valida y, si pasa, lo deja en datos/informes/<pid>.json
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from . import evidencia as ev
from .ajustes import DATOS

CARPETA = DATOS / "informes"
MAX_PRIORIDADES = 2
CAMPOS_PRIORIDAD = ("titulo", "observacion", "evidencias", "posible_explicacion", "falta_verificar", "ejercicio",
                    "como_revisar")
# Cuentas de partidas ("tus próximas 10") se permiten en el ejercicio y en cómo revisarlo; nada más.
CAMPOS_CON_CUENTAS = ("ejercicio", "como_revisar", "proxima_revision")
PROHIBIDAS = [r"\bcaus(ó|o|a|aste|aron)\b", r"\bpor culpa\b", r"\btilt", r"\brend[ií]s como\b", r"\bmmr\b",
              r"\belo real\b", r"\bapost", r"\bsiempre perd", r"\bnunca gan"]


def _textos(inf: dict):
    yield "resumen", inf.get("resumen", "")
    for i, p in enumerate(inf.get("prioridades", [])):
        for k in CAMPOS_PRIORIDAD:
            if k != "evidencias":
                yield f"prioridades[{i}].{k}", p.get(k, "")
    for i, t in enumerate(inf.get("mantener", [])):
        yield f"mantener[{i}].texto", t.get("texto", "")
    yield "proxima_revision", inf.get("proxima_revision", "")


def validar(inf: dict, paquete: dict, nombres_vinculados: set[str]) -> list[str]:
    errores = []
    ids = {e["id"]: e for e in paquete["evidencias"]}
    if inf.get("persona") != paquete["persona"] or inf.get("modo") != paquete["modo"]:
        errores.append("La persona o el modo no coinciden con el paquete.")
    if inf.get("hash") != paquete["hash"]:
        errores.append("El hash no es el del paquete actual: rearmá el paquete y revisá el informe.")
    prios = inf.get("prioridades") or []
    if not 1 <= len(prios) <= MAX_PRIORIDADES:
        errores.append(f"Tiene que haber entre 1 y {MAX_PRIORIDADES} prioridades.")
    for i, p in enumerate(prios):
        for k in CAMPOS_PRIORIDAD:
            if not p.get(k):
                errores.append(f"prioridades[{i}] no tiene {k}.")
        for e in p.get("evidencias") or []:
            if e not in ids:
                errores.append(f"prioridades[{i}] cita {e!r}, que no está en el paquete.")
            elif ids[e]["tipo"] == "contexto":
                errores.append(f"prioridades[{i}] se apoya en {e!r}, que es contexto (sin intervalo).")
        for e in p.get("momentos") or []:  # minutos del VOD para «cómo revisarlo»: opcionales, del paquete
            if not str(e).startswith("vod.") or e not in ids:
                errores.append(f"prioridades[{i}] cita el momento {e!r}, que no es un momento del VOD del paquete.")
        if len(p.get("momentos") or []) > 3:
            errores.append(f"prioridades[{i}] cita más de 3 momentos del VOD.")
    for i, t in enumerate(inf.get("mantener") or []):
        for e in t.get("evidencias") or []:
            if e not in ids:
                errores.append(f"mantener[{i}] cita {e!r}, que no está en el paquete.")
    for campo, texto in _textos(inf):
        if not isinstance(texto, str):
            errores.append(f"{campo} tiene que ser texto.")
            continue
        base = campo.split(".")[-1]
        numeros = re.findall(r"\d+(?:[.,]\d+)?\s*%?", texto)
        permitidos = base in CAMPOS_CON_CUENTAS
        for x in numeros:
            if not permitidos or "%" in x or "," in x or "." in x or int(re.sub(r"\D", "", x)) > 50:
                errores.append(f"{campo} tiene una cifra ({x.strip()!r}): las cifras van por evidencia, no en el texto.")
        for pat in PROHIBIDAS:
            if re.search(pat, texto, re.I):
                errores.append(f"{campo} usa lenguaje prohibido ({pat}).")
        if "#" in texto:
            errores.append(f"{campo} parece tener un Riot ID: no se nombra a nadie por su cuenta.")
    # Solo se nombra a gente vinculada. Lo que tiene pinta de nombre de cuenta (dígitos o mayúsculas en el medio,
    # como "Fulanito98" o "PeronInLoveWith") y no es de un vinculado ni un campeón se rechaza. Un nombre común
    # ("Juan") no se puede detectar así: eso lo cuida quien escribe.
    texto_total = " ".join(t for _, t in _textos(inf) if isinstance(t, str))
    for palabra in set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]{3,}\b", texto_total)):
        pinta_cuenta = bool(re.search(r"\d", palabra)) or bool(re.search(r"[a-z][A-Z]", palabra))
        if pinta_cuenta and palabra not in nombres_vinculados and not any(palabra in n for n in nombres_vinculados):
            errores.append(f"{palabra!r} parece un nombre de cuenta que no es de un vinculado.")
    return errores


def publicable(inf: dict, paquete: dict) -> dict:
    """El informe con las evidencias citadas copiadas adentro, listo para datos/informes/<pid>.json."""
    citadas = {e for p in inf["prioridades"] for e in p["evidencias"]} | {
        e for t in inf.get("mantener") or [] for e in t.get("evidencias") or []}
    return {**inf, "fecha": inf.get("fecha") or date.today().isoformat(), "nombre": paquete["nombre"],
            "datos_al": paquete.get("datos_al"), "autor": "Claude, a pedido de Lucca",
            "evidencias": [e for e in paquete["evidencias"] if e["id"] in citadas],
            "publicado": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def validar_archivo(ruta: str) -> int:
    inf = json.loads(Path(ruta).read_text(encoding="utf-8"))
    paquete = ev.armar(inf["persona"], inf.get("modo", "solo"))
    nombres = {p["nombre"] for p in (ev._leer("personas.json") or [])}
    # Los campeones también son nombres propios permitidos (con y sin espacios: "Dr. Mundo" y "DrMundo").
    for c in ((ev._leer("campeones.json") or {}).get("campeones") or {}).values():
        nombres |= {c.get("nombre", ""), c.get("key", "")}
    errores = validar(inf, paquete, nombres)
    if errores:
        print("El informe NO pasa:\n- " + "\n- ".join(errores))
        return 1
    CARPETA.mkdir(parents=True, exist_ok=True)
    destino = CARPETA / f"{inf['persona']}.json"
    destino.write_text(json.dumps(publicable(inf, paquete), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Pasa. Guardado en {destino}")
    return 0
