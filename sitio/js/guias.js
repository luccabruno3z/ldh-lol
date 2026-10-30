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
        <p class="nota">Todas las colas de Grieta. El winrate ajustado suma 10 partidas al 50 % para que nadie quede arriba con 3 de 3.</p></section>`;
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
