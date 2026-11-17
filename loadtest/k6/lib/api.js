/**
 * Cliente HTTP de las pruebas: agrega los encabezados de tráfico de carga y
 * etiqueta cada petición con:
 *   name  -> plantilla del endpoint ("GET /api/products/{slug}"), para que los
 *            percentiles se agrupen por ruta y no por URL (cardinalidad acotada).
 *   grupo -> navegacion | carrito | checkout | cuenta | estaticos, para los umbrales.
 */
import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";
import { BASE_URL } from "./config.js";

/**
 * Clasificación de fallos, para distinguir en el informe un error del SERVIDOR
 * (5xx) de uno de RED/CLIENTE (status 0: sin respuesta, conexión rechazada o
 * reiniciada, timeout, falla de TLS o DNS), que puede originarse en el
 * generador o en la red intermedia y no en la aplicación.
 */
const fallosRed = new Counter("fallos_red");
const fallos5xx = new Counter("fallos_5xx");
const fallos4xx = new Counter("fallos_4xx");
let erroresMostrados = 0;

function track(res) {
  for (const r of Array.isArray(res) ? res : [res]) {
    if (r.status === 0) {
      fallosRed.add(1);
      if (erroresMostrados++ < 15) console.warn(`fallo de red (${r.error_code}): ${r.error}`);
    } else if (r.status >= 500) {
      fallos5xx.add(1);
    } else if (r.status >= 400 && r.status !== 409) {
      fallos4xx.add(1);
    }
  }
  return res;
}

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
  return track(http.get(`${BASE_URL}${path}`, params(name, grupo)));
}

export function post(path, body, name, grupo) {
  return track(http.post(
    `${BASE_URL}${path}`,
    body === undefined ? null : JSON.stringify(body),
    params(name, grupo, { "Content-Type": "application/json" }),
  ));
}

/**
 * Varias peticiones en paralelo, como hace el navegador (p. ej. listado + facetas).
 * `requests`: [[path, name, grupo], ...]
 */
export function batch(requests) {
  return track(http.batch(
    requests.map(([path, name, grupo]) => ["GET", `${BASE_URL}${path}`, null, params(name, grupo || "navegacion")]),
  ));
}

/** Imágenes (servidas por Nginx), como las pediría el navegador. */
export function assets(paths) {
  if (!paths.length) return [];
  return track(http.batch(
    paths.map((p) => ["GET", `${BASE_URL}${p}`, null, { headers: { "X-Traffic-Type": "load_test" }, tags: { name: "GET /media/*", grupo: "estaticos" } }]),
  ));
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
