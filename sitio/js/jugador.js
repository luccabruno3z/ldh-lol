/* jugador.js — perfil mínimo: cabecera con rango, KPIs por cola y rol (con n e
   intervalo), forma reciente con su prueba e historial de partidas. */

import { state, loadPerfil, loadHistorial } from './data.js';
import { onRoute, go } from './router.js';
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

function tablaKpis(filas) {
    if (!filas.length) return '<p class="empty-state">Sin partidas en este filtro.</p>';
    return `<div class="table-wrap"><table class="data-table kpis">
      <thead><tr><th>Cola</th><th>Rol</th><th class="num">n</th>${COLS.map(([, l]) => `<th class="num">${l}</th>`).join('')}</tr></thead>
      <tbody>${filas.map(f => `
        <tr class="${f.muestra_chica ? 'chica' : ''}${f.rol === 'Todos' ? ' total' : ''}">
          <td>${escapeHtml(nombreCola(f.cola))}</td>
          <td>${escapeHtml(f.rol)}${f.muestra_chica ? ' <span class="tag">muestra chica</span>' : ''}</td>
          <td class="num mono">${f.n}</td>
          ${COLS.map(([k, , t]) => `<td class="num">${conIntervalo(f[k], t)}</td>`).join('')}
        </tr>`).join('')}</tbody>
    </table></div>
    <p class="nota">Cada valor lleva su intervalo del ${Math.round((state.ajustes?.confianza || 0.95) * 100)} % (Wilson para el winrate, bootstrap para el resto).
      Las filas con menos de ${state.ajustes?.min_partidas ?? 10} partidas van al final.</p>`;
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

async function mostrar(id) {
    const cont = document.getElementById('perfil');
    if (!id) {
        actual = null;
        cont.innerHTML = `<div class="cards">${state.personas.map(p =>
            `<a class="card persona" href="#/jugadores/${encodeURIComponent(p.id)}"><span class="persona-nombre">${escapeHtml(p.nombre)}</span>
             <span class="chip ${tierClase(p.solo)}">${escapeHtml(rangoTexto(p.solo))}</span></a>`).join('')}</div>`;
        return;
    }
    if (actual === id) return;
    actual = id;
    cont.innerHTML = '<div class="skeleton"></div>';
    let p;
    try { p = await loadPerfil(id); } catch {
        cont.innerHTML = '<div class="error-state">No encontré ese jugador. Solo aparecen las cuentas que se vincularon.</div>';
        return;
    }
    const vistas = Object.keys(p.kpis);
    cont.innerHTML = `${cabecera(p)}
      <section class="section">
        <div class="section-head"><h3>KPIs por cola y rol</h3>
          ${vistas.length > 1 ? `<label class="selector">Cuenta
            <select id="kpi-cuenta">${vistas.map(v => `<option value="${escapeHtml(v)}">${v === 'todas' ? 'Todas las cuentas' : escapeHtml(v)}</option>`).join('')}</select></label>` : ''}
        </div>
        <div id="kpi-tabla">${tablaKpis(p.kpis.todas)}</div>
      </section>
      ${forma(p.forma)}
      <div id="historial"></div>`;
    document.getElementById('kpi-cuenta')?.addEventListener('change', (e) => {
        document.getElementById('kpi-tabla').innerHTML = tablaKpis(p.kpis[e.target.value] || []);
    });
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
