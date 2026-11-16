# Configuración de Google Analytics 4 — TCGMASTER

Guía para dejar la propiedad GA4 lista para el curso. Los pasos en la
consola de Google los hace una persona del equipo (requieren su cuenta).

## 1. Crear la propiedad y el flujo de datos
1. En <https://analytics.google.com>: **Administrar → Crear → Propiedad**.
   - Nombre: `TCGMASTER`. Zona horaria: **Chile**. Moneda: **Peso chileno (CLP)**.
2. **Flujos de datos → Agregar flujo → Web**: URL del sitio (la del deploy o
   `http://localhost:8080` para pruebas) y nombre `TCGMASTER web`.
3. Copiar el **ID de medición** (`G-XXXXXXXXXX`) y ponerlo en `.env`:
   ```
   VITE_GA4_MEASUREMENT_ID=G-XXXXXXXXXX
   ```
   Luego reconstruir el frontend: `docker compose up -d --build web`.
   El ID no es secreto (viaja en el HTML de todas formas).

## 2. Medición mejorada (en el flujo de datos web)
- **Desactivar** "Cambios de página basados en eventos del historial del
  navegador". El sitio es una SPA y envía `page_view` por su cuenta; si queda
  activado, cada página se cuenta dos veces.
- Dejar activados: desplazamientos, clics salientes, búsqueda en el sitio
  (parámetro `q`). La participación (`user_engagement`) es automática.

## 3. Definiciones personalizadas
**Administrar → Definiciones personalizadas.**

Dimensiones (ámbito: **Evento**):

| Nombre | Parámetro | Para qué |
|---|---|---|
| Tipo de tráfico | `tipo_trafico` | Separar tráfico real de pruebas de carga |
| Calificación Web Vital | `metric_rating` | good / needs-improvement / poor |
| ID Web Vital | `metric_id` | Agrupar reportes de una carga de página |
| Tipo de envío | `shipping_tier` | retiro_tienda / envio_domicilio |
| Medio de pago | `payment_type` | webpay / simulado |

Métricas personalizadas (ámbito: **Evento**):

| Nombre | Parámetro | Unidad |
|---|---|---|
| Valor Web Vital | `metric_value` | Estándar (LCP e INP en ms; CLS sin unidad) |

> **Por qué `tipo_trafico` y no `traffic_type`:** el sitio envía ambos con el
> mismo valor (`real` o `load_test`). GA4 trata `traffic_type` como campo
> reservado: lo guarda para sus filtros de tráfico interno (viaja como `tt`)
> y no aparece como parámetro de evento, así que una dimensión con ese nombre
> queda vacía. `tipo_trafico` es un parámetro normal y sí se puede reportar.
>
> **No** crear un filtro de datos de "tráfico interno" en estado *Activo* para
> `traffic_type = load_test`: GA4 elimina esos datos de forma permanente.
> Para comparar real vs. carga, usar la dimensión "Tipo de tráfico" en los
> informes o en Explorar.

## 4. Eventos clave (conversiones)
`purchase` ya es evento clave por defecto. Opcional: marcar también
`begin_checkout` y `add_to_cart` para el embudo.

## 5. Dar acceso al profesor
**Administrar → Administración de acceso a la propiedad → + → Agregar
usuarios**: `j.aranda@utem.cl`, rol **Lector**.

## 6. Verificar
1. Poner `VITE_ANALYTICS_DEBUG=true` en el `.env` de la raíz y abrir el sitio
   (`docker compose up -d --build web` -> http://localhost:8080, o
   `cd frontend` + `npm run dev` -> http://localhost:5173; ambos leen ese
   `.env`). Cada evento aparece en la consola como `[GA4] nombre_evento {...}`,
   lleva `debug_mode` y la sesión aparece en **Administrar → DebugView**.
   Desactivar los bloqueadores de anuncios para `localhost`.
2. Recorrer: home → listado → detalle → agregar al carrito → carrito →
   checkout → pago → resultado.
3. En DebugView deben aparecer, en orden: `page_view`, `view_item_list`,
   `select_item`, `view_item`, `add_to_cart`, `view_cart`, `begin_checkout`,
   `add_shipping_info`, `add_payment_info`, `purchase`, y además `LCP`, `INP`,
   `CLS`. Todos con el parámetro `traffic_type`.

## Eventos que envía el sitio

| Evento | Cuándo | Parámetros principales |
|---|---|---|
| `page_view` | Cada cambio de página | page_location, page_path, page_title |
| `view_item_list` | Al mostrar un listado o bloque del home | item_list_id, item_list_name, items |
| `select_item` | Clic en un producto de una lista | item_list_id, items |
| `search` | Búsqueda por texto | search_term, results_count |
| `view_item` | Detalle de producto | currency, value, items |
| `add_to_cart` / `remove_from_cart` | Cambios en el carrito | currency, value, items |
| `view_cart` | Abrir el carrito | currency, value, items |
| `begin_checkout` | Entrar al checkout | currency, value, items |
| `add_shipping_info` | Enviar datos de entrega | shipping_tier, value, items |
| `add_payment_info` | Antes de ir a la pasarela | payment_type, value, items |
| `purchase` | Pago aprobado (una vez por pedido) | transaction_id, currency=CLP, value, shipping, items |
| `LCP` / `INP` / `CLS` | Core Web Vitals de cada visita | value, metric_value, metric_rating, metric_id |

Todos llevan `traffic_type` y `tipo_trafico` con el valor `real | load_test`.

## Marcar tráfico de prueba de carga
- Navegadores automatizados (Playwright, k6 browser): abrir el sitio con
  `?traffic_type=load_test`. Se recuerda en toda la pestaña y también se envía
  a la API (`X-Traffic-Type`), así GA4, la API y Nginx coinciden.
- Alternativa: compilar una copia del frontend con `VITE_TRAFFIC_TYPE=load_test`.
