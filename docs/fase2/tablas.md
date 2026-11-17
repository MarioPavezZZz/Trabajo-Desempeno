# Tablas de resultados (generadas por loadtest/tools/analizar.py)

## Resumen por escenario (lado cliente, k6)

| Escenario | Duración | Peticiones | Throughput medio (req/s) | Throughput máx. 10 s | Sesiones | Promedio | Mediana | p90 | p95 | p99 | Máx. | Errores | Checks | Compras aprob. / rech. | Sin stock (409) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baja | 5.3 min | 6 693 | 21.0 | 30.4 | 267 | 17.7 | 14.0 | 25.1 | 31.2 | 75.0 | 357 | 0.00 % | 100.00 % | 35 / 4 | 0 |
| normal | 15.3 min | 104 670 | 114.3 | 134.2 | 4 195 | 17.1 | 13.4 | 23.8 | 30.2 | 81.1 | 501 | 0.00 % | 100.00 % | 558 / 56 | 414 |
| normal-r2 | 15.3 min | 104 560 | 113.7 | 131.7 | 4 195 | 17.3 | 13.3 | 24.0 | 30.7 | 88.8 | 470 | 0.00 % | 100.00 % | 569 / 46 | 348 |
| pico | 5.5 min | 65 619 | 198.8 | 478.4 | 2 952 | 74.3 | 17.0 | 165.8 | 389.4 | 1 069.8 | 3 730 | 5.49 % | 84.06 % | 299 / 40 | 84 |
| pico-sin-img | 5.5 min | 22 982 | 69.6 | 171.7 | 2 992 | 186.3 | 35.3 | 583.4 | 867.7 | 1 595.1 | 3 178 | 13.19 % | 86.81 % | 323 / 38 | 137 |
| estres-abortado | 2.1 min | 2 514 | 20.0 | 40.8 | 296 | 22.2 | 14.1 | 29.2 | 51.0 | 317.4 | 341 | 10.02 % | 89.95 % | 37 / 7 | 1 |

Tiempos en ms. «Errores» = respuestas 4xx/5xx o sin respuesta (un 409 por falta de stock no cuenta como error).

## Tiempo de respuesta por tipo de operación (p95, ms)

| Escenario | navegacion | carrito | checkout | sesión completa (mediana, s) |
|---|---|---|---|---|
| baja | 34.1 | 21.6 | 319.8 | 12.1 |
| normal | 41.5 | 27.7 | 322.3 | 12.0 |
| normal-r2 | 42.4 | 28.4 | 322.3 | 11.9 |
| pico | 819.1 | 875.2 | 1 078.0 | 14.3 |
| pico-sin-img | 839.5 | 878.4 | 1 144.7 | 14.1 |
| estres-abortado | 34.4 | 24.7 | 321.1 | 11.7 |

## Tiempo de respuesta por endpoint (p95 / p99, ms)

| Endpoint | baja | normal | normal-r2 | pico | pico-sin-img | estres-abortado |
|---|---|---|---|---|---|---|
| `GET /api/cart` | 17.5 / 22.0 | 19.0 / 37.9 | 20.9 / 40.1 | 764.8 / 1 335.6 | 771.1 / 1 488.6 | 18.6 / 25.9 |
| `GET /api/checkout/simulado/retorno` | 330.1 / 347.1 | 334.6 / 348.2 | 334.6 / 376.6 | 1 498.0 / 1 942.0 | 1 567.7 / 2 200.3 | 328.8 / 340.7 |
| `GET /api/home` | 62.8 / 82.7 | 67.7 / 91.2 | 71.8 / 119.8 | 831.8 / 1 710.4 | 870.7 / 1 395.4 | 61.2 / 89.8 |
| `GET /api/products` | 29.5 / 52.6 | 41.0 / 64.9 | 39.9 / 62.7 | 874.8 / 1 666.6 | 885.7 / 1 640.3 | 31.7 / 53.3 |
| `GET /api/products/facets` | 26.4 / 41.2 | 36.0 / 59.2 | 35.6 / 64.0 | 845.9 / 1 573.0 | 901.1 / 1 741.3 | 26.7 / 47.1 |
| `GET /api/products/{slug}` | 18.8 / 24.9 | 21.5 / 40.9 | 21.8 / 43.2 | 718.3 / 1 468.1 | 716.3 / 1 536.7 | 17.8 / 31.5 |
| `GET /api/products/{slug}/related` | 20.7 / 27.1 | 23.8 / 45.0 | 23.8 / 51.3 | 813.7 / 1 528.7 | 793.7 / 1 448.5 | 19.4 / 47.2 |
| `GET /media/*` | 28.2 / 39.8 | 24.5 / 34.6 | 24.9 / 37.2 | 31.7 / 51.3 | — | — |
| `POST /api/auth/login` | 156.1 / 171.6 | 142.8 / 192.0 | 161.7 / 278.8 | 909.5 / 1 496.9 | 1 145.0 / 1 662.2 | 85.3 / 89.6 |
| `POST /api/auth/register` | 157.4 / 188.2 | 186.1 / 294.7 | 204.7 / 376.8 | 1 094.6 / 1 570.9 | 1 176.4 / 1 580.5 | 146.0 / 154.4 |
| `POST /api/cart/items` | 23.1 / 27.7 | 30.3 / 64.1 | 31.1 / 69.7 | 937.4 / 1 519.1 | 936.0 / 1 563.0 | 27.0 / 48.4 |
| `POST /api/checkout` | 27.6 / 32.2 | 37.6 / 59.7 | 41.0 / 72.7 | 1 223.9 / 2 239.8 | 1 189.2 / 1 676.4 | 33.9 / 37.3 |

## Recursos del servidor (VM 2 vCPU, 8 GB)

| Escenario | CPU host prom. / máx. (%) | %steal máx. | %iowait máx. | Carga (load1) máx. | CPU API prom. / máx. (% de 1 núcleo) | CPU BD prom. / máx. | CPU Nginx máx. | CPU Caddy máx. | Mem. API máx. (MB) | Mem. BD máx. (MB) | Pool BD máx. | Disco escr. máx. (KB/s) | Red salida prom. / máx. (KB/s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baja | 6.8 / 9.2 | 0.0 | 0.4 | 0.70 | 5.4 / 27.4 | 1.7 / 5.9 | 1.7 | 3.9 | 182 | 88 | 0 | 207 | 484 / 733 |
| normal | 20.0 / 25.4 | 0.0 | 1.0 | 1.70 | 21.4 / 62.0 | 6.1 / 13.8 | 3.7 | 10.3 | 201 | 168 | 2 | 489 | 1 913 / 2 360 |
| normal-r2 | 20.6 / 27.1 | 0.0 | 0.6 | 1.79 | 20.6 / 59.5 | 6.4 / 23.2 | 4.7 | 10.6 | 207 | 194 | 2 | 594 | 1 954 / 2 547 |
| pico | 36.3 / 88.5 | 0.0 | 1.5 | 3.55 | 38.4 / 101.6 | 17.9 / 56.7 | 11.2 | 34.7 | 208 | 208 | 30 | 954 | 3 082 / 8 031 |
| pico-sin-img | 32.4 / 81.7 | 0.0 | 1.0 | 4.10 | 37.3 / 101.5 | 16.3 / 61.1 | 5.4 | 12.2 | 211 | 169 | 30 | 650 | 299 / 799 |
| estres-abortado | 9.8 / 21.6 | 0.0 | 0.6 | 0.47 | 11.7 / 39.6 | 3.4 / 9.3 | 1.7 | 4.0 | 207 | 152 | 1 | 459 | 100 / 236 |

## Lado servidor (/metrics de la API, ventanas de 5 s)

Solo peticiones a la API (las imágenes las sirve Nginx). Las corridas anteriores a la corrección de `scrape_metrics.py` omiten en req/s y latencia las rutas con parámetros (`{slug}`, `{transaction_id}`); se marcan con *.

| Escenario | req/s API prom. / máx. | Latencia API prom. (ms) | p95 API máx. (ms) | p99 API máx. (ms) | Peticiones en curso máx. | 5xx totales aprox. |
|---|---|---|---|---|---|---|
| baja * | 5.2 / 8.0 | 16.8 | 380 | 476 | 3 | 0 |
| normal * | 21.8 / 27.8 | 22.6 | 430 | 486 | 6 | 0 |
| normal-r2 | 36.1 / 44.2 | 16.3 | 433 | 487 | 5 | 0 |
| pico * | 34.8 / 88.2 | 110.0 | 1 693 | 2 600 | 95 | 0 |
| pico-sin-img * | 36.6 / 91.8 | 104.9 | 1 690 | 2 581 | 96 | 0 |
| estres-abortado * | 10.9 / 25.2 | 19.7 | 453 | 491 | 2 | 0 |

## Core Web Vitals (navegadores reales, k6 browser)

| Escenario | LCP p75 / p95 (ms) | INP p75 / p95 (ms) | CLS p75 | FCP p75 (ms) | TTFB p75 / p95 (ms) | Páginas recorridas |
|---|---|---|---|---|---|---|
| baja | 235 / 340 | 76 / 95 | 0.001 | 235 | 43 / 54 | 129 |
| normal-r2 | 268 / 350 | 80 / 102 | 0.001 | 268 | 49 / 60 | 195 |
| pico | 21 149 / 21 192 | 80 / 104 | 0.001 | 21 147 | 44 / 374 | 54 |

Umbrales «buenos» de Google (p75): LCP ≤ 2 500 ms, INP ≤ 200 ms, CLS ≤ 0,1.

## Punto de saturación (corrida «pico-sin-img», ventanas de 10 s)

- Throughput máximo sostenido en una ventana: **171.7 req/s** (t = 140 s, 465 VUs, p95 1 347 ms).
- Primera ventana degradada (p95 > 800 ms o errores > 1 %): t = 110 s, 99.5 req/s, 408 VUs, p95 520 ms, errores 4.62 %, CPU API 75 %.
