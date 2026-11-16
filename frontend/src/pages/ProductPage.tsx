/**
 * Detalle de producto: imagen grande, datos, precio, stock, selector de
 * cantidad, botón para agregar al carrito y productos relacionados.
 *
 * La imagen principal es el elemento LCP de esta página: se pide con
 * prioridad alta y declara su tamaño para no mover el contenido (CLS).
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { trackAddToCart, trackViewItem, usePageView } from "../analytics";
import { ConditionChip, Price, RarityPips } from "../components/Indicators";
import ProductGrid from "../components/ProductGrid";
import SectionHeading from "../components/SectionHeading";
import { api, ApiError, errorMessage } from "../lib/api";
import { addableQuantities } from "../lib/cart";
import { ACCESSORY_TYPE, CONDITION, GAME_NAMES, LANGUAGE, RARITY, SEALED_TYPE, formatDate } from "../lib/format";
import { useCart, useCartActions } from "../lib/session";
import type { ProductDetail } from "../lib/types";

/** Filas de la ficha técnica según el tipo de producto. */
function specs(p: ProductDetail): [string, React.ReactNode][] {
  const rows: [string, React.ReactNode][] = [];
  if (p.game_name) rows.push(["Juego", p.game_name]);
  if (p.set) rows.push(["Expansión", `${p.set.name} (${formatDate(p.set.release_date)})`]);
  if (p.product_type === "carta") {
    if (p.card_number) rows.push(["Número", p.card_number]);
    if (p.card_type) rows.push(["Tipo", p.card_type]);
    if (p.rarity_tier)
      rows.push([
        "Rareza",
        <span className="flex items-center gap-2" key="r">
          <RarityPips tier={p.rarity_tier} />
          {RARITY[p.rarity_tier].label}
          {p.rarity && <span className="text-ivory-dim">({p.rarity})</span>}
        </span>,
      ]);
    if (p.condition)
      rows.push([
        "Estado",
        <span className="flex items-center gap-2" key="c">
          <ConditionChip condition={p.condition} />
          {CONDITION[p.condition].label}
        </span>,
      ]);
    if (p.language) rows.push(["Idioma", LANGUAGE[p.language]]);
    rows.push(["Acabado", p.is_foil ? "Foil" : "Normal"]);
  }
  if (p.sealed_type) rows.push(["Producto", SEALED_TYPE[p.sealed_type]]);
  if (p.accessory_type) rows.push(["Producto", ACCESSORY_TYPE[p.accessory_type]]);
  if (p.units_per_item && p.product_type !== "carta") rows.push(["Contenido", `${p.units_per_item} unidades`]);
  if (p.language && p.product_type === "sellado") rows.push(["Idioma", LANGUAGE[p.language]]);
  return rows;
}

function AddToCart({ product }: { product: ProductDetail }) {
  const cart = useCart().data;
  const { add } = useCartActions();
  const inCart = cart?.items.find((i) => i.product.id === product.id)?.quantity ?? 0;
  const options = addableQuantities(product.stock, inCart);
  const [quantity, setQuantity] = useState(1);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    if (quantity > (options[options.length - 1] ?? 1)) setQuantity(1);
  }, [options, quantity]);
  useEffect(() => {
    if (!added) return;
    const t = window.setTimeout(() => setAdded(false), 2500);
    return () => window.clearTimeout(t);
  }, [added]);

  if (product.stock === 0) {
    return <p className="mt-6 font-semibold text-cond-hp">Agotado por ahora.</p>;
  }

  return (
    <div className="mt-6">
      {options.length > 0 ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(
              { productId: product.id, quantity },
              {
                onSuccess: () => {
                  setAdded(true);
                  trackAddToCart(product, quantity);
                },
              },
            );
          }}
        >
          <div>
            <label htmlFor="cantidad" className="block text-sm text-ivory-dim">
              Cantidad
            </label>
            <select
              id="cantidad"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              className="price mt-1 rounded-sm border border-felt-line bg-felt px-3 py-2 text-ivory focus:border-brass"
            >
              {options.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={add.isPending}
            className={`min-w-48 rounded-sm px-5 py-2.5 font-semibold transition-colors ${
              added ? "bg-cond-nm text-felt" : "bg-brass text-felt hover:bg-brass-bright"
            } disabled:opacity-60`}
          >
            {add.isPending ? "Agregando…" : added ? "Agregado al carrito" : "Agregar al carrito"}
          </button>
        </form>
      ) : (
        <p className="text-ivory-dim">Ya tienes en el carrito todas las unidades disponibles.</p>
      )}
      <p className="mt-3 text-sm text-ivory-dim" aria-live="polite">
        {add.isError ? (
          <span className="text-cond-hp">{errorMessage(add.error)}</span>
        ) : inCart > 0 ? (
          <>
            Tienes {inCart} en el{" "}
            <Link to="/carrito" className="font-semibold text-brass hover:text-brass-bright">
              carrito
            </Link>
            .
          </>
        ) : (
          `${product.stock} ${product.stock === 1 ? "unidad disponible" : "unidades disponibles"}`
        )}
      </p>
    </div>
  );
}

export default function ProductPage() {
  const { slug = "" } = useParams();
  const { data: product, error, isLoading } = useQuery({
    queryKey: ["product", slug],
    queryFn: () => api.product(slug),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });
  const related = useQuery({ queryKey: ["related", slug], queryFn: () => api.related(slug), enabled: !!product });

  usePageView(product ? `${product.name} | TCGMASTER` : null);
  // view_item una vez por producto (no en cada nueva consulta del mismo).
  useEffect(() => {
    if (product) trackViewItem(product);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product?.id]);

  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto max-w-shop px-4 py-24 sm:px-6">
        <h1 className="font-display text-3xl">{notFound ? "Este producto no existe" : "No pudimos cargar el producto"}</h1>
        <p className="mt-3 text-ivory-dim">
          {notFound ? "Puede que ya no esté a la venta." : "Recarga la página en unos segundos."}
        </p>
        <Link to="/cartas" className="mt-6 inline-block font-semibold text-brass hover:text-brass-bright">
          Volver al catálogo
        </Link>
      </div>
    );
  }

  const isCard = product?.product_type === "carta";
  return (
    <div className="mx-auto max-w-shop px-4 pt-8 sm:px-6">
      <nav aria-label="Ruta" className="text-sm text-ivory-dim">
        <Link to="/" className="hover:text-ivory">Inicio</Link>
        <span aria-hidden="true"> / </span>
        {product && (
          <Link
            to={product.product_type === "carta" ? "/cartas" : product.product_type === "sellado" ? "/sellados" : "/accesorios"}
            className="hover:text-ivory"
          >
            {product.product_type === "carta" ? "Cartas" : product.product_type === "sellado" ? "Sellados" : "Accesorios"}
          </Link>
        )}
      </nav>

      <div className="mt-6 grid gap-10 md:grid-cols-[minmax(0,26rem)_1fr]">
        {/* Imagen: proporción fija reservada desde el primer render (CLS = 0). */}
        <div className="mx-auto w-full max-w-[14rem] sm:max-w-[22rem] md:max-w-none">
          {isLoading || !product ? (
            <div className="skeleton aspect-[5/7] w-full rounded-[10px]" />
          ) : isCard ? (
            <div className={`${product.is_foil ? "foil-frame p-[3px]" : ""} rounded-[12px]`}>
              <img
                src={product.image}
                srcSet={`${product.thumb} 244w, ${product.image} 488w`}
                sizes="(min-width: 768px) 416px, (min-width: 640px) 352px, 224px"
                alt={`Carta ${product.name}`}
                width={488}
                height={680}
                {...({ fetchpriority: "high" } as Record<string, string>)}
                className="aspect-[5/7] h-auto w-full rounded-[10px] object-cover"
              />
            </div>
          ) : (
            <div className="flex aspect-[5/7] items-center justify-center rounded-[10px] bg-ivory p-8">
              <img
                src={product.image}
                alt={product.name}
                width={480}
                height={480}
                {...({ fetchpriority: "high" } as Record<string, string>)}
                className="max-h-[80%] w-auto max-w-full object-contain"
              />
            </div>
          )}
        </div>

        <div>
          {product ? (
            <>
              <p className="text-sm text-ivory-dim">{product.set_name ?? (product.game ? GAME_NAMES[product.game] : "Accesorio")}</p>
              <h1 className="mt-1 font-display text-3xl leading-tight sm:text-4xl">{product.name}</h1>
              <div className="mt-5">
                <Price price={product.price_clp} before={product.compare_at_price_clp} />
                {product.discount_pct ? (
                  <p className="price mt-1 text-sm text-ivory-dim">Ahorras {product.discount_pct} % sobre el precio anterior.</p>
                ) : null}
              </div>
              <AddToCart product={product} />

              <dl className="mt-10 grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2.5 border-t border-felt-line pt-6 text-sm">
                {specs(product).map(([label, value]) => (
                  <div key={label} className="contents">
                    <dt className="text-ivory-dim">{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>

              {product.description && (
                <div className="mt-8 border-t border-felt-line pt-6">
                  <h2 className="font-display text-xl">{isCard ? "Texto de la carta" : "Descripción"}</h2>
                  <p className="mt-2 max-w-prose whitespace-pre-line text-sm leading-relaxed text-ivory-dim">
                    {product.description}
                  </p>
                </div>
              )}
            </>
          ) : (
            <div aria-hidden="true" className="space-y-4">
              <div className="skeleton h-4 w-40" />
              <div className="skeleton h-10 w-3/4" />
              <div className="skeleton h-7 w-32" />
              <div className="skeleton h-11 w-72" />
            </div>
          )}
        </div>
      </div>

      <section aria-labelledby="relacionados" className="mt-16">
        <SectionHeading id="relacionados" title="También te puede interesar" />
        {related.data && related.data.length === 0 ? (
          <p className="text-ivory-dim">No hay productos relacionados con stock en este momento.</p>
        ) : (
          <ProductGrid
            products={related.data}
            list={{ id: "relacionados", name: "Productos relacionados" }}
            placeholders={6}
          />
        )}
      </section>
    </div>
  );
}
