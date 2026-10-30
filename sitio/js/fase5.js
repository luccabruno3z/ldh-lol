/* fase5.js — bloques del perfil que salen de la investigación: rachas y pausas (Deng 2024). Cada bloque falla
   solo. Cada persona se compara consigo misma: si no, el que juega peor aparece más en las rachas. */

import { cachedFetch, EN_MODO } from './data.js';
import { escapeHtml, num, campeon } from './utils.js';

const pct = (v) => (v == null ? '—' : `${num(v * 100, 0)} %`);
const pts = (v) => `${v > 0 ? '+' : ''}${num(v * 100, 1)}`;

/** Una barra horizontal de 0 a 100 % con su intervalo, la línea de 50 y el valor. */
function barra(m) {
    if (!m?.n) return '<span class="dim">sin partidas</span>';
    const w = (x) => `${Math.max(0, Math.min(100, x * 100))}%`;
    return `<span class="rb-pista" role="img" aria-label="${pct(m.v)}, de ${pct(m.lo)} a ${pct(m.hi)}, ${m.n} partidas">
        <span class="rb-ic" style="left:${w(m.lo)};width:${w(m.hi - m.lo)}"></span>
        <span class="rb-v" style="left:${w(m.v)}"></span><span class="rb-mitad"></span></span>`;
}

function lectura(d) {
    const c = d.comparaciones.corta_vs_sigue, s = d.estados.tras_2_sigue, k = d.estados.tras_2_corta;
    if (!s.n || !k.n) return 'Todavía no hay suficientes rachas de 2 derrotas para comparar.';
    const veredicto = c.muestra_chica ? 'Con tan pocas partidas no se puede decir nada todavía.'
        : c.senal ? `<strong>${c.dif.v > 0 ? 'Te conviene cortar' : 'Cortar no te ayuda'}</strong>: la diferencia se separa del ruido.`
        : 'La diferencia es <strong>ruido</strong>: con estas partidas no cambia nada cortar o seguir.';
    return `Después de 2 derrotas, si seguís enseguida ganás <strong>${pct(s.v)}</strong> (${s.n} partidas); si cortás, <strong>${pct(k.v)}</strong> (${k.n}). ${veredicto}`;
}

export async function bloqueRachas(p, cont, modo) {
    if (p._cuenta) return;  // las rachas son de la persona: una sesión puede mezclar cuentas
    const [d, g] = await Promise.all([cachedFetch(`rachas/${encodeURIComponent(p.id)}.json`), cachedFetch('rachas/grupo.json')]);
    const m = d.modos?.[modo];
    if (!m) { cont.innerHTML = ''; return; }
    const gr = g.modos?.[modo] || {};
    const filas = Object.entries(d.estados).map(([k, nombre]) => `<div class="rb-fila${k.startsWith('tras_2') ? ' rb-clave' : ''}">
        <span class="rb-nombre">${escapeHtml(nombre)}</span>${barra(m.estados[k])}
        <span class="rb-num"><strong>${pct(m.estados[k].v)}</strong> <span class="dim">n = ${m.estados[k].n}</span></span></div>`).join('');
    const grupo = (c, txt) => (c?.v == null ? '' : `<li>${txt}: <strong>${pts(c.v)} pts</strong> <span class="dim">(${pts(c.lo)} a ${pts(c.hi)}, ${c.personas} personas)</span> ${c.ruido ? '<span class="tag">ruido</span>' : `<span class="tag ${c.v > 0 ? 'win' : 'loss'}">señal</span>`}</li>`);
    cont.innerHTML = `<section class="section">
      <h3>¿Te conviene seguir? <span class="dim">· ${escapeHtml(EN_MODO[modo])}</span></h3>
      <p class="lead">${lectura(m)}</p>
      <div class="rb-lista">${filas}</div>
      <p class="dim small">Winrate de la partida según cómo venías. La línea del medio es 50 %; la franja, el intervalo del 95 %. De la partida ${d.largas_desde} de la sesión en adelante: ${pct(m.sesion.largas.v)} (${m.sesion.largas.n}), antes ${pct(m.sesion.primeras.v)} (${m.sesion.primeras.n}).</p>
      <h4>En el grupo, cada uno contra sí mismo</h4>
      <ul class="rb-grupo">
        ${grupo(gr.racha_vs_victoria, 'Después de 2+ derrotas seguidas, contra después de ganar')}
        ${grupo(gr.corta_vs_sigue, `Cortar ${d.corte_min}+ min después de 2 derrotas, contra seguir`)}
        ${grupo(gr.largas_vs_cortas, `De la partida ${d.largas_desde} de la sesión en adelante, contra las primeras`)}
      </ul>
      <p class="nota">Una sesión son partidas con menos de ${d.sesion_min} min entre una y otra; "cortar" es esperar ${d.corte_min} min o más. Cuentan todas tus colas para saber cómo venías (una ARAM también corta una racha). Lo del grupo compara a cada persona consigo misma (Mantel–Haenszel), porque si no, el que juega peor aparece más en las rachas. En Corea, Deng y otros (2024) encontraron algo parecido: rachas de derrotas con peor rendimiento, y mejor con pausas.</p>
    </section>`;
}

// ---- Lo que te cuestan las muertes (costo = probabilidad de ganar que pierde tu equipo) ----

const MAPA = { x0: -120, y0: -120, x1: 14870, y1: 14980 };  // el mismo minimapa de fase4.js
const FASES = { temprana: 'Antes del 14', media: 'Del 14 al 25', tardia: 'Después del 25' };
const P = (v, d = 1) => (v == null ? '—' : num(v * 100, d));
const OBJ = { baron: 'el Barón', ancestral: 'el Ancestral', dragon: 'un dragón', heraldo: 'el Heraldo', larva: 'larvas', torre: 'una torre', inhib: 'un inhibidor' };

function perdidos(xs) {
    const u = [...new Set(xs || [])];
    return u.length ? `el rival tomó ${u.map(x => OBJ[x] || x).join(', ')}` : 'sin objetivo perdido';
}

function mapaMuertes(puntos, version) {
    const S = 320;
    const fase = (m) => (m < 14 ? 'temprana' : m < 25 ? 'media' : 'tardia');
    const circ = puntos.map(([m, x, y, c]) => {
        const px = ((x - MAPA.x0) / (MAPA.x1 - MAPA.x0)) * S, py = S - ((y - MAPA.y0) / (MAPA.y1 - MAPA.y0)) * S;
        return `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="${(2 + Math.sqrt(Math.max(c, 0)) * 30).toFixed(1)}" class="mu-p mu-${fase(m)}"><title>Minuto ${num(m, 0)}: ${P(c)} pts</title></circle>`;
    }).join('');
    return `<svg class="g-mapa mu-mapa" viewBox="0 0 ${S} ${S}" role="img" aria-label="${puntos.length} muertes sobre el minimapa; el tamaño es lo que costó cada una">
      <image href="https://ddragon.leagueoflegends.com/cdn/${version}/img/map/map11.png" width="${S}" height="${S}" opacity="0.5"/>${circ}</svg>
      <p class="fr-leyenda"><span class="fr-item"><span class="fr-sw mu-temprana"></span>antes del 14</span> <span class="fr-item"><span class="fr-sw mu-media"></span>del 14 al 25</span> <span class="fr-item"><span class="fr-sw mu-tardia"></span>después del 25</span> <span class="dim">· más grande = costó más · todo visto desde tu base abajo a la izquierda (las del lado rojo, espejadas)</span></p>`;
}

export async function bloqueMuertes(p, cont, modo, version) {
    if (p._cuenta) return;
    const d = await cachedFetch(`muertes/${encodeURIComponent(p.id)}.json`, { silent: true });
    const m = d?.modos?.[modo];
    if (!m || !Object.keys(m.roles).length) { cont.innerHTML = ''; return; }
    const roles = Object.keys(m.roles);
    let rol = 'Todos';
    const pintar = () => {
        const r = m.roles[rol], med = d.mediana_grupo[`${modo}|${rol}`];
        const max = Math.max(...Object.values(r.fases).map(x => x.costo || 0), 0.001);
        const fases = Object.entries(FASES).map(([k, n]) => {
            const f = r.fases[k];
            return `<div class="rb-fila"><span class="rb-nombre">${n}</span>
              <span class="rb-pista"><span class="mu-barra mu-${k}" style="width:${((f.costo || 0) / max) * 100}%"></span></span>
              <span class="rb-num"><strong>${P(f.costo)} pts</strong> <span class="dim">por muerte · ${f.n}</span></span></div>`;
        }).join('');
        const comp = med == null ? '' : r.por_partida > med * 1.1 ? `, más que la mediana del grupo (${P(med, 0)})`
            : r.por_partida < med * 0.9 ? `, menos que la mediana del grupo (${P(med, 0)})` : `, como la mediana del grupo (${P(med, 0)})`;
        cont.querySelector('#mu-cuerpo').innerHTML = !r.n ? '<p class="dim">Sin muertes con timeline en este rol.</p> ' : `
          <p class="lead">Cada muerte le cuesta a tu equipo <strong>${P(r.por_muerte.v)} puntos</strong> de probabilidad de ganar <span class="dim">(${P(r.por_muerte.lo)} a ${P(r.por_muerte.hi)}, ${r.n} muertes)</span>. Por partida suman <strong>${P(r.por_partida, 0)} puntos</strong>${comp}. El <strong>${P(r.con_objetivo, 0)} %</strong> de tus muertes le regalan un objetivo al rival en el minuto siguiente.</p>
          <div class="mu-grid"><div>${rol === 'Todos' ? mapaMuertes(m.puntos, version) : '<p class="dim">El mapa muestra todos tus roles juntos.</p>'}</div>
            <div><h4>Cuándo</h4><div class="rb-lista">${fases}</div>
              <h4>Dónde te cuestan más</h4>
              <div class="table-wrap"><table class="data-table"><thead><tr><th>Zona</th><th class="num">Muertes</th><th class="num">Por muerte</th><th class="num">Por partida</th></tr></thead>
                <tbody>${r.zonas.slice(0, 6).map(z => `<tr><td>${escapeHtml(z.nombre)}</td><td class="num mono">${z.n}</td><td class="num mono">${P(z.costo)}</td><td class="num mono">${P(z.total / r.partidas)}</td></tr>`).join('')}</tbody></table></div></div></div>`;
    };
    cont.innerHTML = `<section class="section">
      <div class="section-head"><h3>Lo que te cuestan las muertes <span class="dim">· ${escapeHtml(EN_MODO[modo])}</span></h3>
        ${roles.length > 1 ? `<label class="selector">Rol <select id="mu-rol">${roles.map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r === 'Todos' ? 'Todos los roles' : r)}</option>`).join('')}</select></label>` : ''}</div>
      <div id="mu-cuerpo"></div>
      ${m.caras.length ? `<h4>Tus 3 muertes más caras de las últimas 20 partidas</h4><div class="mu-caras">${m.caras.map(c => `<div class="card mu-cara">
          <span class="mu-cara-v">−${P(c.costo, 0)} pts</span><span>Minuto ${num(c.min, 0)} · ${escapeHtml(c.zona_nombre || '')} · ${escapeHtml(c.rol || '')}</span>
          <span class="dim">${escapeHtml(perdidos(c.perdidos))}${c.arriba ? ', ibas ganando' : ''}</span></div>`).join('')}</div>` : ''}
      <p class="nota">${escapeHtml(d.nota)} Sale del modelo de probabilidad de ganar (Guías → Cómo calculamos la probabilidad de ganar). Morir no siempre es un error: lo que más pesa es morir y que el rival se lleve algo, y morir tarde, cuando un Barón decide la partida (regla 9 del coaching).</p></section>`;
    pintar();
    cont.querySelector('#mu-rol')?.addEventListener('change', (e) => { rol = e.target.value; pintar(); });
}

// ---- Gráfico de una partida: la probabilidad de ganar de tu equipo, minuto a minuto ----

const ICONO = { baron: 'B', ancestral: 'A', dragon: 'D', heraldo: 'H', inhib: 'I' };

export function curvaPartida(d, pid) {
    const lado = d.lados?.[pid] === 'rojo' ? 'rojo' : 'azul';
    const eq = lado === 'azul' ? 100 : 200;
    const ys = d.curva.map(v => (lado === 'azul' ? v : 1 - v));
    const W = 620, H = 200, m = { l: 30, r: 10, t: 12, b: 22 };
    const n = Math.max(1, ys.length - 1);
    const x = (i) => m.l + (i / n) * (W - m.l - m.r), y = (v) => m.t + (1 - v) * (H - m.t - m.b);
    const linea = ys.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    const area = `${x(0)},${y(0.5)} ${linea} ${x(n)},${y(0.5)}`;
    const marcas = d.eventos.filter(e => (e.persona === pid && (e.tipo === 'muerte' || e.tipo === 'kill')) || ICONO[e.tipo]).map(e => {
        const i = Math.min(n, e.min), v = ys[Math.round(i)] ?? 0.5;
        if (e.tipo === 'muerte') return `<circle cx="${x(i)}" cy="${y(v)}" r="${3 + Math.sqrt(e.costo) * 18}" class="cp-muerte"><title>Moriste en el ${num(e.min, 1)}: −${P(e.costo)} pts, ${perdidos(e.perdidos)}</title></circle>`;
        if (e.tipo === 'kill') return `<circle cx="${x(i)}" cy="${y(v)}" r="3" class="cp-kill"><title>Kill en el ${num(e.min, 1)}</title></circle>`;
        const nuestro = e.equipo === eq;
        return `<text x="${x(i)}" y="${nuestro ? H - m.b - 4 : m.t + 9}" class="cp-obj ${nuestro ? 'cp-obj--nuestro' : 'cp-obj--rival'}" text-anchor="middle">${ICONO[e.tipo]}<title>${nuestro ? 'Tu equipo' : 'El rival'} tomó ${OBJ[e.tipo] || e.tipo} en el ${num(e.min, 1)}</title></text>`;
    }).join('');
    const k = d.clave;
    let lect = '';
    if (k) {
        const dv = lado === 'azul' ? k.delta : -k.delta;
        const ev = d.eventos.filter(e => e.min > k.min - 1 && e.min <= k.min && (ICONO[e.tipo] || e.tipo === 'muerte'));
        const que = ev.length ? ev.map(e => (e.tipo === 'muerte' ? (e.persona === pid ? 'tu muerte' : 'una muerte de alguien del grupo')
            : `${e.equipo === eq ? 'tu equipo tomó' : 'el rival tomó'} ${OBJ[e.tipo]}`)).join(', ') : 'peleas y oro';
        lect = `El minuto que más pesó fue el ${k.min}: <strong>${dv > 0 ? '+' : '−'}${P(Math.abs(dv), 0)} pts</strong> (${escapeHtml(que)}).`;
    }
    const marcasY = [0, 0.5, 1].map(v => `<text x="${m.l - 5}" y="${y(v) + 4}" class="g-eje" text-anchor="end">${v * 100}</text>`).join('');
    const marcasX = [...Array(Math.floor(n / 5) + 1).keys()].map(i => i * 5).map(t => `<text x="${x(t)}" y="${H - 6}" class="g-eje" text-anchor="middle">${t}</text>`).join('');
    return `<div class="cp">
      <p class="cp-lectura">${lect}</p>
      <svg class="cp-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Probabilidad de ganar de tu equipo minuto a minuto; terminó en ${d.ganador === eq ? 'victoria' : 'derrota'}">
        <polygon points="${area}" class="cp-area"/>
        <line x1="${m.l}" x2="${W - m.r}" y1="${y(0.5)}" y2="${y(0.5)}" class="g-medio"/>
        <polyline points="${linea}" class="g-linea"/>${marcas}${marcasY}${marcasX}</svg>
      <p class="fr-leyenda"><span class="fr-item"><span class="fr-sw cp-sw-muerte"></span>tus muertes (más grande, más costó)</span> <span class="fr-item"><span class="fr-sw cp-sw-kill"></span>tus kills</span> <span class="dim">· B Barón, A Ancestral, D dragón, H Heraldo, I inhibidor (abajo tu equipo, arriba el rival)</span></p></div>`;
}

// ---- Curva de aprendizaje: cuánto rendís con un campeón según cuántas partidas llevás con él ----

function grafCurva(tramos, propio) {
    const W = 560, H = 200, m = { l: 34, r: 10, t: 14, b: 26 };
    const vals = [...tramos, ...(propio || [])].flatMap(t => [t.lo, t.hi, t.v]).filter(v => v != null);
    const lim = Math.max(6, ...vals.map(Math.abs)) * 1.1;
    const n = tramos.length, paso = (W - m.l - m.r) / n;
    const x = (i) => m.l + paso * (i + 0.5), y = (v) => m.t + (1 - (v + lim) / (2 * lim)) * (H - m.t - m.b);
    const banda = (ts, cls) => {
        const ok = ts.map((t, i) => [t, i]).filter(([t]) => t.lo != null);
        if (ok.length < 2) return '';
        return `<polygon points="${[...ok.map(([t, i]) => `${x(i)},${y(t.hi)}`), ...ok.reverse().map(([t, i]) => `${x(i)},${y(t.lo)}`)].join(' ')}" class="${cls}"/>`;
    };
    const linea = (ts, cls) => `<polyline points="${ts.map((t, i) => [t, i]).filter(([t]) => t.v != null).map(([t, i]) => `${x(i)},${y(t.v)}`).join(' ')}" class="${cls}"/>`
        + ts.map((t, i) => (t.v == null ? '' : `<circle cx="${x(i)}" cy="${y(t.v)}" r="3.5" class="${cls}-p"><title>Partidas ${t.tramo}: ${t.v > 0 ? '+' : ''}${num(t.v, 1)} (${t.n} partidas)</title></circle>`)).join('');
    return `<svg class="g-evo cv-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Rendimiento contra tu nivel normal según cuántas partidas llevás con el campeón">
      <line x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}" class="g-medio"/>
      <text x="${m.l - 5}" y="${y(0) + 4}" class="g-eje" text-anchor="end">0</text>
      <text x="${m.l - 5}" y="${y(lim * 0.8) + 4}" class="g-eje" text-anchor="end">+${num(lim * 0.8, 0)}</text>
      <text x="${m.l - 5}" y="${y(-lim * 0.8) + 4}" class="g-eje" text-anchor="end">−${num(lim * 0.8, 0)}</text>
      ${banda(tramos, 'cv-banda')}${linea(tramos, 'cv-grupo')}
      ${propio ? banda(propio, 'cv-banda-p') + linea(propio, 'cv-propio') : ''}
      ${tramos.map((t, i) => `<text x="${x(i)}" y="${H - 8}" class="g-eje" text-anchor="middle">${t.tramo}</text>`).join('')}
    </svg>`;
}

export async function bloqueCurvas(p, cont, modo) {
    if (p._cuenta) return;
    const [d, g] = await Promise.all([cachedFetch(`curvas/${encodeURIComponent(p.id)}.json`, { silent: true }),
                                      cachedFetch('curvas/grupo.json', { silent: true })]);
    const gr = g?.modos?.[modo];
    if (!gr) { cont.innerHTML = ''; return; }
    const camps = d?.modos?.[modo]?.campeones || [];
    let sel = camps[0] ? `${camps[0].champ}|${camps[0].rol}` : '';
    const t0 = gr.tramos[0], tN = gr.tramos[gr.tramos.length - 1];
    const cruza = gr.tramos.find(t => t.v != null && t.v >= 0);
    const ESTADO = { 'por encima': 'win', 'por debajo': 'loss', 'a tu nivel': '' };
    const pintar = () => {
        const c = camps.find(x => `${x.champ}|${x.rol}` === sel);
        cont.querySelector('#cv-graf').innerHTML = grafCurva(gr.tramos, c?.tramos)
            + `<p class="fr-leyenda"><span class="fr-item"><span class="fr-sw cv-sw-grupo"></span>el grupo, con campeones nuevos</span>${c ? ` <span class="fr-item"><span class="fr-sw cv-sw-propio"></span>vos con ${escapeHtml(campeon(c.champ))}</span>` : ''} <span class="dim">· 0 = tu nivel normal en el rol</span></p>`
            + (c ? `<p>Con <strong>${escapeHtml(campeon(c.champ))}</strong> (${escapeHtml(c.rol)}, ${c.n} partidas), en tus últimas ${c.ahora.n} estás <span class="tag ${ESTADO[c.estado]}">${escapeHtml(c.estado)}</span> de tu nivel normal: ${c.ahora.v > 0 ? '+' : ''}${num(c.ahora.v, 1)} <span class="dim">(${num(c.ahora.lo, 1)} a ${num(c.ahora.hi, 1)})</span>.</p>` : '');
    };
    cont.innerHTML = `<section class="section">
      <div class="section-head"><h3>¿Cuánto te lleva aprender un campeón? <span class="dim">· ${escapeHtml(EN_MODO[modo])}</span></h3>
        ${camps.length ? `<label class="selector">Campeón <select id="cv-sel">${camps.map(c => `<option value="${c.champ}|${escapeHtml(c.rol)}">${escapeHtml(campeon(c.champ))} · ${escapeHtml(c.rol)} (${c.n})</option>`).join('')}</select></label>` : ''}</div>
      <p class="lead">En el grupo, las primeras ${t0.tramo} partidas con un campeón nuevo se juega <strong>${num(Math.abs(t0.v), 1)} puntos por debajo</strong> del nivel normal (gana ${pct(t0.winrate.v)})${cruza ? `; desde la partida <strong>${escapeHtml(cruza.tramo.split(/[–+]/)[0])}</strong> ya se está en el nivel normal` : ''}, y con ${tN.tramo} partidas, ${tN.v > 0 ? '+' : ''}${num(tN.v, 1)} (gana ${pct(tN.winrate.v)}).</p>
      <div id="cv-graf"></div>
      ${camps.length ? `<h4>Tus campeones (10+ partidas)</h4><div class="cv-chips">${camps.map(c => `<button type="button" class="chip-cola cv-chip" data-c="${c.champ}|${escapeHtml(c.rol)}">${escapeHtml(campeon(c.champ))} <span class="tag ${ESTADO[c.estado]}">${escapeHtml(c.estado)}</span></button>`).join('')}</div>` : '<p class="dim">Todavía no tenés campeones con 10+ partidas en este modo.</p>'}
      <p class="nota">${escapeHtml(d?.nota || g.nota)} ${escapeHtml(g.nota_grupo)} La franja es el intervalo del 95 %. "Por encima" o "por debajo" solo cuando el intervalo de tus últimas 10 partidas con ese campeón no toca el cero. Parecido a lo que muestran los análisis de maestría (iTero): se aprende rápido las primeras ~20 partidas y después se aplana.</p></section>`;
    pintar();
    cont.querySelector('#cv-sel')?.addEventListener('change', (e) => { sel = e.target.value; pintar(); });
    cont.querySelectorAll('.cv-chip').forEach(b => b.addEventListener('click', () => {
        sel = b.dataset.c;
        const s = cont.querySelector('#cv-sel');
        if (s) s.value = sel;
        pintar();
    }));
}

/** Al tocar el botón de una fila del historial se abre debajo el gráfico de esa partida. */
export function activarCurvas(tbody, pid) {
    tbody.addEventListener('click', async (e) => {
        const btn = e.target.closest('.cp-toggle');
        if (!btn) return;
        const tr = btn.closest('tr');
        if (tr.nextElementSibling?.classList.contains('cp-fila')) {
            tr.nextElementSibling.remove();
            btn.setAttribute('aria-expanded', 'false');
            btn.textContent = '▸';
            return;
        }
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = '▾';
        tr.insertAdjacentHTML('afterend', '<tr class="cp-fila"><td colspan="15"><div class="cp-cont"><div class="skeleton"></div></div></td></tr>');
        const cont = tr.nextElementSibling.querySelector('.cp-cont');
        const d = await cachedFetch(`partida/${encodeURIComponent(btn.dataset.id)}.json`, { silent: true });
        cont.innerHTML = d ? curvaPartida(d, pid) : '<p class="dim">Esta partida no tiene timeline: no hay gráfico.</p>';
    });
}
