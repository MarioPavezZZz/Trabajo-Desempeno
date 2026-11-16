/**
 * Conversión de productos de la tienda al formato de ítem de e-commerce de GA4.
 * https://developers.google.com/analytics/devguides/collection/ga4/ecommerce
 */
import type { Cart, Order, ProductSummary } from "../lib/types";

export const CURRENCY = "CLP";

const GAME_BRAND: Record<string, string> = {
  pokemon: "Pokémon TCG",
  magic: "Magic: The Gathering",
  yugioh: "Yu-Gi-Oh!",
};
const TYPE_CATEGORY: Record<string, string> = {
  carta: "Cartas",
  sellado: "Sellados",
  accesorio: "Accesorios",
};

export interface GaItem {
  item_id: string;
  item_name: string;
  item_brand?: string;
  item_category?: string;
  item_category2?: string;
  item_variant?: string;
  item_list_id?: string;
  item_list_name?: string;
  index?: number;
  price: number;
  discount?: number;
  quantity: number;
}

export interface ListContext {
  id: string;
  name: string;
}

/** Variante visible de una carta: "NM / ES / Foil". */
function variant(p: ProductSummary): string | undefined {
  const parts = [p.condition, p.language, p.is_foil ? "Foil" : null, p.sealed_type, p.accessory_type].filter(Boolean);
  return parts.length ? parts.join(" / ") : undefined;
}

/** Producto -> ítem GA4 (sin campos vacíos). */
export function toGaItem(p: ProductSummary, quantity = 1, list?: ListContext, index?: number): GaItem {
  const item: GaItem = {
    item_id: String(p.id),
    item_name: p.name,
    item_brand: p.game ? GAME_BRAND[p.game] : "Accesorios",
    item_category: TYPE_CATEGORY[p.product_type],
    item_category2: p.set_name ?? undefined,
    item_variant: variant(p),
    price: p.price_clp,
    discount: p.compare_at_price_clp ? p.compare_at_price_clp - p.price_clp : undefined,
    quantity,
  };
  if (list) {
    item.item_list_id = list.id;
    item.item_list_name = list.name;
  }
  if (index !== undefined) item.index = index;
  return Object.fromEntries(Object.entries(item).filter(([, v]) => v !== undefined)) as unknown as GaItem;
}

/** Ítems del carrito con sus cantidades. */
export function cartItems(cart: Cart): GaItem[] {
  return cart.items.map((line) => toGaItem(line.product, line.quantity));
}

/** Ítems de un pedido (precio pagado, copiado al momento de la compra). */
export function orderItems(order: Order): GaItem[] {
  return order.items.map((item) => ({
    item_id: String(item.product_id),
    item_name: item.name,
    price: item.unit_price_clp,
    quantity: item.quantity,
  }));
}
