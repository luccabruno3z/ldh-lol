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

const num = (v, dec) => (v == null ? '—' : Number(v).toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec }));

/** Valor con su intervalo y n. tipo: 'pct' (0–1), 'pct100' (0–100) o decimales. */
export function conIntervalo(m, tipo = 1) {
    if (!m || m.v == null) return '<span class="dim">—</span>';
    const f = (x) => (tipo === 'pct' ? num(x * 100, 0) : tipo === 'pct100' ? num(x, 0) : num(x, tipo));
    const suf = tipo === 'pct' || tipo === 'pct100' ? ' %' : '';
    const ic = m.lo == null ? '' : `<span class="ic">${f(m.lo)}–${f(m.hi)}</span>`;
    return `<span class="v">${f(m.v)}${suf}</span>${ic}`;
}

export { num };
