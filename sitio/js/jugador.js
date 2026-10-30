/* jugador.js — perfil: cabecera con rango, KPIs por cola y rol (con n e intervalo),
   forma reciente con su prueba, los bloques de la fase 2 (fase2.js), el coaching (fase3.js) e historial. */

import { state, loadPerfil, loadHistorial, cachedFetch, MODOS, modoGuardado, guardarModo } from './data.js';
import { seccionEvolucion } from './graficos.js';
import { onRoute, go } from './router.js';
import { bloquesFase2 } from './fase2.js';
import { bloquesFase3 } from './fase3.js';
import { bloquesFase4 } from './fase4.js';
import { bloqueRachas } from './fase5.js';
import { escapeHtml, rangoTexto, tierClase, nombreCola, conIntervalo, iconoCampeon, campeon, fecha, num } from './utils.js';

const COLS = [
    ['winrate', 'Winrate', 'pct'], ['kda', 'KDA', 2], ['cs_min', 'CS/min', 1], ['oro_min', 'Oro/min', 0],
    ['dano_min', 'Daño/min', 0], ['dano_pct', '% daño', 'pct100'], ['vision_min', 'Visión/min', 2], ['kp', 'Part. kills', 'pct100'],
];
const FORMA = [['winrate', 'Winrate', 'pct'], ['kda', 'KDA', 2], ['cs_min', 'CS/min', 1], ['dano_min', 'Daño/min', 0], ['kp', 'Part. kills', 'pct100']];

let actual = null;

function buscar(texto) {
    const t = texto.trim().toLowerCase();
    if (!t) return null;
    return state.personas.find(p => p.id === t || p.nombre.toLowerCase() === t)
        || state.personas.find(p => p.cuentas.some(c => c.toLowerCase() === t || c.toLowerCase().split('#')[0] === t))
        || state.personas.find(p => p.nombre.toLowerCase().includes(t) || p.cuentas.some(c => c.toLowerCase().includes(t)));
}

function cabecera(p) {
    // Riot cuenta W/L de la temporada; la lista de partidas a veces no llega tan atrás.
    const faltantes = r => {
      const total = r.wins + r.losses;
      return r.guardadas != null && total - r.guardadas >= 5
        ? `<span class="dim" title="Riot ya no lista las partidas más viejas de esta cuenta">· ${r.guardadas} de ${total} guardadas</span>`
        : '';
    };
    const rangos = p.cuentas.map(c => [c.riot_id, (p.rango || {})[c.riot_id] || {}]);
    return `
    <section class="section perfil-head">
      <h2 class="perfil-nombre">${escapeHtml(p.nombre)}</h2>
      <p class="dim">${p.n} partidas desde el 8/1/2026 · última ${fecha(p.ultima)}</p>
      <div class="cuentas">${rangos.length ? rangos.map(([rid, colas]) => `
        <div class="cuenta">
          <span class="mono">${escapeHtml(rid)}</span>
          ${['solo', 'flex'].filter(c => colas[c]).map(c => `
            <span class="chip ${tierClase(colas[c])}" title="${escapeHtml(nombreCola(c))}">
              ${c === 'solo' ? 'Solo' : 'Flex'}: ${escapeHtml(rangoTexto(colas[c]))} · ${colas[c].wins} V / ${colas[c].losses} D</span>
            ${faltantes(colas[c])}`).join('')
          || '<span class="chip tier-none">Sin clasificar</span>'}
        </div>`).join('') : '<span class="dim">Sin datos de rango todavía.</span>'}
      </div>
    </section>`;
}

/** Lo importante de un vistazo: rango, winrate del modo elegido, mejor rol y forma reciente. */
function resumen(p, modo) {
    const principal = (p.kpis?.todas || []).find(f => f.rol === 'Todos' && f.cola === modo);
    const solo = Object.values(p.rango || {}).map(c => c.solo).filter(Boolean).sort((a, b) => (b.valor ?? -1) - (a.valor ?? -1))[0];
    const mejor = principal && p.mejor_rol?.[principal.cola];
    const f = p.forma, dif = f?.comparacion?.winrate?.dif;
    const tarjeta = (titulo, valor, detalle, clase = '') =>
        `<div class="res-card ${clase}"><span class="res-tit">${titulo}</span><span class="res-val">${valor}</span><span class="res-det">${detalle}</span></div>`;
    return `<div class="resumen">
      ${tarjeta('Solo/Dúo', solo ? escapeHtml(rangoTexto(solo).split(' · ')[0]) : 'Sin clasificar',
                solo ? `${solo.lp} LP · ${solo.wins} V / ${solo.losses} D` : 'todavía sin rango', tierClase(solo))}
      ${tarjeta(`Winrate en ${escapeHtml(MODOS[modo])}`, principal ? conIntervalo(principal.winrate, 'pct') : '—', principal ? `${principal.n} partidas` : 'sin partidas en este modo')}
      ${tarjeta('Mejor rol', mejor ? escapeHtml(mejor.rol) : '—',
                mejor ? `${Math.round(mejor.winrate_aj * 100)} % ajustado en ${mejor.n} partidas` : 'ningún rol con confianza media todavía')}
      ${f ? tarjeta('Últimas 10', conIntervalo(f.comparacion.winrate.ultimas, 'pct'),
                dif?.ruido ? 'igual que tu resto (ruido)' : dif?.v > 0 ? 'mejor que tu resto' : 'peor que tu resto',
                dif?.ruido ? '' : dif?.v > 0 ? 'res-bien' : 'res-mal') : ''}
    </div>`;
}

/** Partidas de cada modo (fila "Todos" de los KPIs). */
const nModo = (p, m) => (p.kpis?.todas || []).find(f => f.cola === m && f.rol === 'Todos')?.n || 0;

/** El modo guardado por quien mira; si no hay, el de solo/dúo cuando alcanza para el coaching, si no Todo. */
function modoInicial(p) {
    return modoGuardado() || (nModo(p, 'solo') >= 30 ? 'solo' : 'todo');
}

/** Solo/Dúo · Normales · Todo, con cuántas partidas tiene cada uno. Maneja todo el perfil. */
function barraModo(p, modo) {
    return `<div class="modo-bar" role="group" aria-label="Qué partidas mirar">
      <span class="modo-tit">Modo</span>
      ${Object.entries(MODOS).map(([m, l]) => `<button type="button" class="modo-btn${m === modo ? ' is-active' : ''}" data-modo="${m}"
        aria-pressed="${m === modo}" title="${m === 'todo' ? 'Solo/dúo, flex y normales juntas' : escapeHtml(l)}">${l} <span class="dim">${nModo(p, m)}</span></button>`).join('')}
    </div>`;
}

function filasKpis(filas) {
    return filas.map(f => `
        <tr class="${f.muestra_chica ? 'chica' : ''}${f.rol === 'Todos' ? ' total' : ''}">
          <td>${escapeHtml(f.rol)}</td>
          <td class="num mono">${f.n}</td>
          ${COLS.map(([k, , t]) => `<td class="num">${conIntervalo(f[k], t)}</td>`).join('')}
        </tr>`).join('');
}

/** Una cola por vez; las filas con muestra chica quedan plegadas al final (antes eran la mitad de la tabla). */
function tablaKpis(filas, cola) {
    const deCola = filas.filter(f => f.cola === cola);
    if (!deCola.length) return '<p class="empty-state">Sin partidas en este modo.</p>';
    const grandes = deCola.filter(f => !f.muestra_chica), chicas = deCola.filter(f => f.muestra_chica);
    const cab = `<thead><tr><th>Rol</th><th class="num">n</th>${COLS.map(([, l]) => `<th class="num">${l}</th>`).join('')}</tr></thead>`;
    return `<div class="table-wrap"><table class="data-table kpis">${cab}<tbody>${filasKpis(grandes)}</tbody></table></div>
    ${chicas.length ? `<details class="plegable"><summary>${chicas.length} ${chicas.length === 1 ? 'rol' : 'roles'} con muestra chica (${chicas.map(f => `${escapeHtml(f.rol)} ${f.n}`).join(', ')})</summary>
      <div class="table-wrap"><table class="data-table kpis">${cab}<tbody>${filasKpis(chicas)}</tbody></table></div></details>` : ''}
    <p class="nota">Cada valor lleva su intervalo del ${Math.round((state.ajustes?.confianza || 0.95) * 100)} % (Wilson para el winrate, bootstrap para el resto).
      Los roles con menos de ${state.ajustes?.min_partidas ?? 10} partidas no permiten sacar conclusiones.</p>`;
}

function grafForma(partidas) {
    const max = Math.max(5, ...partidas.map(p => Math.max(p.k, p.d)));
    const w = 28, gap = 8, h = 90;
    const barras = partidas.map((p, i) => {
        const x = i * (w + gap);
        const hk = (p.k / max) * (h / 2 - 4), hd = (p.d / max) * (h / 2 - 4);
        return `<g><title>${escapeHtml(campeon(p.champ))}: ${p.k}/${p.d}/${p.a} · ${p.win ? 'victoria' : 'derrota'}</title>
          <rect x="${x}" y="${h / 2 - hk}" width="${w}" height="${hk}" class="bar-k"/>
          <rect x="${x}" y="${h / 2}" width="${w}" height="${hd}" class="bar-d"/>
          <rect x="${x}" y="${h + 4}" width="${w}" height="6" rx="2" class="${p.win ? 'res-win' : 'res-loss'}"/></g>`;
    }).join('');
    const ancho = partidas.length * (w + gap) - gap;
    return `<svg class="forma-graf" viewBox="0 0 ${ancho} ${h + 12}" role="img" aria-label="Kills arriba y muertes abajo de las últimas partidas, con el resultado debajo">
      <line x1="0" x2="${ancho}" y1="${h / 2}" y2="${h / 2}" class="eje"/>${barras}</svg>
      <p class="leyenda"><span class="sw bar-k"></span>kills <span class="sw bar-d"></span>muertes <span class="sw res-win"></span>victoria <span class="sw res-loss"></span>derrota</p>`;
}

function forma(f) {
    if (!f) return '';
    const fmtDif = (d, t) => {
        if (d.v == null) return '<span class="dim">muestra insuficiente</span>';
        const k = t === 'pct' ? 100 : 1, dec = t === 'pct' || t === 'pct100' ? 0 : t;
        const s = (x) => `${x > 0 ? '+' : ''}${num(x * k, dec)}`;
        return `<span class="v">${s(d.v)}</span><span class="ic">${s(d.lo)} a ${s(d.hi)}</span>
                ${d.ruido ? '<span class="tag">ruido</span>' : `<span class="tag ${d.v > 0 ? 'win' : 'loss'}">${d.v > 0 ? 'mejor' : 'peor'}</span>`}`;
    };
    return `
    <section class="section">
      <h3>Forma reciente <span class="dim">· ${escapeHtml(nombreCola(f.cola))}</span></h3>
      ${grafForma(f.partidas)}
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th></th><th class="num">Últimas ${f.n_ultimas}</th><th class="num">Resto (${f.n_resto})</th><th class="num">Diferencia</th></tr></thead>
        <tbody>${FORMA.map(([k, l, t]) => `<tr><td>${l}</td>
          <td class="num">${conIntervalo(f.comparacion[k].ultimas, t)}</td>
          <td class="num">${conIntervalo(f.comparacion[k].resto, t)}</td>
          <td class="num">${fmtDif(f.comparacion[k].dif, t)}</td></tr>`).join('')}</tbody>
      </table></div>
      <p class="nota">"Ruido" quiere decir que el intervalo de la diferencia cruza el cero: con estas muestras no se puede decir que cambió.</p>
    </section>`;
}

function filaHistorial(m) {
    const lp = m.lp ? (m.lp.exacto ? `${m.lp.delta > 0 ? '+' : ''}${m.lp.delta}` : `tramo de ${m.lp.tramo}: ${m.lp.delta > 0 ? '+' : ''}${m.lp.delta}`) : '';
    return `<tr class="${m.win ? 'r-win' : 'r-loss'}">
      <td class="mono">${fecha(m.inicio)}</td>
      <td>${escapeHtml(nombreCola(m.cola))}</td>
      <td class="champ">${iconoCampeon(m.champ, 28)}<span>${escapeHtml(campeon(m.champ))}</span></td>
      <td>${escapeHtml(m.rol || '—')}</td>
      <td>${m.lado === 'azul' ? 'Azul' : 'Rojo'}</td>
      <td class="mono">${m.k}/${m.d}/${m.a}</td>
      <td class="num mono">${num(m.cs_min, 1)}</td>
      <td class="num mono">${num(m.oro, 0)}</td>
      <td class="num mono">${num(m.dano, 0)}</td>
      <td class="num mono">${m.vision ?? '—'}</td>
      <td>${m.win ? '<span class="win">Victoria</span>' : '<span class="loss">Derrota</span>'}</td>
      <td class="mono">${escapeHtml(m.parche || '')}</td>
      <td class="mono">${lp}</td>
      <td class="dim mono">${escapeHtml(m.cuenta)}</td>
    </tr>`;
}

async function historial(p, cont) {
    let pagina = 0;
    cont.innerHTML = `<section class="section"><h3>Historial</h3>
      <div class="table-wrap"><table class="data-table hist">
        <thead><tr><th>Fecha</th><th>Cola</th><th>Campeón</th><th>Rol</th><th>Lado</th><th>K/D/A</th><th class="num">CS/min</th>
          <th class="num">Oro</th><th class="num">Daño</th><th class="num">Visión</th><th>Resultado</th><th>Parche</th><th>LP</th><th>Cuenta</th></tr></thead>
        <tbody></tbody></table></div>
      <button class="btn" type="button" hidden>Ver más</button></section>`;
    const tbody = cont.querySelector('tbody'), btn = cont.querySelector('button');
    if (p._cuenta) {  // vista de una cuenta: sus últimas partidas vienen en el mismo archivo
        tbody.innerHTML = p._cuenta.historial.map(filaHistorial).join('')
            || '<tr><td colspan="14" class="empty-state">Sin partidas todavía.</td></tr>';
        return;
    }
    const mas = async () => {
        pagina += 1;
        const h = await loadHistorial(p.id, pagina);
        tbody.insertAdjacentHTML('beforeend', h.partidas.map(filaHistorial).join(''));
        btn.hidden = pagina >= h.paginas;
    };
    btn.addEventListener('click', () => mas().catch(err => console.error('[historial]', err)));
    if (p.n) await mas();
    else tbody.innerHTML = '<tr><td colspan="14" class="empty-state">Sin partidas todavía.</td></tr>';
}

// Pestañas del perfil: el perfil entero era muy largo para el celular. La pestaña y la cuenta van en
// la URL (#/jugadores/<persona>/<pestaña>/<cuenta>), así se puede compartir el link exacto.
const PESTANAS = { resumen: 'Resumen', coaching: 'Coaching', campeones: 'Roles y campeones', mapa: 'Mapa y jungla', partidas: 'Partidas' };
let vistaActual = null;

function mostrarPestana(tab) {
    const t = PESTANAS[tab] ? tab : 'resumen';
    document.querySelectorAll('#perfil [data-pestana]').forEach(el => { el.hidden = el.dataset.pestana !== t; });
    document.querySelectorAll('#perfil .perfil-tab').forEach(a => {
        a.classList.toggle('is-active', a.dataset.tab === t);
        a.setAttribute('aria-selected', a.dataset.tab === t);
    });
}

async function mostrar(param) {
    const cont = document.getElementById('perfil');
    const [id, tabRuta, cuentaRuta] = (param || '').split('/');
    if (!id) {
        actual = null;
        cont.innerHTML = `<div class="cards">${state.personas.map(p =>
            `<a class="card persona" href="#/jugadores/${encodeURIComponent(p.id)}"><span class="persona-nombre">${escapeHtml(p.nombre)}</span>
             <span class="chip ${tierClase(p.solo)}">${escapeHtml(rangoTexto(p.solo))}</span></a>`).join('')}</div>`;
        return;
    }
    const vista = cuentaRuta != null && cuentaRuta !== '' ? Number(cuentaRuta) : null;
    // Misma persona y misma cuenta: solo se cambia de pestaña, sin volver a cargar nada.
    if (actual === id && vistaActual === vista) { mostrarPestana(tabRuta); return; }
    actual = id;
    vistaActual = vista;
    cont.innerHTML = '<div class="skeleton"></div>';
    let p;
    try { p = await loadPerfil(id); } catch {
        cont.innerHTML = '<div class="error-state">No encontré ese jugador. Solo aparecen las cuentas que se vincularon.</div>';
        return;
    }
    await pintarPerfil(cont, p, vista, tabRuta);
}

/** Botones "Todas · cuenta 1 · cuenta 2" para quien tiene varias cuentas. */
function botonesCuenta(p, vista) {
    if (!p.vistas_cuenta?.length) return '';
    const b = (idx, txt, n) => `<button type="button" class="cuenta-btn${vista === idx ? ' is-active' : ''}" data-vista="${idx ?? ''}"
        aria-pressed="${vista === idx}">${txt}${n != null ? ` <span class="dim">${n}</span>` : ''}</button>`;
    return `<div class="cuentas-vista" role="group" aria-label="Ver el perfil de una sola cuenta">
      ${b(null, 'Todas las cuentas', p.n)}${p.vistas_cuenta.map(v => b(v.indice, escapeHtml(v.riot_id), v.n)).join('')}</div>`;
}

/** Arma el perfil entero. vista = null (todas las cuentas) o el índice de una cuenta. */
async function pintarPerfil(cont, base, vista, tabInicial = 'resumen', modoElegido = null) {
    let p = base;
    if (vista != null) {
        const c = await cachedFetch(`cuenta/${encodeURIComponent(base.id)}/${vista}.json`);
        p = { ...base, cuentas: [{ riot_id: c.riot_id, n: c.n }], rango: c.rango, n: c.n, ultima: c.ultima,
              kpis: { todas: c.kpis }, forma: c.forma, evolucion: c.evolucion, mejor_rol: c.mejor_rol, _cuenta: c };
    }
    const modo = modoElegido || modoInicial(p);
    // Orden: lo que se lee de un vistazo (forma) y lo que ayuda a mejorar (coaching, roles, pool)
    // antes que la tabla de KPIs, que es el detalle.
    const ruta = (tab, v = vista) => `#/jugadores/${encodeURIComponent(base.id)}/${tab}${v != null ? `/${v}` : ''}`;
    cont.innerHTML = `${cabecera(p)}
      ${botonesCuenta(base, vista)}
      ${barraModo(p, modo)}
      ${resumen(p, modo)}
      <nav class="perfil-tabs" role="tablist" aria-label="Secciones del perfil">${Object.entries(PESTANAS).map(([k, l]) =>
        `<a class="perfil-tab" role="tab" data-tab="${k}" href="${ruta(k)}">${l}</a>`).join('')}</nav>
      <div data-pestana="resumen">${forma(p.forma)}${seccionEvolucion(p.evolucion, modo)}<div id="f5-rachas"></div></div>
      <div data-pestana="coaching"><div id="fase3"></div></div>
      <div data-pestana="campeones"><div id="fase2"></div><div id="f4-matchups"></div></div>
      <div data-pestana="mapa"><div id="f4-heatmap"></div><div id="f4-jungla"></div>
        ${p._cuenta ? '<p class="empty-state">El mapa y la jungla se calculan con todas tus cuentas juntas.</p>' : ''}</div>
      <div data-pestana="partidas">
        <section class="section">
          <h3>KPIs por rol <span class="dim">· ${escapeHtml(MODOS[modo])}</span></h3>
          <div id="kpi-tabla">${tablaKpis(p.kpis.todas, modo)}</div>
        </section>
        <div id="historial"></div></div>`;
    // Las cuentas cambian la URL: el router vuelve a entrar y arma la vista de esa cuenta.
    cont.querySelectorAll('.cuenta-btn').forEach(btn => btn.addEventListener('click', () => {
        const v = btn.dataset.vista === '' ? null : Number(btn.dataset.vista);
        const tab = cont.querySelector('.perfil-tab.is-active')?.dataset.tab || 'resumen';
        location.hash = ruta(tab, v);
    }));
    // El modo cambia todo el perfil: se vuelve a armar en la misma pestaña (los JSON ya están en caché).
    cont.querySelectorAll('.modo-btn').forEach(btn => btn.addEventListener('click', () => {
        if (btn.dataset.modo === modo) return;
        guardarModo(btn.dataset.modo);
        const tab = cont.querySelector('.perfil-tab.is-active')?.dataset.tab || 'resumen';
        pintarPerfil(cont, base, vista, tab, btn.dataset.modo).catch(err => console.error('[perfil]', err));
    }));
    mostrarPestana(tabInicial);
    bloquesFase3(p, document.getElementById('fase3'), modo).catch(err => console.error('[coaching]', err));
    bloquesFase2(p, document.getElementById('fase2'), modo);
    bloqueRachas(p, document.getElementById('f5-rachas'), modo).catch(err => console.error('[rachas]', err));
    bloquesFase4(p, { matchups: document.getElementById('f4-matchups'), heatmap: document.getElementById('f4-heatmap'),
                      jungla: document.getElementById('f4-jungla') }, modo);
    await historial(p, document.getElementById('historial'));
}

export function initJugador() {
    const lista = document.getElementById('buscar-opciones');
    lista.innerHTML = state.personas.flatMap(p => [p.nombre, ...p.cuentas]).map(n => `<option value="${escapeHtml(n)}">`).join('');
    document.getElementById('buscar').addEventListener('submit', (e) => {
        e.preventDefault();
        const input = document.getElementById('buscar-input');
        const p = buscar(input.value);
        if (p) { go('jugadores', p.id); input.value = ''; }
        else document.getElementById('perfil').innerHTML = '<div class="error-state">No encontré a nadie con ese nombre en el grupo.</div>';
    });
    onRoute('jugadores', (id) => mostrar(id).catch(err => console.error('[perfil]', err)));
}
