/* fase5.js — bloques del perfil que salen de la investigación: rachas y pausas (Deng 2024). Cada bloque falla
   solo. Cada persona se compara consigo misma: si no, el que juega peor aparece más en las rachas. */

import { cachedFetch, EN_MODO } from './data.js';
import { escapeHtml, num } from './utils.js';

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
