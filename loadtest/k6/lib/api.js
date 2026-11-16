/**
 * Cliente HTTP de las pruebas: agrega los encabezados de tráfico de carga y
 * etiqueta cada petición con:
 *   name  -> plantilla del endpoint ("GET /api/products/{slug}"), para que los
 *            percentiles se agrupen por ruta y no por URL (cardinalidad acotada).
 *   grupo -> navegacion | carrito | checkout | cuenta | estaticos, para los umbrales.
 */
import http from "k6/http";
import { check } from "k6";
import { BASE_URL } from "./config.js";

const HEADERS = {
  Accept: "application/json",
  "X-Traffic-Type": "load_test", // la API usa el simulador de pago y marca pedidos/carritos
  "User-Agent": "TCGMASTER-k6/1.0 (prueba de carga INFB8091)",
};

// 409 (sin stock) es un resultado de negocio esperado, no un error del servidor.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 399 }, 409));

/** Arma una query string (k6 no trae URLSearchParams). */
export function qs(params) {
  const parts = [];
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === "") continue;
    const values = Array.isArray(value) ? value : [value];
    for (const v of values) parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(v)}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

function params(name, grupo, extraHeaders) {
  return { headers: { ...HEADERS, ...(extraHeaders || {}) }, tags: { name, grupo } };
}

export function get(path, name, grupo = "navegacion") {
  return http.get(`${BASE_URL}${path}`, params(name, grupo));
}

export function post(path, body, name, grupo) {
  return http.post(
    `${BASE_URL}${path}`,
    body === undefined ? null : JSON.stringify(body),
    params(name, grupo, { "Content-Type": "application/json" }),
  );
}

/**
 * Varias peticiones en paralelo, como hace el navegador (p. ej. listado + facetas).
 * `requests`: [[path, name, grupo], ...]
 */
export function batch(requests) {
  return http.batch(
    requests.map(([path, name, grupo]) => ["GET", `${BASE_URL}${path}`, null, params(name, grupo || "navegacion")]),
  );
}

/** Imágenes (servidas por Nginx), como las pediría el navegador. */
export function assets(paths) {
  if (!paths.length) return [];
  return http.batch(
    paths.map((p) => ["GET", `${BASE_URL}${p}`, null, { headers: { "X-Traffic-Type": "load_test" }, tags: { name: "GET /media/*", grupo: "estaticos" } }]),
  );
}

export function json(res) {
  try {
    return res.json();
  } catch (_) {
    return null;
  }
}

export function ok(res, label, expected = [200]) {
  return check(res, { [`${label}: ${expected.join("/")}`]: (r) => expected.includes(r.status) });
}

/** Cada sesión nueva parte sin cookies (sin carrito ni sesión de la iteración anterior). */
export function newSession() {
  http.cookieJar().clear(BASE_URL);
}
