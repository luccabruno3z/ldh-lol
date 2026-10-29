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
