/* utils.js — formato, nombres y piezas de HTML compartidas. */

import { state } from './data.js';

export function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const TIERS = { IRON: 'Hierro', BRONZE: 'Bronce', SILVER: 'Plata', GOLD: 'Oro', PLATINUM: 'Platino', EMERALD: 'Esmeralda',
    DIAMOND: 'Diamante', MASTER: 'Maestro', GRANDMASTER: 'Gran Maestro', CHALLENGER: 'Retador' };
const SIN_DIVISION = new Set(['MASTER', 'GRANDMASTER', 'CHALLENGER']);

export function rangoTexto(r) {
    if (!r || !r.tier) return 'Sin clasificar';
    const div = SIN_DIVISION.has(r.tier) ? '' : ` ${r.division}`;
    return `${TIERS[r.tier] || r.tier}${div} · ${r.lp} LP`;
}

export const tierClase = (r) => (r && r.tier ? `tier-${r.tier.toLowerCase()}` : 'tier-none');

export function nombreCola(c) {
    return state.ajustes?.nombres_cola?.[c] || c;
}

export function campeon(id) {
    const c = state.campeones?.campeones?.[id];
    return c ? c.nombre : `Campeón ${id}`;
}

export function iconoCampeon(id, size = 32) {
    const c = state.campeones?.campeones?.[id];
    if (!c) return `<span class="champ-icon champ-icon--vacio" style="width:${size}px;height:${size}px"></span>`;
    const src = `https://ddragon.leagueoflegends.com/cdn/${state.campeones.version}/img/champion/${c.key}.png`;
    return `<img class="champ-icon" src="${src}" alt="${escapeHtml(c.nombre)}" title="${escapeHtml(c.nombre)}" width="${size}" height="${size}" loading="lazy">`;
}

export function fecha(ms, conHora = true) {
    if (!ms) return '—';
    const d = new Date(ms);
    const opts = { day: '2-digit', month: '2-digit', ...(conHora ? { hour: '2-digit', minute: '2-digit' } : {}) };
    return d.toLocaleString('es-AR', opts);
}

export function hace(ms) {
    if (!ms) return '—';
    const min = Math.round((Date.now() - ms) / 60000);
    if (min < 60) return `hace ${min} min`;
    const h = Math.round(min / 60);
    if (h < 48) return `hace ${h} h`;
    return `hace ${Math.round(h / 24)} días`;
}

// Signo menos de verdad (−) y no el guión: "−116" no se confunde con un rango ni con "15-116".
const num = (v, dec) => (v == null ? '—' : Number(v).toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec })
    .replace(/^-(?=.*[1-9])/, '−').replace(/^-/, ''));

/** ¿El intervalo del 95 % de la diferencia a − b deja afuera al cero? Aproximado desde el intervalo de cada uno
    (se = ancho / 3,92). Igual que se_separan en bot/services/formato.py. */
export function seSeparan(a, b) {
    if (!a || !b || [a.v, a.lo, a.hi, b.v, b.lo, b.hi].some(x => x == null)) return false;
    if (a.lo > b.hi || b.lo > a.hi) return true;  // si ni se tocan, se separan (cubre los intervalos asimétricos)
    const se = Math.hypot((a.hi - a.lo) / 3.92, (b.hi - b.lo) / 3.92);
    return se > 0 && Math.abs(a.v - b.v) > 1.96 * se;
}

/** Valor con su intervalo y n. tipo: 'pct' (0–1), 'pct100' (0–100) o decimales. Rangos como "x a y", el % una sola vez. */
export function conIntervalo(m, tipo = 1) {
    if (!m || m.v == null) return '<span class="dim">—</span>';
    const f = (x) => (tipo === 'pct' ? num(x * 100, 0) : tipo === 'pct100' ? num(x, 0) : num(x, tipo));
    const suf = tipo === 'pct' || tipo === 'pct100' ? ' %' : '';
    const ic = m.lo == null ? '' : `<span class="ic">${f(m.lo)} a ${f(m.hi)}${suf}</span>`;
    return `<span class="v">${f(m.v)}${suf}</span>${ic}`;
}

/** Una diferencia como pista que diverge del cero: la franja es el intervalo, la marca el valor. rango = media
    pista (en las mismas unidades que v). tono: 'pos', 'neg' o '' (ruido). */
export function pistaDif(v, lo, hi, rango, tono = '', etiqueta = '') {
    const pos = (x) => 50 + (Math.max(-rango, Math.min(rango, x)) / rango) * 50;
    return `<span class="dv-pista${tono ? ` dv-${tono}` : ''}" role="img" aria-label="${escapeHtml(etiqueta)}">
        <span class="dv-cero"></span><span class="dv-ic" style="left:${pos(lo)}%;width:${pos(hi) - pos(lo)}%"></span>
        <span class="dv-v" style="left:${pos(v)}%"></span></span>`;
}

export { num };

/** "¿Cómo se calcula?": el detalle técnico (pruebas, correcciones, citas) plegado, para que la lectura
    rápida quede con la etiqueta y la conclusión. */
export function como(html) {
    return html ? `<details class="como"><summary>¿Cómo se calcula?</summary><p class="nota">${html}</p></details>` : '';
}

/** La etiqueta de muestra chica dice siempre su umbral, así no hay que adivinar qué es "chica" en cada tabla. */
export function tagChica(min, que = 'partidas') {
    return ` <span class="tag" title="Menos de ${min} ${que}: el número puede cambiar mucho con pocas partidas más">muestra chica</span>`;
}
