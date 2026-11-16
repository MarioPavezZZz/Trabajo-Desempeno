/**
 * Carga de Google Analytics 4 (gtag.js) y envío de eventos.
 *
 * - Sin `VITE_GA4_MEASUREMENT_ID` no se carga nada externo.
 * - gtag.js (~100 KB) se descarga cuando el navegador queda libre después del
 *   primer render, para no competir con el LCP. Los eventos previos esperan en
 *   `dataLayer` y se envían al cargar.
 * - Es una SPA: los `page_view` se envían a mano en cada cambio de página
 *   (`send_page_view: false`); en GA4 hay que desactivar los cambios de página
 *   por historial de la medición mejorada (ver docs/ga4-configuracion.md).
 * - `VITE_ANALYTICS_DEBUG=true` muestra cada evento en la consola y activa
 *   `debug_mode` (aparece en DebugView de GA4).
 */
import { getTrafficType } from "./trafficType";

type Gtag = (...args: unknown[]) => void;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: Gtag;
  }
}

const RAW_ID = (import.meta.env.VITE_GA4_MEASUREMENT_ID ?? "").trim();
const DEBUG = import.meta.env.VITE_ANALYTICS_DEBUG === "true";

/** ID de medición GA4 válido ("G-" + mayúsculas/números) o cadena vacía. */
export function validMeasurementId(raw: string): string {
  return /^G-[A-Z0-9]{4,20}$/.test(raw) ? raw : "";
}

const MEASUREMENT_ID = validMeasurementId(RAW_ID);
// Un valor mal escrito (p. ej. un comentario tomado como valor desde .env) no
// debe cargar gtag.js con un ID inválido: se desactiva y se avisa.
if (RAW_ID && !MEASUREMENT_ID && typeof console !== "undefined") {
  console.warn(`[GA4] VITE_GA4_MEASUREMENT_ID inválido ("${RAW_ID.slice(0, 30)}"): analítica desactivada.`);
}

export const analyticsEnabled = MEASUREMENT_ID !== "";

export type EventParams = Record<string, unknown>;

let initialized = false;

/** Prepara gtag y programa la descarga del script. Seguro de llamar varias veces. */
export function initAnalytics(): void {
  if (initialized || typeof window === "undefined") return;
  initialized = true;
  if (DEBUG) console.info(`[GA4] ${analyticsEnabled ? `activo (${MEASUREMENT_ID})` : "sin ID: solo consola"}`);
  if (!analyticsEnabled) return;

  window.dataLayer = window.dataLayer ?? [];
  // gtag exige recibir el objeto `arguments`, no un arreglo.
  window.gtag = function gtag() {
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer!.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", MEASUREMENT_ID, {
    send_page_view: false,
    // Desde el primer evento, URL y referrer sin claves ni tokens.
    page_location: sanitizeUrl(window.location.href),
    page_referrer: sanitizeUrl(document.referrer),
    traffic_type: getTrafficType(),
    ...(DEBUG ? { debug_mode: true } : {}),
  });

  const load = () => {
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
    document.head.appendChild(script);
  };
  // Safari no tiene requestIdleCallback: se usa una espera fija.
  const whenIdle = () => {
    if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(load, { timeout: 3000 });
    else setTimeout(load, 1500);
  };
  if (document.readyState === "complete") whenIdle();
  else window.addEventListener("load", whenIdle, { once: true });
}

/**
 * Parámetros de URL que nunca deben llegar a GA4: la clave de acceso a un
 * pedido de invitado y los tokens de la pasarela (con ellos se podría ver
 * un pedido ajeno).
 */
const SENSITIVE_PARAMS = ["clave", "token", "token_ws", "TBK_TOKEN", "TBK_ORDEN_COMPRA", "TBK_ID_SESION"];

/** URL sin parámetros sensibles (se conserva el resto, p. ej. filtros del listado). */
export function sanitizeUrl(url: string): string {
  if (!url) return url;
  try {
    const parsed = new URL(url, "http://local");
    for (const name of SENSITIVE_PARAMS) parsed.searchParams.delete(name);
    const isAbsolute = /^https?:\/\//.test(url);
    return isAbsolute ? parsed.toString() : parsed.pathname + parsed.search + parsed.hash;
  } catch {
    return url.split("?")[0];
  }
}

/**
 * Fija la URL y el referrer limpios para todos los eventos siguientes. gtag
 * adjunta la URL del documento a cada evento: sin esto, la clave del pedido
 * viajaría en `purchase` y en cualquier otro evento de esa página.
 */
export function setPageContext(location: string, referrer: string): void {
  if (analyticsEnabled && window.gtag) {
    window.gtag("set", { page_location: sanitizeUrl(location), page_referrer: sanitizeUrl(referrer) });
  }
}

/**
 * Parámetros comunes de todos los eventos (función pura, testeable):
 * - `traffic_type`: lo pide la especificación. GA4 lo trata como campo
 *   reservado (lo envía como `tt`, para sus filtros de tráfico interno), así
 *   que NO sirve como dimensión personalizada.
 * - `tipo_trafico`: copia del mismo valor como parámetro normal; es el que se
 *   registra como dimensión para separar real vs. prueba de carga en informes.
 * - `debug_mode`: en modo debug va en cada evento. Ponerlo solo en
 *   gtag('config') no agregó `_dbg=1` a las peticiones y DebugView no mostraba nada.
 */
export function eventPayload(params: EventParams, trafficType: string, debug: boolean): EventParams {
  return {
    ...params,
    traffic_type: trafficType,
    tipo_trafico: trafficType,
    ...(debug ? { debug_mode: true } : {}),
  };
}

/** Envía un evento a GA4 (y a la consola en modo debug). */
export function sendEvent(name: string, params: EventParams = {}): void {
  const payload = eventPayload(params, getTrafficType(), DEBUG);
  if (DEBUG) console.info(`[GA4] ${name}`, payload);
  if (analyticsEnabled && typeof window !== "undefined" && window.gtag) {
    window.gtag("event", name, payload);
  }
}

/**
 * Envía un evento y espera a que gtag lo despache antes de navegar fuera del
 * sitio (p. ej. hacia Transbank). Si GA4 no responde en `timeoutMs`, sigue igual:
 * la analítica nunca debe bloquear una compra.
 */
export function sendEventBeforeLeaving(name: string, params: EventParams, timeoutMs = 600): Promise<void> {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        resolve();
      }
    };
    window.setTimeout(finish, timeoutMs);
    if (!analyticsEnabled || !window.gtag) {
      sendEvent(name, params);
      finish();
      return;
    }
    sendEvent(name, { ...params, event_callback: finish, event_timeout: timeoutMs });
  });
}
