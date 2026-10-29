/* router.js — una vista por pestaña, ruteada por hash. Basado en el de LDH Stats PR.

   Rutas: #/<vista> y #/<vista>/<parámetro>. En "jugadores" el parámetro es el
   id de la persona (#/jugadores/lucca). Cualquier otro hash (p.ej. #main del
   skip-link) no cambia de vista. */

const DEFAULT_VIEW = 'inicio';
const SITE_TITLE = 'LDH Stats LoL';

let panels = {};
let currentView = null;
const listeners = {};

function resolve(hash) {
    const h = (hash || '').replace(/^#/, '');
    if (!h || h === '/') return { view: DEFAULT_VIEW, param: null };
    if (!h.startsWith('/')) return null;
    const [view, ...rest] = h.slice(1).split('/');
    if (!panels[view]) return { view: DEFAULT_VIEW, param: null, canonical: true };
    return { view, param: rest.length ? decodeURIComponent(rest.join('/')) : null };
}

function show(view) {
    Object.entries(panels).forEach(([name, panel]) => panel.classList.toggle('is-active', name === view));
    document.querySelectorAll('[data-view]').forEach(a => {
        if (a.dataset.view === view) a.setAttribute('aria-current', 'page');
        else a.removeAttribute('aria-current');
    });
    const title = panels[view]?.querySelector('.view-title');
    document.title = title ? `${title.textContent} — ${SITE_TITLE}` : SITE_TITLE;
}

function apply() {
    const route = resolve(location.hash);
    if (!route) return;
    if (route.canonical) history.replaceState(null, '', `#/${route.view}`);
    const changed = route.view !== currentView;
    show(route.view);
    currentView = route.view;
    if (changed) window.scrollTo({ top: 0, behavior: 'instant' });
    (listeners[route.view] || []).forEach(fn => fn(route.param));
}

/** Una funcionalidad se suscribe a su vista; recibe el parámetro de la ruta. */
export function onRoute(view, fn) {
    (listeners[view] ||= []).push(fn);
}

export function go(view, param) {
    location.hash = param ? `#/${view}/${encodeURIComponent(param)}` : `#/${view}`;
}

export function initRouter() {
    panels = {};
    document.querySelectorAll('[data-view-panel]').forEach(p => { panels[p.dataset.viewPanel] = p; });
    window.addEventListener('hashchange', apply);
    apply();
}
