/**
 * Comportamientos de usuario (recorridos). Cada función es UNA sesión
 * completa: empieza sin cookies, navega con pausas aleatorias y termina.
 *
 * Las peticiones imitan lo que hace el frontend real en cada página (mismos
 * endpoints y mismas peticiones en paralelo), así la carga sobre el servidor
 * se parece a la de personas usando el sitio.
 */
import { group, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { assets, batch, get, json, newSession, ok, post, qs } from "./api.js";
import { LOADTEST_PASSWORD, THINK, WITH_ASSETS, loadtestEmail } from "./config.js";

// ---- Métricas de negocio (aparecen en el reporte junto a las HTTP) ----
export const comprasAprobadas = new Counter("compras_aprobadas");
export const comprasRechazadas = new Counter("compras_rechazadas");
export const sinStock = new Counter("sin_stock_409");
export const checkoutExitoso = new Rate("checkout_exitoso");
export const duracionCheckout = new Trend("duracion_checkout", true);
export const duracionSesion = new Trend("duracion_sesion", true);

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const chance = (p) => Math.random() < p;

/** Pausa de "lectura" entre acciones (se escala con THINK). */
function pause(min = 1, max = 4) {
  if (THINK > 0) sleep((min + Math.random() * (max - min)) * THINK);
}

function loadThumbs(items, n) {
  if (WITH_ASSETS) assets(items.slice(0, n).map((p) => p.thumb).filter(Boolean));
}

// ------------------------------------------------------------------ páginas
export function viewHome() {
  const res = get("/api/home", "GET /api/home");
  ok(res, "home");
  const body = json(res);
  if (body) loadThumbs([...body.new_arrivals, ...body.featured_sealed], 10);
  return body;
}

/** Listado con filtros al azar (como el panel de filtros de la página). */
export function viewListing(data, overrides = {}) {
  // `type: undefined` explícito = sin tipo (la búsqueda abarca todo el catálogo).
  const type = "type" in overrides ? overrides.type : pick(["carta", "carta", "carta", "sellado", "accesorio"]);
  const filters = { type, ...overrides };
  if (type !== "accesorio" && !overrides.q && chance(0.7)) filters.game = pick(data.games);
  if (type === "carta" && !overrides.q) {
    if (chance(0.3)) filters.rarity = pick(["rara", "epica", "legendaria"]);
    if (chance(0.25)) filters.condition = "NM";
    if (chance(0.2)) filters.in_stock = "true";
  }
  if (chance(0.3)) filters.sort = pick(["price_asc", "price_desc", "name"]);
  const pageQuery = qs({ ...filters, page_size: 24, page: overrides.page });
  const facetQuery = qs(filters);
  const [products, facets] = batch([
    [`/api/products${pageQuery}`, "GET /api/products"],
    [`/api/products/facets${facetQuery}`, "GET /api/products/facets"],
  ]);
  ok(products, "listado");
  ok(facets, "facetas");
  const body = json(products);
  if (body) loadThumbs(body.items, 8);
  return body;
}

export function viewProduct(slug) {
  const [detail, related] = batch([
    [`/api/products/${slug}`, "GET /api/products/{slug}"],
    [`/api/products/${slug}/related`, "GET /api/products/{slug}/related"],
  ]);
  ok(detail, "detalle");
  ok(related, "relacionados");
  const body = json(detail);
  if (body && WITH_ASSETS) assets([body.image]);
  return body;
}

/** Agrega al carrito. Si no hay stock (409) prueba otro producto, hasta 3 veces. */
export function addToCart(candidates, quantity = 1) {
  for (let i = 0; i < 3; i++) {
    const product = pick(candidates);
    const res = post("/api/cart/items", { product_id: product.id, quantity }, "POST /api/cart/items", "carrito");
    ok(res, "agregar al carrito", [201, 409]);
    if (res.status === 201) return product;
    if (res.status === 409) sinStock.add(1);
  }
  return null;
}

export function viewCart() {
  const res = get("/api/cart", "GET /api/cart", "carrito");
  ok(res, "carrito");
  return json(res);
}

/**
 * Checkout completo con el simulador de pago (k6 envía X-Traffic-Type: load_test).
 * `decision=auto` aprueba con la probabilidad configurada en el servidor.
 */
export function checkout(asGuest) {
  const start = Date.now();
  ok(get("/api/checkout/options", "GET /api/checkout/options", "checkout"), "opciones de pago");
  const delivery = chance(0.5)
    ? { shipping_method: "retiro" }
    : { shipping_method: "domicilio", street: "Av. Prueba 123", comuna: "Santiago", region: "Metropolitana", phone: "+56911111111" };
  const body = asGuest
    ? { ...delivery, contact_name: "Cliente k6", contact_email: "cliente-k6@example.com" }
    : delivery;
  const res = post("/api/checkout", body, "POST /api/checkout", "checkout");
  ok(res, "crear pedido", [201, 409]);
  if (res.status !== 201) {
    if (res.status === 409) sinStock.add(1);
    checkoutExitoso.add(false);
    return null;
  }
  const order = json(res);
  pause(2, 6); // tiempo "en la pasarela"
  const done = get(
    `/api/checkout/simulado/retorno${qs({ token: order.payment.token, decision: "auto", formato: "json" })}`,
    "GET /api/checkout/simulado/retorno",
    "checkout",
  );
  ok(done, "confirmar pago");
  const result = json(done);
  const approved = result && result.status === "pagada";
  (approved ? comprasAprobadas : comprasRechazadas).add(1);
  checkoutExitoso.add(Boolean(result));
  duracionCheckout.add(Date.now() - start);
  ok(
    get(`/api/orders/${order.transaction_id}${qs({ clave: order.access_key })}`, "GET /api/orders/{id}", "checkout"),
    "ver pedido",
  );
  return result;
}

// --------------------------------------------------------------- recorridos
function session(name, fn) {
  newSession();
  const start = Date.now();
  group(name, fn);
  duracionSesion.add(Date.now() - start, { recorrido: name });
}

/** Navega el home, un listado y 1 a 3 productos; se va sin comprar. */
export function navegante(data) {
  session("navegante", () => {
    viewHome();
    pause();
    const list = viewListing(data);
    pause();
    const items = list && list.items.length ? list.items : data.products.carta;
    for (let i = 0, n = 1 + Math.floor(Math.random() * 3); i < n; i++) {
      viewProduct(pick(items).slug);
      pause(2, 6);
    }
    if (chance(0.3)) viewListing(data, { page: 2 });
  });
}

/** Busca por texto (a veces con errores de tipeo), pagina y abre un resultado. */
export function buscador(data) {
  session("buscador", () => {
    viewHome();
    pause();
    let results = viewListing(data, { type: undefined, q: pick(data.terms), sort: "relevance" });
    pause();
    if (chance(0.4)) {
      results = viewListing(data, { type: undefined, q: pick(data.terms), sort: "relevance" });
      pause();
    }
    if (results && results.items.length) viewProduct(pick(results.items).slug);
  });
}

/** Agrega productos, revisa el carrito y se va sin pagar (abandono). */
export function abandono(data) {
  session("abandono", () => {
    viewListing(data, { type: "carta" });
    pause();
    const product = pick(data.products.carta);
    viewProduct(product.slug);
    pause();
    addToCart(data.products.carta);
    if (chance(0.4)) addToCart(chance(0.5) ? data.products.sellado : data.products.accesorio);
    pause();
    viewCart();
    pause(3, 8);
  });
}

/** Compra completa como invitado. */
export function comprador_invitado(data) {
  session("comprador_invitado", () => {
    viewHome();
    pause();
    viewListing(data);
    pause();
    viewProduct(pick(data.products.carta).slug);
    pause();
    const added = addToCart(data.products.carta);
    if (chance(0.3)) addToCart(data.products.sellado);
    viewCart();
    pause();
    if (added) checkout(true);
  });
}

/**
 * Cliente nuevo: se registra (bcrypt), compra, cierra sesión y vuelve a
 * entrar para ver sus pedidos (bcrypt otra vez). Cada sesión usa un correo
 * propio para que dos usuarios virtuales nunca compartan carrito.
 */
export function comprador_cuenta(data) {
  session("comprador_cuenta", () => {
    const email = loadtestEmail();
    const reg = post("/api/auth/register", { email, password: LOADTEST_PASSWORD, full_name: "Cliente k6" }, "POST /api/auth/register", "cuenta");
    ok(reg, "registro", [201]);
    pause();
    viewListing(data, { type: "carta" });
    pause();
    viewProduct(pick(data.products.carta).slug);
    const added = addToCart(data.products.carta);
    viewCart();
    pause();
    if (added) checkout(false);
    ok(post("/api/auth/logout", undefined, "POST /api/auth/logout", "cuenta"), "cerrar sesión", [204]);
    pause();
    ok(post("/api/auth/login", { email, password: LOADTEST_PASSWORD }, "POST /api/auth/login", "cuenta"), "ingresar");
    ok(get("/api/orders", "GET /api/orders", "cuenta"), "mis pedidos");
  });
}

export const JOURNEYS = { navegante, buscador, abandono, comprador_invitado, comprador_cuenta };
