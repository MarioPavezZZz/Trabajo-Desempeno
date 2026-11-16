/**
 * Listado del catálogo (Cartas, Sellados, Ofertas, Accesorios y Búsqueda).
 *
 * El estado de filtros, orden y página vive en la URL. Se hacen dos
 * peticiones en paralelo: la página de productos y las facetas (conteos).
 * Mientras llega una página nueva se mantiene la anterior en pantalla
 * (placeholderData), así la grilla no se vacía ni salta.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { trackSearch, usePageView } from "../analytics";
import FilterPanel from "../components/FilterPanel";
import Pagination from "../components/Pagination";
import ProductGrid from "../components/ProductGrid";
import { api } from "../lib/api";
import {
  activeFilterCount,
  clearFilters,
  type ListingState,
  parseListing,
  serializeListing,
  toApiParams,
  toFacetParams,
} from "../lib/filters";
import type { SortOption } from "../lib/types";
import type { Section } from "./sections";

const PAGE_SIZE = 24;

const SORT_OPTIONS: { value: SortOption; label: string; needsQuery?: boolean }[] = [
  { value: "relevance", label: "Más relevantes", needsQuery: true },
  { value: "newest", label: "Más recientes" },
  { value: "price_asc", label: "Precio: menor a mayor" },
  { value: "price_desc", label: "Precio: mayor a menor" },
  { value: "name", label: "Nombre (A-Z)" },
];

export default function ListingPage({ section }: { section: Section }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const state = useMemo(() => parseListing(searchParams), [searchParams]);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const productsQuery = useQuery({
    queryKey: ["products", section.path, toApiParams(state, section.preset, PAGE_SIZE).toString()],
    queryFn: () => api.products(toApiParams(state, section.preset, PAGE_SIZE)),
    placeholderData: keepPreviousData,
  });
  const facetsQuery = useQuery({
    queryKey: ["facets", section.path, toFacetParams(state, section.preset).toString()],
    queryFn: () => api.facets(toFacetParams(state, section.preset)),
    placeholderData: keepPreviousData,
  });
  const setsQuery = useQuery({
    queryKey: ["sets"],
    queryFn: api.sets,
    staleTime: 5 * 60_000,
    enabled: section.filters.includes("set"),
  });

  const title = section.path === "/buscar" && state.q ? `Resultados para «${state.q}»` : section.title;
  usePageView(`${title} | TCGMASTER`);

  // Búsqueda por texto: se informa una vez por término, cuando llega el resultado.
  const searchTotal = state.q && !productsQuery.isPlaceholderData ? productsQuery.data?.total : undefined;
  useEffect(() => {
    if (state.q && searchTotal !== undefined) trackSearch(state.q, searchTotal);
  }, [state.q, searchTotal]);

  function update(next: ListingState, scroll = false) {
    setSearchParams(serializeListing(next));
    if (scroll) window.scrollTo({ top: 0 });
  }

  const data = productsQuery.data;
  const total = data?.total ?? 0;
  const [singular, plural] = section.noun;
  const sortValue = state.sort ?? (state.q ? "relevance" : "newest");
  const filterCount = activeFilterCount(state);

  return (
    <div className="mx-auto max-w-shop px-4 pt-10 sm:px-6">
      <header className="border-b border-felt-line pb-5">
        <h1 className="font-display text-3xl sm:text-4xl">{title}</h1>
        {section.intro && <p className="mt-2 max-w-prose text-ivory-dim">{section.intro}</p>}
      </header>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <p className="price text-sm text-ivory-dim" aria-live="polite">
          {data ? `${total.toLocaleString("es-CL")} ${total === 1 ? singular : plural}` : "Cargando…"}
        </p>
        <div className="flex w-full items-center gap-3 sm:w-auto">
          <button
            type="button"
            onClick={() => setFiltersOpen(true)}
            className="shrink-0 whitespace-nowrap rounded-sm border border-felt-line px-3 py-1.5 text-sm font-semibold lg:hidden"
          >
            Filtros{filterCount > 0 ? ` (${filterCount})` : ""}
          </button>
          <label htmlFor="orden" className="sr-only whitespace-nowrap text-sm text-ivory-dim sm:not-sr-only">
            Ordenar por
          </label>
          <select
            id="orden"
            value={sortValue}
            onChange={(e) => update({ ...state, sort: e.target.value as SortOption, page: 1 })}
            className="min-w-0 flex-1 rounded-sm border border-felt-line bg-felt px-2 py-1.5 text-sm text-ivory focus:border-brass sm:flex-none"
          >
            {SORT_OPTIONS.filter((o) => !o.needsQuery || state.q).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-6 grid gap-10 lg:grid-cols-[15rem_1fr]">
        {/* En escritorio el panel es una columna fija; en celular, un panel lateral. */}
        <aside
          aria-label="Filtros"
          className={`${
            filtersOpen ? "fixed inset-0 z-40 overflow-y-auto bg-felt p-5" : "hidden"
          } lg:static lg:block lg:p-0`}
        >
          {filtersOpen && (
            <button
              type="button"
              onClick={() => setFiltersOpen(false)}
              className="mb-4 w-full rounded-sm bg-brass py-2 text-sm font-semibold text-felt lg:hidden"
            >
              Ver {total.toLocaleString("es-CL")} {total === 1 ? singular : plural}
            </button>
          )}
          <FilterPanel
            state={state}
            facets={facetsQuery.data}
            sets={setsQuery.data}
            groups={section.filters}
            onChange={(next) => update(next)}
          />
        </aside>

        <section aria-label="Productos" className={productsQuery.isPlaceholderData ? "opacity-60" : ""}>
          {productsQuery.isError ? (
            <p className="py-16 text-ivory-dim">No pudimos cargar los productos. Recarga la página.</p>
          ) : data && data.items.length === 0 ? (
            <div className="py-16">
              <p className="font-display text-2xl">No hay {plural} con estos filtros</p>
              <p className="mt-2 text-ivory-dim">Quita algún filtro o prueba con otra búsqueda.</p>
              {filterCount > 0 && (
                <button
                  type="button"
                  onClick={() => update(clearFilters(state))}
                  className="mt-5 rounded-sm border border-brass px-4 py-2 text-sm font-semibold text-brass hover:bg-brass hover:text-felt"
                >
                  Quitar filtros
                </button>
              )}
            </div>
          ) : (
            <ProductGrid
              products={data?.items}
              list={{ id: section.path.slice(1) || "listado", name: title }}
              placeholders={12}
              eagerCount={4}
              className="grid-cols-2 sm:grid-cols-3 xl:grid-cols-4"
            />
          )}
          {data && (
            <Pagination
              page={state.page}
              totalPages={data.total_pages}
              onPage={(page) => update({ ...state, page }, true)}
            />
          )}
        </section>
      </div>
    </div>
  );
}
