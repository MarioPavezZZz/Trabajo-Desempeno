/**
 * Eventos de GA4 de la tienda. Toda la interfaz llama a estas funciones;
 * nadie llama a gtag directamente. Nombres y parámetros siguen el esquema de
 * e-commerce recomendado por Google, con montos en CLP.
 */
import type { Cart, Order, ProductSummary } from "../lib/types";
import { sanitizeUrl, sendEvent, sendEventBeforeLeaving, setPageContext } from "./ga4";
import { cartItems, CURRENCY, type ListContext, orderItems, toGaItem } from "./items";

export function trackPageView(path: string, title: string): void {
  const location = sanitizeUrl(window.location.origin + path);
  setPageContext(location, document.referrer);
  sendEvent("page_view", {
    page_location: location,
    page_path: sanitizeUrl(path),
    page_title: title,
  });
}

export function trackViewItemList(list: ListContext, products: ProductSummary[]): void {
  if (products.length === 0) return;
  sendEvent("view_item_list", {
    item_list_id: list.id,
    item_list_name: list.name,
    items: products.map((p, i) => toGaItem(p, 1, list, i)),
  });
}

export function trackSelectItem(list: ListContext, product: ProductSummary, index: number): void {
  sendEvent("select_item", {
    item_list_id: list.id,
    item_list_name: list.name,
    items: [toGaItem(product, 1, list, index)],
  });
}

export function trackSearch(term: string, results: number): void {
  sendEvent("search", { search_term: term, results_count: results });
}

export function trackViewItem(product: ProductSummary): void {
  sendEvent("view_item", { currency: CURRENCY, value: product.price_clp, items: [toGaItem(product)] });
}

export function trackAddToCart(product: ProductSummary, quantity: number): void {
  sendEvent("add_to_cart", {
    currency: CURRENCY,
    value: product.price_clp * quantity,
    items: [toGaItem(product, quantity)],
  });
}

export function trackRemoveFromCart(product: ProductSummary, quantity: number): void {
  sendEvent("remove_from_cart", {
    currency: CURRENCY,
    value: product.price_clp * quantity,
    items: [toGaItem(product, quantity)],
  });
}

/** Cambio de cantidad en el carrito: se informa como agregar o quitar la diferencia. */
export function trackQuantityChange(product: ProductSummary, before: number, after: number): void {
  if (after > before) trackAddToCart(product, after - before);
  else if (after < before) trackRemoveFromCart(product, before - after);
}

export function trackViewCart(cart: Cart): void {
  sendEvent("view_cart", { currency: CURRENCY, value: cart.subtotal_clp, items: cartItems(cart) });
}

export function trackBeginCheckout(cart: Cart): void {
  sendEvent("begin_checkout", { currency: CURRENCY, value: cart.subtotal_clp, items: cartItems(cart) });
}

export function trackAddShippingInfo(cart: Cart, shippingTier: string, shipping: number): void {
  sendEvent("add_shipping_info", {
    currency: CURRENCY,
    value: cart.subtotal_clp + shipping,
    shipping_tier: shippingTier,
    items: cartItems(cart),
  });
}

/** Se espera a que GA4 despache el evento: justo después el navegador sale hacia la pasarela. */
export function trackAddPaymentInfo(cart: Cart, paymentType: string, total: number): Promise<void> {
  return sendEventBeforeLeaving("add_payment_info", {
    currency: CURRENCY,
    value: total,
    payment_type: paymentType,
    items: cartItems(cart),
  });
}

/** Parámetros de `purchase` (función pura, testeable). */
export function purchaseParams(order: Order): Record<string, unknown> {
  return {
    transaction_id: order.transaction_id,
    currency: CURRENCY,
    value: order.total_clp,
    shipping: order.shipping_clp,
    tax: 0,
    payment_type: order.payment?.provider === "mock" ? "simulado" : "webpay",
    items: orderItems(order),
  };
}

const PURCHASE_KEY = "tcg_purchase_sent";

/** True si este pedido todavía no se informó en este navegador (evita duplicados al recargar). */
export function shouldSendPurchase(transactionId: string, storage: Pick<Storage, "getItem" | "setItem"> | null): boolean {
  if (!storage) return true;
  try {
    const sent: string[] = JSON.parse(storage.getItem(PURCHASE_KEY) ?? "[]");
    if (sent.includes(transactionId)) return false;
    storage.setItem(PURCHASE_KEY, JSON.stringify([...sent, transactionId].slice(-50)));
    return true;
  } catch {
    return true;
  }
}

export function trackPurchase(order: Order): void {
  if (order.status !== "pagada") return;
  let storage: Storage | null = null;
  try {
    storage = window.localStorage;
  } catch {
    /* sin almacenamiento */
  }
  if (shouldSendPurchase(order.transaction_id, storage)) sendEvent("purchase", purchaseParams(order));
}
