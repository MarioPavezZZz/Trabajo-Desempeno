/**
 * Tokens visuales de TCGMASTER — estética "vitrina de coleccionista".
 *
 * El fondo es el paño verde de una vitrina o mesa de juego (no negro); el latón
 * se reserva para precios, bordes de cartas valiosas y foco. El lacre marca
 * ofertas y agotados. Ver docs/diseno-visual.md para la justificación.
 */
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        felt: {
          DEFAULT: "#13241E", // fondo: paño de vitrina
          raised: "#1A2F27", // paneles y placas
          deep: "#0E1B16", // franjas y pie
          line: "#2E473C", // bordes finos
        },
        brass: {
          DEFAULT: "#B8913A", // precios y detalles
          bright: "#D9B45A", // foco y hover
          dim: "#7E6630",
        },
        ivory: {
          DEFAULT: "#EDE6D6", // texto principal
          dim: "#A8B2A4", // texto secundario
        },
        wax: "#9E2B25", // lacre: ofertas, agotado
        cond: {
          nm: "#7DBB89",
          lp: "#B5C26A",
          mp: "#D9A25A",
          hp: "#D07468",
        },
        trend: {
          up: "#7DBB89",
          down: "#D07468",
        },
      },
      fontFamily: {
        display: ['"Gloock"', "Georgia", "serif"],
        sans: ['"Public Sans"', "system-ui", "sans-serif"],
      },
      // Escala modular 1.25 (tercera mayor) sobre 16 px.
      fontSize: {
        xs: ["0.8rem", { lineHeight: "1.2rem" }],
        sm: ["0.875rem", { lineHeight: "1.3rem" }],
        base: ["1rem", { lineHeight: "1.55rem" }],
        lg: ["1.25rem", { lineHeight: "1.75rem" }],
        xl: ["1.563rem", { lineHeight: "2rem" }],
        "2xl": ["1.953rem", { lineHeight: "2.3rem" }],
        "3xl": ["2.441rem", { lineHeight: "2.75rem" }],
        "4xl": ["3.052rem", { lineHeight: "3.3rem" }],
      },
      maxWidth: {
        shop: "78rem",
      },
    },
  },
  plugins: [],
} satisfies Config;
