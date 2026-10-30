/* comparar.js — dos jugadores, métrica por métrica, en la misma cola y el mismo rol (regla 4).
   Ruta: #/comparar/<a>/<b>. Sin las partidas de cada uno no hay prueba de diferencia: se dice
   "se separan" solo si los dos intervalos no se pisan, que es más exigente que una prueba. */

import { state, loadPerfil, cachedFetch } from './data.js';
import { onRoute, go } from './router.js';
import { escapeHtml, nombreCola, conIntervalo, num } from './utils.js';
import { radar } from './graficos.js';

const METRICAS = [
    ['winrate', 'Winrate', 'pct'], ['kda', 'KDA', 2], ['cs_min', 'CS/min', 1], ['oro_min', 'Oro/min', 0],
    ['dano_min', 'Daño/min', 0], ['dano_pct', '% del daño', 'pct100'], ['vision_min', 'Visión/min', 2], ['kp', 'Part. kills', 'pct100'],
];
const sel = { a: null, b: null, cola: 'solo', rol: 'Todos' };

function opciones(valores, actual, nombre = (x) => x) {
    return valores.map(v => `<option value="${escapeHtml(v)}"${v === actual ? ' selected' : ''}>${escapeHtml(nombre(v))}</option>`).join('');
}

function fila(nombre, tipo, ma, mb) {
    if (!ma || !mb || ma.v == null || mb.v == null) {
        return `<div class="vs-fila"><span class="vs-nombre">${nombre}</span><span class="dim vs-sin">sin dato de los dos</span></div>`;
    }
    const k = tipo === 'pct' ? 1 : 1;
    const max = Math.max(Math.abs(ma.hi ?? ma.v), Math.abs(mb.hi ?? mb.v), 1e-9) * k;
    const w = (m) => `${Math.max(2, Math.min(100, (Math.abs(m.v) / max) * 100))}%`;
    const separan = ma.lo != null && mb.lo != null && (ma.lo > mb.hi || mb.lo > ma.hi);
    const gana = separan ? (ma.v > mb.v ? 'a' : 'b') : null;
    return `<div class="vs-fila">
      <span class="vs-nombre">${nombre}</span>
      <div class="vs-lado vs-a${gana === 'a' ? ' gana' : ''}"><span class="vs-val">${conIntervalo(ma, tipo)}</span><span class="vs-barra"><i style="width:${w(ma)}"></i></span></div>
      <div class="vs-lado vs-b${gana === 'b' ? ' gana' : ''}"><span class="vs-barra"><i style="width:${w(mb)}"></i></span><span class="vs-val">${conIntervalo(mb, tipo)}</span></div>
      <span class="vs-veredicto">${separan ? '<span class="tag win">se separan</span>' : '<span class="tag">se pisan</span>'}</span>
    </div>`;
}

async function radarComun(a, b, rol) {
    if (rol === 'Todos') return '<p class="nota">Elegí un rol para comparar el Performance de los dos contra su franja.</p>';
    const [ca, cb] = await Promise.all([a, b].map(id => cachedFetch(`coaching/${encodeURIComponent(id)}.json`).catch(() => null)));
    const ra = ca?.roles?.[rol], rb = cb?.roles?.[rol];
    if (!ra || !rb || ra.sin_referencia || rb.sin_referencia) {
        return `<p class="nota">El radar de Performance necesita que los dos tengan 10+ partidas de ${escapeHtml(rol)} en solo/dúo y referencia en su franja.</p>`;
    }
    if (ca.franja !== cb.franja) {
        return `<p class="nota">Están en franjas distintas (${escapeHtml(ca.franja)} y ${escapeHtml(cb.franja)}): cada Performance se mide contra su propia franja, así que superponerlos engañaría.</p>`;
    }
    return `<h4>Performance en ${escapeHtml(rol)} contra ${escapeHtml(ca.franja)}</h4>
      ${radar(ra.componentes, { segundo: rb.componentes, titulo: 'Componentes de los dos jugadores' })}
      <p class="nota" style="text-align:center"><span class="sw-a"></span> ${escapeHtml(nombre(sel.a))} · <span class="sw-b"></span> ${escapeHtml(nombre(sel.b))} · el anillo punteado es la mitad de la franja</p>`;
}

const nombre = (id) => state.personas.find(p => p.id === id)?.nombre || id;

async function render() {
    const cont = document.getElementById('comparar-cuerpo');
    const ids = state.personas.map(p => p.id);
    sel.a ||= ids[0];
    sel.b ||= ids.find(i => i !== sel.a);
    const [pa, pb] = await Promise.all([loadPerfil(sel.a), loadPerfil(sel.b)]);
    const filasDe = (p) => p.kpis.todas;
    const colas = [...new Set(filasDe(pa).map(f => f.cola))].filter(c => filasDe(pb).some(f => f.cola === c));
    if (!colas.includes(sel.cola)) sel.cola = colas[0];
    const roles = ['Todos', ...['Top', 'Jungla', 'Mid', 'ADC', 'Support'].filter(r =>
        filasDe(pa).some(f => f.cola === sel.cola && f.rol === r) && filasDe(pb).some(f => f.cola === sel.cola && f.rol === r))];
    if (!roles.includes(sel.rol)) sel.rol = 'Todos';
    const fa = filasDe(pa).find(f => f.cola === sel.cola && f.rol === sel.rol);
    const fb = filasDe(pb).find(f => f.cola === sel.cola && f.rol === sel.rol);
    cont.innerHTML = `
      <div class="vs-controles">
        <label class="selector">Jugador <select id="cmp-a">${opciones(ids, sel.a, nombre)}</select></label>
        <button type="button" class="btn-sec" id="cmp-swap" aria-label="Invertir">⇄</button>
        <label class="selector">contra <select id="cmp-b">${opciones(ids, sel.b, nombre)}</select></label>
        <label class="selector">Cola <select id="cmp-cola">${opciones(colas, sel.cola, nombreCola)}</select></label>
        <label class="selector">Rol <select id="cmp-rol">${opciones(roles, sel.rol)}</select></label>
      </div>
      ${!colas.length ? '<p class="empty-state">No tienen ninguna cola en común.</p>' : `
      <div class="vs-cab"><span></span><a href="#/jugadores/${encodeURIComponent(sel.a)}" class="vs-a-nombre">${escapeHtml(nombre(sel.a))}</a>
        <a href="#/jugadores/${encodeURIComponent(sel.b)}" class="vs-b-nombre">${escapeHtml(nombre(sel.b))}</a><span></span></div>
      <div class="vs-cab dim"><span></span><span>${fa ? `${fa.n} partidas` : '—'}</span><span>${fb ? `${fb.n} partidas` : '—'}</span><span></span></div>
      <div class="vs">${METRICAS.map(([k, n, t]) => fila(n, t, fa?.[k], fb?.[k])).join('')}</div>
      ${(fa?.muestra_chica || fb?.muestra_chica) ? '<p class="nota">Alguno tiene menos de 10 partidas en este filtro: muestra chica, sin conclusiones.</p>' : ''}
      <p class="nota">"Se separan" solo cuando los dos intervalos no se tocan; si se pisan, con estas partidas no se puede decir quién rinde más. Es la misma cola y el mismo rol para los dos.</p>
      <div id="cmp-radar"></div>`}`;
    const cambiar = () => go('comparar', `${sel.a}/${sel.b}`);
    cont.querySelector('#cmp-a').addEventListener('change', e => { sel.a = e.target.value; cambiar(); });
    cont.querySelector('#cmp-b').addEventListener('change', e => { sel.b = e.target.value; cambiar(); });
    cont.querySelector('#cmp-swap').addEventListener('click', () => { [sel.a, sel.b] = [sel.b, sel.a]; cambiar(); });
    cont.querySelector('#cmp-cola')?.addEventListener('change', e => { sel.cola = e.target.value; render(); });
    cont.querySelector('#cmp-rol')?.addEventListener('change', e => { sel.rol = e.target.value; render(); });
    const r = cont.querySelector('#cmp-radar');
    if (r) r.innerHTML = await radarComun(sel.a, sel.b, sel.rol);
}

export function initComparar() {
    onRoute('comparar', (param) => {
        const [a, b] = (param || '').split('/');
        const ids = state.personas.map(p => p.id);
        if (ids.includes(a)) sel.a = a;
        if (ids.includes(b)) sel.b = b;
        render().catch(err => {
            console.error('[comparar]', err);
            document.getElementById('comparar-cuerpo').innerHTML = '<div class="error-state">No se pudo cargar la comparación.</div>';
        });
    });
}

export { num };
