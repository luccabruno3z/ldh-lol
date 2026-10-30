/* rankings.js — rankings del grupo por período, por rol y dúos.
   Rutas: #/rankings/periodo, #/rankings/roles, #/rankings/duos. Todo dentro de
   cada cola; el valor principal es el ajustado, así nadie sube al podio con dos partidas. */

import { state, cachedFetch, MODOS, EN_MODO } from './data.js';
import { onRoute } from './router.js';
import { escapeHtml, nombreCola, conIntervalo, num } from './utils.js';
import { nombrePersona, pct, chipConf, winrateAj, difWinrate, senal } from './fase2.js';

const GRIETA = ['solo', 'flex', 'normal'];
const ROLES = ['Top', 'Jungla', 'Mid', 'ADC', 'Support'];
const PERIODOS = { semana: 'Últimos 7 días', mes: 'Últimos 30 días', temporada: 'Temporada' };
const TABS = { periodo: 'Por período', roles: 'Por rol', duos: 'Dúos', mejora: 'Quién más mejoró' };

const sel = { tab: 'periodo', periodo: 'mes', cola: 'solo', ventana: 'historico', modo: 'solo' };

const persona = (id) => `<a href="#/jugadores/${encodeURIComponent(id)}">${escapeHtml(nombrePersona(id))}</a>`;

function opciones(id, valores, actual, etiqueta) {
    return `<label class="selector">${etiqueta} <select id="${id}">${Object.entries(valores).map(([v, l]) =>
        `<option value="${v}"${v === actual ? ' selected' : ''}>${escapeHtml(l)}</option>`).join('')}</select></label>`;
}

// "Todo" junta solo, flex y normales: así entra quien juega poco de cada una.
const colas = (conTodo = true) => Object.fromEntries([...GRIETA, ...(conTodo ? ['todo'] : [])].map(c => [c, nombreCola(c)]));

async function porPeriodo(cont) {
    const d = await cachedFetch(`rankings/${sel.periodo}.json`);
    const c = d.colas[sel.cola];
    const podio = c.podio.map((id, i) => {
        const r = c.tabla.find(t => t.persona === id);
        return `<div class="podio-lugar p${i + 1}"><span class="podio-num">${i + 1}</span>${persona(id)}
          <span class="v">${pct(r.winrate_aj)}</span><span class="dim">${r.n} partidas</span></div>`;
    }).join('');
    cont.innerHTML = `
      <div class="section-head">${opciones('rk-periodo', PERIODOS, sel.periodo, 'Período')}${opciones('rk-cola', colas(), sel.cola, 'Cola')}</div>
      ${c.podio.length ? `<div class="podio">${podio}</div>` : '<p class="empty-state">Nadie llega a confianza media con 50 % ajustado o más en este período: no hay podio.</p>'}
      ${c.tabla.length ? `<div class="table-wrap"><table class="data-table">
        <thead><tr><th class="num">#</th><th>Jugador</th><th class="num">n</th><th class="num">Winrate ajustado</th><th class="num">KDA ajustado</th><th>Confianza</th></tr></thead>
        <tbody>${c.tabla.map(r => `<tr><td class="num mono">${r.puesto}</td><td>${persona(r.persona)}</td><td class="num mono">${r.n}</td>
          <td class="num">${winrateAj(r)}</td>
          <td class="num"><span class="v">${num(r.kda_aj, 2)}</span><span class="ic">real ${num(r.kda.v, 2)}</span></td>
          <td>${chipConf(r.confianza)}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${c.sin_muestra.length ? `<p class="nota">Sin muestra suficiente (menos de ${d.min} partidas): ${c.sin_muestra.map(([id, n]) => `${escapeHtml(nombrePersona(id))} (${n})`).join(', ')}.</p>` : ''}
      <p class="nota">Ordenado por winrate ajustado (${state.ajustes?.ajuste_muestra?.k_tasa ?? 10} partidas sumadas al 50 %). El podio exige confianza media o alta y ${Math.round((state.ajustes?.rankings?.piso_podio ?? 0.5) * 100)} % ajustado o más.</p>`;
    cont.querySelector('#rk-periodo').addEventListener('change', (e) => { sel.periodo = e.target.value; render(); });
    cont.querySelector('#rk-cola').addEventListener('change', (e) => { sel.cola = e.target.value; render(); });
}

async function porRol(cont) {
    const d = await cachedFetch('rankings/roles.json');
    const v = d[sel.ventana];
    const dec = (k) => (k.startsWith('dif_oro') ? 0 : k.startsWith('dif_cs') ? 1 : 2);
    cont.innerHTML = `
      <div class="section-head">${opciones('rk-ventana', { historico: 'Temporada', reciente: `Últimos ${d.reciente.dias} días` }, sel.ventana, 'Ventana')}${opciones('rk-cola', colas(), sel.cola, 'Cola')}</div>
      <div class="roles-grid">${ROLES.map(rol => {
        const g = v.grupos[`${sel.cola}|${rol}`];
        const s = (x) => `${x > 0 && g.metrica.startsWith('dif') ? '+' : ''}${num(x, dec(g.metrica))}`;
        return `<div class="card rol-card"><h4>${rol} <span class="dim">· ${escapeHtml(g.nombre)}</span></h4>
          ${g.tabla.length ? `<ol class="rol-lista">${g.tabla.map(r => `<li>${persona(r.persona)}
            <span class="v">${s(r.valor.v)}</span><span class="ic">${s(r.valor.lo)} a ${s(r.valor.hi)} · ${r.n} partidas</span></li>`).join('')}</ol>`
            : `<p class="dim">Nadie tiene ${v.min}+ partidas de ${rol} en esta cola.</p>`}</div>`;
    }).join('')}</div>
      <p class="nota">Cada rol se mide con lo suyo y contra el rival directo de la misma partida: oro a los 15 para las líneas y la jungla, visión por minuto para el support. Entra quien tiene ${v.min}+ partidas en el rol con confianza media o alta.</p>`;
    cont.querySelector('#rk-ventana').addEventListener('change', (e) => { sel.ventana = e.target.value; render(); });
    cont.querySelector('#rk-cola').addEventListener('change', (e) => { sel.cola = e.target.value; render(); });
}

async function duos(cont) {
    const d = await cachedFetch('sinergia.json');
    // Un par aparece dos veces (A con B y B con A): se muestra una fila con las dos diferencias.
    // Los dúos se prueban cola por cola (sumar "todo" duplicaría las pruebas).
    const cola = GRIETA.includes(sel.cola) ? sel.cola : 'solo';
    const pares = new Map();
    d.filas.filter(r => r.cola === cola).forEach(r => {
        const k = [r.persona, r.companero].sort().join('|');
        const e = pares.get(k) || { a: null, b: null };
        if (r.persona < r.companero) e.a = r; else e.b = r;
        pares.set(k, e);
    });
    const filas = [...pares.values()].filter(e => e.a && e.b).sort((x, y) => y.a.juntos - x.a.juntos);
    cont.innerHTML = `
      <div class="section-head">${opciones('rk-cola', colas(false), cola, 'Cola')}</div>
      ${filas.length ? `<div class="table-wrap"><table class="data-table">
        <thead><tr><th>Dúo</th><th class="num">Juntos</th><th class="num">Winrate juntos</th><th class="num">Para el primero</th><th class="num">Para el segundo</th></tr></thead>
        <tbody>${filas.map(({ a, b }) => `<tr class="${a.muestra_chica ? 'chica' : ''}">
          <td>${persona(a.persona)} + ${persona(a.companero)}${a.muestra_chica ? ' <span class="tag">muestra chica</span>' : ''}</td>
          <td class="num mono">${a.juntos}</td>
          <td class="num">${conIntervalo(a.con, 'pct')}</td>
          <td class="num">${difWinrate(a.dif)} ${senal(a)}</td>
          <td class="num">${difWinrate(b.dif)} ${senal(b)}</td></tr>`).join('')}</tbody></table></div>`
        : '<p class="empty-state">No hay dúos con suficientes partidas en esta cola.</p>'}
      <p class="nota">"Para el primero" es cuánto cambia el winrate del primero cuando juega con el segundo, contra cuando juega sin esa persona en la misma cola (y al revés). ${escapeHtml(d.nota)}</p>`;
    cont.querySelector('#rk-cola').addEventListener('change', (e) => { sel.cola = e.target.value; render(); });
}

async function mejora(cont) {
    const d = await cachedFetch('rankings/mejora.json');
    const tabla = d.modos?.[sel.modo] || d.tabla;
    const signo = (v) => `${v > 0 ? '+' : ''}${num(v, 1)}`;
    cont.innerHTML = `<div class="section-head">${d.modos ? opciones('rk-modo', MODOS, sel.modo, 'Modo') : ''}</div>` + (tabla.length ? `<div class="table-wrap"><table class="data-table">
      <thead><tr><th>Jugador</th><th>Rol</th><th class="num">Partidas</th><th class="num">De → a</th><th class="num">Cada 100 partidas</th><th></th></tr></thead>
      <tbody>${tabla.map(x => `<tr class="${x.veredicto === 'mejorando' ? '' : 'chica'}"><td>${persona(x.persona)}</td><td>${escapeHtml(x.rol)}</td>
        <td class="num mono">${x.n}</td><td class="num mono">${num(x.inicio, 0)} → ${num(x.ahora, 0)}</td>
        <td class="num"><span class="v">${signo(x.pendiente)}</span><span class="ic">${signo(x.lo)} a ${signo(x.hi)}</span></td>
        <td><span class="tag ${x.veredicto === 'mejorando' ? 'win' : x.veredicto === 'empeorando' ? 'loss' : ''}">${escapeHtml(x.veredicto)}</span></td></tr>`).join('')}</tbody></table></div>
      <p class="nota">${escapeHtml(d.nota)} Cada uno se mide contra su propia franja, así que se puede comparar a un Hierro con un Esmeralda.</p>`
      : `<p class="empty-state">Nadie tiene 30+ partidas de ${escapeHtml(EN_MODO[sel.modo])} en un rol con referencia.</p>`);
    cont.querySelector('#rk-modo')?.addEventListener('change', (e) => { sel.modo = e.target.value; render(); });
}

function render() {
    const cont = document.getElementById('rankings-cuerpo');
    document.querySelectorAll('#rankings-tabs a').forEach(a => a.classList.toggle('is-active', a.dataset.tab === sel.tab));
    cont.innerHTML = '<div class="skeleton"></div>';
    const fn = { periodo: porPeriodo, roles: porRol, duos, mejora }[sel.tab];
    fn(cont).catch(err => {
        console.error('[rankings]', err);
        cont.innerHTML = '<div class="error-state">No se pudo cargar este ranking.</div>';
    });
}

export function initRankings() {
    document.getElementById('rankings-tabs').innerHTML = Object.entries(TABS).map(([k, l]) =>
        `<a href="#/rankings/${k}" data-tab="${k}">${l}</a>`).join('');
    onRoute('rankings', (tab) => {
        sel.tab = TABS[tab] ? tab : 'periodo';
        render();
    });
}
