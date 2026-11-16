/**
 * Home: de arriba hacia abajo, lanzamientos (hero), selector de juegos,
 * cartas recién ingresadas con filtro por juego, sellados destacados,
 * ofertas y cartas con mayor variación de precio.
 *
 * Todo llega en una sola petición (/api/home); solo el filtro de novedades
 * hace peticiones adicionales y pequeñas.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { usePageView } from "../analytics";
import { RarityPips } from "../components/Indicators";
import ProductGrid from "../components/ProductGrid";
import SectionHeading from "../components/SectionHeading";
import { api } from "../lib/api";
import { formatChange, formatCLP, formatDate, GAME_NAMES, SEALED_TYPE } from "../lib/format";
import type { HomeData } from "../lib/types";

// ----------------------------------------------------------------- Hero
type Release = HomeData["hero"][number];

/** Placa de marfil con el logo del set (los íconos de Magic son negros: necesitan fondo claro). */
function SetPlate({ release, large }: { release: Release; large: boolean }) {
  return (
    <div className={`flex items-center justify-center rounded-sm bg-ivory ${large ? "h-44 sm:h-56" : "h-24"} p-4`}>
      {release.set.logo && (
        <img
          src={release.set.logo}
          alt={`Logo de ${release.set.name}`}
          width={480}
          height={200}
          // El logo del lanzamiento principal suele ser el elemento LCP: se pide primero.
          // (React 18 no conoce `fetchPriority`; se pasa el atributo HTML en minúsculas.)
          {...((large ? { fetchpriority: "high" } : {}) as Record<string, string>)}
          loading="eager"
          className="max-h-full w-auto max-w-full object-contain"
        />
      )}
    </div>
  );
}

/** Nombre corto del sellado en la tarjeta de precios: "Display de 36 sobres". */
function sealedLabel(name: string, sealedType: string | null): string {
  const label = SEALED_TYPE[sealedType ?? ""] ?? name;
  const packs = name.match(/\((\d+) sobres\)/)?.[1];
  return packs ? `${label} de ${packs} sobres` : label;
}

/** Tarjeta de precios de la vitrina: cada producto sellado con puntos guía hasta su precio. */
function PriceCard({ release }: { release: Release }) {
  return (
    <ul className="mt-4 space-y-2">
      {release.products.map((p) => (
        <li key={p.id}>
          <Link to={`/producto/${p.slug}`} className="price-leader group text-sm">
            <span className="text-ivory group-hover:text-brass-bright">{sealedLabel(p.name, p.sealed_type)}</span>
            <span className="price font-semibold text-brass">{formatCLP(p.price_clp)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ReleaseBlock({ release, large }: { release: Release; large: boolean }) {
  return (
    <article className={`flex flex-col border border-felt-line bg-felt-raised p-5 ${large ? "sm:p-7" : ""}`}>
      <SetPlate release={release} large={large} />
      <p className="mt-5 text-sm text-ivory-dim">
        {GAME_NAMES[release.set.game]}, lanzado el {formatDate(release.set.release_date)}
      </p>
      <h3 className={`font-display leading-tight ${large ? "text-3xl sm:text-4xl" : "text-2xl"}`}>
        {release.set.name}
      </h3>
      <PriceCard release={release} />
      <Link
        to={`/cartas?set=${release.set.id}`}
        className="mt-5 self-start text-sm font-semibold text-brass hover:text-brass-bright"
      >
        Ver cartas sueltas de {release.set.name}
      </Link>
    </article>
  );
}

function Hero({ data }: { data: HomeData | undefined }) {
  const [main, ...rest] = data?.hero ?? [];
  return (
    <section aria-labelledby="lanzamientos" className="mx-auto max-w-shop px-4 pt-10 sm:px-6">
      <h1 id="lanzamientos" className="font-display text-3xl sm:text-4xl">
        Lanzamientos en vitrina
      </h1>
      <p className="mt-2 max-w-prose text-ivory-dim">
        La expansión más reciente de cada juego, sellada y con su precio a la vista.
      </p>
      <div className="mt-8 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        {main ? <ReleaseBlock release={main} large /> : <div className="skeleton h-[30rem]" />}
        <div className="grid gap-5">
          {rest.length
            ? rest.map((r) => <ReleaseBlock key={r.set.id} release={r} large={false} />)
            : [0, 1].map((i) => <div key={i} className="skeleton h-[14.5rem]" />)}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------- Selector de juegos
function GameSelector({ data }: { data: HomeData | undefined }) {
  return (
    <section aria-labelledby="juegos" className="mx-auto mt-16 max-w-shop px-4 sm:px-6">
      <SectionHeading id="juegos" title="Elige un juego" />
      <ul className="grid gap-px overflow-hidden border border-felt-line bg-felt-line sm:grid-cols-3">
        {(data?.games ?? []).map((g) => (
          <li key={g.slug}>
            <Link
              to={`/cartas?game=${g.slug}`}
              className="flex h-full items-center gap-4 bg-felt p-5 hover:bg-felt-raised"
            >
              <span className="flex h-16 w-24 shrink-0 items-center justify-center rounded-sm bg-ivory p-2">
                {g.logo && (
                  <img src={g.logo} alt="" width={96} height={64} loading="lazy" className="max-h-full w-auto object-contain" />
                )}
              </span>
              <span>
                <span className="block font-display text-2xl leading-tight">{g.name}</span>
                <span className="price text-sm text-ivory-dim">{g.product_count} productos</span>
              </span>
            </Link>
          </li>
        ))}
        {!data && [0, 1, 2].map((i) => <li key={i} className="skeleton h-[6.5rem]" />)}
      </ul>
    </section>
  );
}

// ------------------------------------------------------------- Novedades
const GAME_TABS = [
  { value: "", label: "Todos" },
  { value: "pokemon", label: "Pokémon" },
  { value: "magic", label: "Magic" },
  { value: "yugioh", label: "Yu-Gi-Oh!" },
];

function NewArrivals({ data }: { data: HomeData | undefined }) {
  const [game, setGame] = useState("");
  const filtered = useQuery({
    queryKey: ["new-arrivals", game],
    queryFn: () => api.newArrivals(game),
    enabled: game !== "",
  });
  const products = game === "" ? data?.new_arrivals : filtered.data;

  return (
    <section aria-labelledby="novedades" className="mx-auto mt-16 max-w-shop px-4 sm:px-6">
      <SectionHeading
        id="novedades"
        title="Recién ingresadas"
        description="Las últimas cartas sueltas que llegaron a la tienda."
        link={{ to: game ? `/cartas?game=${game}` : "/cartas", label: "Ver todas las cartas" }}
      >
        <div role="group" aria-label="Filtrar por juego" className="flex rounded-sm border border-felt-line">
          {GAME_TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              aria-pressed={game === tab.value}
              onClick={() => setGame(tab.value)}
              className={`px-3 py-1.5 text-sm font-semibold ${
                game === tab.value ? "bg-brass text-felt" : "text-ivory-dim hover:text-ivory"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </SectionHeading>
      <ProductGrid
        products={products}
        list={{ id: `home_novedades${game ? `_${game}` : ""}`, name: "Home: recién ingresadas" }}
        placeholders={12}
      />
    </section>
  );
}

// ------------------------------------------------- Variación de precios
function PriceMovers({ data }: { data: HomeData | undefined }) {
  if (data && data.price_movers.length === 0) return null;
  return (
    <section aria-labelledby="variacion" className="mx-auto mt-16 max-w-shop px-4 sm:px-6">
      <SectionHeading
        id="variacion"
        title="Mayor variación de precio"
        description="Cartas cuyo precio más cambió en los últimos 30 días."
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[36rem] text-sm">
          <thead className="text-left text-ivory-dim">
            <tr>
              <th scope="col" className="pb-2 font-semibold">Carta</th>
              <th scope="col" className="pb-2 font-semibold">Rareza</th>
              <th scope="col" className="pb-2 text-right font-semibold">Hace 30 días</th>
              <th scope="col" className="pb-2 text-right font-semibold">Hoy</th>
              <th scope="col" className="pb-2 text-right font-semibold">Variación</th>
            </tr>
          </thead>
          <tbody className="price">
            {(data?.price_movers ?? []).map(({ product, old_price_clp, change_pct }) => (
              <tr key={product.id} className="border-t border-felt-line">
                <td className="py-2 pr-4">
                  <Link to={`/producto/${product.slug}`} className="flex items-center gap-3 hover:text-brass-bright">
                    <img src={product.thumb} alt="" width={30} height={42} loading="lazy" className="rounded-[2px]" />
                    <span>
                      <span className="block font-semibold">{product.name}</span>
                      <span className="block text-xs text-ivory-dim">{product.set_name}</span>
                    </span>
                  </Link>
                </td>
                <td className="py-2 pr-4">{product.rarity_tier && <RarityPips tier={product.rarity_tier} />}</td>
                <td className="py-2 text-right text-ivory-dim">{formatCLP(old_price_clp)}</td>
                <td className="py-2 text-right font-semibold text-brass">{formatCLP(product.price_clp)}</td>
                <td className={`py-2 text-right font-semibold ${change_pct >= 0 ? "text-trend-up" : "text-trend-down"}`}>
                  <span aria-hidden="true">{change_pct >= 0 ? "▲ " : "▼ "}</span>
                  {formatChange(change_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ----------------------------------------------------------------- Página
export default function HomePage() {
  const { data, isError } = useQuery({ queryKey: ["home"], queryFn: api.home });

  usePageView("TCGMASTER: cartas coleccionables, sobres y accesorios");

  if (isError) {
    return (
      <div className="mx-auto max-w-shop px-4 py-24 sm:px-6">
        <h1 className="font-display text-3xl">No pudimos cargar la tienda</h1>
        <p className="mt-3 text-ivory-dim">La API no respondió. Recarga la página en unos segundos.</p>
      </div>
    );
  }

  return (
    <>
      <Hero data={data} />
      <GameSelector data={data} />
      <NewArrivals data={data} />

      <section aria-labelledby="sellados" className="mx-auto mt-16 max-w-shop px-4 sm:px-6">
        <SectionHeading
          id="sellados"
          title="Sellados destacados"
          link={{ to: "/sellados", label: "Ver todos los sellados" }}
        />
        <ProductGrid
          products={data?.featured_sealed}
          list={{ id: "home_sellados", name: "Home: sellados destacados" }}
          placeholders={6}
        />
      </section>

      <section aria-labelledby="ofertas" className="mx-auto mt-16 max-w-shop px-4 sm:px-6">
        <SectionHeading
          id="ofertas"
          title="Ofertas activas"
          description="Ordenadas por porcentaje de descuento."
          link={{ to: "/ofertas", label: "Ver todas las ofertas" }}
        />
        <ProductGrid
          products={data?.offers}
          list={{ id: "home_ofertas", name: "Home: ofertas activas" }}
          placeholders={6}
        />
      </section>

      <PriceMovers data={data} />
    </>
  );
}
