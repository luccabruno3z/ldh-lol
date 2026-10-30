/* data.js — lectura de los JSON publicados en api/. Rutas relativas: anda igual
   en local (python -m http.server -d salida) y en Pages. Caché en memoria con
   TTL y, si la red falla, se devuelve lo último que se tuvo (stale-while-error). */

const API = 'api';
const CACHE_TTL = 5 * 60 * 1000;
const memoryCache = new Map();

export const state = { meta: null, personas: [], campeones: null, ajustes: null };

export async function cachedFetch(path, { ttl = CACHE_TTL, silent = false } = {}) {
    const url = `${API}/${path}`;
    const cached = memoryCache.get(url);
    if (cached && Date.now() - cached.time < ttl) return cached.data;
    try {
        const resp = await fetch(url);
        if (!resp.ok) { if (silent) return null; throw new Error(`HTTP ${resp.status} en ${url}`); }
        const data = await resp.json();
        memoryCache.set(url, { data, time: Date.now() });
        return data;
    } catch (err) {
        if (cached) return cached.data;
        if (silent) return null;
        throw err;
    }
}

export async function loadBase() {
    const [meta, personas, campeones, ajustes] = await Promise.all([
        cachedFetch('meta.json'), cachedFetch('personas.json'),
        cachedFetch('campeones.json', { silent: true }), cachedFetch('ajustes.json', { silent: true }),
    ]);
    Object.assign(state, { meta, personas, campeones, ajustes });
    return state;
}

export const loadPerfil = (id) => cachedFetch(`perfil/${encodeURIComponent(id)}.json`);
export const loadHistorial = (id, pagina) => cachedFetch(`historial/${encodeURIComponent(id)}/${pagina}.json`);
export const loadRecientes = () => cachedFetch('recientes.json', { silent: true });

// Modo del perfil (solo/dúo, normales o todo junto). Se recuerda en el navegador de quien mira; si el
// almacenamiento no anda, se arranca en el modo con más partidas de cada jugador.
export const MODOS = { solo: 'Solo/Dúo', normal: 'Normales', todo: 'Todo' };
export function modoGuardado() {
    try { const m = localStorage.getItem('ldh-modo'); return MODOS[m] ? m : null; } catch { return null; }
}
export function guardarModo(m) {
    try { localStorage.setItem('ldh-modo', m); } catch { /* sin almacenamiento: queda en memoria */ }
}
export const rutaCoaching = (id, modo = 'solo') =>
    modo === 'solo' ? `coaching/${encodeURIComponent(id)}.json` : `coaching/${modo}/${encodeURIComponent(id)}.json`;
// Para frases: "en solo/dúo", "en normales", "en todas las colas".
export const EN_MODO = { solo: 'solo/dúo', normal: 'normales', todo: 'todas las colas' };
