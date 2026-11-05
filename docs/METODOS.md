# Métodos

Cómo sale cada número. Las constantes están en `config/ajustes.json`. Las decisiones operativas y los límites de los
datos están en [RUNBOOK.md](RUNBOOK.md); las reglas de los informes, en [REGLAS_EVIDENCIA.md](REGLAS_EVIDENCIA.md).

## Reglas que valen para todo

- **n e intervalo siempre.** Tasas con Wilson al 95 %; medias y diferencias con bootstrap (`bootstrap_reps` = 2000,
  semilla 23). Cuando las filas no son independientes (minutos de una misma partida), el bootstrap remuestrea partidas.
- **Comparar con una prueba.** Dos grupos se separan si el intervalo de la diferencia no cruza el cero: "señal" o
  "ruido". Que dos intervalos se toquen no alcanza para decir nada.
- **Muchas comparaciones a la vez → Benjamini–Hochberg.** Rankings de compañeros, sinergia, conversión y dúos.
- **Muestra chica al final.** Con menos de `min_partidas` (10) o el mínimo propio de cada bloque, la fila va al final y
  se marca.
- **Ajuste por muestra.** El winrate ajustado suma `k_tasa` = 10 partidas al 50 %; el KDA, 20 muertes a la mediana del rol.
- **Cada uno contra sí mismo** cuando quien juega peor podría aparecer más en una condición: rachas, compañeros, curvas.
- **Correlación no es causa.** Los textos dicen "se asocia con" y "estimación del modelo", nunca "te hace ganar" ni "tilt".
- **Sin estimar rango (política de Riot).** El Performance se compara solo contra la franja propia.
- **Colas separadas.** ARAM nunca se mezcla con la Grieta.

## Fase 2: roles, campeones, sinergia y rankings

- Todo dentro de cada cola y contra el par correcto: el rival directo de la misma partida o la mediana del grupo en el rol.
- **Pool:** una partida es "del pool" si ese par (campeón, posición) tenía 5+ partidas en los 90 días anteriores.
- **Sinergia:** el winrate con cada amigo contra sin él, con BH sobre todos los pares.

## Fase 3: coaching contra la referencia

- **Referencia:** jugadores al azar de cada división de solo/dúo con 10+ partidas en su rol principal, en 3 franjas ×
  5 roles. Una celda con menos de 20 jugadores no da percentiles.
- **Performance:** 7 componentes, cada uno un percentil contra la celda, con los pesos y la sigmoide de `performance`.
  El winrate usa Bayes empírico (la dispersión real de la franja, sin el azar de 10 partidas).
- **Índice por partida y tendencia:** percentil promedio de la partida contra la franja y el rol (0–100) y su recta,
  en puntos cada 100 partidas, con bootstrap.

## Fase 5: modelo de victoria y lo que depende de él

- **Modelo** (`ldh/victoria.py`): regresión logística sobre el estado azul − rojo en cada minuto:
  - oro, XP, kills y torres, con un coeficiente por tramo de 10 minutos;
  - inhibidores, dragones, alma, larvas, Heraldo, Barón y Ancestral;
  - y el lado.
- **Simetría del modelo.** Cada estado entra también visto desde el rojo, así que el lado mide la ventaja real del azul.
- **Validación.** Se aparta el 20 % de las partidas, no de las filas. Se mide Brier, log-loss, acierto a los 15 y calibración por deciles, por cola y por tramo.
- **Si falla la validación.** Un decil a más de 5 puntos frena todo lo que depende del modelo.
- **Caída estimada por muerte:** el modelo un minuto después, con la muerte y sin ella. "Sin ella" saca la kill, su oro y lo que
  el rival tomó en ese minuto. Es una estimación, no la causa demostrada.
- **Rachas:** estado previo a cada partida y Mantel–Haenszel por persona.
- **Curvas:** índice por partida menos el nivel normal en el rol, según cuántas partidas llevaba con el campeón.
- **Mejores compañeros:** winrate de cada compañero con Q contra sin Q en el mismo período, combinado con Mantel–Haenszel.

## Fase 6

### Pool objetivo

- **Cumplimiento:** qué parte de las últimas 20 partidas del rol fue con la pool (Wilson).
- **Dentro contra fuera desde que se declaró:** la prueba de Fisher.
- **Antes contra después:** la proporción dentro de la pool y el índice.

### Conversión de ventajas (`fase5.conversion`)

- La probabilidad del equipo al minuto 15 (`p15`) sale del modelo. Entran partidas de 16 minutos o más.
- Hay tres tramos: ventaja (p15 ≥ 0,6), pareja y desventaja (p15 ≤ 0,4).
- En cada tramo se mide el residuo: victorias reales menos esperadas (la suma de p15), por partida, con bootstrap.
- El modelo se entrenó con estas partidas, así que el residuo del grupo da ≈ 0 por construcción. Se publica cada uno
  contra el grupo:
  - z = (residuo − residuo del grupo) · n / √Σ p15(1 − p15);
  - corrección BH entre personas, por modo y tramo.
- Con menos de 15 partidas en un tramo no se prueba.
- Es del equipo, no solo de la persona.

### Valor de los objetivos (`fase5.valor_objetivos`)

- Se parte de un estado parejo (todo en cero, sin el término de lado). Δp = σ(peso del objetivo + su oro) − 0,5.
  - El Barón suma 1.500 de oro y la torre 250, que el modelo ve en la diferencia de oro.
- El equivalente en oro es la diferencia de oro que daría el mismo logit en ese tramo.
- El intervalo sale de 50 reentrenamientos con partidas remuestreadas. Se guarda en `.cache/fase5_objetivos.json` y solo se
  recalcula si cambian las partidas.
- Dragones, Heraldo, inhibidores y Barón tienen un solo peso, así que Δp no cambia con el minuto: solo cambia el
  equivalente en oro.
- Es nuestro elo (LAS, de Hierro a Esmeralda) y una estimación, no un experimento.

### Dúos normalizados (`fase5.duos`)

- Entra cada pareja con 15+ partidas en el mismo equipo.
- El período va de la primera a la última partida juntos. En ese período se mide el winrate de cada uno sin el otro (10+ partidas cada uno).
- El esperado es logit(e) = logit(a) + logit(b) − logit(0,5), y se compara con el winrate juntos.
- El intervalo y el p salen de un bootstrap paramétrico: se vuelven a sortear las tres muestras, así que el esperado también
  tiene ruido. Después, BH entre parejas por modo.
- Con menos de 30 partidas juntos es "muestra chica" y no puede dar señal.
- Es una asociación: también pesan la cola, el horario y contra quién juegan cuando van juntos.

## Fase 7

### Momentos para el VOD (`fase5.momentos`)
- Cada partida con timeline suma hasta 6 momentos en `api/partida/<id>.json`, ordenados por tiempo:
  - los 3 tramos entre frames donde más se movió la chance del modelo (2 puntos o más), con las kills de cada lado y los objetivos del tramo;
  - las 3 muertes de vinculados con mayor caída estimada (1 punto o más). Si una cae dentro de un tramo de la lista, va adentro de ese tramo.
- El minuto (mm:ss) es el del primer evento del tramo, para buscarlo en la repetición.
- Los tramos se miden entre frames y no en el minuto redondo: el minuto k·60 000 ms cae unos ms antes del frame k, y el oro de ese minuto quedaría afuera. La curva publicada también se evalúa en cada frame desde la fase 7 (antes el oro entraba con un minuto de atraso y el gráfico no coincidía con la lista). El modelo se sigue entrenando en el minuto redondo; pasarlo a frames pide reentrenarlo.
- Es lo que estima el modelo, no la causa. Sirve para elegir qué mirar.
- El paquete de evidencia suma como `contexto` los momentos de las últimas 5 partidas con timeline de la persona (`vod.<partida>.<n>`). El informe los puede citar en `momentos`.

### Rosters premade (`ldh/roster.py`)
- **Detección.** Grafo de quién juega con quién: cada lado de partida de Flex o Normales con 4+ vinculados suma 1 a cada par. Las comunidades (Louvain de networkx, semilla 1) son los planteles. Louvain pone a cada jugador en una sola comunidad, así que el que juega con varios grupos quedaría afuera de todos: después se suma al plantel a quien jugó 10+ partidas con 3+ del plantel (una pasada; un jugador puede estar en varios rosters). Una partida es del roster con 4+ del plantel en el mismo lado; se publica con 10+ partidas. El id sale de los 3 con más partidas (el núcleo).
- **`config/rosters.json` (opcional):** `{"rosters": [{"id": "r…", "nombre": "…"}, {"id": "srx", "nombre": "SRX", "plantel": ["pid", …]}]}`. Con `nombre` se renombra un roster detectado; con `plantel` se fija a mano (reemplaza a la comunidad que más se le parece).
- **Métricas por partida**, desde la timeline: oro a los 14 del equipo, primer dragón, primer Heraldo, placas antes del 14 (tomadas − cedidas; en este parche hay placas en las 3 torres de cada línea y caen toda la partida, así que contarlas todas mediría quién ganó), visión del equipo por minuto, parte de los objetivos grandes (dragones, Heraldo, Barón, larvas, Ancestral) y cierre (ganadas de las que tenían 60 %+ al 15 según el modelo, evaluado en el frame).
- **Intervalos:** Wilson para proporciones y bootstrap para medias, cada uno con su n. Ventanas: última semana, últimas 4 semanas y temporada, contadas desde la última partida guardada.
- **Referencia:** los demás lados de Flex y Normales con algún vinculado que no son de un roster. Diferencia de medias con bootstrap y p bilateral del bootstrap; BH sobre todas las comparaciones de todos los rosters. Señal, a confirmar o ruido como en el resto del sitio; menos de 10 partidas es muestra chica y no se etiqueta.
- Es descriptivo: el roster juega contra otros rivales y en otros horarios que la referencia. Sirve para elegir qué revisar, no prueba la causa. El winrate va solo como contexto.

## Cómo verificar un cambio de cálculo

1. `python -m ldh publicar` en local y leer los JSON nuevos.
2. Probar con un caso conocido. Si no se reproduce, revisar el cálculo, la ventana y la definición, sin ajustar la
   métrica para que coincida.
3. Revisar la web en claro, oscuro y a 375 px, en los tres modos, sin errores en la consola.
4. Armar las tarjetas del bot contra los datos locales.
