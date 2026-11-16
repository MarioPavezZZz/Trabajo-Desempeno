/**
 * Tarjeta de producto para grillas.
 *
 * - Cartas: el arte ocupa la tarjeta; las foil llevan un marco iridiscente.
 * - Sellados y accesorios: su imagen es un logo, se muestra sobre una placa
 *   de marfil junto con el tipo de producto, para que un sobre y un display
 *   del mismo set se distingan a simple vista.
 *
 * Las imágenes declaran ancho y alto (proporción de carta 5:7) para que la
 * grilla no salte mientras cargan (CLS = 0).
 */
import { Link } from "react-router-dom";
import { ACCESSORY_TYPE, GAME_NAMES, SEALED_TYPE } from "../lib/format";
import type { ProductSummary } from "../lib/types";
import { ConditionChip, LanguageTag, Price, RarityPips } from "./Indicators";

interface Props {
  product: ProductSummary;
  /** Las primeras tarjetas visibles se cargan sin diferir (ayuda al LCP). */
  eager?: boolean;
  /** Se llama al abrir el producto (evento select_item de GA4). */
  onSelect?: () => void;
}

function Artwork({ product, eager }: Props) {
  const imgProps = {
    src: product.thumb,
    alt: "",
    width: 244,
    height: 340,
    loading: eager ? ("eager" as const) : ("lazy" as const),
    decoding: "async" as const,
  };

  if (product.product_type === "carta") {
    const art = <img {...imgProps} className="aspect-[5/7] h-auto w-full rounded-[5px] object-cover" />;
    return product.is_foil ? (
      <div className="foil-frame rounded-[7px] p-[2px]">{art}</div>
    ) : (
      <div className="rounded-[7px] border-2 border-transparent">{art}</div>
    );
  }

  const kind =
    product.product_type === "sellado"
      ? SEALED_TYPE[product.sealed_type ?? ""]
      : ACCESSORY_TYPE[product.accessory_type ?? ""];
  return (
    <div className="flex aspect-[5/7] flex-col rounded-[7px] bg-ivory p-3">
      <div className="flex flex-1 items-center justify-center">
        <img {...imgProps} className="max-h-[70%] w-auto max-w-full object-contain" />
      </div>
      <p className="font-display text-xl leading-tight text-felt">{kind}</p>
    </div>
  );
}

export default function ProductCard({ product, eager = false, onSelect }: Props) {
  const soldOut = product.stock === 0;
  return (
    <article className="group relative flex flex-col">
      <div className={`relative ${soldOut ? "opacity-50" : ""}`}>
        <Artwork product={product} eager={eager} />
        {product.discount_pct ? (
          <span className="price absolute right-2 top-2 rounded-sm bg-wax px-1.5 text-xs font-semibold leading-5 text-ivory">
            −{product.discount_pct} %
          </span>
        ) : null}
      </div>

      <div className="mt-3 flex flex-1 flex-col gap-1">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug">
          {/* El enlace cubre toda la tarjeta (pseudo-elemento) sin anidar elementos interactivos. */}
          <Link
            to={`/producto/${product.slug}`}
            onClick={onSelect}
            className="after:absolute after:inset-0 group-hover:text-brass-bright"
          >
            {product.name}
          </Link>
        </h3>
        <p className="line-clamp-1 text-xs text-ivory-dim">
          {product.set_name ?? (product.game ? GAME_NAMES[product.game] : "Accesorio")}
        </p>

        {product.product_type === "carta" && (
          <div className="mt-1 flex items-center gap-2">
            {product.condition && <ConditionChip condition={product.condition} />}
            {product.language && <LanguageTag language={product.language} />}
            {product.is_foil && <span className="text-xs font-semibold text-brass-bright">Foil</span>}
            {product.rarity_tier && (
              <span className="ml-auto">
                <RarityPips tier={product.rarity_tier} />
              </span>
            )}
          </div>
        )}

        <div className="mt-auto pt-2">
          <Price price={product.price_clp} before={product.compare_at_price_clp} />
          <p className={`text-xs ${soldOut ? "text-cond-hp" : "text-ivory-dim"}`}>
            {soldOut
              ? "Agotado"
              : product.stock === 1
                ? "Última unidad"
                : product.stock === 2
                  ? "Últimas 2 unidades"
                  : "Disponible"}
          </p>
        </div>
      </div>
    </article>
  );
}

/** Espacio reservado con la misma forma de la tarjeta mientras cargan los datos. */
export function ProductCardSkeleton() {
  return (
    <div aria-hidden="true">
      <div className="skeleton aspect-[5/7] rounded-[7px]" />
      <div className="skeleton mt-3 h-4 w-4/5 rounded-sm" />
      <div className="skeleton mt-2 h-3 w-3/5 rounded-sm" />
      <div className="skeleton mt-4 h-5 w-2/5 rounded-sm" />
    </div>
  );
}
