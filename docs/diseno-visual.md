# Diseño visual — TCGMASTER

Estética elegida: **vitrina de coleccionista** (opción A, aprobada el 2026-11-15).

## Idea
La tienda se ve como el interior de una vitrina: un paño verde oscuro donde
el arte de las cartas es lo que resalta, con detalles de latón reservados para
lo que el cliente busca con la vista (precios, cartas valiosas, foco).

El elemento distintivo es la **tarjeta de precios con puntos guía** del hero
(como la etiqueta de precios de una vitrina de joyería): cada producto sellado
con una línea de puntos hasta su precio. Todo lo demás es sobrio.

## Paleta
| Token | Hex | Uso |
|---|---|---|
| `felt` | `#13241E` | Fondo (paño de vitrina; deliberadamente verde, no negro) |
| `felt-raised` | `#1A2F27` | Paneles y placas |
| `felt-deep` | `#0E1B16` | Encabezado y pie |
| `felt-line` | `#2E473C` | Bordes finos |
| `brass` | `#B8913A` | Precios, rareza, enlaces |
| `brass-bright` | `#D9B45A` | Foco de teclado, hover |
| `ivory` | `#EDE6D6` | Texto principal y placas de logos |
| `ivory-dim` | `#A8B2A4` | Texto secundario |
| `wax` (lacre) | `#9E2B25` | Descuentos |
| `cond-nm/lp/mp/hp` | verde → rojo | Escala de estado de conservación |

Los logos de set van sobre una **placa de marfil**: los íconos de Scryfall son
glifos negros y no se verían sobre el paño.

## Tipografía
- **Gloock** (serif de alto contraste) para títulos y nombres de set.
- **Public Sans** para la interfaz; cifras tabulares en precios y tablas.
- Escala modular 1,25 sobre 16 px. Fuentes servidas por nosotros (`@fontsource`),
  solo subconjunto latino y pesos usados (400 / 600 / 700).

## Indicadores
- **Rareza:** cinco rombos, los llenos indican el nivel (común → legendaria).
- **Estado:** etiqueta NM / LP / MP / HP con borde de color de la escala.
- **Foil:** marco iridiscente estático (gradiente cónico, sin animación).
- **Oferta:** porcentaje en lacre y precio anterior tachado.
- **Stock:** "Disponible", "Últimas 2 unidades", "Última unidad", "Agotado".

## Reglas para Core Web Vitals
- Toda imagen declara ancho y alto (proporción de carta 5:7): CLS = 0.
- Las primeras tarjetas y el logo del lanzamiento principal se cargan sin
  diferir; el resto con `loading="lazy"`.
- Sin animaciones automáticas, carruseles ni 3D. Las únicas transiciones son
  cambios de color en respuesta al usuario.
- El home va en el paquete principal; las demás páginas se cargan aparte.
- Mientras carga una página se reserva la pantalla completa, para que el pie
  no salte (corrigió un CLS de 0,19 medido en el primer prototipo).
