# Arquitectura

LDH Stats LoL tiene tres piezas: el pipeline arma los datos, la web los muestra y el bot de Discord también.
La web y el bot nunca llaman a Riot: los dos leen los JSON que el pipeline publica en `api/`.

```
Riot API ──► ingesta ──► rama `datos` (crudo inmutable) ──► reconstruir ──► ldh.sqlite
                              ▲                                                │
     release `timelines` ─────┘ (un .tar por mes)                              ▼
                                                                  publicar (fases 2 a 6)
     repo `ldh-lol-metas` (pools que escribe el bot) ─────────────────────────►│
                                                                               ▼
                                        salida/  =  sitio/ + api/*.json + descargas/ldh.sqlite
                                                   │                         │
                                           GitHub Pages (web)         bot en Railway (HTTP)
```

## Dónde vive cada cosa

| Qué | Dónde | Quién escribe |
|---|---|---|
| Código | rama `main` | Solo con aprobación de Lucca. El workflow nunca commitea acá. |
| Crudo de partidas, rango, estado, `personas.json`, referencia, informes | rama `datos` (en local, worktree `datos/`) | El workflow y los informes a mano |
| Timelines | release `timelines`, un `.tar` por plataforma y mes; en local, `timelines/` | El workflow |
| Pools objetivo | repo público `luccabruno3z/ldh-lol-metas`, archivo `pools.json` | El bot, con `GITHUB_TOKEN_METAS` |
| Base | `salida/descargas/ldh.sqlite` | Se rehace de cero en cada corrida |
| JSON publicados | `salida/api/` (GitHub Pages) | `ldh/publicar.py` |
| Caché del modelo y la referencia | `.cache/` (no va a git; en Actions, `actions/cache`) | El pipeline |
| Estado del bot | volumen de Railway (`BOT_DATA_DIR`) | El bot |

## Una corrida (`.github/workflows/actualizar.yml`)

Hoy se lanza a mano (`workflow_dispatch`). El cron está comentado hasta tener la clave personal de Riot.

1. Hace checkout de `main`, de `datos` en `datos/` y de `ldh-lol-metas` en `metas/` (sin token; si falla, sigue).
2. Baja las timelines del release y revisa que la clave de Riot responda.
3. Corre `python -m ldh`, que hace `ingestar`, `reconstruir` y `publicar` en ese orden.
4. Commitea en `datos` (con `git pull --rebase` antes del push) y sube los meses de timelines que cambiaron.
5. Publica `salida/` en Pages.

`concurrency` evita dos corridas a la vez y el tope es de 55 minutos.

## Pipeline (`ldh/`)

| Módulo | Qué hace |
|---|---|
| `__main__.py` | La línea de comandos (ver abajo). |
| `ajustes.py` | Rutas, `.env` y `config/ajustes.json`: todas las constantes salen de ahí. |
| `riot/` | El cliente de la API de Riot, con rate limit y `Retry-After`. |
| `ingesta.py` | Resuelve cuentas nuevas, anota el rango si cambió y baja las partidas nuevas desde el 8/1/2026, con tope de partidas y de tiempo. |
| `almacen.py` | El crudo de la rama `datos`: un archivo por partida que no se reescribe, ids anónimos con `ANON_SALT`. |
| `timelines.py` | Empaqueta y desempaqueta las timelines del release; frena si falta más del 5 %. |
| `base.py` | Rehace `ldh.sqlite` desde el crudo. Si cambia `extract_match_stats`, subir `EXTRACTOR_VERSION`. |
| `coach/` | Extracción de stats por partida, heredada de Coach AI. |
| `estadistica.py` | Wilson, bootstrap, diferencias, Fisher, Benjamini–Hochberg y ajuste por muestra. |
| `publicar.py` | Arma `salida/api/`: perfil, historial y meta, y llama a cada fase. Solo personas vinculadas. Valida todos los JSON antes de terminar. |
| `fase2.py` | Roles, campeones con pool, sinergia y rankings por período y rol. |
| `referencia.py` | La muestra de referencia por franja y rol (`python -m ldh referencia`). |
| `fase3.py` | Coaching: percentiles contra la referencia, Performance, primeros 15 minutos, índice por partida y tendencia. |
| `fase4.py` | Equipos, matchups, heatmaps y jungla. |
| `victoria.py` | El modelo de probabilidad de ganar minuto a minuto. |
| `fase5.py` | Rachas, modelo, caída por muerte, curvas, compañeros, pool objetivo, conversión, valor de los objetivos y dúos normalizados. |
| `evidencia.py`, `informe.py` | Paquete de evidencia y validador de los informes de coaching. |

### Línea de comandos

| Comando | Qué hace |
|---|---|
| `python -m ldh` (o `todo`) | Ingesta, reconstrucción y publicación. |
| `python -m ldh ingestar` / `reconstruir` / `publicar` | Cada paso suelto. `publicar` sirve para probar cambios de cálculo sin gastar API. |
| `python -m ldh referencia [armar]` | Baja la muestra de referencia (horas de API) o solo la reduce a `datos/referencia/`. |
| `python -m ldh timelines empaquetar <carpeta> [--desde <epoch>]` | Arma los `.tar` del release. |
| `python -m ldh timelines desempaquetar <carpeta>` | Los abre en `timelines/`. |
| `python -m ldh evidencia <persona> [solo\|normal\|todo]` | Paquete de evidencia para un informe. |
| `python -m ldh validar_informe <archivo>` | Valida un informe y lo deja en `datos/informes/`. |

Variables de entorno: `RIOT_API_KEY`, `ANON_SALT`, `LDH_SEMILLA` (opcional, la carpeta `data/` de Coach AI, solo lectura), `LDH_CACHE`, `LDH_TIMELINES`, `LDH_METAS`.

## Web (`sitio/`)

Un sitio estático sin build: módulos ES que leen `api/*.json`. `publicar` copia `sitio/` a `salida/`.

| Archivo | Qué hace |
|---|---|
| `index.html`, `css/styles.css` | La página y los estilos: tokens de color para tema claro y oscuro, Montserrat para el texto, Bebas Neue para títulos y Roboto Mono para cifras. |
| `js/main.js`, `js/router.js` | Arranque y rutas por hash (`#/jugadores/<id>/<pestaña>`). |
| `js/data.js` | `cachedFetch` (con caché, pedidos en curso compartidos y 404 silenciosos), los modos y el rol compartido entre bloques del perfil (`rolGuardado`, `elegirRol`, `alCambiarRol`). |
| `js/utils.js` | Formato de números es-AR, `escapeHtml`, `conIntervalo`. |
| `js/inicio.js` | Inicio. |
| `js/jugador.js` | El perfil: pestañas Resumen, Coaching, Roles y campeones, Mapa y jungla, Partidas. Cada bloque falla solo. |
| `js/fase2.js` … `js/fase5.js` | Los bloques del perfil de cada fase. |
| `js/rankings.js` | Rankings: período, rol, dúos, mejores compañeros, quién más mejoró. |
| `js/comparar.js`, `js/equipos.js`, `js/guias.js` | Comparar, Equipos y Guías (referencia, modelo de victoria, valor de los objetivos). |
| `js/graficos.js` | Gráficos SVG propios. |
| `sw.js` | Service worker con caché de los archivos. |

Para probar en local: `python -m ldh publicar` y `python -m http.server 8010 -d salida` (configuración `ldh-lol-web` en `.claude/launch.json`).
Si se edita `sitio/` sin volver a publicar, hay que copiar `sitio/` a `salida/` a mano.

## Bot (`bot/`)

discord.py con comandos híbridos (prefijo `-` y slash). Corre en Railway con el `Dockerfile` propio; `railway.json` solo redeploya cuando cambia `bot/**`, `requirements-bot.txt` o el `Dockerfile`.

| Carpeta | Qué tiene |
|---|---|
| `main.py` | La lista de cogs, el registro de los DynamicItems y la sincronización de slash commands (solo si cambiaron, `slash_huella.txt`). |
| `cogs/` | Los comandos por tema: `perfil`, `coaching`, `rankings`, `fase4`, `feed`, `pool`, `extra`. |
| `ui/` | Tarjetas y vistas con menús y botones. Son DynamicItems: el estado viaja en el `custom_id`, así siguen andando después de un redeploy. |
| `services/datos.py` | Lee `api/` por HTTP (`LDH_DATA_URL`), con caché de 5 minutos y el dato viejo si falla la red. |
| `services/graficos.py` | Los PNG con matplotlib. |
| `services/formato.py` | Números como la web: miles con punto, decimales con coma. |
| `services/metas.py` | Guarda las pools en `ldh-lol-metas` por la API de contenidos de GitHub. |
| `services/storage.py` | `JSONStorage` sobre el volumen. |

Archivos del volumen: `vinculos.json` (Discord ↔ jugador), `canales.json` (ranking, feed, sugerencias), `feed.json`, `sugerencias.json`, `pools.json`, `pools_pendientes.json`, `slash_huella.txt`.

Variables en Railway: `DISCORD_TOKEN`, `GITHUB_TOKEN_METAS`, y opcionales `LDH_DATA_URL`, `METAS_REPO`, `BOT_DATA_DIR`.

Los comandos están en [BOT.md](BOT.md); los JSON que lee, en [API.md](API.md).
