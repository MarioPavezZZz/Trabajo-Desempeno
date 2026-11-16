/**
 * Filtros del listado guardados en la URL.
 *
 * La URL es la única fuente de verdad: un listado se puede compartir, volver
 * atrás funciona, y los scripts de carga pueden repetir exactamente la misma
 * consulta que hace un usuario.
 *
 * Cada sección (Cartas, Sellados, Ofertas, Accesorios) tiene un "preset" que se
 * suma a lo que elige el usuario sin aparecer en su URL.
 */
import type { SortOption } from "./types";

/** Parámetros de lista (se repiten en la URL: ?game=a&game=b). */
export const MULTI_KEYS = ["game", "set", "rarity", "condition", "lang"] as const;
export type MultiKey = (typeof MULTI_KEYS)[number];

export interface ListingState {
  multi: Record<MultiKey, string[]>;
  foil: "true" | "false" | null;
  minPrice: number | null;
  maxPrice: number | null;
  inStock: boolean;
  q: string | null;
  sort: SortOption | null;
  page: number;
}

export interface SectionPreset {
  type?: "carta" | "sellado" | "accesorio";
  onSale?: boolean;
}

const SORTS: SortOption[] = ["relevance", "newest", "price_asc", "price_desc", "name"];

function toInt(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** URL del navegador -> estado del listado (ignora valores inválidos). */
export function parseListing(search: URLSearchParams): ListingState {
  const multi = Object.fromEntries(
    MULTI_KEYS.map((k) => [k, [...new Set(search.getAll(k).filter(Boolean))]]),
  ) as Record<MultiKey, string[]>;
  const foil = search.get("foil");
  const sort = search.get("sort") as SortOption | null;
  return {
    multi,
    foil: foil === "true" || foil === "false" ? foil : null,
    minPrice: toInt(search.get("min_price")),
    maxPrice: toInt(search.get("max_price")),
    inStock: search.get("in_stock") === "true",
    q: search.get("q")?.trim() || null,
    sort: sort && SORTS.includes(sort) ? sort : null,
    page: Math.max(1, toInt(search.get("page")) ?? 1),
  };
}

/** Estado -> parámetros de URL (solo los que tienen valor, en orden estable). */
export function serializeListing(state: ListingState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  for (const key of MULTI_KEYS) {
    for (const value of [...state.multi[key]].sort()) params.append(key, value);
  }
  if (state.foil) params.set("foil", state.foil);
  if (state.minPrice !== null) params.set("min_price", String(state.minPrice));
  if (state.maxPrice !== null) params.set("max_price", String(state.maxPrice));
  if (state.inStock) params.set("in_stock", "true");
  if (state.sort) params.set("sort", state.sort);
  if (state.page > 1) params.set("page", String(state.page));
  return params;
}

/** Parámetros para la API: lo del usuario + el preset de la sección + tamaño de página. */
export function toApiParams(
  state: ListingState,
  preset: SectionPreset,
  pageSize: number,
): URLSearchParams {
  const params = serializeListing(state);
  if (preset.type) params.set("type", preset.type);
  if (preset.onSale) params.set("on_sale", "true");
  params.set("page_size", String(pageSize));
  return params;
}

/** Parámetros para las facetas: igual que el listado, sin orden ni paginación. */
export function toFacetParams(state: ListingState, preset: SectionPreset): URLSearchParams {
  const params = toApiParams(state, preset, 1);
  for (const key of ["sort", "page", "page_size"]) params.delete(key);
  return params;
}

/** Agrega o quita un valor de un filtro múltiple; cualquier cambio vuelve a la página 1. */
export function toggleValue(state: ListingState, key: MultiKey, value: string): ListingState {
  const current = state.multi[key];
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
  return { ...state, multi: { ...state.multi, [key]: next }, page: 1 };
}

/** Cantidad de filtros activos (para el botón "Filtros" en celular). */
export function activeFilterCount(state: ListingState): number {
  return (
    MULTI_KEYS.reduce((n, k) => n + state.multi[k].length, 0) +
    (state.foil ? 1 : 0) +
    (state.minPrice !== null ? 1 : 0) +
    (state.maxPrice !== null ? 1 : 0) +
    (state.inStock ? 1 : 0)
  );
}

/** Estado sin filtros (conserva la búsqueda y el orden). */
export function clearFilters(state: ListingState): ListingState {
  return {
    ...parseListing(new URLSearchParams()),
    q: state.q,
    sort: state.sort,
  };
}
