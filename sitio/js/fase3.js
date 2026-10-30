/* fase3.js — bloques de coaching del perfil: Performance, tu juego en una mirada, cómo sumar,
   los primeros 15 minutos y contra tu campeón. Todo sale de coaching/<id>.json; cada bloque
   falla solo. Los percentiles son contra jugadores de ranked solo/dúo de tu franja de rango y tu rol;
   el modo (solo/dúo, normales o todo) elige qué partidas tuyas entran. */

import { state, cachedFetch, rutaCoaching, MODOS, EN_MODO } from './data.js';
import { escapeHtml, iconoCampeon, campeon, num } from './utils.js';
import { pct, chipConf } from './fase2.js';
import { radar, seccionTendencia, graficoFranjas } from './graficos.js';

/** Valor de una métrica con su formato: signo en las diferencias, % donde corresponde. */
function fmt(m, x) {
    if (x == null) return '—';
    const signo = m.clave?.startsWith('dif') && x > 0 ? '+' : '';
    return `${signo}${num(x, m.dec ?? 2)}${m.unidad ? ' ' + m.unidad : ''}`;
}

// En el rango la unidad va una sola vez, al final: "−20 a +13 pts".
const valorIc = (m) => `<span class="v">${fmt(m, m.v)}</span>${m.lo == null ? '' : `<span class="ic">${fmt({ ...m, unidad: '' }, m.lo)} a ${fmt(m, m.hi)}</span>`}`;

/** Barra de percentil con su intervalo sombreado. */
function barra(p, lo, hi, titulo) {
    if (p == null) return '<span class="dim">—</span>';
    const w = (x) => `${Math.max(0, Math.min(100, x * 100))}%`;
    const clase = lo != null && lo > (state.ajustes?.performance?.umbral_fortaleza ?? 0.6) ? 'alto'
        : hi != null && hi < (state.ajustes?.performance?.umbral_debilidad ?? 0.4) ? 'bajo' : '';
    return `<span class="pbar ${clase}" title="${escapeHtml(titulo || '')}" role="img" aria-label="Percentil ${Math.round(p * 100)}">
      ${lo != null ? `<span class="pbar-ic" style="left:${w(lo)};width:${w(hi - lo)}"></span>` : ''}
      <span class="pbar-v" style="left:${w(p)}"></span><span class="pbar-mitad"></span></span>`;
}

const mejorQue = (m) => (m.pct == null ? '' : `mejor que el ${Math.round(m.pct * 100)} %<span class="ic">${Math.round(m.pct_lo * 100)} a ${Math.round(m.pct_hi * 100)}</span>`);

function selector(id, etiqueta, valores, actual, nombre = (x) => x) {
    return `<label class="selector">${etiqueta} <select id="${id}">${valores.map(v =>
        `<option value="${escapeHtml(v)}"${v === actual ? ' selected' : ''}>${escapeHtml(nombre(v))}</option>`).join('')}</select></label>`;
}

// ---- Performance ----

function performance(r, franja) {
    const pf = r.performance;
    // Solo contra tu propia franja: decir "rendís como un X" sería estimar un rango, y la política
    // de Riot prohíbe las alternativas al sistema de rangos (calculadoras de MMR/ELO).
    const lectura = pf.lo > 0.5 ? `Por encima de la mitad de los jugadores de <strong>${escapeHtml(franja)}</strong> en este rol.`
        : pf.hi < 0.5 ? `Por debajo de la mitad de los jugadores de <strong>${escapeHtml(franja)}</strong> en este rol.`
        : `A la par de la mitad de los jugadores de <strong>${escapeHtml(franja)}</strong> en este rol: el intervalo cruza el 50.`;
    const franjas = '';
    return `<div class="perf-radar">
      <div class="perf">
        <div class="perf-num"><span class="perf-v">${num(pf.v * 100, 0)}</span><span class="dim">/100</span>
          <span class="ic">${num(pf.lo * 100, 0)} a ${num(pf.hi * 100, 0)}</span></div>
        <div><p class="lead">${lectura}</p><div class="perf-franjas">${franjas}</div></div>
      </div>
      <div>${radar(r.componentes, { titulo: `Tus 7 componentes contra ${franja}; el anillo punteado es la mitad de tu franja` })}
        <p class="nota" style="text-align:center">El anillo punteado es la mitad de tu franja (50).</p></div>
      </div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Componente</th><th>Nivel en tu franja</th><th class="num">Peso</th><th class="num">Aporta</th><th class="num">Puede sumar</th></tr></thead>
        <tbody>${r.componentes.map(c => `<tr>
          <td>${escapeHtml(c.nombre)}${c.sin_dato ? ' <span class="tag">sin dato</span>' : ''}<div class="dim small">${c.metricas.map(k => escapeHtml(r.metricas[k]?.nombre || k)).join(' · ')}</div></td>
          <td>${c.sin_dato ? '<span class="dim">cuenta como 50</span>' : `${barra(c.nivel, c.lo, c.hi)} <span class="mono">${num(c.nivel * 100, 0)}</span><span class="ic">${num(c.lo * 100, 0)} a ${num(c.hi * 100, 0)}</span>`}</td>
          <td class="num mono">${num(c.peso * 100, 0)}</td>
          <td class="num mono">${num(c.aporte * 100, 1)}</td>
          <td class="num mono">${num(c.margen * 100, 1)}</td></tr>`).join('')}</tbody></table></div>
      <p class="nota">Cada componente es tu percentil contra ${r.n_ref} jugadores de ${escapeHtml(franja)} en el mismo rol (50 = la mitad de tu franja), y el Performance es la suma con los pesos. Con pocas partidas el índice se acerca a 50: con ${r.n} partidas pesa ${num(100 / (1 + Math.exp(-(r.n - (state.ajustes?.performance?.penalizacion_centro ?? 15)) / (state.ajustes?.performance?.penalizacion_escala ?? 4))), 0)} %. Los intervalos son bootstrap de tus partidas.${r.ref_winrate_crudo != null ? ` Los jugadores de referencia entran por su rango actual y en esas partidas ganaron el ${Math.round(r.ref_winrate_crudo * 100)} % (vienen de ${r.ref_winrate_crudo < 0.47 ? 'bajar' : r.ref_winrate_crudo > 0.53 ? 'subir' : 'ir parejos'}): sus victorias y derrotas se ponderan al 50 %.` : ''}</p>`;
}

// ---- Tu juego en una mirada y cómo sumar ----

function itemMetrica(m) {
    return `<li class="fd-item">
      <div class="fd-cab"><strong>${escapeHtml(m.nombre)}</strong> ${valorIc(m)}</div>
      <div>${barra(m.pct, m.pct_lo, m.pct_hi)} <span class="dim">${mejorQue(m)} · mediana de tu franja ${fmt(m, m.mediana)}</span></div>
      ${m.consejo ? `<p class="consejo">${escapeHtml(m.consejo)}</p>` : ''}
      ${m.nota ? `<p class="nota">${escapeHtml(m.nota)}</p>` : ''}</li>`;
}

function mirada(r) {
    const lista = (xs, vacio) => (xs.length ? `<ul class="fd-lista">${xs.map(itemMetrica).join('')}</ul>` : `<p class="dim">${vacio}</p>`);
    return `<div class="fd">
      <div><h4>Fortalezas</h4>${lista(r.fortalezas, 'Ninguna métrica queda claramente arriba de tu franja.')}</div>
      <div><h4>A mejorar</h4>${lista(r.mejorar, 'Ninguna métrica queda claramente abajo de tu franja.')}</div></div>
      <p class="nota">Entra una métrica cuando todo su intervalo de percentil queda arriba de ${Math.round((state.ajustes?.performance?.umbral_fortaleza ?? 0.6) * 100)} o abajo de ${Math.round((state.ajustes?.performance?.umbral_debilidad ?? 0.4) * 100)}; si cruza el medio, no se puede decir ni una cosa ni la otra.</p>`;
}

function sumar(r) {
    if (!r.sumar.length) return '';
    return `<ol class="sumar">${r.sumar.map(s => {
        const m = s.meta;
        const meta = !m ? '' : m.ya_supera
            ? `Ya estás en la mediana de ${escapeHtml(m.franja)} en ${escapeHtml(m.nombre.toLowerCase())} (${fmt(m, m.desde)}).`
            : `Meta: <strong>${escapeHtml(m.nombre.toLowerCase())}</strong> de ${fmt(m, m.desde)} a ${fmt(m, m.hasta)}, la mediana de ${escapeHtml(m.franja)}.`;
        return `<li><div class="fd-cab"><strong>${escapeHtml(s.nombre)}</strong> <span class="dim">nivel ${num(s.nivel * 100, 0)} · puede sumar ${num(s.margen * 100, 1)} puntos</span></div>
          <p>${meta}</p><p class="consejo">${escapeHtml(s.consejo)}</p></li>`;
    }).join('')}</ol>
      <p class="nota">Son los dos componentes donde más puntos podés sumar (peso × lo que te falta para 100). El winrate no entra: es el resultado del resto.</p>`;
}

// ---- Primeros 15 minutos ----

function temprano(d, cola, rol) {
    const t = d.temprano?.[cola]?.[rol];
    if (!t) return `<p class="empty-state">Menos de ${state.ajustes?.min_partidas ?? 10} partidas de ${escapeHtml(rol)} en ${escapeHtml(MODOS[cola])}.</p>`;
    const ref = d.roles?.[rol]?.metricas || {};
    const l = t.linea;
    const lineaTxt = l.gana.n && l.pierde.n
        ? `Vas arriba en oro contra tu rival a los 15 en ${pct(l.pct_gana.v)} de las partidas. Cuando vas arriba ganás ${pct(l.gana.v)} (${l.gana.n} partidas); cuando vas abajo, ${pct(l.pierde.v)} (${l.pierde.n}). ${l.senal ? '' : 'La diferencia no se separa del ruido. '}<span class="dim">Fisher p = ${num(l.p, 3)}</span>`
        : '';
    return `<div class="table-wrap"><table class="data-table">
      <thead><tr><th>Métrica</th><th class="num">Tu promedio</th><th>Contra tu franja</th><th class="num">Mediana de tu franja</th></tr></thead>
      <tbody>${Object.entries(t.metricas).map(([k, m]) => {
        const mm = { ...m, clave: k }, r = ref[k];
        return `<tr><td>${escapeHtml(m.nombre)}</td><td class="num">${valorIc(mm)} <span class="dim">n = ${m.n}</span></td>
          <td>${r ? `${barra(r.pct, r.pct_lo, r.pct_hi)} <span class="dim small">${mejorQue(r)}</span>` : '<span class="dim">sin referencia</span>'}</td>
          <td class="num mono">${r ? fmt({ ...r, clave: k }, r.mediana) : '—'}</td></tr>`;
    }).join('')}</tbody></table></div>
      ${lineaTxt ? `<p class="lead">${lineaTxt}</p>` : ''}
      <p class="nota">Las diferencias son contra el rival directo de la misma partida (la misma posición del otro equipo).</p>`;
}

// ---- Contra tu campeón ----

function contraCampeon(lista, modo) {
    if (!lista.length) return '';
    const bloques = lista.map(c => `<div class="campeon-ref">
      <div class="fd-cab">${iconoCampeon(c.campeon_id, 28)}<strong>${escapeHtml(campeon(c.campeon_id))}</strong> <span class="dim">${escapeHtml(c.rol)} · tus ${c.n} partidas contra ${c.n_ref} de ${c.jugadores_ref} jugadores distintos</span></div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Métrica</th><th class="num">Vos</th><th class="num">Ellos</th><th class="num">Diferencia</th><th></th></tr></thead>
        <tbody>${[{ clave: 'winrate', nombre: 'Winrate', dec: 0, unidad: '%', mejor: true, tuyo: null, ellos: null, ...c.winrate, pctw: true }, ...c.filas].map(f => {
            // Una diferencia entre porcentajes son puntos, no un porcentaje.
            const ff = f.pctw ? { ...f, v: f.v * 100, lo: f.lo * 100, hi: f.hi * 100, clave: 'dif', unidad: 'pts' }
                : { ...f, clave: 'dif' + f.clave, unidad: f.unidad === '%' ? 'pts' : f.unidad };
            const bien = f.ruido ? '<span class="tag">ruido</span>' : `<span class="tag ${(f.v > 0) === f.mejor ? 'win' : 'loss'}">${(f.v > 0) === f.mejor ? 'mejor' : 'peor'}</span>`;
            return `<tr><td>${escapeHtml(f.nombre)}</td>
              <td class="num mono">${f.pctw ? `${num(c.winrate_tuyo * 100, 0)} %` : fmt(f, f.tuyo)}</td><td class="num mono">${f.pctw ? `${num(c.winrate_ellos * 100, 0)} %` : fmt(f, f.ellos)}</td>
              <td class="num">${valorIc(ff)}</td><td>${bien}</td></tr>`;
        }).join('')}</tbody></table></div></div>`);
    // Los dos con más partidas a la vista; el resto plegado (con 9 campeones el bloque era media página).
    return bloques.slice(0, 2).join('') +
        (bloques.length > 2 ? `<details class="plegable"><summary>${bloques.length - 2} campeones más</summary>${bloques.slice(2).join('')}</details>` : '') +
        `<p class="nota">"Ellos" son los desconocidos que jugaron el mismo campeón en el mismo rol en las partidas del grupo (${escapeHtml(EN_MODO[modo])}), en tu franja; se sacan las partidas donde su rival directo era alguien del grupo. Es por partida (casi todos aparecen una vez), por eso va la columna de jugadores distintos. Son compañeros y rivales del grupo en partes iguales y en total ganan el 50 %, así que jugar con o contra ustedes no los sesga.</p>`;
}

// ---- Armado ----

/** De dónde sale la franja: rango de solo/dúo, de flex o, sin rango, toda la referencia del rol. */
function textoFranja(d) {
    if (d.fuente_franja === 'sin_rango') {
        return `Sin rango en solo/dúo ni en flex: te comparo contra toda la referencia del rol, de <strong>${escapeHtml(d.franja)}</strong> (no es tu franja).`;
    }
    const de = d.fuente_franja === 'flex' ? 'tu rango de flex (no tenés de solo/dúo)' : 'tu rango de solo/dúo';
    return `Te comparo contra jugadores de ranked solo/dúo de <strong>${escapeHtml(d.franja)}</strong>, tu franja por ${de}.`;
}

export async function bloquesFase3(p, cont, modo = 'solo') {
    if (p._cuenta) {
        // El coaching necesita muestra y una franja por rango: se calcula con todas las cuentas juntas.
        cont.innerHTML = '<section class="section"><h3>Coaching</h3><p class="empty-state">El coaching, los primeros 15 minutos y la sinergia se calculan con todas tus cuentas juntas. Volvé a "Todas las cuentas" para verlos.</p></section>';
        return;
    }
    const d = await cachedFetch(rutaCoaching(p.id, modo));
    const roles = Object.keys(d.roles || {});
    let rol = d.rol_con_referencia || d.rol_principal || roles[0];
    const rolesT = Object.keys(d.temprano?.[modo] || {});
    let rolT = rolesT.includes(rol) ? rol : rolesT[0];
    const nombreModo = MODOS[modo];

    const coaching = () => {
        const r = d.roles[rol];
        if (r.sin_referencia) {
            return `<p class="empty-state">La referencia de ${escapeHtml(d.franja)} en ${escapeHtml(rol)} tiene ${r.n_ref} jugadores con ${state.ajustes?.referencia?.min_partidas ?? 10}+ partidas; hacen falta ${state.ajustes?.referencia?.min_jugadores ?? 20}. Sin eso no se muestran percentiles.</p>`;
        }
        return `<h4>Tu Performance <span class="dim">· ${escapeHtml(rol)} en ${escapeHtml(EN_MODO[modo])} · ${r.n} partidas</span> ${chipConf(r.confianza)}</h4>${performance(r, d.franja)}
          ${r.por_franja?.length ? `<h4>Contra cada franja</h4>${graficoFranjas(r.por_franja)}
            <p class="nota">Tu promedio al lado de la mediana de los ${r.n_ref} jugadores de referencia de cada franja en ${escapeHtml(rol)} (ranked solo/dúo de LAS, victorias y derrotas al 50 %). Cada fila tiene su escala. Muestra a qué distancia está cada elo; no dice a qué franja te parecés, porque Riot no permite estimar rangos.</p>` : ''}
          <h4>Tu juego en una mirada</h4>${mirada(r)}
          <h4>¿Estás mejorando?</h4>${seccionTendencia(r.tendencia, rol, d.franja)}
          <h4>Cómo sumar</h4>${sumar(r)}`;
    };
    const vacio = `<p class="empty-state">Ningún rol con ${state.ajustes?.min_partidas ?? 10}+ partidas en ${escapeHtml(EN_MODO[modo])}${d.n_modo ? ` (tenés ${d.n_modo} en total)` : ''}.${modo !== 'todo' ? ' Probá el modo Todo, arriba: junta todas tus partidas de la Grieta.' : ''}</p>`;
    cont.innerHTML = `<section class="section" id="f3-coaching">
        <div class="section-head"><h3>Coaching</h3>${roles.length > 1 ? selector('f3-rol', 'Rol', roles, rol) : ''}</div>
        <p class="dim">${textoFranja(d)}</p>
        ${d.nota_modo ? `<p class="aviso-modo">${escapeHtml(d.nota_modo)}</p>` : ''}
        <div id="f3-cuerpo">${roles.length ? coaching() : vacio}</div>
      </section>
      ${rolesT.length ? `<section class="section">
        <div class="section-head"><h3>Tus primeros 15 minutos</h3>${rolesT.length > 1 ? selector('f3-rolT', 'Rol', rolesT, rolT) : ''}</div>
        <div id="f3-temprano">${temprano(d, modo, rolT)}</div></section>` : ''}
      ${d.campeones?.length ? `<section class="section"><h3>Contra tu campeón</h3>${contraCampeon(d.campeones, modo)}</section>` : ''}`;

    cont.querySelector('#f3-rol')?.addEventListener('change', (e) => {
        rol = e.target.value;
        cont.querySelector('#f3-cuerpo').innerHTML = coaching();
    });
    cont.querySelector('#f3-rolT')?.addEventListener('change', (e) => {
        rolT = e.target.value;
        cont.querySelector('#f3-temprano').innerHTML = temprano(d, modo, rolT);
    });
}
