/**
 * Secciones del catálogo. Todas usan la misma página de listado con un
 * filtro fijo (preset) y un conjunto de filtros visibles.
 */
import type { SectionPreset } from "../lib/filters";

export type FilterGroup = "game" | "set" | "rarity" | "condition" | "lang" | "foil" | "price" | "stock";

export interface Section {
  path: string;
  title: string;
  /** Sustantivo para el conteo: "450 cartas". */
  noun: [singular: string, plural: string];
  intro: string;
  preset: SectionPreset;
  filters: FilterGroup[];
}

const ALL_FILTERS: FilterGroup[] = ["game", "set", "rarity", "condition", "lang", "foil", "price", "stock"];

export const SECTIONS: Section[] = [
  {
    path: "/cartas",
    title: "Cartas",
    noun: ["carta", "cartas"],
    intro: "Cartas sueltas de Pokémon, Magic y Yu-Gi-Oh!, con estado, idioma y acabado indicados en cada una.",
    preset: { type: "carta" },
    filters: ALL_FILTERS,
  },
  {
    path: "/sellados",
    title: "Sellados",
    noun: ["producto sellado", "productos sellados"],
    intro: "Sobres, displays, cajas de entrenador y mazos de cada expansión, sin abrir.",
    preset: { type: "sellado" },
    filters: ["game", "set", "lang", "price", "stock"],
  },
  {
    path: "/ofertas",
    title: "Ofertas",
    noun: ["oferta", "ofertas"],
    intro: "Productos con precio rebajado. El precio anterior aparece tachado.",
    preset: { onSale: true },
    filters: ALL_FILTERS,
  },
  {
    path: "/accesorios",
    title: "Accesorios",
    noun: ["accesorio", "accesorios"],
    intro: "Fundas, carpetas, deck boxes, playmats y toploaders para proteger tu colección.",
    preset: { type: "accesorio" },
    filters: ["price", "stock"],
  },
  {
    path: "/buscar",
    title: "Búsqueda",
    noun: ["resultado", "resultados"],
    intro: "",
    preset: {},
    filters: ALL_FILTERS,
  },
];
