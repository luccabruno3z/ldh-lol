/* main.js — arranque. Cada funcionalidad corre aislada en safe(): si una falla,
   el resto de la página sigue andando. */

import { loadBase } from './data.js';
import { initRouter } from './router.js';
import { initInicio } from './inicio.js';
import { initJugador } from './jugador.js';
import { initRankings } from './rankings.js';
import { initComparar } from './comparar.js';
import { initEquipos } from './equipos.js';
import { initGuias } from './guias.js';

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

/** Tablas apilables: cada celda sin data-label toma el texto de su encabezado (sin la línea chica .ic), así en el
    celular cada fila se lee como "Etiqueta ··· valor" sin repetir las etiquetas en cada tabla. */
function etiquetar(raiz) {
    raiz.querySelectorAll('table.tabla-apilable').forEach(t => {
        const ths = [...(t.tHead?.rows[t.tHead.rows.length - 1]?.cells || [])];
        if (!ths.length || t.tHead.rows.length > 1) return;  // con encabezado de dos filas, cada td trae su data-label
        const nombres = ths.map(th => {
            const c = th.cloneNode(true);
            c.querySelectorAll('.ic, .sr-only').forEach(x => x.remove());
            return c.textContent.trim();
        });
        t.querySelectorAll('tbody tr').forEach(tr => [...tr.cells].forEach((td, i) => {
            if (i && td.colSpan === 1 && !td.hasAttribute('data-label') && nombres[i]) td.dataset.label = nombres[i];
        }));
    });
}

/** Menús que se deslizan de costado: un degradé en el borde avisa que hay más (antes se cortaban en "Rankin"). */
function marcarDesliza(el) {
    const resto = el.scrollWidth - el.clientWidth - el.scrollLeft;
    el.classList.toggle('sigue-der', resto > 4);
    el.classList.toggle('sigue-izq', el.scrollLeft > 4);
}

function initCelular() {
    const main = document.getElementById('main');
    let pendiente = false;
    const pasar = () => {
        pendiente = false;
        etiquetar(main);
        document.querySelectorAll('.main-nav, .perfil-tabs').forEach(el => {
            if (!el.dataset.desliza) {
                el.dataset.desliza = '1';
                el.addEventListener('scroll', () => marcarDesliza(el), { passive: true });
                // Las pestañas del perfil se arman antes de tener su ancho final: se vuelve a medir al cambiar.
                if (window.ResizeObserver) new ResizeObserver(() => marcarDesliza(el)).observe(el);
            }
            marcarDesliza(el);
        });
    };
    new MutationObserver(() => { if (!pendiente) { pendiente = true; requestAnimationFrame(pasar); } })
        .observe(main, { childList: true, subtree: true });
    addEventListener('resize', pasar);
    pasar();
}

async function boot() {
    safe('tema', initTema);
    safe('celular', initCelular);
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
    safe('comparar', initComparar);
    safe('equipos', initEquipos);
    safe('guias', initGuias);
    safe('router', initRouter);
}

boot();
