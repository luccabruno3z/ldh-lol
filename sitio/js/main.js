/* main.js — arranque. Cada funcionalidad corre aislada en safe(): si una falla,
   el resto de la página sigue andando. */

import { loadBase } from './data.js';
import { initRouter } from './router.js';
import { initInicio } from './inicio.js';
import { initJugador } from './jugador.js';
import { initRankings } from './rankings.js';

function safe(name, fn) {
    try {
        const r = fn();
        if (r && typeof r.catch === 'function') r.catch(err => console.error(`[${name}]`, err));
    } catch (err) {
        console.error(`[${name}]`, err);
    }
}

function initTema() {
    const root = document.documentElement;
    let guardado = null;
    try { guardado = localStorage.getItem('tema'); } catch { /* sin storage */ }
    if (guardado) root.dataset.theme = guardado;
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
        const oscuro = root.dataset.theme
            ? root.dataset.theme === 'dark'
            : matchMedia('(prefers-color-scheme: dark)').matches;
        root.dataset.theme = oscuro ? 'light' : 'dark';
        try { localStorage.setItem('tema', root.dataset.theme); } catch { /* sin storage */ }
    });
}

async function boot() {
    safe('tema', initTema);
    try {
        await loadBase();
    } catch (err) {
        console.error('[datos]', err);
        document.getElementById('main').insertAdjacentHTML('afterbegin',
            '<div class="error-state">No se pudieron cargar los datos. Probá recargar en un rato.</div>');
        return;
    }
    safe('inicio', initInicio);
    safe('jugador', initJugador);
    safe('rankings', initRankings);
    safe('router', initRouter);
}

boot();
