/* data.js — lectura de los JSON publicados en api/. Rutas relativas: anda igual
   en local (python -m http.server -d salida) y en Pages. Caché en memoria con
   TTL y, si la red falla, se devuelve lo último que se tuvo (stale-while-error). */

const API = 'api';
const CACHE_TTL = 5 * 60 * 1000;
const memoryCache = new Map();

export const state = { meta: null, personas: [], campeones: null, ajustes: null };

/* Rol elegido en el perfil. Lo comparten los selectores de rol de la página (Coaching, primeros 15 minutos y
   muertes) y sobrevive al cambio de modo, que vuelve a pintar el perfil entero. */
const rolPerfil = { pid: null, rol: null };
export function rolGuardado(pid, opciones) {
    return rolPerfil.pid === pid && opciones.includes(rolPerfil.rol) ? rolPerfil.rol : null;
}
export function elegirRol(pid, rol) {
    rolPerfil.pid = pid; rolPerfil.rol = rol;
    document.dispatchEvent(new CustomEvent('ldh:rol', { detail: { pid, rol } }));
}
/** Escucha los cambios de rol de otros bloques. Un solo oyente por contenedor: al volver a pintar se reemplaza. */
export function alCambiarRol(cont, pid, fn) {
    if (cont._oyenteRol) document.removeEventListener('ldh:rol', cont._oyenteRol);
    cont._oyenteRol = (e) => { if (e.detail.pid === pid && cont.isConnected) fn(e.detail.rol); };
    document.addEventListener('ldh:rol', cont._oyenteRol);
}

// Pedidos en curso: dos bloques que piden el mismo JSON a la vez comparten la misma respuesta.
const enCurso = new Map();

export function cachedFetch(path, opciones = {}) {
    const url = `${API}/${path}`;
    const cached = memoryCache.get(url);
    if (cached && Date.now() - cached.time < (opciones.ttl ?? CACHE_TTL) && (cached.data !== null || opciones.silent)) {
        return Promise.resolve(cached.data);
    }
    const clave = `${url}|${opciones.silent ? 1 : 0}`;
    if (!enCurso.has(clave)) enCurso.set(clave, pedir(url, opciones).finally(() => enCurso.delete(clave)));
    return enCurso.get(clave);
}

async function pedir(url, { silent = false } = {}) {
    const cached = memoryCache.get(url);
    try {
        const resp = await fetch(url);
        // Un 404 esperado (un jugador sin informe o sin pool) se guarda como vacío: no se vuelve a pedir en cada pantalla.
        if (resp.status === 404 && silent) { memoryCache.set(url, { data: null, time: Date.now() }); return null; }
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
