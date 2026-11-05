/* rankings.js — rankings del grupo por período, por rol y dúos.
   Rutas: #/rankings/periodo, #/rankings/roles, #/rankings/duos. Todo dentro de
   cada cola; el valor principal es el ajustado, así nadie sube al podio con dos partidas. */

import { state, cachedFetch, MODOS, EN_MODO } from './data.js';
import { onRoute } from './router.js';
import { escapeHtml, nombreCola, conIntervalo, num, pistaDif, como, tagChica } from './utils.js';
import { nombrePersona, pct, chipConf, winrateAj, difWinrate, senal, NOTA_SENAL } from './fase2.js';

const GRIETA = ['solo', 'flex', 'normal'];
const ROLES = ['Top', 'Jungla', 'Mid', 'ADC', 'Support'];
const PERIODOS = { semana: 'Últimos 7 días', mes: 'Últimos 30 días', temporada: 'Temporada' };
const TABS = { periodo: 'Por período', roles: 'Por rol', duos: 'Dúos', companeros: 'Mejores compañeros', mejora: 'Quién más mejoró' };

const sel = { tab: 'periodo', periodo: 'mes', cola: 'solo', ventana: 'historico', modo: 'solo' };

const persona = (id) => `<a href="#/jugadores/${encodeURIComponent(id)}">${escapeHtml(nombrePersona(id))}</a>`;

function opciones(id, valores, actual, etiqueta) {
    return `<label class="selector">${etiqueta} <select id="${id}">${Object.entries(valores).map(([v, l]) =>
        `<option value="${v}"${v === actual ? ' selected' : ''}>${escapeHtml(l)}</option>`).join('')}</select></label>`;
}

// "Todo" junta solo, flex y normales: así entra quien juega poco de cada una.
const colas = (conTodo = true) => Object.fromEntries([...GRIETA, ...(conTodo ? ['todo'] : [])].map(c => [c, nombreCola(c)]));

async function porPeriodo(cont) {
    const d = await cachedFetch(`rankings/${sel.periodo}.json`);
    const c = d.colas[sel.cola];
    const podio = c.podio.map((id, i) => {
        const r = c.tabla.find(t => t.persona === id);
        return `<div class="podio-lugar p${i + 1}"><span class="podio-num">${i + 1}</span>${persona(id)}
          <span class="v">${pct(r.winrate_aj)}</span><span class="dim">${r.n} partidas</span></div>`;
    }).join('');
    cont.innerHTML = `
      <div class="section-head">${opciones('rk-periodo', PERIODOS, sel.periodo, 'Período')}${opciones('rk-cola', colas(), sel.cola, 'Cola')}</div>
      ${c.podio.length ? `<div class="podio">${podio}</div>` : '<p class="empty-state">Nadie llega a confianza media con 50 % ajustado o más en este período: no hay podio.</p>'}
      ${c.tabla.length ? `<div class="table-wrap"><table class="data-table">
        <thead><tr><th class="num">#</th><th>Jugador</th><th class="num">n</th><th class="num">Winrate ajustado</th><th class="num">KDA ajustado</th><th>Confianza</th></tr></thead>
        <tbody>${c.tabla.map(r => `<tr><td class="num mono">${r.puesto}</td><td>${persona(r.persona)}</td><td class="num mono">${r.n}</td>
          <td class="num">${winrateAj(r)}</td>
          <td class="num"><span class="v">${num(r.kda_aj, 2)}</span><span class="ic">real ${num(r.kda.v, 2)}</span></td>
          <td>${chipConf(r.confianza)}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${c.sin_muestra.length ? `<p class="nota">Sin muestra suficiente (menos de ${d.min} partidas): ${c.sin_muestra.map(([id, n]) => `${escapeHtml(nombrePersona(id))} (${n})`).join(', ')}.</p>` : ''}
      <p class="nota">Ordenado por winrate ajustado (${state.ajustes?.ajuste_muestra?.k_tasa ?? 10} partidas sumadas al 50 %). El podio exige confianza media o alta y ${Math.round((state.ajustes?.rankings?.piso_podio ?? 0.5) * 100)} % ajustado o más.</p>`;
    cont.querySelector('#rk-periodo').addEventListener('change', (e) => { sel.periodo = e.target.value; render(); });
    cont.querySelector('#rk-cola').addEventListener('change', (e) => { sel.cola = e.target.value; render(); });
}

async function porRol(cont) {
    const d = await cachedFetch('rankings/roles.json');
    const v = d[sel.ventana];
    const dec = (k) => (k.startsWith('dif_oro') ? 0 : k.startsWith('dif_cs') ? 1 : 2);
    cont.innerHTML = `
      <div class="section-head">${opciones('rk-ventana', { historico: 'Temporada', reciente: `Últimos ${d.reciente.dias} días` }, sel.ventana, 'Ventana')}${opciones('rk-cola', colas(), sel.cola, 'Cola')}</div>
      <div class="roles-grid">${ROLES.map(rol => {
        const g = v.grupos[`${sel.cola}|${rol}`];
        const s = (x) => `${x > 0 && g.metrica.startsWith('dif') ? '+' : ''}${num(x, dec(g.metrica))}`;
        return `<div class="card rol-card"><h4>${rol} <span class="dim">· ${escapeHtml(g.nombre)}</span></h4>
          ${g.tabla.length ? `<ol class="rol-lista">${g.tabla.map(r => `<li>${persona(r.persona)}
            <span class="v">${s(r.valor.v)}</span><span class="ic">${s(r.valor.lo)} a ${s(r.valor.hi)} · ${r.n} partidas</span></li>`).join('')}</ol>`
            : `<p class="dim">Nadie tiene ${v.min}+ partidas de ${rol} en esta cola.</p>`}</div>`;
    }).join('')}</div>
      <p class="nota">Cada rol se mide con lo suyo y contra el rival directo de la misma partida: oro a los 15 para las líneas y la jungla, visión por minuto para el support. Entra quien tiene ${v.min}+ partidas en el rol con confianza media o alta.</p>`;
    cont.querySelector('#rk-ventana').addEventListener('change', (e) => { sel.ventana = e.target.value; render(); });
    cont.querySelector('#rk-cola').addEventListener('change', (e) => { sel.cola = e.target.value; render(); });
}

/** Una frase con lo que se puede hacer con la tabla: qué dúo conviene armar y cuál no, o que todavía no se sabe. */
function conclusionDuos(t, nombre) {
    const ok = t.filter(r => !r.muestra_chica);
    const sen = ok.filter(r => r.senal), conf = ok.filter(r => !r.senal && (r.dif.lo > 0 || r.dif.hi < 0));
    const par = (r) => `<strong>${escapeHtml(nombre(r.a))} + ${escapeHtml(nombre(r.b))}</strong>`;
    const frases = sen.map(r => r.dif.v > 0 ? `${par(r)} rinde más junto que por separado: es un dúo para repetir.`
        : `${par(r)} rinde menos junto que por separado: conviene probar otras combinaciones.`);
    if (!frases.length && conf.length) frases.push(`${conf.map(par).join(', ')} ${conf.length > 1 ? 'pintan' : 'pinta'} distinto de lo esperado, pero falta muestra para confirmarlo: seguí jugando y mirá de nuevo.`);
    if (!frases.length) frases.push(ok.length ? 'Ningún dúo rinde distinto de lo esperado: jueguen con quien quieran, los números no marcan preferencia.' : 'Todavía no hay dúos con muestra suficiente para sacar una conclusión.');
    return `<p class="conclusion">${frases.join(' ')}</p>`;
}

/** Dúos normalizados (fase 6): juntos contra lo que daría cada uno por separado en el mismo período. */
function tablaNormalizada(n) {
    const t = n?.modos?.[sel.modo] || [];
    const pts = (v) => `${v > 0 ? '+' : ''}${num(v * 100, 0)}`;
    const pval = (p) => (p < 0.001 ? '< 0,001' : num(p, 3));
    const min = (n?.min_juntos ?? 15) * 2;
    return `<h2 class="h3">¿Rinden juntos más que por separado?</h2>
      <p class="dim">Para cada dúo: el winrate jugando juntos contra el que darían si cada uno aportara lo que gana sin el otro.</p>
      ${conclusionDuos(t, nombrePersona)}
      ${t.length ? `<div class="table-wrap"><table class="data-table tabla-apilable">
        <thead><tr><th>Dúo</th><th class="num">Juntos</th><th class="num">Winrate juntos</th><th class="num">Esperado<span class="ic">por separado</span></th><th class="num">Juntos − esperado<span class="ic">pts de winrate</span></th><th class="dv-celda"><span class="sr-only">Intervalo sobre el cero</span></th></tr></thead>
        <tbody>${t.map(r => `<tr class="${r.muestra_chica ? 'chica' : ''}">
          <td>${persona(r.a)} + ${persona(r.b)}${r.muestra_chica ? tagChica(min, 'partidas juntos') : ''}</td>
          <td class="num mono" data-label="Juntos">${r.juntos}</td>
          <td class="num" data-label="Winrate juntos">${conIntervalo(r.real, 'pct')}</td>
          <td class="num" data-label="Esperado"><span class="v">${pct(r.esperado)}</span><span class="ic">${pct(r.sin_a.v)} y ${pct(r.sin_b.v)}</span></td>
          <td class="num" data-label="Juntos − esperado" title="p corregido (BH) = ${pval(r.p_bh)}"><span class="v">${pts(r.dif.v)} pts</span><span class="ic">${pts(r.dif.lo)} a ${pts(r.dif.hi)}</span>${r.muestra_chica ? '' : senal(r)}</td>
          <td class="dv-celda">${r.muestra_chica ? '' : pistaDif(r.dif.v, r.dif.lo, r.dif.hi, 0.5, r.senal ? (r.dif.v > 0 ? 'pos' : 'neg') : '', `${pts(r.dif.v)} puntos, de ${pts(r.dif.lo)} a ${pts(r.dif.hi)}`)}</td></tr>`).join('')}</tbody></table></div>`
        : `<p class="empty-state">No hay dúos con ${n?.min_juntos ?? 15}+ partidas juntos en ${escapeHtml(EN_MODO[sel.modo])}.</p>`}
      ${como(`${escapeHtml(n?.nota || '')} ${NOTA_SENAL}`)}`;
}

async function duos(cont) {
    const [d, n] = await Promise.all([cachedFetch('sinergia.json'), cachedFetch('rankings/duos.json', { silent: true })]);
    // Un solo selector (Modo) para las dos tablas. La de abajo se prueba cola por cola (sumar "todo" duplicaría
    // las pruebas): en Todo se ven las tres colas, cada una en su fila.
    const enColas = sel.modo === 'todo' ? GRIETA : [sel.modo];
    const pares = new Map();
    d.filas.filter(r => enColas.includes(r.cola)).forEach(r => {
        const k = [r.cola, ...[r.persona, r.companero].sort()].join('|');
        const e = pares.get(k) || { a: null, b: null };
        if (r.persona < r.companero) e.a = r; else e.b = r;
        pares.set(k, e);
    });
    const filas = [...pares.values()].filter(e => e.a && e.b).sort((x, y) => y.a.juntos - x.a.juntos);
    const minS = d.min_juntos ?? state.ajustes?.min_partidas ?? 10;
    cont.innerHTML = `<div class="section-head">${opciones('rk-modo', MODOS, sel.modo, 'Modo')}</div>
      ${n ? tablaNormalizada(n) : ''}
      <h2 class="h3">¿A quién le sirve más jugar con quién?</h2>
      <p class="dim">Cada uno por su lado: cuánto cambia tu winrate cuando jugás con esa persona, contra cuando jugás sin ella en la misma cola.</p>
      ${filas.length ? `<div class="table-wrap"><table class="data-table tabla-apilable">
        <thead><tr><th>Dúo</th>${sel.modo === 'todo' ? '<th>Cola</th>' : ''}<th class="num">Juntos</th><th class="num">Winrate juntos</th><th class="num">Para el primero<span class="ic">pts de winrate</span></th><th class="num">Para el segundo<span class="ic">pts de winrate</span></th></tr></thead>
        <tbody>${filas.map(({ a, b }) => `<tr class="${a.muestra_chica ? 'chica' : ''}">
          <td>${persona(a.persona)} + ${persona(a.companero)}${a.muestra_chica ? tagChica(minS, 'partidas juntos') : ''}</td>
          ${sel.modo === 'todo' ? `<td data-label="Cola">${escapeHtml(nombreCola(a.cola))}</td>` : ''}
          <td class="num mono" data-label="Juntos">${a.juntos}</td>
          <td class="num" data-label="Winrate juntos">${conIntervalo(a.con, 'pct')}</td>
          <td class="num" data-label="Para el primero">${difWinrate(a.dif)} ${senal(a)}</td>
          <td class="num" data-label="Para el segundo">${difWinrate(b.dif)} ${senal(b)}</td></tr>`).join('')}</tbody></table></div>`
        : '<p class="empty-state">No hay dúos con suficientes partidas en este modo.</p>'}
      ${como(`"Para el primero" es cuánto cambia el winrate del primero cuando juega con el segundo, contra cuando juega sin esa persona en la misma cola (y al revés). Las dos tablas responden preguntas distintas: la de arriba compara al dúo con lo que daría cada uno por separado; esta, a cada uno consigo mismo con y sin el otro. Por eso un mismo dúo puede dar números distintos. Los recuentos tampoco coinciden con "Mejores compañeros": ahí se suman todos los compañeros de una persona, y una partida con dos amigos cuenta para los dos. ${NOTA_SENAL}`)}`;
    cont.querySelector('#rk-modo').addEventListener('change', (e) => { sel.modo = e.target.value; render(); });
}

async function mejora(cont) {
    const d = await cachedFetch('rankings/mejora.json');
    const tabla = d.modos?.[sel.modo] || d.tabla;
    const signo = (v) => `${v > 0 ? '+' : ''}${num(v, 1)}`;
    const mejoran = tabla.filter(x => x.veredicto === 'mejorando');
    const conc = `<p class="conclusion">${mejoran.length ? `${mejoran.map(x => `<strong>${escapeHtml(nombrePersona(x.persona))}</strong> (${escapeHtml(x.rol)})`).join(', ')} ${mejoran.length > 1 ? 'mejoraron' : 'mejoró'} de verdad: su nota de partida subió más de lo que explica el azar.` : 'Nadie mejoró más allá del ruido todavía: los cambios de la tabla pueden ser azar.'}</p>`;
    cont.innerHTML = `<div class="section-head">${d.modos ? opciones('rk-modo', MODOS, sel.modo, 'Modo') : ''}</div>` + (tabla.length ? `${conc}<div class="table-wrap"><table class="data-table">
      <thead><tr><th>Jugador</th><th>Rol</th><th class="num">Partidas</th><th class="num">Nota de partida<span class="ic">de → a</span></th><th class="num">Cambio<span class="ic">pts de nota, en sus partidas</span></th><th></th></tr></thead>
      <tbody>${tabla.map(x => `<tr class="${x.veredicto === 'mejorando' ? '' : 'chica'}"><td>${persona(x.persona)}</td><td>${escapeHtml(x.rol)}</td>
        <td class="num mono">${x.n}</td><td class="num mono">${num(x.inicio, 0)} → ${num(x.ahora, 0)}</td>
        <td class="num"><span class="v">${signo(x.cambio.v)}</span><span class="ic">${signo(x.cambio.lo)} a ${signo(x.cambio.hi)}</span></td>
        <td><span class="tag ${x.veredicto === 'mejorando' ? 'win' : x.veredicto === 'empeorando' ? 'loss' : ''}">${escapeHtml(x.veredicto)}</span></td></tr>`).join('')}</tbody></table></div>
      <p class="nota">La nota de partida va de 0 a 100 (50 = la mitad de tu franja en ese rol). No es el Performance: este mira partida por partida para ver hacia dónde vas. Cada uno se mide contra su propia franja, así que se puede comparar a un Hierro con un Esmeralda.</p>
      ${como(escapeHtml(d.nota))}`
      : `<p class="empty-state">Nadie tiene 30+ partidas de ${escapeHtml(EN_MODO[sel.modo])} en un rol con referencia.</p>`);
    cont.querySelector('#rk-modo')?.addEventListener('change', (e) => { sel.modo = e.target.value; render(); });
}

async function companeros(cont) {
    const d = await cachedFetch('rankings/companeros.json');
    const t = d.modos?.[sel.modo] || [];
    const max = Math.max(...t.filter(r => !r.muestra_chica && r.suma.v != null).map(r => Math.max(Math.abs(r.suma.lo), Math.abs(r.suma.hi))), 0.05);
    const w = (v) => `${Math.min(50, (Math.abs(v) / max) * 50)}%`;
    const fila = (r, i) => {
        const s = r.suma;
        const clase = r.senal ? (s.v > 0 ? 'ag-pos' : 'ag-neg') : 'ag-nada';
        const ic = s.lo == null ? '' : `<span class="cmp-ic" style="left:${50 + Math.max(-50, (s.lo / max) * 50)}%;width:${Math.min(100, ((s.hi - s.lo) / max) * 50)}%"></span>`;
        return `<details class="cmp-fila${r.muestra_chica ? ' chica' : ''}"><summary>
          <span class="cmp-pos mono">${r.muestra_chica ? '' : i + 1}</span>
          <span class="cmp-nombre">${persona(r.persona)}${r.muestra_chica ? tagChica(30, 'partidas con compañeros') : ''}</span>
          <span class="ag-pista">${ic}<span class="ag-barra ${clase}" style="${s.v >= 0 ? 'left:50%' : 'right:50%'};width:${w(s.v || 0)}"></span><span class="ag-cero"></span></span>
          <span class="cmp-num"><strong>${s.v > 0 ? '+' : ''}${num((s.v || 0) * 100, 1)} pts de winrate</strong>
            ${senal(r, s)}
            <span class="dim small">${r.companeros} compañeros · ${r.juntos} partidas</span></span></summary>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>Compañero</th><th class="num">Juntos</th><th class="num">Con ${escapeHtml(nombrePersona(r.persona))}</th><th class="num">Sin, mismo período</th></tr></thead>
            <tbody>${r.detalle.map(x => `<tr><td>${persona(x.companero)}</td><td class="num mono">${x.juntos}</td><td class="num">${conIntervalo(x.con, 'pct')}</td><td class="num">${conIntervalo(x.sin, 'pct')}</td></tr>`).join('')}</tbody></table></div>
        </details>`;
    };
    const grandes = t.filter(r => !r.muestra_chica), chicas = t.filter(r => r.muestra_chica);
    const top = grandes.find(r => r.senal && r.suma.v > 0);
    cont.innerHTML = `<div class="section-head">${opciones('rk-modo', MODOS, sel.modo, 'Modo')}</div>
      <p class="lead">${top ? `Con <strong>${escapeHtml(nombrePersona(top.persona))}</strong> en el equipo, sus compañeros ganan <strong>${num(top.suma.v * 100, 1)} puntos más</strong> que sin esa persona, y no es azar.` : 'Nadie se separa del ruido todavía: con estas partidas no se puede decir quién suma más.'}</p>
      ${grandes.length ? `<div class="cmp-lista">${grandes.map(fila).join('')}</div>` : '<p class="empty-state">Sin datos en este modo.</p>'}
      ${chicas.length ? `<details class="plegable"><summary>${chicas.length} con pocas partidas juntos</summary><div class="cmp-lista">${chicas.map(fila).join('')}</div></details>` : ''}
      <p class="nota">Tocá una fila para ver con quién. Ojo: no mide solo cómo juega cada uno; también pesa con quién y en qué cola suele jugar (en normales, jugar en grupo cambia el emparejamiento).</p>
      ${como(`${escapeHtml(d.nota)} La franja es el intervalo del 95 %. ${NOTA_SENAL}`)}`;
    cont.querySelector('#rk-modo').addEventListener('change', (e) => { sel.modo = e.target.value; render(); });
}

function render() {
    const cont = document.getElementById('rankings-cuerpo');
    document.querySelectorAll('#rankings-tabs a').forEach(a => a.classList.toggle('is-active', a.dataset.tab === sel.tab));
    // Cada pestaña pinta en su propia caja: si se cambia de pestaña antes de que cargue, la caja vieja ya no
    // está en la página y su respuesta tardía no pisa a la nueva.
    const caja = document.createElement('div');
    caja.innerHTML = '<div class="skeleton"></div>';
    cont.replaceChildren(caja);
    const fn = { periodo: porPeriodo, roles: porRol, duos, companeros, mejora }[sel.tab];
    fn(caja).catch(err => {
        console.error('[rankings]', err);
        caja.innerHTML = '<div class="error-state">No se pudo cargar este ranking.</div>';
    });
}

export function initRankings() {
    document.getElementById('rankings-tabs').innerHTML = Object.entries(TABS).map(([k, l]) =>
        `<a href="#/rankings/${k}" data-tab="${k}">${l}</a>`).join('');
    onRoute('rankings', (tab) => {
        sel.tab = TABS[tab] ? tab : 'periodo';
        render();
    });
}
