/**
 * Grilla de productos con estado de carga que reserva el mismo espacio.
 *
 * Si recibe `list`, informa a GA4 `view_item_list` cada vez que llega un
 * conjunto nuevo de productos y `select_item` al abrir uno.
 */
import { useEffect } from "react";
import { type ListContext, trackSelectItem, trackViewItemList } from "../analytics";
import type { ProductSummary } from "../lib/types";
import ProductCard, { ProductCardSkeleton } from "./ProductCard";

interface Props {
  products: ProductSummary[] | undefined;
  /** Lista para GA4 (p. ej. { id: "cartas", name: "Cartas" }). */
  list?: ListContext;
  /** Cantidad de tarjetas fantasma mientras carga. */
  placeholders?: number;
  /** Cantidad de tarjetas iniciales sin carga diferida. */
  eagerCount?: number;
  className?: string;
}

export default function ProductGrid({
  products,
  list,
  placeholders = 8,
  eagerCount = 0,
  className = "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6",
}: Props) {
  // Se compara por identidad del arreglo: una página nueva = un evento.
  useEffect(() => {
    if (list && products) trackViewItemList(list, products);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [products, list?.id]);

  return (
    <div className={`grid gap-x-5 gap-y-8 ${className}`}>
      {products
        ? products.map((p, i) => (
            <ProductCard
              key={p.id}
              product={p}
              eager={i < eagerCount}
              onSelect={list ? () => trackSelectItem(list, p, i) : undefined}
            />
          ))
        : Array.from({ length: placeholders }, (_, i) => <ProductCardSkeleton key={i} />)}
    </div>
  );
}
