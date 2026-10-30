/* fase2.js — bloques del perfil de la fase 2: roles, campeones (con el pool) y
   sinergia. Cada bloque carga su JSON y falla solo: si uno no anda, el resto sí. */

import { state, cachedFetch } from './data.js';
import { escapeHtml, nombreCola, conIntervalo, iconoCampeon, campeon, num } from './utils.js';

const GRIETA = ['solo', 'flex', 'normal'];
const CONF = { alta: 'Confianza alta (15+ partidas)', media: 'Confianza media (8 a 14)', baja: 'Confianza baja: menos de 8 partidas o una sola partida pesa demasiado' };

export const nombrePersona = (id) => state.personas.find(p => p.id === id)?.nombre || id;
export const pct = (v, dec = 0) => (v == null ? '—' : `${num(v * 100, dec)} %`);
export const chipConf = (c) => `<span class="tag conf-${c}" title="${CONF[c]}">${c}</span>`;

/** Winrate ajustado como valor principal y el real con su IC al lado. */
export function winrateAj(t) {
    return `<span class="v">${pct(t.winrate_aj)}</span><span class="ic">real ${pct(t.winrate.v)} · ${t.winrate.lo == null ? '' : `${num(t.winrate.lo * 100, 0)} a ${pct(t.winrate.hi)}`}</span>`;
}

const kdaAj = (t) => `<span class="v">${num(t.kda_aj, 2)}</span><span class="ic">real ${num(t.kda.v, 2)}</span>`;

function selectorCola(id, colas, actual) {
    return `<label class="selector">Cola <select id="${id}">${colas.map(c =>
        `<option value="${c}"${c === actual ? ' selected' : ''}>${escapeHtml(nombreCola(c))}</option>`).join('')}</select></label>`;
}

/** La cola con más partidas, para arrancar el selector ahí. */
function colaPrincipal(filas) {
    const n = {};
    filas.forEach(t => { n[t.cola] = (n[t.cola] || 0) + t.n; });
    return GRIETA.filter(c => n[c]).sort((a, b) => n[b] - n[a])[0];
}

function metrica(m, clave) {
    const dec = clave.startsWith('dif_oro') ? 0 : clave.startsWith('dif_cs') ? 1 : 2;
    if (!m || m.v == null) return '<span class="dim">—</span>';
    const s = (x) => (x == null ? '' : `${x > 0 && clave.startsWith('dif') ? '+' : ''}${num(x, dec)}`);
    return `<span class="v">${s(m.v)}</span>${m.lo == null ? '' : `<span class="ic">${s(m.lo)} a ${s(m.hi)}</span>`}`;
}

// ---- Roles ----

function tablaRoles(d, cola) {
    const filas = d.tabla.filter(t => t.cola === cola);
    if (!filas.length) return '<p class="empty-state">Sin partidas en esta cola.</p>';
    return `<div class="table-wrap"><table class="data-table">
      <thead><tr><th>Rol</th><th class="num">n</th><th class="num">Winrate ajustado</th><th class="num">KDA ajustado</th>
        <th>Métrica del rol</th><th class="num">Mediana del grupo</th><th>Confianza</th></tr></thead>
      <tbody>${filas.map(t => {
        const ms = d.metricas[t.rol] || [];
        const ref = t.referencia || {};
        return `<tr class="${t.muestra_chica ? 'chica' : ''}">
          <td>${escapeHtml(t.rol)}${t.muestra_chica ? ' <span class="tag">muestra chica</span>' : ''}</td>
          <td class="num mono">${t.n}</td>
          <td class="num">${winrateAj(t)}</td>
          <td class="num">${kdaAj(t)}</td>
          <td>${ms.map(m => `<div class="metrica-rol"><span class="dim">${escapeHtml(m.nombre)}</span> ${metrica(t[m.clave], m.clave)}</div>`).join('')}</td>
          <td class="num">${ref.jugadores ? `<span class="v">${pct(ref.winrate)}</span><span class="ic">${ms[0] ? `${escapeHtml(ms[0].nombre)}: ${num(ref[ms[0].clave], ms[0].clave.startsWith('dif_oro') ? 0 : 2)} · ` : ''}${ref.jugadores} jugadores</span>` : '<span class="dim">sin referencia</span>'}</td>
          <td>${chipConf(t.confianza)}</td></tr>`;
    }).join('')}</tbody></table></div>`;
}

async function roles(p, cont) {
    // En la vista de una cuenta, los roles vienen calculados con solo esas partidas.
    const d = p._cuenta ? p._cuenta.roles : await cachedFetch(`roles/${encodeURIComponent(p.id)}.json`);
    let cola = colaPrincipal(d.tabla);
    if (!cola) return;
    const mejor = () => {
        const m = d.mejor[cola];
        return m ? `Mejor rol en ${escapeHtml(nombreCola(cola))}: <strong>${escapeHtml(m.rol)}</strong> (${pct(m.winrate_aj)} ajustado, ${m.n} partidas).`
            : 'Ningún rol llega a confianza media en esta cola: no hay "mejor rol" todavía.';
    };
    cont.innerHTML = `<section class="section">
      <div class="section-head"><h3>Tus roles</h3>${selectorCola('roles-cola', GRIETA, cola)}</div>
      <p class="lead" id="roles-mejor">${mejor()}</p>
      <div id="roles-tabla">${tablaRoles(d, cola)}</div>
      <p class="nota">El winrate ajustado suma ${state.ajustes?.ajuste_muestra?.k_tasa ?? 10} partidas al 50 % y el KDA ajustado ${state.ajustes?.ajuste_muestra?.k_muertes ?? 20} muertes a la mediana del rol: con poca muestra el valor se acerca al centro. La métrica de cada rol se mide contra el rival directo de la misma partida. La referencia es la mediana del grupo en la misma cola y rol, entre quienes tienen ${state.ajustes?.min_partidas ?? 10}+ partidas.</p>
    </section>`;
    cont.querySelector('#roles-cola').addEventListener('change', (e) => {
        cola = e.target.value;
        cont.querySelector('#roles-tabla').innerHTML = tablaRoles(d, cola);
        cont.querySelector('#roles-mejor').innerHTML = mejor();
    });
}

// ---- Campeones y pool ----

function tablaCampeones(filas, todos) {
    const vis = todos ? filas : filas.slice(0, 12);
    if (!vis.length) return '<p class="empty-state">Sin partidas en esta cola.</p>';
    return `<div class="table-wrap"><table class="data-table">
      <thead><tr><th>Campeón</th><th>Posición</th><th class="num">n</th><th class="num">Winrate ajustado</th>
        <th class="num">KDA ajustado</th><th class="num">De tus partidas</th><th>Último parche</th><th>Confianza</th></tr></thead>
      <tbody>${vis.map(t => `<tr class="${t.muestra_chica ? 'chica' : ''}">
        <td class="champ">${iconoCampeon(t.champ, 28)}<span>${escapeHtml(campeon(t.champ))}</span></td>
        <td>${escapeHtml(t.rol || '—')}${t.muestra_chica ? ' <span class="tag">muestra chica</span>' : ''}</td>
        <td class="num mono">${t.n}</td>
        <td class="num">${winrateAj(t)}</td>
        <td class="num">${kdaAj(t)}</td>
        <td class="num mono">${pct(t.popularidad)}</td>
        <td class="mono">${escapeHtml(t.ultimo_parche || '')}</td>
        <td>${chipConf(t.confianza)}</td></tr>`).join('')}</tbody></table></div>`;
}

function grafPool(meses) {
    const w = 26, gap = 6, h = 70;
    const barras = meses.map((m, i) => {
        const v = m.fuera.v ?? 0, x = i * (w + gap), alto = v * h;
        return `<g class="${m.arranque ? 'arranque' : ''}"><title>${m.mes}: ${pct(v)} fuera del pool (${m.n} partidas)${m.arranque ? ' · todavía no hay 90 días de historia' : ''}</title>
          <rect x="${x}" y="${h - alto}" width="${w}" height="${alto}" class="bar-fuera"/>
          <text x="${x + w / 2}" y="${h + 12}" class="eje-txt">${m.mes.slice(5)}</text></g>`;
    }).join('');
    const ancho = Math.max(1, meses.length * (w + gap) - gap);
    return `<svg class="pool-graf" viewBox="0 0 ${ancho} ${h + 16}" role="img" aria-label="Porcentaje de partidas fuera del pool por mes">
      <line x1="0" x2="${ancho}" y1="${h}" y2="${h}" class="eje"/>${barras}</svg>`;
}

function bloquePool(pool, cola) {
    const p = pool.colas[cola];
    if (!p) return '';
    const veredicto = p.p == null ? '<span class="dim">sin partidas de un lado</span>'
        : p.p < (state.ajustes?.ajuste_muestra?.alfa ?? 0.05)
            ? `<span class="tag ${p.dif.v > 0 ? 'win' : 'loss'}">señal</span> <span class="dim">Fisher p = ${num(p.p, 3)}</span>`
            : `<span class="tag">no discrimina</span> <span class="dim">Fisher p = ${num(p.p, 3)}</span>`;
    return `<div class="pool">
      <div class="pool-cifras">
        <div><span class="dim">Dentro del pool</span> ${conIntervalo(p.dentro, 'pct')} <span class="dim">n = ${p.dentro.n}</span></div>
        <div><span class="dim">Fuera del pool</span> ${conIntervalo(p.fuera, 'pct')} <span class="dim">n = ${p.fuera.n}</span></div>
        <div>${veredicto}</div>
      </div>
      <div><p class="dim">Partidas fuera del pool por mes</p>${grafPool(p.por_mes)}</div>
    </div>
    <p class="nota">${escapeHtml(pool.regla)} Los meses en gris todavía no tienen 90 días de historia atrás: ahí casi todo cuenta como "fuera".</p>`;
}

async function campeones(p, cont) {
    const d = p._cuenta ? p._cuenta.campeones : await cachedFetch(`campeones/${encodeURIComponent(p.id)}.json`);
    let cola = colaPrincipal(d.tabla), todos = false;
    if (!cola) return;
    const pintar = () => {
        const filas = d.tabla.filter(t => t.cola === cola);
        cont.querySelector('#camp-tabla').innerHTML = tablaCampeones(filas, todos);
        cont.querySelector('#camp-mas').hidden = filas.length <= 12;
        cont.querySelector('#camp-mas').textContent = todos ? 'Ver menos' : `Ver los ${filas.length}`;
        cont.querySelector('#camp-pool').innerHTML = bloquePool(d.pool, cola);
    };
    cont.innerHTML = `<section class="section">
      <div class="section-head"><h3>Tus campeones</h3>${selectorCola('camp-cola', GRIETA, cola)}</div>
      <div id="camp-tabla"></div><button class="btn" type="button" id="camp-mas" hidden></button>
      <p class="nota">Cada fila es un campeón en una posición: un Darius en bot cuenta como ADC. Ordenado por winrate ajustado; "de tus partidas" es la popularidad, que no es rendimiento.</p>
      <h4>Dentro y fuera de tu pool</h4><div id="camp-pool"></div>
    </section>`;
    cont.querySelector('#camp-cola').addEventListener('change', (e) => { cola = e.target.value; pintar(); });
    cont.querySelector('#camp-mas').addEventListener('click', () => { todos = !todos; pintar(); });
    pintar();
}

// ---- Sinergia ----

export function difWinrate(d) {
    if (!d || d.v == null) return '<span class="dim">—</span>';
    const s = (x) => `${x > 0 ? '+' : ''}${num(x * 100, 0)}`;
    return `<span class="v">${s(d.v)} pts</span><span class="ic">${s(d.lo)} a ${s(d.hi)}</span>`;
}

export const senal = (r) => (r.senal ? `<span class="tag ${r.dif.v > 0 ? 'win' : 'loss'}">señal</span>` : '<span class="tag">ruido</span>');

async function sinergia(p, cont) {
    if (p._cuenta) return;  // la sinergia es de la persona: se compara con y sin cada amigo en todas sus cuentas
    const d = await cachedFetch('sinergia.json');
    const filas = d.filas.filter(r => r.persona === p.id);
    if (!filas.length) return;
    const mc = p.mejor_companero;
    cont.innerHTML = `<section class="section">
      <h3>Con quién rendís</h3>
      <p class="lead">${mc ? `Mejor compañero: <strong>${escapeHtml(nombrePersona(mc.companero))}</strong> en ${escapeHtml(nombreCola(mc.cola))} (${difWinrate(mc.dif)} jugando juntos, ${mc.juntos} partidas).`
        : 'Con ningún compañero rendís mejor más allá del ruido: ninguna mejora supera lo que explica el azar.'}</p>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Compañero</th><th>Cola</th><th class="num">Juntos</th><th class="num">Juntos: winrate</th><th class="num">Sin esa persona</th>
          <th class="num">Sin esa persona, mismo período</th><th class="num">Diferencia</th><th class="num">p ajustado</th><th></th></tr></thead>
        <tbody>${filas.map(r => `<tr class="${r.muestra_chica ? 'chica' : ''}">
          <td><a href="#/jugadores/${encodeURIComponent(r.companero)}">${escapeHtml(nombrePersona(r.companero))}</a>${r.muestra_chica ? ' <span class="tag">muestra chica</span>' : ''}</td>
          <td>${escapeHtml(nombreCola(r.cola))}</td>
          <td class="num mono">${r.juntos}</td>
          <td class="num">${conIntervalo(r.con, 'pct')}</td>
          <td class="num">${conIntervalo(r.sin, 'pct')} <span class="dim">n = ${r.sin.n}</span></td>
          <td class="num">${conIntervalo(r.sin_mismo_periodo, 'pct')}</td>
          <td class="num">${difWinrate(r.dif)}</td>
          <td class="num mono">${num(r.p_bh, 3)}</td>
          <td>${senal(r)}</td></tr>`).join('')}</tbody></table></div>
      <p class="nota">${escapeHtml(d.nota)} "Mismo período" mira solo las partidas sin ese compañero entre la primera y la última que jugaron juntos, para descartar que la diferencia sea de época.</p>
    </section>`;
}

/** Los tres bloques en contenedores propios, cada uno aislado. */
export function bloquesFase2(p, cont) {
    cont.innerHTML = '<div id="f2-roles"></div><div id="f2-campeones"></div><div id="f2-sinergia"></div>';
    [['roles', roles], ['campeones', campeones], ['sinergia', sinergia]].forEach(([n, fn]) =>
        fn(p, cont.querySelector(`#f2-${n}`)).catch(err => console.error(`[${n}]`, err)));
}
