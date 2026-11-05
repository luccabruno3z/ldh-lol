/* rosters.js — los rosters premade (fase 7): quiénes juegan juntos en Flex y Normales y sus métricas de
   proceso, con intervalo y n, contra el resto de las partidas del grupo. */

import { cachedFetch } from './data.js';
import { escapeHtml, num, conIntervalo, como, glos, tagChica, fecha } from './utils.js';
import { evidenciaHtml } from './fase5.js';

const VENTANAS = { semana: 'Última semana', mes: 'Últimas 4 semanas', temporada: 'Temporada' };
const MIN = 10;  // el mismo umbral de muestra chica que el resto del sitio (min_partidas)
const NIVEL = { 'señal': 'win', 'a confirmar': '', ruido: '', 'muestra chica': '' };
const COLA = { flex: 'Flex', normal: 'Normal' };
const sel = { roster: null, ventana: 'temporada' };

/** Cómo se lee cada métrica: proporciones en %, el oro y las placas con signo. */
function valor(k, x, meta) {
    if (!x || x.v == null) return '<span class="dim">—</span>';
    if (meta.tipo === 'prop' || k === 'objetivos') return conIntervalo(x, 'pct');
    if (k === 'oro14') return conIntervalo(x, 0);
    return conIntervalo(x, k === 'vision' ? 2 : 1);
}

function diferencia(k, x, meta) {
    if (!x || x.v == null) return '<span class="dim">—</span>';
    const pct = meta.tipo === 'prop' || k === 'objetivos';
    const f = (v) => (v > 0 ? '+' : '') + (pct ? num(v * 100, 0) : num(v, k === 'vision' ? 2 : k === 'oro14' ? 0 : 1));
    const suf = pct ? ' pts' : '';
    const tag = x.nivel === 'muestra chica' ? tagChica(MIN) : x.nivel ? ` <span class="tag ${NIVEL[x.nivel] ?? ''}">${escapeHtml(x.nivel)}</span>` : '';
    return `<span class="v">${f(x.v)}${suf}</span><span class="ic">${f(x.lo)} a ${f(x.hi)}${suf}</span>${tag}`;
}

/** Una línea de qué mirar: lo que se separa de la referencia, primero lo que pasa la corrección. */
function conclusion(d) {
    const fuera = Object.entries(d.contra_referencia).filter(([, x]) => x.nivel === 'señal' || x.nivel === 'a confirmar');
    if (!fuera.length) return '<p class="conclusion">En la temporada, ninguna métrica de proceso se separa de la referencia: el roster juega como el resto de las partidas del grupo. Con más partidas juntos esto puede cambiar.</p>';
    const txt = fuera.sort(([, a], [, b]) => (a.nivel === 'señal' ? -1 : 1) - (b.nivel === 'señal' ? -1 : 1))
        .map(([k, x]) => `<strong>${escapeHtml(d.metricas[k].nombre.toLowerCase())}</strong> ${x.v > 0 ? 'más alto' : 'más bajo'} que la referencia (${escapeHtml(x.nivel)})`);
    return `<p class="conclusion">Para mirar en la temporada: ${txt.join('; ')}. Es una comparación, no la causa: sirve para elegir qué revisar en los VOD.</p>`;
}

/** Un informe semanal: hasta 2 prioridades con su evidencia y los minutos del VOD que cita. */
function informeHtml(inf) {
    const ev = Object.fromEntries((inf.evidencias || []).map(e => [e.id, e]));
    const lista = (ids) => `<ul class="inf-ev">${(ids || []).map(i => ev[i]).filter(Boolean).map(evidenciaHtml).join('')}</ul>`;
    return `<p class="lead">${escapeHtml(inf.resumen || '')}</p>
      <div class="inf-prios">${inf.prioridades.map((x, i) => `<article class="card inf-prio">
        <h4><span class="inf-num">${i + 1}</span> ${escapeHtml(x.titulo)}</h4>
        <p>${escapeHtml(x.observacion)}</p>
        <details><summary>Ver la evidencia (${x.evidencias.length})</summary>${lista(x.evidencias)}</details>
        <p><strong>Puede ser porque</strong> ${escapeHtml(x.posible_explicacion)}</p>
        <p class="dim"><strong>Falta ver:</strong> ${escapeHtml(x.falta_verificar)}</p>
        <p class="inf-ej"><strong>Para practicar:</strong> ${escapeHtml(x.ejercicio)}</p>
        <p class="dim"><strong>Cómo revisarlo:</strong> ${escapeHtml(x.como_revisar)}</p>
        ${x.momentos?.length ? `<ul class="inf-vod">${x.momentos.map(i => ev[i]).filter(Boolean).map(e => `<li><span class="tag">VOD</span> ${escapeHtml(e.que)}</li>`).join('')}</ul>` : ''}</article>`).join('')}</div>
      ${inf.mantener?.length ? `<h4>Lo que conviene mantener</h4><ul>${inf.mantener.map(t => `<li>${escapeHtml(t.texto)}${t.evidencias?.length ? `<details><summary>evidencia</summary>${lista(t.evidencias)}</details>` : ''}</li>`).join('')}</ul>` : ''}
      ${inf.proxima_revision ? `<p class="dim">Próxima revisión: ${escapeHtml(inf.proxima_revision)}</p>` : ''}`;
}

function informes(d, lista) {
    if (!lista?.length) return '';
    const [ult, ...viejos] = lista;
    return `<section class="section inf"><h3 class="h4">Informe de la semana <span class="dim">· ${escapeHtml(ult.semana)}</span></h3>
      ${informeHtml(ult)}
      ${viejos.length ? `<details><summary>Informes anteriores (${viejos.length})</summary>${viejos.map(v => `<h4>${escapeHtml(v.semana)}</h4>${informeHtml(v)}`).join('')}</details>` : ''}
      <p class="nota">Escrito por ${escapeHtml(ult.autor || 'Claude')} con los datos al ${escapeHtml((ult.datos_al || '').slice(0, 10))}. Cada cifra sale de una evidencia con su intervalo y n; lo que dice "puede ser" es una hipótesis para revisar en los VOD, no un diagnóstico.</p></section>`;
}

function tarjeta(d, inf) {
    const v = d.ventanas[sel.ventana];
    const ref = d.referencia.metricas;
    const filas = Object.entries(d.metricas).map(([k, meta]) => `<tr${k === 'winrate' ? ' class="dim"' : ''}>
        <td>${escapeHtml(meta.nombre)}<span class="ic">${escapeHtml(meta.unidad)}</span></td>
        <td class="num">${valor(k, v.metricas[k], meta)}${v.metricas[k]?.n ? `<span class="ic">n = ${v.metricas[k].n}</span>` : ''}</td>
        <td class="num">${valor(k, ref[k], meta)}</td>
        <td class="num">${k === 'winrate' ? '<span class="dim">solo contexto</span>' : diferencia(k, d.contra_referencia[k], meta)}</td></tr>`).join('');
    const plantel = d.plantel.map(p => `<tr><td><a href="#/jugadores/${encodeURIComponent(p.id)}">${escapeHtml(p.nombre)}</a>${p.nucleo ? ' <span class="tag">núcleo</span>' : ''}</td>
        <td>${escapeHtml(p.rol || '—')}</td><td class="num">${p.partidas}</td></tr>`).join('');
    const ultimas = d.historial.map(h => `<tr><td>${fecha(h.inicio)}</td><td>${COLA[h.cola] || h.cola}</td>
        <td><span class="tag ${h.win ? 'win' : 'loss'}">${h.win ? 'Victoria' : 'Derrota'}</span></td>
        <td class="small">${h.jugadores.map(id => escapeHtml(d.plantel.find(p => p.id === id)?.nombre || id)).join(', ')}</td></tr>`).join('');
    return `<section class="section">
      <div class="section-head"><h2 class="h3">${escapeHtml(d.nombre)}</h2>
        <span class="dim">${d.partidas} partidas juntos · la última ${fecha(d.ultima, false)}</span></div>
      ${conclusion(d)}
      ${informes(d, inf?.informes)}
      <div class="section-head"><h3 class="h4">Métricas de proceso ${glos('g-intervalo', '¿cómo se lee el intervalo?')}</h3>
        <div class="chips-cola" role="group" aria-label="Período">${Object.entries(VENTANAS).map(([k, l]) =>
            `<button type="button" class="chip-cola${k === sel.ventana ? ' is-active' : ''}" data-ventana="${k}" aria-pressed="${k === sel.ventana}">${l} <span class="dim">(${d.ventanas[k].n})</span></button>`).join('')}</div></div>
      ${v.n < MIN ? `<p class="dim">${v.n ? `Solo ${v.n} ${v.n === 1 ? 'partida' : 'partidas'} en este período:` : 'Sin partidas en este período.'} con menos de ${MIN} los números cambian mucho de una partida a otra.</p>` : ''}
      <div class="table-wrap"><table class="data-table tabla-apilable"><thead><tr><th>Métrica</th><th class="num">El roster<span class="ic">${escapeHtml(VENTANAS[sel.ventana].toLowerCase())}</span></th><th class="num">Referencia<span class="ic">${d.referencia.n} partidas</span></th><th class="num">Diferencia<span class="ic">temporada</span></th></tr></thead>
        <tbody>${filas}</tbody></table></div>
      <p class="nota">Referencia: las demás partidas de Flex y Normales del grupo (lados con algún vinculado que no son de un roster). La diferencia es siempre de la temporada entera, con su intervalo del 95 %.</p>
      ${como(`${escapeHtml(d.nota)} Señal: pasa la corrección de Benjamini–Hochberg sobre todas las comparaciones de todos los rosters. A confirmar: el intervalo no toca el cero pero no pasa la corrección. Placas: solo las de antes del minuto 14 (en este parche caen toda la partida). Cierre: de las partidas con 60 % o más de chance al minuto 15 según el modelo, cuántas se ganaron.`)}
      <div class="eq-grid">
        <div><h3 class="h4">Plantel</h3><div class="table-wrap"><table class="data-table tabla-apilable"><thead><tr><th>Jugador</th><th>Rol más jugado</th><th class="num">Partidas</th></tr></thead><tbody>${plantel}</tbody></table></div>
          <p class="nota">Núcleo: los 3 con más partidas en el roster. Una partida cuenta cuando hay 4 o más del plantel en el mismo equipo.</p></div>
        <div><h3 class="h4">Últimas partidas</h3><div class="table-wrap"><table class="data-table tabla-apilable"><thead><tr><th>Fecha</th><th>Cola</th><th>Resultado</th><th>Jugaron</th></tr></thead><tbody>${ultimas}</tbody></table></div></div>
      </div></section>`;
}

export async function renderRosters(cont) {
    const idx = await cachedFetch('roster/index.json', { silent: true });
    const rs = idx?.rosters || [];
    if (!rs.length) {
        cont.innerHTML = '<p class="empty-state">Todavía no hay rosters: hacen falta 10 partidas de Flex o Normales con 4 o más del mismo grupo en el mismo equipo.</p>';
        return;
    }
    if (!rs.some(r => r.id === sel.roster)) sel.roster = rs[0].id;
    const pintar = async () => {
        const [d, inf] = await Promise.all([cachedFetch(`roster/${encodeURIComponent(sel.roster)}.json`),
                                            cachedFetch(`roster/${encodeURIComponent(sel.roster)}/informes.json`, { silent: true })]);
        cont.innerHTML = `<p class="dim">Los grupos que juegan juntos en Flex y Normales, detectados solos por quién juega con quién. Las métricas son de proceso (lo que el equipo controla): con pocas partidas por mes, el winrate casi siempre es ruido.</p>
          ${rs.length > 1 ? `<div class="chips-cola" role="group" aria-label="Roster">${rs.map(r =>
              `<button type="button" class="chip-cola${r.id === sel.roster ? ' is-active' : ''}" data-roster="${escapeHtml(r.id)}" aria-pressed="${r.id === sel.roster}">${escapeHtml(r.nombre)} <span class="dim">(${r.partidas})</span></button>`).join('')}</div>` : ''}
          ${tarjeta(d, inf)}`;
        cont.querySelectorAll('[data-roster]').forEach(b => b.addEventListener('click', () => { sel.roster = b.dataset.roster; pintar(); }));
        cont.querySelectorAll('[data-ventana]').forEach(b => b.addEventListener('click', () => { sel.ventana = b.dataset.ventana; pintar(); }));
    };
    await pintar();
}
