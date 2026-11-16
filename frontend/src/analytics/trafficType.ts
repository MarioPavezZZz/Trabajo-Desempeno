/**
 * Tipo de tráfico de la sesión: `real` o `load_test`.
 *
 * Prioridad:
 * 1. `?traffic_type=load_test|real` en la URL (se guarda en sessionStorage para
 *    toda la pestaña). Así los navegadores automatizados de la Fase 2 se marcan
 *    sin compilar otra versión del sitio.
 * 2. Valor guardado antes en la misma pestaña.
 * 3. `VITE_TRAFFIC_TYPE` del build (por defecto `real`).
 *
 * El mismo valor se envía a GA4 (parámetro `traffic_type`) y a la API
 * (encabezado `X-Traffic-Type`), así las tres fuentes clasifican igual cada visita.
 */
export type TrafficType = "real" | "load_test";

export const STORAGE_KEY = "tcg_traffic_type";

const isTrafficType = (value: string | null | undefined): value is TrafficType =>
  value === "real" || value === "load_test";

/** Decide el tipo de tráfico (función pura, testeable). */
export function resolveTrafficType(
  search: string,
  stored: string | null,
  buildDefault: string | undefined,
): TrafficType {
  const fromUrl = new URLSearchParams(search).get("traffic_type");
  if (isTrafficType(fromUrl)) return fromUrl;
  if (isTrafficType(stored)) return stored;
  return isTrafficType(buildDefault) ? buildDefault : "real";
}

let cached: TrafficType | null = null;

/** Tipo de tráfico de esta pestaña (se calcula una vez y se recuerda). */
export function getTrafficType(): TrafficType {
  if (cached) return cached;
  let stored: string | null = null;
  try {
    stored = window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    /* almacenamiento bloqueado: se usa el valor del build */
  }
  const search = typeof window !== "undefined" ? window.location.search : "";
  cached = resolveTrafficType(search, stored, import.meta.env.VITE_TRAFFIC_TYPE);
  try {
    window.sessionStorage.setItem(STORAGE_KEY, cached);
  } catch {
    /* sin almacenamiento: vale solo para esta carga de página */
  }
  return cached;
}
