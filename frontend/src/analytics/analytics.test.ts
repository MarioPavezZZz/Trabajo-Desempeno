import { describe, expect, it } from "vitest";
import type { Order, ProductSummary } from "../lib/types";
import { purchaseParams, shouldSendPurchase } from "./events";
import { eventPayload, sanitizeUrl, validMeasurementId } from "./ga4";
import { toGaItem } from "./items";
import { resolveTrafficType } from "./trafficType";
import { metricParams } from "./webVitals";

const card: ProductSummary = {
  id: 42,
  slug: "charizard-ex",
  name: "Charizard ex",
  product_type: "carta",
  game: "pokemon",
  set_name: "151",
  thumb: "/media/x.webp",
  price_clp: 276890,
  compare_at_price_clp: 299990,
  discount_pct: 8,
  stock: 1,
  rarity: "Special Illustration Rare",
  rarity_tier: "legendaria",
  condition: "NM",
  language: "JA",
  is_foil: true,
  sealed_type: null,
  accessory_type: null,
  created_at: "2026-11-01T12:00:00Z",
};

describe("eventPayload", () => {
  it("agrega traffic_type y tipo_trafico (copia reportable) a cada evento", () => {
    expect(eventPayload({ value: 1 }, "load_test", false)).toEqual({
      value: 1,
      traffic_type: "load_test",
      tipo_trafico: "load_test",
    });
  });
  it("en modo debug marca cada evento para DebugView", () => {
    expect(eventPayload({}, "real", true)).toMatchObject({ debug_mode: true });
    expect(eventPayload({}, "real", false)).not.toHaveProperty("debug_mode");
  });
});

describe("sanitizeUrl", () => {
  it("quita la clave del pedido y los tokens de pago", () => {
    expect(sanitizeUrl("http://localhost:8080/checkout/resultado/TCG-1?clave=secreta")).toBe(
      "http://localhost:8080/checkout/resultado/TCG-1",
    );
    expect(sanitizeUrl("/checkout/simulado?token=MOCK-abc")).toBe("/checkout/simulado");
    expect(sanitizeUrl("https://x.cl/r?token_ws=1&TBK_TOKEN=2&TBK_ORDEN_COMPRA=3&TBK_ID_SESION=4")).toBe("https://x.cl/r");
  });
  it("conserva los demás parámetros (filtros del listado)", () => {
    expect(sanitizeUrl("/cartas?game=magic&clave=x&condition=NM")).toBe("/cartas?game=magic&condition=NM");
  });
  it("tolera vacíos", () => {
    expect(sanitizeUrl("")).toBe("");
  });
});

describe("validMeasurementId", () => {
  it("acepta IDs de GA4 y rechaza cualquier otra cosa", () => {
    expect(validMeasurementId("G-AB12CD34EF")).toBe("G-AB12CD34EF");
    expect(validMeasurementId("# ej: G-XXXXXXXXXX; vacío = analítica desactivada")).toBe("");
    expect(validMeasurementId("UA-12345-1")).toBe("");
    expect(validMeasurementId("")).toBe("");
  });
});

describe("resolveTrafficType", () => {
  it("la URL manda sobre lo guardado y el valor del build", () => {
    expect(resolveTrafficType("?traffic_type=load_test", "real", "real")).toBe("load_test");
  });
  it("sin URL usa lo guardado en la pestaña", () => {
    expect(resolveTrafficType("", "load_test", "real")).toBe("load_test");
  });
  it("ignora valores desconocidos y por defecto es real", () => {
    expect(resolveTrafficType("?traffic_type=bot", "x", undefined)).toBe("real");
    expect(resolveTrafficType("", null, "load_test")).toBe("load_test");
  });
});

describe("toGaItem", () => {
  it("convierte una carta al formato de ítem de GA4", () => {
    expect(toGaItem(card, 2, { id: "cartas", name: "Cartas" }, 3)).toEqual({
      item_id: "42",
      item_name: "Charizard ex",
      item_brand: "Pokémon TCG",
      item_category: "Cartas",
      item_category2: "151",
      item_variant: "NM / JA / Foil",
      item_list_id: "cartas",
      item_list_name: "Cartas",
      index: 3,
      price: 276890,
      discount: 23100,
      quantity: 2,
    });
  });
  it("no incluye campos vacíos (accesorio sin set ni descuento)", () => {
    const item = toGaItem({
      ...card,
      game: null,
      set_name: null,
      compare_at_price_clp: null,
      product_type: "accesorio",
      condition: null,
      language: null,
      is_foil: false,
      accessory_type: "fundas",
    });
    expect(item).toEqual({
      item_id: "42",
      item_name: "Charizard ex",
      item_brand: "Accesorios",
      item_category: "Accesorios",
      item_variant: "fundas",
      price: 276890,
      quantity: 1,
    });
  });
});

const order: Order = {
  transaction_id: "TCG-261115-ABCDEF1234",
  status: "pagada",
  created_at: "2026-11-15T12:00:00Z",
  paid_at: "2026-11-15T12:01:00Z",
  contact_name: "Ana",
  contact_email: "ana@example.com",
  shipping_method: "domicilio",
  shipping_address: {},
  subtotal_clp: 5390,
  shipping_clp: 3990,
  total_clp: 9380,
  items: [
    { product_id: 7, slug: "sobre", thumb: null, name: "Sobre", quantity: 1, unit_price_clp: 5390, line_total_clp: 5390 },
  ],
  payment: { provider: "webpay", status: "autorizado", authorization_code: "1213", card_last4: "6623" },
};

describe("purchase", () => {
  it("incluye transaction_id, moneda CLP, valor total, envío e ítems", () => {
    expect(purchaseParams(order)).toEqual({
      transaction_id: "TCG-261115-ABCDEF1234",
      currency: "CLP",
      value: 9380,
      shipping: 3990,
      tax: 0,
      payment_type: "webpay",
      items: [{ item_id: "7", item_name: "Sobre", price: 5390, quantity: 1 }],
    });
  });

  it("se informa una sola vez por pedido en el mismo navegador", () => {
    const data = new Map<string, string>();
    const storage = { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
    expect(shouldSendPurchase("TCG-1", storage)).toBe(true);
    expect(shouldSendPurchase("TCG-1", storage)).toBe(false);
    expect(shouldSendPurchase("TCG-2", storage)).toBe(true);
  });

  it("sin almacenamiento igual se informa", () => {
    expect(shouldSendPurchase("TCG-3", null)).toBe(true);
  });
});

describe("Web Vitals", () => {
  it("LCP e INP en milisegundos enteros", () => {
    const p = metricParams({ name: "LCP", value: 1234.6, delta: 1234.6, id: "v4-1", rating: "good" }, "/");
    expect(p).toMatchObject({ value: 1235, metric_value: 1235, metric_rating: "good", metric_id: "v4-1", page_path: "/" });
  });
  it("CLS se multiplica por 1000 en value (GA4 necesita enteros)", () => {
    const p = metricParams({ name: "CLS", value: 0.1234, delta: 0.05, id: "v4-2", rating: "needs-improvement" }, "/cartas");
    expect(p.value).toBe(50);
    expect(p.metric_value).toBe(0.1234);
  });
});
