/**
 * Módulo central de analítica de TCGMASTER (GA4 + Web Vitals).
 * Es el único punto de la aplicación que habla con Google Analytics.
 */
export { analyticsEnabled, initAnalytics } from "./ga4";
export * from "./events";
export type { ListContext } from "./items";
export { getTrafficType } from "./trafficType";
export { usePageView } from "./usePageView";
export { initWebVitals } from "./webVitals";
