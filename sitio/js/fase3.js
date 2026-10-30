/* fase3.js — bloques de coaching del perfil: Performance, tu juego en una mirada, cómo sumar,
   los primeros 15 minutos y contra tu campeón. Todo sale de coaching/<id>.json; cada bloque
   falla solo. Los percentiles son contra jugadores de tu franja de rango y tu rol en solo/dúo. */

import { state, cachedFetch } from './data.js';
import { escapeHtml, nombreCola, iconoCampeon, campeon, num } from './utils.js';
import { pct, chipConf } from './fase2.js';

const COLAS = ['solo', 'flex', 'normal'];

/** Valor de una métrica con su formato: signo en las diferencias, % donde corresponde. */
function fmt(m, x) {
    if (x == null) return '—';
    const signo = m.clave?.startsWith('dif') && x > 0 ? '+' : '';
    return `${signo}${num(x, m.dec ?? 2)}${m.unidad ? ' ' + m.unidad : ''}`;
}

// En el rango la unidad va una sola vez, al final: "−20 a +13 pts".
const valorIc = (m) => `<span class="v">${fmt(m, m.v)}</span>${m.lo == null ? '' : `<span class="ic">${fmt({ ...m, unidad: '' }, m.lo)} a ${fmt(m, m.hi)}</span>`}`;

/** Barra de percentil con su intervalo sombreado. */
function barra(p, lo, hi, titulo) {
    if (p == null) return '<span class="dim">—</span>';
    const w = (x) => `${Math.max(0, Math.min(100, x * 100))}%`;
    const clase = lo != null && lo > (state.ajustes?.performance?.umbral_fortaleza ?? 0.6) ? 'alto'
        : hi != null && hi < (state.ajustes?.performance?.umbral_debilidad ?? 0.4) ? 'bajo' : '';
    return `<span class="pbar ${clase}" title="${escapeHtml(titulo || '')}" role="img" aria-label="Percentil ${Math.round(p * 100)}">
      ${lo != null ? `<span class="pbar-ic" style="left:${w(lo)};width:${w(hi - lo)}"></span>` : ''}
      <span class="pbar-v" style="left:${w(p)}"></span><span class="pbar-mitad"></span></span>`;
}

const mejorQue = (m) => (m.pct == null ? '' : `mejor que el ${Math.round(m.pct * 100)} %<span class="ic">${Math.round(m.pct_lo * 100)} a ${Math.round(m.pct_hi * 100)}</span>`);

function selector(id, etiqueta, valores, actual, nombre = (x) => x) {
    return `<label class="selector">${etiqueta} <select id="${id}">${valores.map(v =>
        `<option value="${escapeHtml(v)}"${v === actual ? ' selected' : ''}>${escapeHtml(nombre(v))}</option>`).join('')}</select></label>`;
}

// ---- Performance ----

function performance(r, franja) {
    const pf = r.performance;
    const lectura = pf.como
        ? `Rendís como un <strong>${escapeHtml(pf.como)}</strong> típico en este rol${pf.pisan.length ? ` (aunque con este intervalo también podría ser ${pf.pisan.map(escapeHtml).join(' o ')})` : ''}.`
        : '';
    const franjas = Object.entries(pf.por_franja).map(([f, x]) =>
        `<div class="perf-franja${f === franja ? ' actual' : ''}"><span class="dim">contra ${escapeHtml(f)}</span> <span class="v">${num(x.v * 100, 0)}</span><span class="ic">${num(x.lo * 100, 0)} a ${num(x.hi * 100, 0)}</span></div>`).join('');
    return `<div class="perf">
        <div class="perf-num"><span class="perf-v">${num(pf.v * 100, 0)}</span><span class="dim">/100</span>
          <span class="ic">${num(pf.lo * 100, 0)} a ${num(pf.hi * 100, 0)}</span></div>
        <div><p class="lead">${lectura}</p><div class="perf-franjas">${franjas}</div></div>
      </div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Componente</th><th>Nivel en tu franja</th><th class="num">Peso</th><th class="num">Aporta</th><th class="num">Puede sumar</th></tr></thead>
        <tbody>${r.componentes.map(c => `<tr>
          <td>${escapeHtml(c.nombre)}${c.sin_dato ? ' <span class="tag">sin dato</span>' : ''}<div class="dim small">${c.metricas.map(k => escapeHtml(r.metricas[k]?.nombre || k)).join(' · ')}</div></td>
          <td>${c.sin_dato ? '<span class="dim">cuenta como 50</span>' : `${barra(c.nivel, c.lo, c.hi)} <span class="mono">${num(c.nivel * 100, 0)}</span><span class="ic">${num(c.lo * 100, 0)} a ${num(c.hi * 100, 0)}</span>`}</td>
          <td class="num mono">${num(c.peso * 100, 0)}</td>
          <td class="num mono">${num(c.aporte * 100, 1)}</td>
          <td class="num mono">${num(c.margen * 100, 1)}</td></tr>`).join('')}</tbody></table></div>
      <p class="nota">Cada componente es tu percentil contra ${r.n_ref} jugadores de ${escapeHtml(franja)} en el mismo rol (50 = la mitad de tu franja), y el Performance es la suma con los pesos. Con pocas partidas el índice se acerca a 50: con ${r.n} partidas pesa ${num(100 / (1 + Math.exp(-(r.n - (state.ajustes?.performance?.penalizacion_centro ?? 15)) / (state.ajustes?.performance?.penalizacion_escala ?? 4))), 0)} %. Los intervalos son bootstrap de tus partidas.</p>`;
}

// ---- Tu juego en una mirada y cómo sumar ----

function itemMetrica(m) {
    return `<li class="fd-item">
      <div class="fd-cab"><strong>${escapeHtml(m.nombre)}</strong> ${valorIc(m)}</div>
      <div>${barra(m.pct, m.pct_lo, m.pct_hi)} <span class="dim">${mejorQue(m)} · mediana de tu franja ${fmt(m, m.mediana)}</span></div>
      ${m.consejo ? `<p class="consejo">${escapeHtml(m.consejo)}</p>` : ''}
      ${m.nota ? `<p class="nota">${escapeHtml(m.nota)}</p>` : ''}</li>`;
}

function mirada(r) {
    const lista = (xs, vacio) => (xs.length ? `<ul class="fd-lista">${xs.map(itemMetrica).join('')}</ul>` : `<p class="dim">${vacio}</p>`);
    return `<div class="fd">
      <div><h4>Fortalezas</h4>${lista(r.fortalezas, 'Ninguna métrica queda claramente arriba de tu franja.')}</div>
      <div><h4>A mejorar</h4>${lista(r.mejorar, 'Ninguna métrica queda claramente abajo de tu franja.')}</div></div>
      <p class="nota">Entra una métrica cuando todo su intervalo de percentil queda arriba de ${Math.round((state.ajustes?.performance?.umbral_fortaleza ?? 0.6) * 100)} o abajo de ${Math.round((state.ajustes?.performance?.umbral_debilidad ?? 0.4) * 100)}; si cruza el medio, no se puede decir ni una cosa ni la otra.</p>`;
}

function sumar(r) {
    if (!r.sumar.length) return '';
    return `<ol class="sumar">${r.sumar.map(s => {
        const m = s.meta;
        const meta = !m ? '' : m.ya_supera
            ? `Ya estás en la mediana de ${escapeHtml(m.franja)} en ${escapeHtml(m.nombre.toLowerCase())} (${fmt(m, m.desde)}).`
            : `Meta: <strong>${escapeHtml(m.nombre.toLowerCase())}</strong> de ${fmt(m, m.desde)} a ${fmt(m, m.hasta)}, la mediana de ${escapeHtml(m.franja)}.`;
        return `<li><div class="fd-cab"><strong>${escapeHtml(s.nombre)}</strong> <span class="dim">nivel ${num(s.nivel * 100, 0)} · puede sumar ${num(s.margen * 100, 1)} puntos</span></div>
          <p>${meta}</p><p class="consejo">${escapeHtml(s.consejo)}</p></li>`;
    }).join('')}</ol>
      <p class="nota">Son los dos componentes donde más puntos podés sumar (peso × lo que te falta para 100). El winrate no entra: es el resultado del resto.</p>`;
}

// ---- Primeros 15 minutos ----

function temprano(d, cola, rol) {
    const t = d.temprano?.[cola]?.[rol];
    if (!t) return `<p class="empty-state">Menos de ${state.ajustes?.min_partidas ?? 10} partidas de ${escapeHtml(rol)} en esta cola.</p>`;
    const ref = cola === 'solo' ? d.roles?.[rol]?.metricas || {} : {};
    const l = t.linea;
    const lineaTxt = l.gana.n && l.pierde.n
        ? `Vas arriba en oro contra tu rival a los 15 en ${pct(l.pct_gana.v)} de las partidas. Cuando vas arriba ganás ${pct(l.gana.v)} (${l.gana.n} partidas); cuando vas abajo, ${pct(l.pierde.v)} (${l.pierde.n}). ${l.senal ? '' : 'La diferencia no se separa del ruido. '}<span class="dim">Fisher p = ${num(l.p, 3)}</span>`
        : '';
    return `<div class="table-wrap"><table class="data-table">
      <thead><tr><th>Métrica</th><th class="num">Tu promedio</th>${cola === 'solo' ? '<th>Contra tu franja</th><th class="num">Mediana de tu franja</th>' : ''}</tr></thead>
      <tbody>${Object.entries(t.metricas).map(([k, m]) => {
        const mm = { ...m, clave: k }, r = ref[k];
        return `<tr><td>${escapeHtml(m.nombre)}</td><td class="num">${valorIc(mm)} <span class="dim">n = ${m.n}</span></td>
          ${cola === 'solo' ? `<td>${r ? `${barra(r.pct, r.pct_lo, r.pct_hi)} <span class="dim small">${mejorQue(r)}</span>` : '<span class="dim">sin referencia</span>'}</td>
          <td class="num mono">${r ? fmt({ ...r, clave: k }, r.mediana) : '—'}</td>` : ''}</tr>`;
    }).join('')}</tbody></table></div>
      ${lineaTxt ? `<p class="lead">${lineaTxt}</p>` : ''}
      <p class="nota">Las diferencias son contra el rival directo de la misma partida (la misma posición del otro equipo). ${cola === 'solo' ? '' : 'Fuera de solo/dúo no hay franja de rango: no hay percentiles.'}</p>`;
}

// ---- Contra tu campeón ----

function contraCampeon(lista) {
    if (!lista.length) return '';
    const bloques = lista.map(c => `<div class="campeon-ref">
      <div class="fd-cab">${iconoCampeon(c.campeon_id, 28)}<strong>${escapeHtml(campeon(c.campeon_id))}</strong> <span class="dim">${escapeHtml(c.rol)} · tus ${c.n} partidas contra ${c.n_ref} de ${c.jugadores_ref} jugadores distintos</span></div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Métrica</th><th class="num">Vos</th><th class="num">Ellos</th><th class="num">Diferencia</th><th></th></tr></thead>
        <tbody>${[{ clave: 'winrate', nombre: 'Winrate', dec: 0, unidad: '%', mejor: true, tuyo: null, ellos: null, ...c.winrate, pctw: true }, ...c.filas].map(f => {
            // Una diferencia entre porcentajes son puntos, no un porcentaje.
            const ff = f.pctw ? { ...f, v: f.v * 100, lo: f.lo * 100, hi: f.hi * 100, clave: 'dif', unidad: 'pts' }
                : { ...f, clave: 'dif' + f.clave, unidad: f.unidad === '%' ? 'pts' : f.unidad };
            const bien = f.ruido ? '<span class="tag">ruido</span>' : `<span class="tag ${(f.v > 0) === f.mejor ? 'win' : 'loss'}">${(f.v > 0) === f.mejor ? 'mejor' : 'peor'}</span>`;
            return `<tr><td>${escapeHtml(f.nombre)}</td>
              <td class="num mono">${f.pctw ? `${num(c.winrate_tuyo * 100, 0)} %` : fmt(f, f.tuyo)}</td><td class="num mono">${f.pctw ? `${num(c.winrate_ellos * 100, 0)} %` : fmt(f, f.ellos)}</td>
              <td class="num">${valorIc(ff)}</td><td>${bien}</td></tr>`;
        }).join('')}</tbody></table></div></div>`);
    // Los dos con más partidas a la vista; el resto plegado (con 9 campeones el bloque era media página).
    return bloques.slice(0, 2).join('') +
        (bloques.length > 2 ? `<details class="plegable"><summary>${bloques.length - 2} campeones más</summary>${bloques.slice(2).join('')}</details>` : '') +
        '<p class="nota">"Ellos" son los desconocidos que jugaron el mismo campeón en el mismo rol en las partidas de solo/dúo del grupo, en tu franja; se sacan las partidas donde su rival directo era alguien del grupo. Es por partida (casi todos aparecen una vez), por eso va la columna de jugadores distintos.</p>';
}

// ---- Armado ----

export async function bloquesFase3(p, cont) {
    const d = await cachedFetch(`coaching/${encodeURIComponent(p.id)}.json`);
    const roles = Object.keys(d.roles || {});
    let rol = d.rol_principal || roles[0];
    const colasT = COLAS.filter(c => d.temprano?.[c]);
    let colaT = colasT.includes('solo') ? 'solo' : colasT[0];
    const rolesT = () => Object.keys(d.temprano?.[colaT] || {});
    let rolT = rolesT().includes(rol) ? rol : rolesT()[0];

    const sinFranja = !d.franja
        ? '<p class="empty-state">Sin rango de solo/dúo: no hay franja contra la cual compararte. Los primeros 15 minutos sí están.</p>' : '';
    const coaching = () => {
        const r = d.roles[rol];
        if (r.sin_referencia) {
            return `<p class="empty-state">La referencia de ${escapeHtml(d.franja)} en ${escapeHtml(rol)} tiene ${r.n_ref} jugadores con ${state.ajustes?.referencia?.min_partidas ?? 10}+ partidas; hacen falta ${state.ajustes?.referencia?.min_jugadores ?? 20}. Sin eso no se muestran percentiles.</p>`;
        }
        return `<h4>Tu Performance <span class="dim">· ${escapeHtml(rol)} en solo/dúo · ${r.n} partidas</span> ${chipConf(r.confianza)}</h4>${performance(r, d.franja)}
          <h4>Tu juego en una mirada</h4>${mirada(r)}
          <h4>Cómo sumar</h4>${sumar(r)}`;
    };
    cont.innerHTML = `<section class="section" id="f3-coaching">
        <div class="section-head"><h3>Coaching</h3>${roles.length > 1 ? selector('f3-rol', 'Rol', roles, rol) : ''}</div>
        ${d.franja ? `<p class="dim">Te comparo contra jugadores de <strong>${escapeHtml(d.franja)}</strong> en solo/dúo, tu franja por rango.</p>` : ''}
        ${sinFranja}<div id="f3-cuerpo">${roles.length ? coaching() : (d.franja ? `<p class="empty-state">Ningún rol con ${state.ajustes?.min_partidas ?? 10}+ partidas de solo/dúo.</p>` : '')}</div>
      </section>
      ${colasT.length ? `<section class="section">
        <div class="section-head"><h3>Tus primeros 15 minutos</h3>
          <span>${selector('f3-colaT', 'Cola', colasT, colaT, nombreCola)} <span id="f3-rolT-wrap">${selector('f3-rolT', 'Rol', rolesT(), rolT)}</span></span></div>
        <div id="f3-temprano">${temprano(d, colaT, rolT)}</div></section>` : ''}
      ${d.campeones?.length ? `<section class="section"><h3>Contra tu campeón</h3>${contraCampeon(d.campeones)}</section>` : ''}`;

    cont.querySelector('#f3-rol')?.addEventListener('change', (e) => {
        rol = e.target.value;
        cont.querySelector('#f3-cuerpo').innerHTML = coaching();
    });
    const pintarT = () => { cont.querySelector('#f3-temprano').innerHTML = temprano(d, colaT, rolT); };
    cont.querySelector('#f3-colaT')?.addEventListener('change', (e) => {
        colaT = e.target.value;
        if (!rolesT().includes(rolT)) rolT = rolesT()[0];
        cont.querySelector('#f3-rolT-wrap').innerHTML = selector('f3-rolT', 'Rol', rolesT(), rolT);
        cont.querySelector('#f3-rolT').addEventListener('change', (ev) => { rolT = ev.target.value; pintarT(); });
        pintarT();
    });
    cont.querySelector('#f3-rolT')?.addEventListener('change', (e) => { rolT = e.target.value; pintarT(); });
}
