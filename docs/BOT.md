# Comandos del bot

Todos funcionan con `-` y como slash command. Donde dice `[jugador]`, sin jugador usa el tuyo (`-vincular`).
Los modos son `solo`, `normal` y `todo`; sin modo, usa solo/dúo si alcanza y si no `todo`.
Las tarjetas con menús solo las maneja quien las abrió y siguen andando después de un redeploy.

## Empezar

| Comando | Qué hace |
|---|---|
| `-vincular <jugador>` / `-desvincular` | Une tu usuario de Discord con tu jugador del grupo. Vincularse hace públicas tus estadísticas. |
| `-menu` | Panel con botones: tu perfil, buscar, rankings, comparar, tu informe, tu pool y la web. |
| `-ayuda`, `-glosario`, `-tips <rol>` | Ayuda por tema, qué significa cada término y consejos por rol. |
| `-sugerencia <texto>` | Deja una idea o un error. |

## Tu perfil

| Comando | Qué hace |
|---|---|
| `-perfil [jugador]` | Pestañas: resumen, roles, campeones, coaching y partidas; botones por cuenta. |
| `-roles [jugador]`, `-campeones [jugador]` | Por rol y por campeón, con el bloque dentro y fuera del pool. |
| `-sinergia [jugador]` | Con qué amigos rendís distinto. |
| `-grafico [jugador] [evolucion\|tendencia\|radar] [rol]` | Un PNG. |
| `-comparar a b [cola] [rol]` | Dos jugadores, métrica por métrica. |

## Coaching

`-coaching` abre una tarjeta con tres menús (qué ver, rol y modo). Los demás comandos abren esa tarjeta en una vista.

| Comando | Vista |
|---|---|
| `-coaching [jugador] [rol] [modo]` | Todas las vistas en una tarjeta. |
| `-performance` | Tu índice y sus 7 componentes contra tu franja. |
| `-mejora` | Las 3 brechas más grandes como metas en números. |
| `-temprano` | CS, oro y XP a los 10 y 15 contra tu rival directo. |
| `-cierre [jugador] [modo]` | ¿Cerrás las que ibas ganando? Ganadas contra esperadas según la probabilidad al minuto 15. |
| `-rachas` | Tu winrate según cómo venías: rachas y pausas. |
| `-partida [jugador] [n]` | Tu probabilidad de ganar minuto a minuto, con ◀ ▶ para recorrer partidas. |
| `-informe [jugador]` | Tu informe de coaching: dos prioridades con su evidencia. |

Desde el menú de coaching también están los gráficos: contra cada franja, radar, tendencia, winrate en el tiempo, rachas, chances al morir y curva de aprendizaje.

## Pool objetivo

| Comando | Qué hace |
|---|---|
| `-pool [jugador] [rol]` | La tarjeta de la pool: menú de rol, menú de campeones (hasta 6) y link al Pool Designer de Machine LoLing. |
| `-pool agregar <campeón> [rol]` | Suma un campeón que no aparece en el menú. |
| `-pool sacar <campeón> [rol]` | Lo saca. |

Cada uno solo cambia su propia pool. Cambiarla reinicia el seguimiento desde ese día.

## Grupo

| Comando | Qué hace |
|---|---|
| `-top [semana\|mes\|temporada] [cola]` | Ranking por período (winrate ajustado), con menús. |
| `-top_rol [rol] [cola] [ventana]` | Ranking por rol contra el rival directo. |
| `-companeros [modo]` | Quién hace ganar más a los demás. |
| `-duos [modo]` | Dúos: si rinden juntos más que lo que da cada uno por separado. |
| `-mejoraron [modo]` | Quién más mejoró contra su franja. |
| `-competencia <desde> [hasta] [cola]` | Quién rindió mejor entre dos fechas. |
| `-ideal` | El 5 ideal: una persona por rol con 10+ partidas ahí. |
| `-inhouse a, b, …` | Dos equipos parejos con 10 jugadores. |
| `-matchups [jugador]`, `-jungla [jugador]`, `-mapa [jugador]` | Contra cada campeón rival, de qué buff arrancás, dónde morís o matás. |

## Para administradores (Gestionar servidor)

| Comando | Qué hace |
|---|---|
| `-canal_ranking #canal` | Publica el top de la semana los lunes desde las 12 (hora argentina). Sin canal, lo apaga. |
| `-canal_feed #canal` | Publica cada partida nueva del grupo y los ascensos y descensos. |
| `-canal_sugerencias #canal` | Adónde llegan las `-sugerencia`. |

## Agregar un comando

1. La tarjeta va en `bot/ui/` o en el cog. Si tiene menús, que sean DynamicItems y se registren en `bot/main.py`.
2. El JSON se lee con un método de `bot/services/datos.py`.
3. La línea de ayuda va en `bot/cogs/extra.py` y la descripción del slash, en el decorador.
4. Probar sin Discord: armar la tarjeta con `LDH_DATA_URL=http://127.0.0.1:8010/api` y revisar el texto (máximo 4.000 caracteres) y que los `custom_id` no se repitan y tengan como mucho 100 caracteres.
