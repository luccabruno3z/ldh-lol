/* graficos.js — gráficos en SVG a mano: sin dependencias, con los colores del tema (claro y
   oscuro) y legibles a 375 px. Cada gráfico muestra su intervalo, como las tablas. */

import { escapeHtml, nombreCola, num } from './utils.js';

const COLAS = ['solo', 'flex', 'normal'];

// ---- Evolución: winrate móvil con su banda de Wilson, y el LP ----

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const P = (v) => `${Math.round(v * 100)} %`;

/** La frase que el gráfico tiene que contestar: ¿venís mejor o peor que en el resto de la temporada? */
function lecturaEvo(c, ventana) {
    if (!c.ultimas) return '';
    const veredicto = c.senal
        ? (c.ultimas.v > c.resto.v ? '<span class="tag win">venís mejor</span>' : '<span class="tag loss">venís peor</span>')
        : '<span class="tag">igual que siempre (ruido)</span>';
    return `<p class="evo-lectura">En tus últimas <strong>${ventana}</strong> ganás <strong>${P(c.ultimas.v)}</strong>; antes, ${P(c.resto.v)}. ${veredicto}
      <span class="dim">Fisher p = ${num(c.p, 2)}</span></p>`;
}

function lineaWinrate(c, ventana) {
    const W = 640, H = 220, m = { l: 34, r: 12, t: 16, b: 24 };
    const pts = c.puntos, t0 = pts[0].t, t1 = pts[pts.length - 1].t;
    const x = (t) => m.l + (t1 === t0 ? 0.5 : (t - t0) / (t1 - t0)) * (W - m.l - m.r);
    const y = (v) => m.t + (1 - v) * (H - m.t - m.b);
    const banda = `${pts.map(p => `${x(p.t)},${y(p.hi)}`).join(' ')} ${[...pts].reverse().map(p => `${x(p.t)},${y(p.lo)}`).join(' ')}`;
    const linea = pts.map(p => `${x(p.t)},${y(p.v)}`).join(' ');
    const ult = pts[pts.length - 1];
    const marcas = [0.25, 0.75].map(v => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" class="g-grilla"/>
        <text x="${m.l - 6}" y="${y(v) + 4}" class="g-eje" text-anchor="end">${v * 100}%</text>`).join('');
    // Un rótulo por mes en el eje: las fechas dicen más que "partida 245".
    const meses = [];
    for (let d = new Date(t0); d.getTime() <= t1; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
        const ini = new Date(d.getFullYear(), d.getMonth(), 1).getTime();
        if (ini >= t0) meses.push(`<text x="${x(ini)}" y="${H - 6}" class="g-eje" text-anchor="middle">${MESES[d.getMonth()]}</text>`);
    }
    const temp = c.temporada?.v;
    const marca = (p, txt, arriba) => `<circle cx="${x(p.t)}" cy="${y(p.v)}" r="3" class="g-punto--hito"/>
        <text x="${x(p.t)}" y="${y(p.v) + (arriba ? -8 : 16)}" class="g-eje g-hito" text-anchor="middle">${txt} ${P(p.v)}</text>`;
    return `<svg class="g-evo" viewBox="0 0 ${W} ${H}" role="img"
        aria-label="Winrate de tus últimas ${ventana} partidas a lo largo de la temporada en ${escapeHtml(nombreCola(c.cola))}; hoy ${P(ult.v)}, en la temporada ${temp != null ? P(temp) : '—'}">
      ${marcas}
      <line x1="${m.l}" x2="${W - m.r}" y1="${y(0.5)}" y2="${y(0.5)}" class="g-medio"/>
      <text x="${m.l - 6}" y="${y(0.5) + 4}" class="g-eje" text-anchor="end">50%</text>
      ${temp != null ? `<line x1="${m.l}" x2="${W - m.r}" y1="${y(temp)}" y2="${y(temp)}" class="g-temporada"/>
        <text x="${m.l + 4}" y="${y(temp) - 5}" class="g-eje g-temporada-txt" text-anchor="start">tu temporada ${P(temp)}</text>` : ''}
      <polygon points="${banda}" class="g-banda"/>
      <polyline points="${linea}" class="g-linea"/>
      ${c.mejor ? marca(c.mejor, 'mejor tramo', true) : ''}${c.peor ? marca(c.peor, 'peor tramo', false) : ''}
      <circle cx="${x(ult.t)}" cy="${y(ult.v)}" r="5" class="g-punto"><title>Hoy: ${P(ult.v)} (${P(ult.lo)} a ${P(ult.hi)})</title></circle>
      <text x="${x(ult.t) - 8}" y="${y(ult.v) - 9}" class="g-eje g-hoy" text-anchor="end">hoy ${P(ult.v)}</text>
      ${meses.join('')}
    </svg>`;
}

function lineaLp(lp) {
    if (lp.length < 2) {
        return `<p class="nota">El LP se anota cada vez que corre la actualización y cambia el rango: ${lp.length ? 'por ahora hay un solo registro' : 'todavía no hay registros'}. Lo anterior no se puede reconstruir (la API solo da el LP actual).</p>`;
    }
    const W = 640, H = 120, m = { l: 34, r: 8, t: 10, b: 18 };
    const t0 = Date.parse(lp[0].t), t1 = Date.parse(lp[lp.length - 1].t);
    const vs = lp.map(f => f.valor), lo = Math.min(...vs) - 50, hi = Math.max(...vs) + 50;
    const x = (t) => m.l + (t1 === t0 ? 0.5 : (Date.parse(t) - t0) / (t1 - t0)) * (W - m.l - m.r);
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    // Escalones: el LP no cambia entre una foto y la siguiente.
    const pasos = lp.map((f, i) => (i ? `${x(f.t)},${y(lp[i - 1].valor)} ` : '') + `${x(f.t)},${y(f.valor)}`).join(' ');
    const ult = lp[lp.length - 1];
    return `<svg class="g-lp" viewBox="0 0 ${W} ${H}" role="img" aria-label="LP de solo/dúo en el tiempo">
      <polyline points="${pasos}" class="g-linea g-linea--lp"/>
      ${lp.map(f => `<circle cx="${x(f.t)}" cy="${y(f.valor)}" r="2.5" class="g-punto--lp"><title>${escapeHtml(f.tier)} ${escapeHtml(f.division || '')} · ${f.lp} LP</title></circle>`).join('')}
      <text x="${W - m.r}" y="${y(ult.valor) - 6}" class="g-eje" text-anchor="end">${escapeHtml(ult.tier)} ${escapeHtml(ult.division || '')} · ${ult.lp} LP</text>
    </svg>`;
}

/** Sección "Tu evolución": una pestaña por cola con 20+ partidas y el LP abajo. */
export function seccionEvolucion(evo) {
    if (!evo) return '';
    const colas = COLAS.filter(c => evo.colas?.[c]);
    if (!colas.length && !evo.lp?.length) return '';
    const principal = colas.sort((a, b) => evo.colas[b].n - evo.colas[a].n)[0];
    return `<section class="section evolucion">
      <div class="section-head"><h3>Tu evolución</h3>
        ${colas.length > 1 ? `<div class="chips-cola" role="tablist">${colas.map(c => `<button type="button" role="tab" class="chip-cola${c === principal ? ' is-active' : ''}"
            data-evo="${c}" aria-selected="${c === principal}">${escapeHtml(nombreCola(c))}</button>`).join('')}</div>` : ''}</div>
      ${colas.map(c => `<div class="evo-panel" data-panel="${c}"${c === principal ? '' : ' hidden'}>
          ${lecturaEvo(evo.colas[c], evo.ventana)}
          ${lineaWinrate({ ...evo.colas[c], cola: c }, evo.ventana)}</div>`).join('')}
      ${colas.length ? `<p class="nota">Cada punto es tu winrate en las ${evo.ventana} partidas anteriores a esa fecha: si la línea sube, venías ganando más. La banda es el margen de error; la línea punteada gris es el 50 % y la naranja, tu promedio de toda la temporada. Si la banda cubre tu promedio, ese tramo no se distingue de tu nivel de siempre.</p>` : ''}
      ${evo.lp?.length ? `<h4>LP en solo/dúo</h4>${lineaLp(evo.lp)}` : ''}
    </section>`;
}

// Las pestañas de cola de la evolución: un solo listener para todos los perfiles.
document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-evo]');
    if (!b) return;
    const sec = b.closest('.evolucion');
    sec.querySelectorAll('[data-evo]').forEach(x => { x.classList.toggle('is-active', x === b); x.setAttribute('aria-selected', x === b); });
    sec.querySelectorAll('.evo-panel').forEach(p => { p.hidden = p.dataset.panel !== b.dataset.evo; });
});

// ---- Tendencia: ¿estás mejorando? (índice por partida contra tu franja) ----

/** t: {puntos [{t, v}], recta {desde, hasta}, pendiente, lo, hi, veredicto, inicio, ahora, ventana, n}. */
export function seccionTendencia(t, rol, franja) {
    if (!t) return `<p class="dim">Hacen falta 30 partidas de ${escapeHtml(rol)} en solo/dúo para medir una tendencia.</p>`;
    const W = 640, H = 210, m = { l: 34, r: 12, t: 14, b: 24 };
    // Eje = número de partida (la recta se ajusta por partida); los meses quedan como rótulos.
    const n1 = Math.max(1, t.n - 1);
    const vs = t.puntos.map(p => p.v), lo = Math.max(0, Math.min(...vs, 40) - 8), hi = Math.min(100, Math.max(...vs, 60) + 8);
    const x = (i) => m.l + (i / n1) * (W - m.l - m.r);
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    const linea = t.puntos.map(p => `${x(p.i)},${y(p.v)}`).join(' ');
    // Un rótulo por mes, salteando los que quedarían pegados al anterior.
    let ultimo = -99;
    const meses = (t.meses || []).filter(mm => { const ok = x(mm.i) - ultimo > 28; if (ok) ultimo = x(mm.i); return ok; })
        .map(mm => `<line x1="${x(mm.i)}" x2="${x(mm.i)}" y1="${m.t}" y2="${H - m.b}" class="g-grilla"/>
          <text x="${x(mm.i) + 3}" y="${H - 6}" class="g-eje">${MESES[mm.mes - 1]}</text>`);
    const clase = t.veredicto === 'mejorando' ? 'win' : t.veredicto === 'empeorando' ? 'loss' : '';
    const signo = (v) => `${v > 0 ? '+' : ''}${num(v, 1)}`;
    return `<p class="evo-lectura">Empezaste la temporada en <strong>${num(t.inicio, 0)}</strong> y hoy estás en <strong>${num(t.ahora, 0)}</strong>
        <span class="tag ${clase}">${escapeHtml(t.veredicto)}</span>
        <span class="dim">${signo(t.pendiente)} puntos cada 100 partidas (${signo(t.lo)} a ${signo(t.hi)})</span></p>
      <svg class="g-evo" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tu índice por partida en ${escapeHtml(rol)} a lo largo de la temporada: de ${num(t.inicio, 0)} a ${num(t.ahora, 0)}, ${escapeHtml(t.veredicto)}">
        <line x1="${m.l}" x2="${W - m.r}" y1="${y(50)}" y2="${y(50)}" class="g-medio"/>
        <text x="${m.l - 6}" y="${y(50) + 4}" class="g-eje" text-anchor="end">50</text>
        <text x="${m.l + 4}" y="${y(50) - 5}" class="g-eje">mitad de ${escapeHtml(franja)}</text>
        <polyline points="${linea}" class="g-linea"/>
        <line x1="${x(t.recta.desde.i)}" y1="${y(t.recta.desde.v)}" x2="${x(t.recta.hasta.i)}" y2="${y(t.recta.hasta.v)}" class="g-recta g-recta--${clase || 'neutra'}"/>
        <circle cx="${x(t.n - 1)}" cy="${y(t.puntos[t.puntos.length - 1].v)}" r="5" class="g-punto"/>
        <text x="${W - m.r}" y="${H - 6}" class="g-eje" text-anchor="end">partida ${t.n}</text>
        ${meses.join('')}
      </svg>
      <p class="nota">Cada partida recibe un índice de 0 a 100: el promedio de tus percentiles en ${t.metricas.map(escapeHtml).join(', ').toLowerCase()}, contra jugadores de ${escapeHtml(franja)} en ${escapeHtml(rol)} (las muertes cuentan al revés). La línea celeste es el promedio de tus últimas ${t.ventana} partidas en cada momento y la recta, la tendencia de toda la temporada (${t.n} partidas). Mide cómo jugás, no si ganaste: el winrate depende demasiado de los compañeros. "Sin tendencia clara" quiere decir que el intervalo de la pendiente cruza el cero.</p>`;
}

// ---- Radar de los componentes del Performance contra tu franja ----

/** comps: [{nombre, nivel (0–1), sin_dato}]. El anillo punteado es 50: la mitad de tu franja. */
export function radar(comps, { titulo = '', segundo = null } = {}) {
    const S = 300, c = S / 2, R = 104, n = comps.length;
    const ang = (i) => -Math.PI / 2 + (2 * Math.PI * i) / n;
    const pt = (i, v) => `${c + Math.cos(ang(i)) * R * v},${c + Math.sin(ang(i)) * R * v}`;
    const poli = (vals) => vals.map((v, i) => pt(i, v)).join(' ');
    const anillos = [0.25, 0.75, 1].map(v => `<polygon points="${poli(comps.map(() => v))}" class="g-grilla"/>`).join('');
    const ejes = comps.map((k, i) => {
        const [lx, ly] = pt(i, 1.18).split(',').map(Number);
        const anc = Math.abs(lx - c) < 4 ? 'middle' : lx > c ? 'start' : 'end';
        return `<line x1="${c}" y1="${c}" x2="${pt(i, 1).split(',')[0]}" y2="${pt(i, 1).split(',')[1]}" class="g-grilla"/>
          <text x="${lx}" y="${ly + 4}" class="g-eje g-eje--radar" text-anchor="${anc}">${escapeHtml(k.nombre)}</text>`;
    }).join('');
    const vals = (cs) => cs.map(k => (k.sin_dato || k.nivel == null ? 0.5 : k.nivel));
    return `<svg class="g-radar" viewBox="-60 -10 ${S + 120} ${S + 20}" role="img" aria-label="${escapeHtml(titulo || 'Componentes contra tu franja')}">
      ${anillos}${ejes}
      <polygon points="${poli(comps.map(() => 0.5))}" class="g-medio"/>
      ${segundo ? `<polygon points="${poli(vals(segundo))}" class="g-area g-area--b"/>` : ''}
      <polygon points="${poli(vals(comps))}" class="g-area"/>
      ${comps.map((k, i) => `<circle cx="${pt(i, vals(comps)[i]).split(',')[0]}" cy="${pt(i, vals(comps)[i]).split(',')[1]}" r="3.5" class="g-punto">
        <title>${escapeHtml(k.nombre)}: ${k.sin_dato ? 'sin dato' : Math.round(k.nivel * 100)}</title></circle>`).join('')}
    </svg>`;
}

export { num };
