/* inicio.js — el grupo con su rango y las últimas partidas. */

import { state, loadRecientes } from './data.js';
import { onRoute } from './router.js';
import { escapeHtml, rangoTexto, tierClase, hace, iconoCampeon, nombreCola, fecha } from './utils.js';

export async function initInicio() {
    const { meta, personas } = state;
    const linea = document.getElementById('meta-linea');
    const ing = meta.ultima_ingesta;
    linea.textContent = `${personas.length} jugadores · ${meta.partidas.toLocaleString('es-AR')} partidas desde el 8/1/2026 · ` +
        `datos actualizados ${hace(Date.parse(meta.generado))}` +
        (ing && ing.cuentas_con_pendientes ? ` · todavía se están bajando partidas de ${ing.cuentas_con_pendientes} cuentas` : '');

    // #/inicio/glosario abre "Cómo leer los números"; #/inicio/glosario/<id> va además a esa entrada.
    const abrirGlosario = (param) => {
        const [que, id] = (param || '').split('/');
        if (que !== 'glosario') return;
        const d = document.getElementById('como-leer');
        d.open = true;
        const dt = id && document.getElementById(`g-${id}`);
        document.querySelectorAll('.glosario .resaltado').forEach(x => x.classList.remove('resaltado'));
        if (dt) { dt.classList.add('resaltado'); dt.nextElementSibling?.classList.add('resaltado'); }
        // Después del scroll arriba que hace el router al cambiar de vista.
        setTimeout(() => (dt || d).scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: dt ? 'center' : 'start' }), 30);
    };
    onRoute('inicio', abrirGlosario);
    // Un link al mismo hash no dispara hashchange: se abre a mano.
    document.addEventListener('click', (e) => {
        const a = e.target.closest('a[href^="#/inicio/glosario"]');
        if (a && a.getAttribute('href') === location.hash) { e.preventDefault(); abrirGlosario(a.getAttribute('href').slice('#/inicio/'.length)); }
    });

    const ordenadas = [...personas].sort((a, b) => (b.n > 0) - (a.n > 0) || b.n - a.n);
    document.getElementById('grupo-lista').innerHTML = ordenadas.map(p => `
        <a class="card persona" href="#/jugadores/${encodeURIComponent(p.id)}">
          <span class="persona-nombre">${escapeHtml(p.nombre)}</span>
          <span class="chip ${tierClase(p.solo)}">${escapeHtml(rangoTexto(p.solo))}</span>
          <span class="dim">${p.n} partidas · última ${hace(p.ultima)}</span>
        </a>`).join('');

    const recientes = (await loadRecientes()) || [];
    const nombre = Object.fromEntries(personas.map(p => [p.id, p.nombre]));
    document.getElementById('ultimas-lista').innerHTML = recientes.length ? `
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Fecha</th><th>Cola</th><th>Quiénes</th><th>Resultado</th></tr></thead>
        <tbody>${recientes.slice(0, 20).map(m => `
          <tr>
            <td class="mono">${fecha(m.inicio)}</td>
            <td>${escapeHtml(nombreCola(m.cola))}</td>
            <td>${m.jugadores.map(j => `<span class="quien">${iconoCampeon(j.champ, 22)} ${escapeHtml(nombre[j.persona] || j.persona)}
                <span class="dim mono">${j.k}/${j.d}/${j.a}</span></span>`).join('')}</td>
            <td>${m.jugadores.every(j => j.win) ? '<span class="win">Victoria</span>'
                 : m.jugadores.every(j => !j.win) ? '<span class="loss">Derrota</span>' : '<span class="dim">Enfrentados</span>'}</td>
          </tr>`).join('')}</tbody>
      </table></div>` : '<p class="empty-state">Todavía no hay partidas.</p>';
}
