# Propuesta de arquitectura — TCGMASTER

> Estado: **PROPUESTA, pendiente de aprobación.** No se ha escrito código de la aplicación.
> Fecha: 2026-11-12.

## 1. Stack recomendado

Se mantiene la sugerencia del equipo (FastAPI + PostgreSQL + React/Vite +
Tailwind + Docker Compose) con agregados pensados para las pruebas de carga.

| Capa | Tecnología | Por qué (visto desde la Fase 2) |
|---|---|---|
| Proxy / estáticos | **Nginx** | Sirve el build de React y las imágenes con caché HTTP; separa “carga de estáticos” de “carga de la API” y permite medir cada una. |
| API | **FastAPI** sobre **Gunicorn + workers Uvicorn** | Asíncrono, rápido; el número de workers (`API_WORKERS`) es un parámetro que se puede variar entre escenarios. |
| Acceso a datos | **SQLAlchemy 2 (async) + asyncpg**, migraciones con **Alembic** | Pool de conexiones configurable (otra variable de saturación medible). |
| Base de datos | **PostgreSQL 16** con `pg_trgm` y búsqueda full-text (`tsvector`) | Búsqueda por texto sin servicio extra; índices GIN medibles con `EXPLAIN ANALYZE`. |
| Frontend | **React 18 + Vite + Tailwind**, React Router, TanStack Query | SPA liviana; el HTML es estático y la carga recae en la API, que es lo que se mide. |
| Métricas | `prometheus-client` (modo multiproceso) → `/metrics` | Formato estándar; Prometheus/Grafana lo leen sin adaptar nada. |
| Logs | `structlog` en JSON | Una línea por petición con ruta, estado y `duration_ms`. |
| Pagos | **Webpay Plus — ambiente de integración** (SDK oficial `transbank-sdk`) + modo `mock` | Credenciales de integración son públicas (no requiere crear cuenta). El modo `mock` evita cargar a Transbank durante las pruebas. |
| Monitoreo (opcional) | Perfil Compose `monitoring`: Prometheus + Grafana + cAdvisor | CPU/memoria por contenedor durante las pruebas, para gráficos del informe. |
| Carga (Fase 1.2) | **k6** (recomendado) | Muchos usuarios virtuales por máquina, umbrales p95/p99 y reporte HTML/JSON nativo. Locust queda como alternativa si se prefieren flujos en Python. |

### Alternativas consideradas y descartadas
- **Next.js con SSR:** mejor LCP inicial y carga de servidor más “realista”, pero
  mezcla render y API en un mismo proceso (más difícil aislar el cuello de botella)
  y es más pesado en hosting gratuito. Se descarta para este alcance.
- **Redis como caché desde el inicio:** se deja **fuera** a propósito. Primero
  medimos la línea base sin caché; agregarla después sirve como “propuesta de
  mejora” con evidencia antes/después en el informe.
- **Django:** más completo pero más lento por petición y síncrono por defecto.

## 2. Diagrama

```
Navegador ──► Nginx :8080 ──┬─► /            build estático de React (gzip, cache-control)
 (GA4 gtag)                 ├─► /media/*     imágenes de cartas (cache 30 días)
                            └─► /api/*  ──►  FastAPI (Gunicorn, N workers) ──► PostgreSQL
                                              │  /health  /metrics
                                              └─► Webpay Plus (integración)  |  mock
k6 (otra máquina) ─────────► Nginx
Prometheus ──scrape──► /metrics, cAdvisor   ──► Grafana   (perfil opcional)
```

## 3. Estructura de carpetas

```
tcgmaster/
├─ AGENTS.md  LogFile.txt  README.md  .env.example  .gitignore
├─ docker-compose.yml               # db, api, web (nginx); límites por variables
├─ docker-compose.monitoring.yml    # prometheus, grafana, cadvisor (opcional)
├─ backend/
│  ├─ Dockerfile  pyproject.toml  alembic.ini
│  ├─ alembic/versions/
│  ├─ app/
│  │  ├─ main.py                    # creación de la app, middlewares
│  │  ├─ core/       config.py  logging.py  metrics.py  security.py
│  │  ├─ db/         session.py  base.py
│  │  ├─ models/     catalog.py  user.py  cart.py  order.py
│  │  ├─ schemas/    (Pydantic)
│  │  ├─ services/   catalog.py  cart.py  checkout.py
│  │  ├─ payments/   base.py  webpay.py  mock.py
│  │  └─ api/routes/ health.py  catalog.py  auth.py  cart.py  checkout.py
│  └─ tests/
├─ frontend/
│  ├─ Dockerfile  nginx.conf  vite.config.ts  tailwind.config.ts
│  ├─ public/fonts/                 # fuentes self-hosted (sin Google Fonts en runtime)
│  └─ src/
│     ├─ pages/  components/  hooks/  lib/api.ts
│     ├─ analytics/  index.ts  ga4.ts  webVitals.ts   # módulo central GA4
│     └─ styles/
├─ scripts/seed_catalog.py
├─ data/  cache/  media/            # ignorados por Git, regenerables
├─ loadtest/                        # Fase 1.2 (k6)
└─ docs/                            # arquitectura, decisiones, material del informe
```

## 4. Modelo de datos

Decisión clave: **una sola tabla `products`** con columnas de carta y de sellado
anulables (desnormalizada). Todos los filtros del listado se resuelven sin JOIN,
lo que simplifica los índices y hace más predecible la latencia bajo carga.

```
games         id, slug, name, sort_order
sets          id, game_id→games, code, name, release_date, logo_path, card_count
products      id, sku (único), slug (único), product_type  [carta|sellado|accesorio]
              game_id→games, set_id→sets (nulo en accesorios)
              name, description, image_path, thumb_path
              price_clp INT, compare_at_price_clp INT NULL   ← si existe, está en oferta
              stock INT ≥ 0, is_featured BOOL, is_active BOOL, created_at
              -- solo cartas --
              rarity, rarity_tier [comun|infrecuente|rara|epica|legendaria]
              condition [NM|LP|MP|HP], language, is_foil, card_number,
              source_api, external_id, attributes JSONB
              -- solo sellados / accesorios --
              sealed_type [sobre|display|caja_entrenador|mazo_estructura], accessory_type
              search_vector TSVECTOR (columna generada: nombre + set + tipo)
price_history product_id, price_clp, recorded_at        ← “mayor variación de precio” (opcional)
users         id, email (único), password_hash, full_name, created_at
carts         id UUID, user_id NULL, status [activo|convertido|abandonado], created_at, updated_at
cart_items    cart_id, product_id, quantity, unit_price_clp   UNIQUE(cart_id, product_id)
orders        id, transaction_id (único), user_id, status [pendiente|pagada|rechazada|anulada],
              total_clp, traffic_type [real|load_test], created_at, paid_at
order_items   order_id, product_id, name_snapshot, quantity, unit_price_clp
payments      id, order_id, provider [webpay|mock], token, buy_order, amount_clp,
              status, authorization_code, raw_response JSONB, created_at
```

**Índices principales**
- `GIN(search_vector)` para búsqueda full-text; `GIN(name gin_trgm_ops)` para coincidencias parciales.
- B-tree compuesto `(product_type, game_id, price_clp)` para filtrar y ordenar por precio.
- `(set_id)`, `(created_at DESC)` para “novedades”, `(rarity_tier)`, `(condition)`.
- Parcial `WHERE compare_at_price_clp IS NOT NULL` para ofertas; parcial `WHERE stock > 0` para disponibilidad.

**Stock:** se descuenta al confirmar el pago con `SELECT … FOR UPDATE` dentro de
una transacción. Es un punto de contención real que conviene medir en Fase 2.

**Carrito:** guardado en BD (no en localStorage) e identificado por cookie; se
asocia al usuario al iniciar sesión. Así el carrito genera carga de escritura
medible y permite estudiar abandono de carrito.

## 5. Páginas

| Ruta | Página | Carga de datos |
|---|---|---|
| `/` | Inicio: hero, selector de juegos, novedades con filtro, sellados destacados, ofertas, (variación de precio) | **Media-alta**: varias consultas pequeñas |
| `/cartas` | Listado de cartas con filtros, orden y paginación | **Alta**: consulta filtrada + facetas (conteos) |
| `/sellados` | Listado de sellados | Media |
| `/ofertas` | Listado de productos con descuento | Media |
| `/accesorios` | Listado de accesorios | Baja |
| `/producto/:slug` | Detalle + relacionados | **Baja-media**: 1 producto + relacionados |
| `/buscar?q=` | Resultados de búsqueda de texto | Alta (full-text) |
| `/carrito` | Carrito | Escritura |
| `/checkout` → `/checkout/resultado` | Resumen, pago Webpay, confirmación | Transaccional |
| `/cuenta/ingresar`, `/cuenta/registro` | Login / registro | CPU (hash de contraseña) |
| `/cuenta` | Mis pedidos | Baja |
| `/blog` | Opcional, solo si sobra tiempo | — |

## 6. API (resumen)

```
GET  /health                     GET  /metrics
GET  /api/games                  GET  /api/sets?game=
GET  /api/home                   (bloques del home en una sola respuesta)
GET  /api/products?type=&game=&set=&rarity=&condition=&lang=&foil=&min=&max=&in_stock=&q=&sort=&page=&page_size=
GET  /api/products/facets?...    (conteos por filtro)
GET  /api/products/{slug}        GET  /api/products/{slug}/related
POST /api/auth/register          POST /api/auth/login     POST /api/auth/logout   GET /api/auth/me
GET  /api/cart   POST /api/cart/items   PATCH /api/cart/items/{id}   DELETE /api/cart/items/{id}
POST /api/checkout               (crea orden + transacción Webpay o mock)
GET|POST /api/checkout/webpay/return   GET /api/orders   GET /api/orders/{transaction_id}
```

## 7. Despliegue (paso 8, propuesta preliminar)

Recomendado: **una VM “Always Free” (Oracle Cloud, ARM)** corriendo el mismo
`docker-compose.yml`. Ventajas: entorno idéntico al local, recursos fijos y
conocidos (clave para interpretar resultados), y no hay suspensión por
inactividad. Alternativa: Render (web) + Neon (Postgres), pero los planes
gratuitos se duermen y limitan CPU, lo que distorsiona las mediciones.
Las pruebas de carga se lanzan **desde otra máquina** distinta al servidor.

## 8. Notas de GA4 relevantes para la Fase 2

- k6 por HTTP no ejecuta JavaScript: **no genera eventos GA4 ni Web Vitals**.
  Para comparar experiencia “normal vs. bajo carga” se usará un grupo pequeño
  de navegadores reales (módulo browser de k6 o Playwright) marcados con
  `traffic_type=load_test`, mientras k6 HTTP genera la carga de fondo.
- `traffic_type` es un parámetro que GA4 usa en sus **filtros de datos**. No
  crear un filtro de “tráfico interno” en modo *Activo* con ese valor, porque
  GA4 descarta los datos de forma permanente; segmentar con una dimensión
  personalizada en su lugar.
