# LDH Stats LoL

Estadísticas de League of Legends de un grupo de amigos, pensadas para mejorar y no solo para rankear. Es la versión LoL de [LDH Stats](https://github.com/luccabruno3z/luccabruno3z.github.io) (Project Reality).

## Cómo está armado

| Pieza | Dónde | Qué hace |
|---|---|---|
| Código | rama `main` | Solo cambia con aprobación. El cron nunca commitea acá. |
| Crudo | rama `datos` | Una partida = un archivo `.json.gz` que no se reescribe. También están `personas.json`, el rango y el estado. |
| Base | `ldh.sqlite` | Se arma de cero en cada corrida desde el crudo, así cualquier corrección se aplica hacia atrás. Se publica para descargar. |
| Web | GitHub Pages | Sitio estático sin build que lee `api/*.json`. |
| Bot | Railway | Lee los mismos JSON por HTTP. Nunca llama a Riot. |

Cada corrida (`python -m ldh`) hace cinco cosas:
1. Resuelve las cuentas nuevas.
2. Anota el rango si cambió.
3. Baja las partidas nuevas desde el 8/1/2026, con tope de partidas y de tiempo.
4. Reconstruye la base.
5. Publica `salida/` (web + `api/` + `descargas/`).

## Reglas de los números

- Ninguna métrica sale sin su **n** y su **intervalo**: Wilson para tasas y bootstrap para medias y diferencias.
- Las filas con menos de `min_partidas` van **al final** de cada tabla y quedan marcadas como "muestra chica".
- Las comparaciones dicen **"ruido"** cuando el intervalo de la diferencia cruza el cero.
- Todo se separa por cola. ARAM nunca se mezcla con la Grieta.
- Las constantes viven en [config/ajustes.json](config/ajustes.json).

## Privacidad

Solo se publican las personas de `personas.json` (rama `datos`), que dieron su OK.

De los demás participantes de cada partida se guardan campeón, rol y stats. Su Riot ID y su PUUID se reemplazan por un id anónimo estable, `anon_<hash>` con la sal `ANON_SALT`.

## Correr en local

Hace falta un `.env` con `RIOT_API_KEY`, `ANON_SALT` y, opcionalmente, `LDH_SEMILLA`: la carpeta `data/` de Coach AI, que se lee y nunca se modifica.

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt -r requirements-bot.txt
git worktree add datos datos
.venv/Scripts/python -m ldh
.venv/Scripts/python -m http.server 8010 -d salida
```

Ver también [docs/RUNBOOK.md](docs/RUNBOOK.md).

LDH Stats LoL no está respaldado por Riot Games y no refleja la opinión de Riot Games ni de nadie involucrado oficialmente en la producción o gestión de League of Legends.
