/* guias.js — guías propias por rol (fase 4). No son guías genéricas, que ya abundan: salen de los
   datos. Qué números tiene un jugador típico de cada franja (la referencia de la fase 3), los
   consejos del rol y quién del grupo lo juega mejor, con qué campeones. Ruta: #/guias/<rol>. */

import { cachedFetch } from './data.js';
import { onRoute } from './router.js';
import { escapeHtml, iconoCampeon, campeon, num } from './utils.js';

const ROLES = ['Top', 'Jungla', 'Mid', 'ADC', 'Support'];
const FRANJAS = ['Hierro–Bronce', 'Plata–Oro', 'Platino–Esmeralda'];
// clave: [etiqueta, decimales, unidad, más es mejor]
const METRICAS = {
    cs10: ['CS a los 10', 0, '', true], cs15: ['CS a los 15', 0, '', true], cs_min: ['CS por minuto', 1, '', true],
    oro_min: ['Oro por minuto', 0, '', true], dif_oro15: ['Oro vs rival a los 15', 0, '', true],
    kp: ['Participación en kills', 0, '%', true], dano: ['% del daño del equipo', 0, '%', true],
    vision_min: ['Visión por minuto', 2, '', true], dif_vision_min: ['Visión/min vs rival', 2, '', true],
    control: ['Wards de control por partida', 1, '', true], obj: ['Participación en dragones, Heraldo y Barón', 0, '%', true],
    muertes_min: ['Muertes por minuto', 3, '', false], kda: ['KDA', 2, '', true],
};
const POR_ROL = {
    Top: ['cs10', 'cs15', 'cs_min', 'dif_oro15', 'oro_min', 'kp', 'dano', 'muertes_min', 'vision_min', 'control', 'obj'],
    Jungla: ['cs10', 'cs15', 'cs_min', 'dif_oro15', 'kp', 'dano', 'muertes_min', 'vision_min', 'control'],
    Mid: ['cs10', 'cs15', 'cs_min', 'dif_oro15', 'oro_min', 'kp', 'dano', 'muertes_min', 'vision_min', 'control', 'obj'],
    ADC: ['cs10', 'cs15', 'cs_min', 'dif_oro15', 'oro_min', 'kp', 'dano', 'muertes_min', 'vision_min', 'control', 'obj'],
    Support: ['vision_min', 'dif_vision_min', 'control', 'kp', 'dano', 'oro_min', 'muertes_min', 'obj'],
};
const COMPONENTES = { combate: 'Combate', efectividad: 'Efectividad', economia: 'Economía', linea: 'Línea', equipo: 'Equipo', consistencia: 'Consistencia' };

let rol = 'Top';

/** Predicho contra real por deciles, con la diagonal (calibración perfecta) y el intervalo de cada punto. */
function grafCalibracion(cal) {
    const S = 260, m = 30, x = (v) => m + v * (S - 2 * m), y = (v) => S - m - v * (S - 2 * m);
    const puntos = cal.map(c => {
        // dif = predicho − real, con su intervalo: el intervalo de lo real es predicho − dif.
        const lo = c.predicho - (c.dif_hi ?? 0), hi = c.predicho - (c.dif_lo ?? 0);
        return `<line x1="${x(c.predicho)}" x2="${x(c.predicho)}" y1="${y(Math.min(lo, hi))}" y2="${y(Math.max(lo, hi))}" class="g-recta"/>
          <circle cx="${x(c.predicho)}" cy="${y(c.real)}" r="4" class="g-punto"><title>Predicho ${num(c.predicho * 100, 0)} %, real ${num(c.real * 100, 0)} % (${c.n} minutos de partida)</title></circle>`;
    }).join('');
    const marcas = [0, 0.25, 0.5, 0.75, 1].map(v => `<text x="${x(v)}" y="${S - 10}" class="g-eje" text-anchor="middle">${v * 100}</text>
        <text x="${m - 6}" y="${y(v) + 4}" class="g-eje" text-anchor="end">${v * 100}</text>`).join('');
    return `<svg class="g-calib" viewBox="0 0 ${S} ${S}" role="img" aria-label="Calibración: lo que predice el modelo contra lo que pasó, por deciles">
      <rect x="${m}" y="${m}" width="${S - 2 * m}" height="${S - 2 * m}" class="g-grilla" fill="none"/>
      <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" class="g-medio"/>${marcas}${puntos}</svg>`;
}

/** Cómo se calcula la probabilidad de ganar (fase 5): para que el gráfico de cada partida tenga respaldo. */
async function modeloVictoria() {
    const d = await cachedFetch('modelo_victoria.json', { silent: true });
    if (!d) return '';
    const v = d.validacion;
    const eq = d.equivalencias.map(e => `<tr><td>${escapeHtml(e.nombre)}</td><td class="num mono">${Math.abs(e.oro) < 200 ? '<span class="dim">casi nada</span>' : `${num(e.oro, 0)} de oro`}</td></tr>`).join('');
    return `<section class="section"><h3>Cómo calculamos la probabilidad de ganar</h3>
      <p>Con el estado de la partida en cada minuto (diferencia de oro, XP, kills, torres, dragones, Barón, inhibidores…) un modelo estima la chance de ganar de cada equipo. Es la idea de la tesis de xPetu, entrenada con las ${num(d.partidas, 0)} partidas del grupo.</p>
      <div class="calib-grid"><div>${grafCalibracion(v.calibracion)}
        <p class="nota" style="text-align:center">Eje horizontal: lo que predice. Vertical: cuántas se ganaron de verdad. Sobre la diagonal es perfecto.</p></div>
        <div><p class="lead">En ${num(v.partidas_prueba, 0)} partidas apartadas, la peor franja se desvía <strong>${num(v.peor_decil * 100, 1)} puntos</strong>. A los 15 minutos acierta el ganador el <strong>${num(v.acierto_15 * 100, 0)} %</strong> de las veces (los estudios dan 72–75 %).</p>
          <h4>Cuánto vale cada cosa, a mitad de partida</h4>
          <div class="table-wrap"><table class="data-table"><tbody>${eq}</tbody></table></div>
          <p class="nota">Lo que suma además del oro que ya da (ese está en la diferencia de oro). Por ejemplo, tener el Barón pesa como ir ${num(d.equivalencias.find(e => e.clave === 'baron')?.oro ?? 0, 0)} de oro arriba.</p></div></div>
    </section>`;
}

/** Qué acompaña a ganar en el rol: cada componente por separado (fase 5). No cambia el Performance. */
async function acompanan(rol) {
    const d = await cachedFetch('acompanan_ganar.json', { silent: true });
    const r = d?.roles?.[rol];
    if (!r) return '';
    const max = Math.max(...r.componentes.map(c => Math.abs(c.dif.hi)), 0.01);
    const filas = r.componentes.map(c => {
        const w = (v) => `${(Math.abs(v) / max) * 50}%`;
        const lado = c.dif.v >= 0 ? 'left:50%' : `right:50%`;
        return `<div class="ag-fila"><span class="ag-nombre">${escapeHtml(c.nombre)}<span class="dim small"> · pesa ${num(c.peso_fijo * 100, 0)} en tu Performance</span></span>
          <span class="ag-pista"><span class="ag-barra ${c.dif.lo > 0 ? 'ag-pos' : c.dif.hi < 0 ? 'ag-neg' : 'ag-nada'}" style="${lado};width:${w(c.dif.v)}"></span><span class="ag-cero"></span></span>
          <span class="ag-num"><strong>${c.dif.v > 0 ? '+' : ''}${num(c.dif.v * 100, 0)} pts</strong> <span class="dim">${num(c.arriba.v * 100, 0)} % contra ${num(c.abajo.v * 100, 0)} %</span></span></div>`;
    }).join('');
    return `<section class="section"><h3>Qué acompaña a ganar · ${rol}</h3>
      <p class="dim">Winrate de las partidas con cada componente en la mitad de arriba de la franja, contra la mitad de abajo (${num(r.n_partidas, 0)} partidas de ${r.n_jugadores} jugadores de referencia).</p>
      <div class="ag-lista">${filas}</div>
      <p class="nota">${escapeHtml(d.nota)} La Efectividad (participación en kills y % del daño) casi no se mueve: son porciones del equipo, y en una derrota tu porción puede ser alta. Probamos aprender los pesos del Performance con estos datos y el KDA se llevaba casi todo (es casi el resultado); por eso quedan los pesos fijos.</p></section>`;
}

async function render() {
    const [ref, consejos, eq] = await Promise.all([cachedFetch('referencia.json'), cachedFetch('consejos.json'), cachedFetch('equipos.json')]);
    const cont = document.getElementById('guias-cuerpo');
    const celda = (fr) => ref.celdas.find(c => c.franja === fr && c.rol === rol);
    const fmt = (k, v) => {
        if (v == null) return '—';
        const [, dec, u] = METRICAS[k];
        return `${k.startsWith('dif') && v > 0 ? '+' : ''}${num(v, dec)}${u ? ' ' + u : ''}`;
    };
    const filas = POR_ROL[rol].map(k => `<tr><td>${escapeHtml(METRICAS[k][0])}${METRICAS[k][3] ? '' : ' <span class="dim">(menos es mejor)</span>'}</td>
        ${FRANJAS.map(fr => `<td class="num mono">${fmt(k, celda(fr)?.medianas?.[k])}</td>`).join('')}</tr>`).join('');
    const quienes = Object.entries(eq.jugadores)
        .filter(([, j]) => (j.roles[rol]?.n || 0) >= eq.min_rol)
        .sort(([, a], [, b]) => b.roles[rol].wr_aj - a.roles[rol].wr_aj).slice(0, 6);
    cont.innerHTML = `
      <nav class="tabs guias-tabs">${ROLES.map(r => `<a href="#/guias/${r}" class="${r === rol ? 'is-active' : ''}">${r}</a>`).join('')}</nav>
      <section class="section"><h3>Los números de cada franja · ${rol}</h3>
        <p class="dim">La mitad de los jugadores de cada franja está por encima de estos números y la mitad por debajo. Es lo que podés apuntar para tu rango y el de arriba.</p>
        <div class="table-wrap"><table class="data-table">
          <thead><tr><th>Métrica</th>${FRANJAS.map(fr => `<th class="num">${fr}<span class="ic">${celda(fr)?.jugadores ?? 0} jugadores</span></th>`).join('')}</tr></thead>
          <tbody>${filas}</tbody></table></div>
        <p class="nota">Medianas por jugador de la muestra de referencia: jugadores al azar de LAS en solo/dúo, con 10+ partidas en ${rol}, bajados el ${escapeHtml(ref.bajada || '—')}. Las victorias y derrotas se ponderan al 50 % (los de Hierro–Bronce venían de bajar). Las diferencias son contra el rival directo de la misma partida.</p></section>
      <section class="section"><h3>Consejos para ${rol}</h3>
        <dl class="glosario">${Object.entries(COMPONENTES).map(([k, n]) => {
            const t = consejos[k]?.[rol] || consejos[k]?.['_'];
            return t ? `<dt>${n}</dt><dd>${escapeHtml(t)}</dd>` : '';
        }).join('')}</dl>
        <p class="nota">Tu perfil te dice cuáles te tocan a vos (Coaching → Cómo sumar), según tus números contra tu franja.</p></section>
      <section class="section"><h3>Quién del grupo juega ${rol}</h3>
        ${quienes.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Jugador</th><th class="num">Winrate ajustado</th><th>Sus campeones (5+ partidas)</th></tr></thead>
          <tbody>${quienes.map(([pid, j]) => `<tr><td><a href="#/jugadores/${encodeURIComponent(pid)}">${escapeHtml(j.nombre)}</a></td>
            <td class="num mono">${num(j.roles[rol].wr_aj * 100, 0)} %<span class="ic">${j.roles[rol].n} partidas</span></td>
            <td>${j.roles[rol].campeones.slice(0, 4).map(c => `<span class="quien">${iconoCampeon(c.id, 22)} ${escapeHtml(campeon(c.id))} <span class="dim">${c.n}</span></span>`).join(' ') || '<span class="dim">—</span>'}</td></tr>`).join('')}</tbody></table></div>`
          : `<p class="empty-state">Nadie del grupo tiene ${eq.min_rol}+ partidas de ${rol}.</p>`}
        <p class="nota">Todas las colas de Grieta. El winrate ajustado suma 10 partidas al 50 % para que nadie quede arriba con 3 de 3.</p></section>
      ${await acompanan(rol).catch(() => '')}
      ${await modeloVictoria().catch(() => '')}`;
}

export function initGuias() {
    onRoute('guias', (param) => {
        if (ROLES.includes(param)) rol = param;
        render().catch(err => {
            console.error('[guias]', err);
            document.getElementById('guias-cuerpo').innerHTML = '<div class="error-state">No se pudieron cargar las guías.</div>';
        });
    });
}
