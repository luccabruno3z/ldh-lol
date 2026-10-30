/* fase4.js — bloques del perfil de la fase 4: matchups contra el rival directo, heatmap de muertes y
   kills sobre el minimapa real de Data Dragon, y qué tan predecible es tu jungla. Cada bloque falla solo.
   Heatmap y jungla van separados por lado del mapa (regla 4: juntar azul y rojo inventaba patrones). */

import { state, cachedFetch } from './data.js';
import { escapeHtml, nombreCola, conIntervalo, iconoCampeon, campeon, num } from './utils.js';

const COLAS = ['solo', 'flex', 'normal'];
// Coordenadas de Grieta del Invocador que cubre la imagen map11.png de Data Dragon.
const MAPA = { x0: -120, y0: -120, x1: 14870, y1: 14980 };

function selector(id, etiqueta, valores, actual, nombre = (x) => x) {
    return `<label class="selector">${etiqueta} <select id="${id}">${valores.map(v =>
        `<option value="${escapeHtml(v)}"${v === actual ? ' selected' : ''}>${escapeHtml(nombre(v))}</option>`).join('')}</select></label>`;
}

// ---- Matchups ----

function tablaMatchups(filas) {
    const grandes = filas.filter(f => !f.muestra_chica), chicas = filas.filter(f => f.muestra_chica);
    const fila = (f) => `<tr class="${f.muestra_chica ? 'chica' : ''}">
        <td class="champ">${iconoCampeon(f.rival, 24)}${escapeHtml(campeon(f.rival))}</td><td>${escapeHtml(f.rol)}</td>
        <td class="num mono">${f.n}</td><td class="num">${conIntervalo(f.winrate, 'pct')}</td>
        <td class="num mono">${num(f.wr_aj * 100, 0)} %</td>
        <td class="num">${conIntervalo(f.dif_oro15, 0)}</td></tr>`;
    const cab = '<thead><tr><th>Contra</th><th>Rol</th><th class="num">n</th><th class="num">Winrate</th><th class="num">Ajustado</th><th class="num">Oro vs él a los 15</th></tr></thead>';
    if (!filas.length) return '<p class="empty-state">Sin partidas en esta cola.</p>';
    return `${grandes.length ? `<div class="table-wrap"><table class="data-table">${cab}<tbody>${grandes.slice(0, 15).map(fila).join('')}</tbody></table></div>`
        : '<p class="dim">Ningún rival se repite 5 veces o más en esta cola.</p>'}
      ${chicas.length ? `<details class="plegable"><summary>${chicas.length} rivales con muestra chica</summary>
        <div class="table-wrap"><table class="data-table">${cab}<tbody>${chicas.slice(0, 40).map(fila).join('')}</tbody></table></div></details>` : ''}`;
}

async function matchups(p, cont) {
    const d = await cachedFetch(`matchups/${encodeURIComponent(p.id)}.json`);
    const colas = COLAS.filter(c => d.tabla.some(f => f.cola === c));
    if (!colas.length) return;
    let cola = colas.sort((a, b) => d.tabla.filter(f => f.cola === b).length - d.tabla.filter(f => f.cola === a).length)[0];
    cont.innerHTML = `<section class="section"><div class="section-head"><h3>Contra quién</h3>${selector('mu-cola', 'Cola', colas, cola, nombreCola)}</div>
      <div id="mu-tabla">${tablaMatchups(d.tabla.filter(f => f.cola === cola))}</div>
      <p class="nota">El rival es el de tu misma posición en el otro equipo. Ordenado por cantidad de partidas: con menos de ${d.min} contra el mismo campeón no se puede decir nada, por eso van plegados. "Oro vs él" es la diferencia de oro contra ese rival a los 15.</p></section>`;
    cont.querySelector('#mu-cola').addEventListener('change', (e) => {
        cola = e.target.value;
        cont.querySelector('#mu-tabla').innerHTML = tablaMatchups(d.tabla.filter(f => f.cola === cola));
    });
}

// ---- Heatmap ----

function dibujarHeatmap(puntos, filtro) {
    const S = 512, B = 32, celda = S / B;
    const sel = puntos.filter(p => p[6] === filtro.tipo && p[3] === filtro.lado && (filtro.cola === 'todas' || p[4] === filtro.cola)
        && (filtro.fase === 'todas' || (filtro.fase === 'temprana' ? p[0] < 14 : filtro.fase === 'media' ? p[0] >= 14 && p[0] < 25 : p[0] >= 25)));
    const grilla = new Map();
    for (const [, x, y] of sel) {
        const px = ((x - MAPA.x0) / (MAPA.x1 - MAPA.x0)) * S, py = S - ((y - MAPA.y0) / (MAPA.y1 - MAPA.y0)) * S;
        const k = `${Math.floor(px / celda)},${Math.floor(py / celda)}`;
        grilla.set(k, (grilla.get(k) || 0) + 1);
    }
    const max = Math.max(1, ...grilla.values());
    // Solo las celdas de la mitad de arriba: con todas pintadas, el mapa entero quedaba de un color.
    const cuentas = [...grilla.values()].sort((a, b) => a - b);
    const umbral = cuentas.length ? cuentas[Math.floor(cuentas.length / 2)] : 1;
    const color = filtro.tipo === 'muerte' ? 'var(--danger)' : 'var(--success)';
    const celdas = [...grilla].filter(([, n]) => n >= umbral).map(([k, n]) => {
        const [cx, cy] = k.split(',').map(Number);
        const op = 0.25 + 0.65 * ((n - umbral) / Math.max(1, max - umbral));
        return `<rect x="${cx * celda}" y="${cy * celda}" width="${celda}" height="${celda}" fill="${color}" fill-opacity="${op.toFixed(2)}"><title>${n}</title></rect>`;
    }).join('');
    const img = `https://ddragon.leagueoflegends.com/cdn/${state.campeones.version}/img/map/map11.png`;
    return `<svg class="g-mapa" viewBox="0 0 ${S} ${S}" role="img" aria-label="${sel.length} ${filtro.tipo === 'muerte' ? 'muertes' : 'kills'} sobre el minimapa">
        <image href="${img}" width="${S}" height="${S}" opacity="0.55"/>${celdas}</svg>
      <p class="dim">${sel.length} ${filtro.tipo === 'muerte' ? 'muertes' : 'kills'} en este filtro.${sel.length < 30 ? ' Con tan pocas, el mapa dice poco.' : ''}</p>`;
}

async function heatmap(p, cont) {
    const d = await cachedFetch(`heatmap/${encodeURIComponent(p.id)}.json`);
    if (!d.puntos?.length) return;
    const f = { tipo: 'muerte', lado: 'azul', cola: 'todas', fase: 'todas' };
    const pintar = () => { cont.querySelector('#hm-mapa').innerHTML = dibujarHeatmap(d.puntos, f); };
    cont.innerHTML = `<section class="section"><div class="section-head"><h3>Dónde morís y dónde matás</h3></div>
      <div class="hm-filtros">
        ${selector('hm-tipo', 'Ver', ['muerte', 'kill'], f.tipo, v => (v === 'muerte' ? 'Muertes' : 'Kills'))}
        ${selector('hm-lado', 'Lado', ['azul', 'rojo'], f.lado, v => (v === 'azul' ? 'Azul (abajo a la izquierda)' : 'Rojo (arriba a la derecha)'))}
        ${selector('hm-cola', 'Cola', ['todas', ...COLAS], f.cola, v => (v === 'todas' ? 'Todas' : nombreCola(v)))}
        ${selector('hm-fase', 'Momento', ['todas', 'temprana', 'media', 'tardia'], f.fase,
            v => ({ todas: 'Toda la partida', temprana: 'Antes del 14', media: 'Del 14 al 25', tardia: 'Después del 25' })[v])}
      </div>
      <div id="hm-mapa"></div>
      <p class="nota">Cada cuadradito junta las muertes (o kills) que cayeron ahí; cuanto más fuerte el color, más se repite. Va separado por lado porque el mapa no se ve igual desde cada base: mezclarlos inventa patrones (regla 4 del coaching).</p></section>`;
    for (const k of ['tipo', 'lado', 'cola', 'fase']) {
        cont.querySelector(`#hm-${k}`).addEventListener('change', (e) => { f[k] = e.target.value; pintar(); });
    }
    pintar();
}

// ---- Jungla ----

async function jungla(p, cont) {
    const d = await cachedFetch(`jungla/${encodeURIComponent(p.id)}.json`);
    if (!d?.lados) return;
    const lados = ['azul', 'rojo'].filter(l => d.lados[l]);
    const pct = (v) => `${num(v * 100, 0)} %`;
    cont.innerHTML = `<section class="section"><h3>¿Qué tan predecible es tu jungla?</h3>
      <div class="eq-grid">${lados.map(l => {
        const x = d.lados[l];
        const otro = x.buff_habitual === 'azul' ? 'rojo' : 'azul';
        const wrA = x.lado_habitual === 'arriba' ? x.wr_arriba : x.wr_abajo, wrB = x.lado_habitual === 'arriba' ? x.wr_abajo : x.wr_arriba;
        return `<div class="card eq-card"><h4>Lado ${l} <span class="dim">${x.n} partidas</span></h4>
          <p>Arrancás en el <strong>buff ${x.buff_habitual}</strong> el <strong>${pct(x.pct_habitual)}</strong> de las veces
            ${x.predecible ? '<span class="tag loss">predecible</span>' : '<span class="tag">variás</span>'}</p>
          <p class="dim">Arrancando en el ${x.buff_habitual}: ${conIntervalo(wrA, 'pct')} (${wrA.n}) · en el ${otro}: ${conIntervalo(wrB, 'pct')} (${wrB.n})
            ${x.p != null ? `· Fisher p = ${num(x.p, 2)}` : ''}</p></div>`;
      }).join('')}</div>
      <p class="nota">Dónde estás en el minuto 1, esperando el primer campamento. "Predecible" quiere decir que hasta el borde de abajo del intervalo pasa el ${num(d.umbral * 100, 0)} %: el jungla rival puede jugar tu ruta sin verte. Mezclar un poco tiene sentido si el winrate no cambia entre un arranque y el otro. Va por lado porque desde cada base el mapa es distinto.</p></section>`;
}

/** Los tres bloques, cada uno aislado. En la vista de una sola cuenta no se muestran. */
export function bloquesFase4(p, cont) {
    if (p._cuenta) { cont.innerHTML = ''; return; }
    cont.innerHTML = '<div id="f4-jungla"></div><div id="f4-matchups"></div><div id="f4-heatmap"></div>';
    [['jungla', jungla], ['matchups', matchups], ['heatmap', heatmap]].forEach(([n, fn]) =>
        fn(p, cont.querySelector(`#f4-${n}`)).catch(err => console.error(`[${n}]`, err)));
}
