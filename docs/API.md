# Los JSON publicados (`api/`)

Todo lo que muestran la web y el bot sale de estos archivos. Los arma `ldh/publicar.py` en cada corrida y se sirven en
`https://luccabruno3z.github.io/ldh-lol/api/`. `<pid>` es el id de la persona (`personas.json`). Solo hay archivos de
personas vinculadas.

Los modos son `solo` (solo/dúo), `normal` y `todo` (solo, flex y normales). Las colas son `solo`, `flex`, `normal` y `aram`. Toda tasa viene como
`{v, lo, hi, n}` (Wilson) y toda media o diferencia, con su intervalo de bootstrap.

## Generales

| Archivo | Qué tiene | Lo usa |
|---|---|---|
| `personas.json` | Las personas vinculadas: id, nombre, cuentas, partidas, última partida y rango de solo/dúo. | Todo |
| `meta.json` | Cuándo se generó, la última ingesta, cuántas partidas y personas, la versión de Data Dragon. | Web, evidencia |
| `ajustes.json` | Copia de `config/ajustes.json`. | Web |
| `campeones.json` | Nombres y keys de Data Dragon. | Web, bot |
| `recientes.json` | Las partidas nuevas, para el feed del bot. | Bot (`-canal_feed`) |
| `partidas_resumen.json` | Una fila por partida y persona, para competencias. | Bot (`-competencia`) |
| `ldh.sqlite` (release `base`) | La base completa. No está en Pages: se sube al release `base` en cada corrida (https://github.com/luccabruno3z/ldh-lol/releases/download/base/ldh.sqlite). | Descarga |

## Por persona

| Archivo | Qué tiene | Fase |
|---|---|---|
| `perfil/<pid>.json` | Resumen, forma reciente, evolución, rango, cuentas. | 1 |
| `cuenta/<pid>/<n>.json` | El perfil de una sola cuenta (personas con varias). | 1 |
| `historial/<pid>/<página>.json` | El historial paginado. | 1 |
| `roles/<pid>.json` | Rendimiento por rol y cola, ajustado por muestra. | 2 |
| `campeones/<pid>.json` | Campeón por rol, y dentro contra fuera del pool. | 2 |
| `coaching/<pid>.json`, `coaching/normal/<pid>.json`, `coaching/todo/<pid>.json` | Performance, percentiles, primeros 15 minutos, índice y tendencia, por modo. | 3 |
| `matchups/<pid>.json` | Contra cada campeón rival directo. | 4 |
| `heatmap/<pid>.json` | Muertes y kills sobre el minimapa, por lado. | 4 |
| `jungla/<pid>.json` | De qué buff arranca, por lado. | 4 |
| `rachas/<pid>.json` | Winrate según cómo venía (rachas y pausas). | 5 |
| `muertes/<pid>.json` | Caída estimada por muerte, por modo y rol; mapa y las 3 más caras. | 5 |
| `curvas/<pid>.json` | Curva de aprendizaje por campeón. | 5 |
| `pool_objetivo/<pid>.json` | Seguimiento de la pool declarada con `-pool`. | 6 |
| `conversion/<pid>.json` | Ganadas contra esperadas según la probabilidad al minuto 15. | 6 |
| `informes/<pid>.json` | Informe de coaching, si hay. | 6 |

## Del grupo

| Archivo | Qué tiene | Fase |
|---|---|---|
| `rankings/semana.json`, `mes.json`, `temporada.json` | Ranking por período y cola. | 2 |
| `rankings/roles.json` | Ranking por rol contra el rival directo. | 2 |
| `sinergia.json` | Cuánto cambia cada uno con cada amigo, por cola. | 2 |
| `referencia.json`, `consejos.json` | Medianas de la referencia por franja y rol, y consejos. | 3 |
| `rankings/mejora.json` | Quién más mejoró. | 3 |
| `equipos.json` | 5 ideal y fuerzas por rol para el balanceador. | 4 |
| `modelo_victoria.json` | Coeficientes, validación, calibración, equivalencias en oro y `objetivos` (valor de cada objetivo con su intervalo). | 5 y 6 |
| `partida/<match>.json` | Probabilidad del azul por minuto y momentos clave de cada partida. | 5 |
| `rachas/grupo.json`, `curvas/grupo.json` | Lo mismo que por persona, para el grupo. | 5 |
| `acompanan_ganar.json` | Qué componente acompaña a ganar, por rol. | 5 |
| `rankings/companeros.json` | Mejores compañeros (Mantel–Haenszel). | 5 |
| `rankings/duos.json` | Dúos normalizados: juntos contra lo esperado. | 6 |

## Formatos de lo último que se agregó

### `conversion/<pid>.json`

```json
{"modos": {"solo": {"ventaja":    {"n": 155, "ganadas": 120, "esperadas": 119.6, "v": 0.0025, "lo": -0.07, "hi": 0.06,
                                   "contra_grupo": 0.008, "p": 0.81, "p_bh": 0.87, "senal": false, "muestra_chica": false},
                    "pareja": {}, "desventaja": {}}},
 "grupo": {"solo": {"ventaja": {"n": 1277, "ganadas": 977, "esperadas": 982.7, "v": -0.004, "lo": -0.03, "hi": 0.02}}},
 "tramos": {"ventaja": [0.6, 1.01], "pareja": [0.4, 0.6], "desventaja": [-0.01, 0.4]},
 "nota": "…"}
```

`v` es victorias reales menos esperadas por partida. Con `muestra_chica` (menos de 15) no hay `p` ni `senal`.

### `modelo_victoria.json → objetivos`

```json
{"filas": [{"clave": "baron", "nombre": "El Barón activo", "min": 20,
            "dp": {"v": 0.178, "lo": 0.151, "hi": 0.199}, "oro": {"v": 3902, "lo": 3400, "hi": 4574}}],
 "minutos": [10, 15, 20, 25], "reps": 50, "partidas": 6027, "nota": "…"}
```

### `rankings/duos.json`

```json
{"modos": {"todo": [{"a": "ratsqueen", "b": "tgeblaster", "juntos": 118, "ganadas": 41,
                     "real": {"v": 0.347, "lo": 0.27, "hi": 0.44, "n": 118},
                     "sin_a": {}, "sin_b": {}, "esperado": 0.557,
                     "dif": {"v": -0.209, "lo": -0.31, "hi": -0.11}, "p": 0.0005, "p_bh": 0.031,
                     "senal": true, "muestra_chica": false}]},
 "min_juntos": 15, "nota": "…"}
```

### `pool_objetivo/<pid>.json`

`roles.<Rol>` con `campeones`, `desde` y, por modo, `cumplimiento`, `desde_que_la_declaraste` (dentro y fuera, Fisher),
`antes_y_despues` y `campeones` (n, winrate, índice y estado de la curva).
