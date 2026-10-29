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
