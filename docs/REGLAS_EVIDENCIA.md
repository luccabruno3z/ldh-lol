# Reglas de evidencia para los informes de coaching

Los informes los escribe Claude a pedido de Lucca, a partir del paquete de evidencia (`python -m ldh evidencia <persona> [modo]`).
Este documento dice qué puede afirmar un informe y con qué palabras. El validador (`python -m ldh validar_informe`) controla la parte que se puede chequear con código. El resto lo cuida quien escribe.

## Flujo
1. `python -m ldh evidencia <persona> [solo|normal|todo]` arma `.cache/evidencia/<persona>-<modo>.json` y muestra una línea por evidencia.
2. Se escribe el borrador, con el esquema de abajo, citando ids del paquete.
3. `python -m ldh validar_informe <borrador.json>`. Si pasa, queda en `datos/informes/<persona>.json`.
4. `python -m ldh publicar` lo copia a `api/informes/`. Commit a `datos` y push solo con el OK de Lucca.

## Tipos de evidencia y lenguaje

| Tipo | Qué es | Cómo se dice | Cómo no se dice |
|---|---|---|---|
| `observacion` | Un promedio tuyo con su intervalo (percentil, oro a los 15, curva de un campeón) | "tus muertes por minuto están en la parte baja de tu franja" | "morís demasiado por mal posicionamiento" |
| `asociacion` | Una diferencia entre dos grupos de partidas (pool, rachas, línea ganada, tendencia, campeón contra referencia) | "se asocia con", "cuando… ganás más" | "te hace ganar", "por eso perdés" |
| `estimacion_modelo` | Lo que calcula un modelo (Performance, caída estimada por muerte) | "según el modelo", "estimado" | "te costó", "perdiste por" |
| `contexto` | Sin intervalo (franja, rol principal) | Se puede mencionar | Nunca es la base de una prioridad |

- **"Ruido"** (el intervalo cruza el cero, o muestra chica) no es una conclusión: se puede usar como "todavía no se ve", nunca como "no te afecta".
- **Percentiles bajos:** un percentil bajo no es un defecto por sí solo. Puede ser el estilo del rol o del campeón (un Support que lleva oro muere más). Si el paquete trae `nota_publicada`, se tiene en cuenta.

## Esquema del borrador
```json
{
  "persona": "lucca", "modo": "solo", "hash": "<del paquete>",
  "resumen": "Una o dos frases, sin cifras.",
  "prioridades": [
    {"titulo": "…", "observacion": "…", "evidencias": ["met.Support.muertes_min", "muertes.Support"],
     "posible_explicacion": "…", "falta_verificar": "…", "ejercicio": "…", "como_revisar": "…",
     "momentos": ["vod.LA2_1633906575.2"]}
  ],
  "mantener": [{"texto": "…", "evidencias": ["comp.Support.economia"]}],
  "proxima_revision": "Cuando tengas unas 20 partidas más."
}
```

## Lo que controla el validador
- Entre 1 y 2 prioridades, cada una con todos sus campos.
- Cada id citado existe en el paquete. Las prioridades no se apoyan en `contexto`.
- `momentos` es opcional: hasta 3 ids `vod.<partida>.<n>` del paquete (los momentos para el VOD de las últimas 5 partidas con timeline), para que «cómo revisarlo» apunte a un minuto concreto. Son contexto: no sostienen la prioridad.
- El hash coincide con el paquete actual. Si cambiaron los datos, el informe se revisa.
- Sin cifras en el texto: ni porcentajes, ni decimales. Solo se aceptan cuentas de partidas (hasta 50) en el ejercicio, en cómo revisarlo y en la próxima revisión. Las cifras las pinta la web desde las evidencias.
- Sin lenguaje causal ni de diagnóstico: "causó", "por culpa", "tilt", "rendís como" (estimar elo está prohibido por Riot), "MMR", apuestas.
- Sin Riot IDs, y sin nombres propios de gente que no se vinculó. Cualquier nombre dudoso se marca para revisarlo a mano.

## Casos conocidos
Se mantienen como pruebas de regresión: Mordekaiser de Lucca, objetivos de Glarrex, BuscoNovia en compañeros. Si un caso conocido no se reproduce, se revisan el cálculo, la ventana, la definición y la conclusión original. **No se ajusta la métrica para que coincida.**

## Privacidad
- El paquete usa el id de persona y el nombre público del sitio. Nunca lleva PUUID, Discord ID ni la sal de anonimización.
- Solo hay informes de personas vinculadas.
- Un informe es una lectura de datos que ya son públicos en el sitio. Si alguien no quiere el suyo, se borra `datos/informes/<persona>.json`.
