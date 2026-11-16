/**
 * Perfil "navegadores": unos pocos navegadores reales (Chromium) recorren la
 * tienda mientras otra prueba genera carga HTTP de fondo.
 *
 * Para qué: la carga HTTP de k6 no ejecuta JavaScript, así que no produce
 * eventos de GA4 ni Web Vitals. Estos navegadores sí: abren el sitio con
 * ?traffic_type=load_test, así sus eventos llegan a GA4 marcados como prueba
 * y se puede comparar la experiencia real "sin carga" vs "bajo carga" (Fase 2).
 * k6 además registra LCP, CLS y FCP de cada página (browser_web_vital_*).
 *
 * Variables: BASE_URL, VUS (navegadores simultáneos, por defecto 2),
 * DURATION (por defecto 5m).
 */
import { browser } from "k6/browser";
import { sleep } from "k6";

const BASE_URL = (__ENV.BASE_URL || "http://host.docker.internal:8080").replace(/\/+$/, "");

export const options = {
  scenarios: {
    navegadores: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 2),
      duration: __ENV.DURATION || "5m",
      options: { browser: { type: "chromium" } },
    },
  },
  thresholds: {
    browser_web_vital_lcp: ["p(75)<2500"],
    browser_web_vital_cls: ["p(75)<0.1"],
  },
  summaryTrendStats: ["avg", "med", "p(75)", "p(90)", "p(95)", "max"],
};

export default async function () {
  const page = await browser.newPage();
  try {
    // Home marcado como tráfico de prueba (queda guardado para toda la pestaña).
    await page.goto(`${BASE_URL}/?traffic_type=load_test`, { waitUntil: "networkidle" });
    sleep(2 + Math.random() * 3);

    // Listado de cartas desde el menú (navegación dentro de la SPA).
    await page.locator('nav a[href="/cartas"]').click();
    await page.waitForSelector("article h3 a");
    sleep(2 + Math.random() * 3);

    // Abre un producto al azar de la primera página.
    const links = await page.$$("article h3 a");
    if (links.length) {
      await links[Math.floor(Math.random() * links.length)].click();
      await page.waitForSelector("dl"); // ficha técnica del detalle cargada
      sleep(3 + Math.random() * 4);
    }
  } finally {
    await page.close();
  }
}

export function handleSummary(data) {
  return { "/results/summary.json": JSON.stringify(data, null, 2), stdout: "\n" };
}
