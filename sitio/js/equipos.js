/* equipos.js — el 5 ideal del grupo y el balanceador de inhouses (fase 4).

   Requisitos del doc de lecciones (balanceador que se usó para Clash):
   1. Nadie va a un rol con menos de min_rol partidas ahí (regla 14).
   2. No el mismo campeón en los dos equipos.
   3. Si no hay ninguna asignación donde todos cumplan, decirlo y mostrar el mejor compromiso.
   La fuerza de cada uno en un rol es su winrate ajustado ahí (10 partidas al 50 %). */

import { state, cachedFetch } from './data.js';
import { onRoute } from './router.js';
import { escapeHtml, iconoCampeon, campeon, num } from './utils.js';

const ROLES = ['Top', 'Jungla', 'Mid', 'ADC', 'Support'];
let datos = null;
const elegidos = new Set();

function permutaciones(xs) {
    if (xs.length <= 1) return [xs];
    return xs.flatMap((x, i) => permutaciones([...xs.slice(0, i), ...xs.slice(i + 1)]).map(p => [x, ...p]));
}
const PERMS = permutaciones([0, 1, 2, 3, 4]);

/** Mejor asignación de 5 personas a los 5 roles: primero cuántos cumplen el mínimo, después la fuerza. */
function mejorAsignacion(pids) {
    let mejor = null;
    for (const perm of PERMS) {
        let cumplen = 0, suma = 0;
        const asig = ROLES.map((rol, k) => {
            const r = datos.jugadores[pids[perm[k]]].roles[rol];
            const n = r ? r.n : 0;
            if (n >= datos.min_rol) cumplen += 1;
            const f = r ? r.wr_aj : 0.45;  // sin partidas en el rol: por debajo del promedio
            suma += f;
            return { rol, pid: pids[perm[k]], n, wr_aj: r ? r.wr_aj : null };
        });
        const cand = { asig, cumplen, fuerza: suma / 5 };
        if (!mejor || cand.cumplen > mejor.cumplen || (cand.cumplen === mejor.cumplen && cand.fuerza > mejor.fuerza)) mejor = cand;
    }
    return mejor;
}

function combinaciones(xs, k) {
    if (k === 0) return [[]];
    if (xs.length < k) return [];
    const [a, ...r] = xs;
    return [...combinaciones(r, k - 1).map(c => [a, ...c]), ...combinaciones(r, k)];
}

/** Las 126 particiones 5v5 (el primero siempre en A para no contar dos veces cada una). */
function balancear(pids) {
    const [primero, ...resto] = pids;
    let mejor = null;
    for (const c of combinaciones(resto, 4)) {
        const A = [primero, ...c], B = resto.filter(p => !c.includes(p));
        const a = mejorAsignacion(A), b = mejorAsignacion(B);
        const cumplen = a.cumplen + b.cumplen;
        const dif = Math.abs(a.fuerza - b.fuerza);
        const cand = { a, b, cumplen, dif };
        if (!mejor || cand.cumplen > mejor.cumplen || (cand.cumplen === mejor.cumplen && cand.dif < mejor.dif)) mejor = cand;
    }
    return mejor;
}

/** Un campeón por jugador: el de mejor winrate ajustado con min_campeon+ en ese rol, sin repetir entre equipos. */
function campeones(asigs) {
    const usados = new Set(), out = new Map();
    // Primero los que tienen menos opciones, así no se quedan sin ninguna.
    const orden = asigs.flat().map(x => ({ ...x, ops: datos.jugadores[x.pid].roles[x.rol]?.campeones || [] }))
        .sort((p, q) => p.ops.length - q.ops.length);
    for (const x of orden) {
        const c = x.ops.find(o => !usados.has(o.id));
        if (c) usados.add(c.id);
        out.set(`${x.pid}|${x.rol}`, c || null);
    }
    return out;
}

const nombre = (pid) => escapeHtml(datos.jugadores[pid]?.nombre || pid);
const pct = (v) => (v == null ? '—' : `${num(v * 100, 0)} %`);

function tablaEquipo(titulo, eq, champs, clase) {
    return `<div class="card eq-card ${clase}"><h4>${titulo} <span class="dim">fuerza ${pct(eq.fuerza)}</span></h4>
      <table class="data-table"><tbody>${eq.asig.map(x => {
        const c = champs?.get(`${x.pid}|${x.rol}`);
        const falta = x.n < datos.min_rol;
        return `<tr class="${falta ? 'chica' : ''}"><td class="dim">${x.rol}</td>
          <td><a href="#/jugadores/${encodeURIComponent(x.pid)}">${nombre(x.pid)}</a>${falta ? ` <span class="tag loss">${x.n} partidas</span>` : ''}</td>
          <td class="num mono">${pct(x.wr_aj)}<span class="ic">${x.n} part.</span></td>
          <td class="champ">${c ? `${iconoCampeon(c.id, 22)}${escapeHtml(campeon(c.id))} <span class="dim">${c.n}</span>` : '<span class="dim">sin campeón con 5+</span>'}</td></tr>`;
      }).join('')}</tbody></table></div>`;
}

function resultado() {
    const cont = document.getElementById('eq-resultado');
    const pids = [...elegidos];
    if (pids.length !== 10) {
        cont.innerHTML = `<p class="empty-state">Elegí 10 jugadores (${pids.length} de 10).</p>`;
        return;
    }
    const r = balancear(pids);
    const champs = campeones([r.a.asig, r.b.asig]);
    const pA = r.a.fuerza / (r.a.fuerza + r.b.fuerza);
    const parejo = Math.abs(pA - 0.5) < 0.02;
    const aviso = r.cumplen < 10
        ? `<p class="error-state">No hay ninguna forma de armar dos equipos donde los 10 tengan ${datos.min_rol}+ partidas en su rol. Este es el mejor compromiso: ${r.cumplen} de 10 cumplen (los marcados en rojo).</p>` : '';
    cont.innerHTML = `${aviso}
      <p class="evo-lectura">${parejo ? '<span class="tag">parejo</span>' : ''} Equipo A ${pct(pA)} · Equipo B ${pct(1 - pA)}
        <span class="dim">diferencia de fuerza ${num(Math.abs(r.a.fuerza - r.b.fuerza) * 100, 1)} puntos</span></p>
      <div class="eq-grid">${tablaEquipo('Equipo A', r.a, champs, 'eq-a')}${tablaEquipo('Equipo B', r.b, champs, 'eq-b')}</div>
      <p class="nota">Probabilidad = fuerza A / (fuerza A + fuerza B), como el predictor del doc de funcionalidades. Es una estimación sin calibrar: todavía no hay inhouses registradas para medir si acierta. "Parejo" si la diferencia es menor a 2 puntos. Los campeones sugeridos son los de mejor winrate ajustado en ese rol con 5+ partidas, sin repetir entre equipos.</p>`;
}

function ideal() {
    if (!datos.ideal?.length) return '<p class="empty-state">No hay cinco personas distintas con 10+ partidas en cada rol.</p>';
    return datos.ideal.map((op, i) => `<div class="card eq-card${i ? '' : ' eq-a'}"><h4>${i ? `Opción ${i + 1}` : 'El 5 ideal'} <span class="dim">fuerza ${pct(op.fuerza)}</span></h4>
      <table class="data-table"><tbody>${op.equipo.map(x => `<tr><td class="dim">${x.rol}</td>
        <td><a href="#/jugadores/${encodeURIComponent(x.persona)}">${nombre(x.persona)}</a></td>
        <td class="num mono">${pct(x.wr_aj)}<span class="ic">${x.n} part.</span></td></tr>`).join('')}</tbody></table></div>`).join('');
}

async function render() {
    datos ||= await cachedFetch('equipos.json');
    const cont = document.getElementById('equipos-cuerpo');
    const pids = Object.keys(datos.jugadores).sort((a, b) => datos.jugadores[a].nombre.localeCompare(datos.jugadores[b].nombre));
    cont.innerHTML = `
      <section class="section"><h3>El 5 ideal del grupo</h3>
        <p class="dim">Una persona por rol, todas distintas, con ${datos.min_rol}+ partidas en ese rol, que sume el mejor winrate ajustado.</p>
        <div class="eq-grid">${ideal()}</div>
        <p class="nota">${escapeHtml(datos.nota)}</p></section>
      <section class="section"><h3>Armar una inhouse</h3>
        <p class="dim">Elegí 10 y el balanceador arma los dos equipos más parejos, con cada uno en un rol donde tenga ${datos.min_rol}+ partidas.</p>
        <div class="eq-elegir">${pids.map(p => `<label class="eq-chip"><input type="checkbox" value="${escapeHtml(p)}"${elegidos.has(p) ? ' checked' : ''}> ${nombre(p)}</label>`).join('')}</div>
        <div id="eq-resultado"></div></section>`;
    cont.querySelectorAll('.eq-elegir input').forEach(cb => cb.addEventListener('change', () => {
        if (cb.checked) elegidos.add(cb.value); else elegidos.delete(cb.value);
        resultado();
    }));
    resultado();
}

export function initEquipos() {
    onRoute('equipos', () => render().catch(err => {
        console.error('[equipos]', err);
        document.getElementById('equipos-cuerpo').innerHTML = '<div class="error-state">No se pudo cargar equipos.</div>';
    }));
}

export { state };
