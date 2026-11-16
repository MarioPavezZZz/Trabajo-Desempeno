/**
 * Core Web Vitals reales de cada visita (LCP, INP, CLS) enviados como eventos GA4.
 *
 * Formato recomendado por Google para Web Vitals en GA4: el nombre del evento
 * es la métrica, `value` es el delta (así las sumas en GA4 no duplican) y
 * `metric_id` agrupa los reportes de una misma carga de página.
 * CLS no tiene unidades: se multiplica por 1000 para que `value` sea entero.
 */
import { type Metric, onCLS, onINP, onLCP } from "web-vitals";
import { sendEvent } from "./ga4";

/** Parámetros del evento para una métrica (función pura, testeable). */
export function metricParams(metric: Pick<Metric, "name" | "value" | "delta" | "id" | "rating">, path: string) {
  const scale = metric.name === "CLS" ? 1000 : 1;
  return {
    value: Math.round(metric.delta * scale),
    metric_value: metric.name === "CLS" ? Number(metric.value.toFixed(4)) : Math.round(metric.value),
    metric_delta: Math.round(metric.delta * scale),
    metric_id: metric.id,
    metric_rating: metric.rating,
    page_path: path,
    non_interaction: true,
  };
}

function report(metric: Metric): void {
  sendEvent(metric.name, metricParams(metric, window.location.pathname));
}

/** Registra los observadores (una vez, al iniciar la aplicación). */
export function initWebVitals(): void {
  onLCP(report);
  onINP(report);
  onCLS(report);
}
