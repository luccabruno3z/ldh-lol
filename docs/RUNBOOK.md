# Runbook

## Secretos

| Dónde | Nombre | Para qué |
|---|---|---|
| Actions | `RIOT_API_KEY` | Clave **personal** de Riot. La de desarrollo vence a las 24 h. |
| Actions | `ANON_SALT` | Sal de los ids anónimos. **No cambiarla nunca**: los ids dejarían de coincidir con el crudo ya guardado. |
| Actions | `DISCORD_WEBHOOK` | Opcional. Avisa cuando una corrida falla. |
| Railway | `DISCORD_TOKEN` | Token del bot. |
| Railway | `LDH_DATA_URL` | Opcional. Por defecto `https://luccabruno3z.github.io/ldh-lol/api`. |

## Prender el cron

1. Pedir una clave personal en developer.riotgames.com: hay que registrar el producto y no tiene vencimiento.
2. Cargarla en el secreto `RIOT_API_KEY`.
3. Descomentar el `schedule` de `.github/workflows/actualizar.yml` (es un cambio en `main`, así que necesita aprobación).

## Sumar o sacar a alguien

- Para sumar a alguien, editar `personas.json` en la rama `datos`. La próxima corrida resuelve el PUUID y baja su historial desde el 8/1/2026.
- Si se suma alguien que ya aparecía en partidas guardadas, se lo reconoce por su id anónimo.
- Al sacar a alguien, deja de publicarse en la corrida siguiente. Su crudo queda con su PUUID real: si pide que se borre, hay que reescribir esos archivos.

## Si una corrida falla

- **"La clave de Riot está vencida"**: renovar `RIOT_API_KEY`.
- **Timeout de 55 min**: bajar `tope_partidas_por_corrida` o `tope_segundos_por_corrida` en `config/ajustes.json`. Lo que no entra se baja en la corrida siguiente.
- **Un JSON no carga**: `publicar` valida todos antes de terminar. Si falla, Pages no se actualiza y el sitio sigue con la versión anterior.
- **Conflicto al pushear a `datos`**: no debería pasar, porque `concurrency` evita dos corridas a la vez. Si pasa, la próxima corrida vuelve a bajar lo que faltó.

## Corregir un cálculo

Corregir el código y correr de nuevo. La base se rehace desde el crudo, así que la corrección se aplica a todo el historial sin volver a bajar nada.

Si cambia `extract_match_stats`, subir `EXTRACTOR_VERSION` en `ldh/base.py`.

## Límites conocidos de los datos

- **La lista de partidas de Riot no siempre llega al 8/1.** En algunas cuentas `match-v5 by-puuid/ids` se corta meses después del inicio de temporada, aunque las partidas viejas sigan existiendo si se piden por id. Medido el 29/10: monarca tiene 830 de 1228 partidas de solo, y mac55 111 de 171. El perfil lo muestra como "N de M guardadas".
- **Remakes donde el vinculado fue el AFK.** Riot le cuenta la derrota, pero acá no entran (remake = `gameEndedInEarlySurrender`). Explica parte de las 1 a 3 derrotas que le faltan a varias cuentas.

## Fase 2: qué se publica y con qué reglas

- `api/roles/<persona>.json`, `api/campeones/<persona>.json` (con el bloque del pool), `api/sinergia.json` y `api/rankings/{semana,mes,temporada,roles}.json`. Los arma `ldh/fase2.py` y las constantes están en `config/ajustes.json` (`ajuste_muestra`, `pool`, `sinergia`, `rankings`).
- Todo va dentro de cada cola. El valor principal es el ajustado por muestra; el real va al lado.
- **Sinergia:** el p se ajusta por Benjamini-Hochberg sobre todos los pares. Con un p crudo, unos 15 de 298 pares salen "significativos" por azar.
- **Jungla:** la participación en objetivos épicos se probó y no discrimina (mediana 94 %). Se mide el oro contra el jungla rival a los 15.
- **Pool:** los meses sin 90 días de historia previa salen marcados como "arranque", porque ahí todo cuenta como fuera del pool.

## Fase 3: referencia y coaching

- **Muestra de referencia:** `python -m ldh referencia` baja jugadores al azar de cada división de solo/dúo (league-v4 entries) y se queda con los que tienen 10+ partidas en su rol principal. Usa 95 de los 100 pedidos cada 2 minutos; si otra herramienta usa la misma clave, el cliente respeta el Retry-After. Se puede cortar y retomar: el crudo queda en `.cache/referencia/` (no va a git) y el avance en `.cache/referencia/estado.json`.
- `python -m ldh referencia armar` reduce ese crudo a `datos/referencia/filas.jsonl.gz` (una fila por partida y jugador, con id anónimo). Eso es lo único que va a la rama `datos`; `publicar` lo lee de ahí.
- **Celdas:** 3 franjas (Hierro–Bronce, Plata–Oro, Platino–Esmeralda) × 5 roles. Una celda con menos de 20 jugadores no da percentiles; el perfil lo dice.
- **La franja de cada persona** sale de su mejor rango actual de solo/dúo. Sin rango, no hay percentiles (sí los primeros 15 minutos).
- **Performance:** 7 componentes, cada uno es un percentil contra la celda; pesos y sigmoide en `config/ajustes.json` (`performance`). El winrate usa Bayes empírico: con 10 partidas por jugador de referencia casi toda la dispersión es azar, así que se estima la dispersión real de la franja y se compara contra esa.
- **Participación en objetivos:** dragones, Heraldo y Barón, sin larvas ni estructuras. Con larvas y estructuras Lucca y Glarrex daban igual (0,35); así reproduce la brecha conocida (0,65 contra 0,42 en solo/dúo desde el 14/08).
- **Contra tu campeón:** sin API. Compara con los desconocidos que jugaron el mismo campeón y rol en las partidas de solo/dúo del grupo, en la misma franja, sacando las partidas donde su rival directo era alguien del grupo.
- **Consejos:** `config/consejos.json`, por componente o métrica y por rol. Solo aparecen cuando el número marca la brecha.
- **Refrescar la referencia:** con la clave personal, volver a correr `python -m ldh referencia` cada tanto (los jugadores ya bajados no se vuelven a pedir).

## Timelines

- No van a git. La copia local está en `./timelines/` y la durable en el release `timelines` del repo, un `.tar` por mes (`timelines-la2-2026-01.tar`).
- El workflow las baja antes de correr (`gh release download`), las abre con `python -m ldh timelines desempaquetar tl-tar` y al final sube solo los meses que cambiaron (`empaquetar --desde`, `gh release upload --clobber`).
- Si faltan las timelines de más del 5 % de las partidas, `reconstruir` se frena en vez de publicar una base incompleta.
- En otra PC: `gh release download timelines -p 'timelines-*.tar' -D tl-tar` y `python -m ldh timelines desempaquetar tl-tar`.
