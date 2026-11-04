# DESIGN.md — LDH Stats LoL

## Dirección

**Inspirado en TRON.** Una grilla oscura donde los datos son líneas de luz: fondo casi negro, superficies apenas más
claras, contornos finos y un solo color protagonista, el cian, que brilla. El naranja es el contrapunto (como los
programas rivales de la película) y se usa poco. No se copia nada de la película: ni logos, ni tipografías, ni
imágenes. Se toman la paleta, la luz y la geometría.

El sitio es de **Operate/Read**: la gente viene a leer sus números. La personalidad vive en los detalles (el brillo
de una barra, los títulos en Bebas Neue, la geometría fina), nunca a costa de leer rápido una tabla.

## Color (tokens en `sitio/css/styles.css`, `:root`)

| Token | Oscuro (principal) | Claro | Uso |
|---|---|---|---|
| `--bg` | `#0a0a0f` | `#f4f6fa` | Fondo de la grilla |
| `--bg-2` | `#0f0f19` | `#e9edf4` | Header, pistas de las barras |
| `--surface` | `rgba(15,15,25,.85)` | `#ffffff` | Secciones |
| `--accent` | `#00e5e5` | `#00707c` | La línea de luz: links, barras, marcas, foco |
| `--accent-dim` | cian al 10 % | cian al 10 % | Fondos de lo activo, franjas de intervalo neutras |
| `--secondary` | `#ffa500` | `#9a5a00` | Contrapunto naranja (marca "LoL", detalles) |
| `--success` / `--danger` | `#00e07a` / `#ff4466` | `#0b7a40` / `#c62844` | Solo para "señal" a favor o en contra, victoria y derrota |
| `--text` / `--text-muted` / `--text-dim` | blanco / `#a0a0b0` / `#9090a2` | | Jerarquía del texto |
| `--border` | cian al 15 % | negro al 12 % | Contornos de controles |
| `--hairline` | blanco al 6 % | negro al 7 % | Separadores de filas y secciones |
| `--glow` | `0 0 6px` cian al 70 % | `none` | El brillo de las líneas de luz |
| `--tier-*` | | | Colores de cada división |

Reglas:
- **El brillo es solo para líneas de datos** (barras, marcas de valor) y solo en oscuro, vía `--glow`. No en texto, cards
  ni botones. En claro, las mismas líneas van sólidas sin brillo.
- Verde y rojo significan "se separa del ruido" a favor o en contra. Lo que es ruido va en cian o gris, nunca en verde
  o rojo.
- Contraste AA en los dos temas (verificado en la auditoría de noviembre de 2026).

## Tipografía

- **Títulos:** Bebas Neue (`--font-display`), espaciado `.03em`. `h2.h3` y `h3.h4` dejan el nivel semántico y el
  tamaño por separado.
- **Texto:** Montserrat 400–700 (`--font-body`), 15 px.
- **Cifras:** Roboto Mono (`--font-mono`) solo para datos y medidas; `tabular-nums` en las tablas.
- Notas a 62ch como máximo y párrafos guía (`.lead`) a 65ch.

## Geometría y forma

- Radios: `--r-sm` 6 px, `--r-md` 12 px, `--r-lg` 16 px. Las secciones llevan `--r-lg`, borde `--hairline` y `--shadow`.
- Dentro de una sección los bloques son planos (sin otra card adentro).
- Las pistas de los gráficos son finas (6–12 px), redondeadas, con fondo `--bg-2` y un contorno interior `--hairline`.

## Patrones de datos

- **Valor + intervalo:** `<span class="v">` arriba y `<span class="ic">` (mono, chico, dim) abajo, vía `conIntervalo`.
- **Pista de diferencia** (`pistaDif` en `utils.js`, clases `.dv-*`): cero al medio, franja = intervalo, marca = valor.
  Neutra en cian con brillo; con señal, en verde o rojo. Se usa en conversión y dúos.
- **Barra de magnitud** (`.obj-barra`): cian con `--glow`; en gris si es ruido.
- **Barras de winrate** (`.rb-*`) y **barras que divergen** (`.ag-*`) en rachas y "qué acompaña a ganar".
- **Muestra chica:** la fila va al final con `tr.chica` (texto dim) y la etiqueta `.tag`.
- **Tablas en celular:** las tablas nuevas usan `.tabla-apilable`. Por debajo de 600 px cada fila es un bloque y cada
  `td` muestra su `data-label`. Las pistas se ocultan, porque el número y su intervalo ya están. Las tablas viejas se
  desplazan dentro de `.table-wrap`.

## Voz

Castellano rioplatense, directo. Cada número con su n y su intervalo; "se asocia con", nunca "te hace ganar".
"Ruido" cuando no se separa. Sin estimar rangos (política de Riot).
