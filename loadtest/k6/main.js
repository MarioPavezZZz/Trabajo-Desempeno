/**
 * Prueba de carga de TCGMASTER (k6).
 *
 * Un escenario por comportamiento (navegante, buscador, abandono, comprador
 * invitado, comprador con cuenta). Cada uno recibe una fracción de las
 * sesiones totales según WEIGHTS, así el reporte separa las métricas por
 * comportamiento y la mezcla se mantiene igual en todos los perfiles.
 *
 * Ejecutar con loadtest/run.ps1 (Windows) o loadtest/run.sh, que además
 * guardan el reporte HTML, el resumen JSON y las métricas del servidor.
 */
import { textSummary } from "https://jslib.k6.io/k6-summary/0.1.0/index.js";
import { BASE_URL, PERFIL, PROFILES, WEIGHTS, maxVUs, profileStages } from "./lib/config.js";
import { loadCatalog } from "./lib/data.js";
import * as journeys from "./lib/journeys.js";

const profile = PROFILES[PERFIL];
if (!profile) throw new Error(`Perfil desconocido: ${PERFIL}. Usa: ${Object.keys(PROFILES).join(", ")}`);

function buildScenarios() {
  const scenarios = {};
  for (const [name, weight] of Object.entries(WEIGHTS)) {
    if (profile.kind === "smoke") {
      // Humo: una sesión de cada comportamiento, una tras otra, para validar el flujo.
      scenarios[name] = { executor: "per-vu-iterations", vus: 1, iterations: 1, exec: name, maxDuration: "3m" };
      continue;
    }
    const stages = profileStages(profile).map((s) => ({
      duration: s.duration,
      target: s.target === 0 ? 0 : Math.max(1, Math.round(s.target * weight)),
    }));
    const vus = Math.max(5, Math.ceil(maxVUs(profile) * weight));
    scenarios[name] = {
      executor: "ramping-arrival-rate",
      exec: name,
      startRate: 0,
      timeUnit: "1m", // tasas en sesiones por minuto (permite tasas bajas enteras)
      preAllocatedVUs: Math.max(2, Math.ceil(vus * 0.25)),
      maxVUs: vus,
      stages,
      tags: { recorrido: name },
    };
  }
  return scenarios;
}

// Endpoints con percentiles propios en el resumen (umbral vacío = solo reportar).
const ENDPOINTS = [
  "GET /api/home",
  "GET /api/products",
  "GET /api/products/facets",
  "GET /api/products/{slug}",
  "GET /api/products/{slug}/related",
  "POST /api/cart/items",
  "GET /api/cart",
  "POST /api/checkout",
  "GET /api/checkout/simulado/retorno",
  "POST /api/auth/register",
  "POST /api/auth/login",
  "GET /media/*",
];

const stress = PERFIL === "estres";
const thresholds = {
  // Errores: <1 %; en estrés se aborta si supera 10 % (ya se encontró el quiebre).
  http_req_failed: stress ? [{ threshold: "rate<0.10", abortOnFail: true, delayAbortEval: "30s" }] : ["rate<0.01"],
  "http_req_duration{grupo:navegacion}": ["p(95)<800"],
  "http_req_duration{grupo:carrito}": ["p(95)<800"],
  "http_req_duration{grupo:checkout}": ["p(95)<1500"],
  checks: ["rate>0.98"],
};
for (const name of ENDPOINTS) thresholds[`http_req_duration{name:${name}}`] = [];

export const options = {
  scenarios: buildScenarios(),
  thresholds,
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
  discardResponseBodies: false,
  setupTimeout: "2m",
  tags: { perfil: PERFIL },
};

export function setup() {
  console.log(`TCGMASTER k6 | perfil=${PERFIL} | sitio=${BASE_URL}`);
  return loadCatalog();
}

export const navegante = (data) => journeys.navegante(data);
export const buscador = (data) => journeys.buscador(data);
export const abandono = (data) => journeys.abandono(data);
export const comprador_invitado = (data) => journeys.comprador_invitado(data);
export const comprador_cuenta = (data) => journeys.comprador_cuenta(data);

export function handleSummary(data) {
  const dir = __ENV.RESULTS_DIR || "/results";
  return {
    stdout: textSummary(data, { indent: " ", enableColors: true }),
    [`${dir}/resumen.txt`]: textSummary(data, { indent: " ", enableColors: false }),
    [`${dir}/summary.json`]: JSON.stringify(data, null, 2),
  };
}
