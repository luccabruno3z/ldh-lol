/* rosters.js — los rosters de la Virguhouse y de SRX (fase 7). Los declara Lucca desde el bot; acá se ven en dos
   capas: el plantel (cada jugador en su rol, desde sus propias partidas) y el equipo junto (métricas de proceso
   con intervalo y n contra el resto de las partidas del grupo). */

import { cachedFetch } from './data.js';
import { escapeHtml, num, conIntervalo, como, glos, tagChica, fecha, campeon, tierNombre } from './utils.js';
import { evidenciaHtml } from './fase5.js';

const VENTANAS = { semana: 'Última semana', mes: 'Últimas 4 semanas', temporada: 'Temporada' };
const MIN = 10;  // el mismo umbral de muestra chica que el resto del sitio (min_partidas)
const NIVEL = { 'señal': 'win', 'a confirmar': '', ruido: '', 'muestra chica': '' };
const COLA = { flex: 'Flex', normal: 'Normal' };
const sel = { roster: null, ventana: 'temporada' };
const CARPETA = { virguhouse: 'Virguhouse', srx: 'SRX' };
const pct = (v) => (v == null ? '—' : `${num(v * 100, 0)} %`);
const ROLES = ['Top', 'Jungla', 'Mid', 'ADC', 'Support'];

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

/** La capa del plantel: cada jugador en su rol con sus propias partidas (está aunque nunca hayan jugado juntos). */
function plantelHtml(d) {
    const filas = d.plantel.map(p => {
        const er = p.en_rol;
        const r = p.rango ? `${escapeHtml(tierNombre(p.rango.tier))} ${escapeHtml(p.rango.division || '')}` : '<span class="dim">sin rango</span>';
        return `<tr><td><a href="#/jugadores/${encodeURIComponent(p.id)}">${escapeHtml(p.nombre)}</a>${p.estado === 'suplente' ? ' <span class="tag">suplente</span>' : ''}</td>
          <td>${escapeHtml(p.rol || '—')}</td><td>${r}</td>
          <td class="num">${er ? `${er.n}<span class="ic">gana ${pct(er.winrate.v)}</span>` : '<span class="dim">0</span>'}${er?.muestra_chica ? tagChica(MIN) : ''}</td>
          <td class="num">${p.performance ? `${num(p.performance.v * 100, 0)}<span class="ic">${num(p.performance.lo * 100, 0)} a ${num(p.performance.hi * 100, 0)}</span>` : '<span class="dim">—</span>'}</td>
          <td>${(p.campeones || []).map(c => escapeHtml(campeon(c.champ))).join(', ') || '<span class="dim">—</span>'}</td>
          <td class="num">${p.partidas_juntos}</td></tr>`;
    }).join('');
    const faltan = ROLES.filter(r => !d.cobertura?.[r]);
    return `<h3 class="h4">Plantel</h3>
      ${faltan.length ? `<p class="conclusion">Sin titular en ${faltan.join(', ')}.</p>` : ''}
      <div class="table-wrap"><table class="data-table tabla-apilable"><thead><tr><th>Jugador</th><th>Rol</th><th>Rango<span class="ic">solo/dúo</span></th><th class="num">Partidas en el rol</th><th class="num">Performance ${glos('g-performance')}</th><th>Campeones del rol</th><th class="num">Con el equipo</th></tr></thead><tbody>${filas || '<tr><td colspan="7" class="dim">Sin jugadores todavía.</td></tr>'}</tbody></table></div>
      <p class="nota">Cada fila sale de las partidas de ese jugador en su rol (todas las colas), así que está desde el primer día aunque el equipo nunca haya jugado junto. Performance: de solo/dúo, contra su franja de elo. «Con el equipo»: partidas con ${d.juntos}+ del plantel en el mismo lado.</p>`;
}

function equipoHtml(d) {
    if (!d.partidas) {
        return `<h3 class="h4">El equipo junto</h3><p class="empty-state">Todavía no jugaron juntos (${d.juntos}+ del plantel en el mismo equipo, en Flex o Normales). Las métricas del equipo aparecen cuando jueguen; mientras, el plantel de arriba sale de las partidas de cada uno.</p>`;
    }
    const v = d.ventanas[sel.ventana];
    const ref = d.referencia.metricas;
    const filas = Object.entries(d.metricas).map(([k, meta]) => `<tr${k === 'winrate' ? ' class="dim"' : ''}>
        <td>${escapeHtml(meta.nombre)}<span class="ic">${escapeHtml(meta.unidad)}</span></td>
        <td class="num">${valor(k, v.metricas[k], meta)}${v.metricas[k]?.n ? `<span class="ic">n = ${v.metricas[k].n}</span>` : ''}</td>
        <td class="num">${valor(k, ref[k], meta)}</td>
        <td class="num">${k === 'winrate' ? '<span class="dim">solo contexto</span>' : diferencia(k, d.contra_referencia[k], meta)}</td></tr>`).join('');
    const ultimas = d.historial.map(h => `<tr><td>${fecha(h.inicio)}</td><td>${COLA[h.cola] || h.cola}</td>
        <td><span class="tag ${h.win ? 'win' : 'loss'}">${h.win ? 'Victoria' : 'Derrota'}</span></td>
        <td class="small">${h.jugadores.map(id => escapeHtml(d.plantel.find(p => p.id === id)?.nombre || id)).join(', ')}</td></tr>`).join('');
    return `<div class="section-head"><h3 class="h4">El equipo junto: métricas de proceso ${glos('g-intervalo', '¿cómo se lee el intervalo?')}</h3>
        <div class="chips-cola" role="group" aria-label="Período">${Object.entries(VENTANAS).map(([k, l]) =>
            `<button type="button" class="chip-cola${k === sel.ventana ? ' is-active' : ''}" data-ventana="${k}" aria-pressed="${k === sel.ventana}">${l} <span class="dim">(${d.ventanas[k].n})</span></button>`).join('')}</div></div>
      ${conclusion(d)}
      ${v.n < MIN ? `<p class="dim">${v.n ? `Solo ${v.n} ${v.n === 1 ? 'partida' : 'partidas'} en este período:` : 'Sin partidas en este período.'} con menos de ${MIN} los números cambian mucho de una partida a otra.</p>` : ''}
      <div class="table-wrap"><table class="data-table tabla-apilable"><thead><tr><th>Métrica</th><th class="num">El roster<span class="ic">${escapeHtml(VENTANAS[sel.ventana].toLowerCase())}</span></th><th class="num">Referencia<span class="ic">${d.referencia.n} partidas</span></th><th class="num">Diferencia<span class="ic">temporada</span></th></tr></thead>
        <tbody>${filas}</tbody></table></div>
      <p class="nota">Referencia: las demás partidas de Flex y Normales del grupo (lados con algún vinculado que no son de un roster). La diferencia es siempre de la temporada entera, con su intervalo del 95 %.</p>
      ${como(`${escapeHtml(d.nota)} Señal: pasa la corrección de Benjamini–Hochberg sobre todas las comparaciones de todos los rosters. A confirmar: el intervalo no toca el cero pero no pasa la corrección. Placas: solo las de antes del minuto 14 (en este parche caen toda la partida). Cierre: de las partidas con 60 % o más de chance al minuto 15 según el modelo, cuántas se ganaron.`)}
      <h3 class="h4">Últimas partidas juntos</h3><div class="table-wrap"><table class="data-table tabla-apilable"><thead><tr><th>Fecha</th><th>Cola</th><th>Resultado</th><th>Jugaron</th></tr></thead><tbody>${ultimas}</tbody></table></div>`;
}

function tarjeta(d, inf) {
    return `<section class="section">
      <div class="section-head"><h2 class="h3">${escapeHtml(d.nombre)} <span class="tag">${escapeHtml(CARPETA[d.carpeta] || d.carpeta)}</span></h2>
        <span class="dim">${d.plantel.length} en el plantel · ${d.partidas} partidas juntos${d.ultima ? ` · la última ${fecha(d.ultima, false)}` : ''}</span></div>
      ${plantelHtml(d)}
      ${informes(d, inf?.informes)}
      ${equipoHtml(d)}</section>`;
}

function sugerenciasHtml(sug) {
    if (!sug?.length) return '';
    return `<section class="section"><h3 class="h4">Grupos que juegan juntos y todavía no son un roster</h3>
      <p class="dim">Detectados por quién juega con quién en Flex y Normales (10+ partidas con 4+ juntos). Lucca los declara desde el bot con <code>-roster declarar</code>.</p>
      <ul>${sug.map(s => `<li><strong>${escapeHtml(s.nombre)}</strong> <span class="dim">· ${s.partidas} partidas</span><br><span class="small">${s.plantel.map(p => `${escapeHtml(p.nombre)} (${escapeHtml(p.rol || '—')}, ${p.partidas})`).join(' · ')}</span></li>`).join('')}</ul></section>`;
}

export async function renderRosters(cont) {
    const idx = await cachedFetch('roster/index.json', { silent: true });
    const rs = idx?.rosters || [];
    if (!rs.length) {
        cont.innerHTML = `<p class="empty-state">Todavía no hay rosters. Lucca los crea desde el bot con <code>-roster crear</code>.</p>${sugerenciasHtml(idx?.sugerencias)}`;
        return;
    }
    if (!rs.some(r => r.id === sel.roster)) sel.roster = rs[0].id;
    const chips = () => Object.entries(CARPETA).map(([c, nombre]) => {
        const deC = rs.filter(r => (r.carpeta || 'virguhouse') === c);
        return deC.length ? `<div class="roster-carpeta"><span class="dim">${nombre}</span> <div class="chips-cola" role="group" aria-label="Rosters de ${nombre}">${deC.map(r =>
            `<button type="button" class="chip-cola${r.id === sel.roster ? ' is-active' : ''}" data-roster="${escapeHtml(r.id)}" aria-pressed="${r.id === sel.roster}">${escapeHtml(r.nombre)} <span class="dim">(${r.partidas})</span></button>`).join('')}</div></div>` : '';
    }).join('');
    const pintar = async () => {
        const [d, inf] = await Promise.all([cachedFetch(`roster/${encodeURIComponent(sel.roster)}.json`),
                                            cachedFetch(`roster/${encodeURIComponent(sel.roster)}/informes.json`, { silent: true })]);
        cont.innerHTML = `<p class="dim">Los equipos de la Virguhouse y de SRX. Cada uno se ve en dos capas: el plantel, con lo que cada jugador hace en su rol, y el equipo junto, con métricas de proceso de las partidas que juegan juntos (con pocas partidas por mes, el winrate casi siempre es ruido).</p>
          ${chips()}
          ${tarjeta(d, inf)}
          ${sugerenciasHtml(idx.sugerencias)}`;
        cont.querySelectorAll('[data-roster]').forEach(b => b.addEventListener('click', () => { sel.roster = b.dataset.roster; pintar(); }));
        cont.querySelectorAll('[data-ventana]').forEach(b => b.addEventListener('click', () => { sel.ventana = b.dataset.ventana; pintar(); }));
    };
    await pintar();
}
