# AGENTS.md — TCGMASTER

Guía para cualquier agente de codificación (Claude Code u otro) que trabaje en
este repositorio. **Léela completa al iniciar cada sesión**, junto con
`LogFile.txt`.

---

## 1. El proyecto

- **Curso:** INFB8091 — Desempeño de Sistemas (UTEM), Trabajo Semestre 2 - 2026.
- **Opción elegida:** Opción 1 — Comercio electrónico.
- **Comercio:** **TCGMASTER**, tienda online *individual* (no marketplace) de
  cartas coleccionables (TCG). Juegos: **Pokémon TCG, Magic: The Gathering y
  Yu-Gi-Oh!** (pendiente de confirmación final por el equipo).
- **Productos:** cartas sueltas, productos sellados (sobres, displays, cajas de
  entrenador, mazos de estructura) y accesorios.
- **Objetivo del curso:** construir el sitio (Fase 1.1), generar carga sintética
  realista (Fase 1.2, k6 o Locust) y analizar desempeño servidor + experiencia
  de usuario con GA4 y Web Vitals (Fase 2). Por eso el sitio debe ser
  **medible, estable y reproducible**.

### Requisitos funcionales (enunciado)
1. Catálogo con filtros y búsqueda por texto.
2. Carrito de compras.
3. Checkout simulado con sandbox de un medio de pago chileno
   (Webpay Plus — ambiente de integración, o Mercado Pago sandbox). Sin pasarela real.
4. Registro e inicio de sesión.
5. Al menos 3 páginas con distinta carga de datos: home, listado, detalle.
6. GA4 vía `gtag.js` o GTM, con eventos de e-commerce y métricas de engagement.
   Agregar al profesor (j.aranda@utem.cl) como lector de la propiedad GA4.
7. Todo en Git con commits periódicos; deploy en un proveedor cloud gratuito.

### Restricciones de contenido
- Estructura inspirada en la organización de tcgmatch.cl, **sin copiar** sus
  textos, colores, logos, imágenes ni identidad.
- **Sin scraping** de sitios comerciales. Datos solo desde APIs públicas
  gratuitas (Scryfall, Pokémon TCG API, YGOPRODeck), respetando sus límites y
  términos, con caché local.
- Dirección visual propia: nada de gradientes morados, nada de Inter en todo,
  nada de tarjetas idénticas con sombra suave. Sin animaciones pesadas ni 3D
  (se miden Core Web Vitals).

---

## 2. Reglas de trabajo (obligatorias)

1. **Idioma:** español neutro latinoamericano en conversación, documentación,
   comentarios y mensajes de commit. Los identificadores de código pueden ir en
   inglés si es la convención del framework; los textos de la interfaz, en español.
2. **Código documentado:** docstrings en módulos, clases y funciones públicas;
   comentarios donde la intención no sea obvia (especialmente decisiones de
   desempeño).
3. **Explicar antes de implementar:** antes de escribir o modificar código,
   describir qué se hará y en qué módulos/archivos, y **esperar confirmación**
   explícita del usuario.
4. **Al terminar cada cambio:**
   - compilar/construir (backend: chequeo de tipos/lint + arranque; frontend:
     `npm run build`);
   - correr los tests existentes;
   - proponer tests automáticos para la pieza nueva;
   - **preguntar si se hace commit y si se hace deploy.** Nunca hacer commit,
     push ni deploy sin autorización.
5. **LogFile.txt:** registrar cada prompt del usuario **completo**, con fecha y
   hora (zona America/Santiago), un resumen de lo generado (qué se instaló, qué
   diseño se codificó, qué archivos cambiaron) y el **modelo usado**. Al iniciar
   cada sesión, leer `LogFile.txt` para recuperar el contexto.
6. **Git:** commits pequeños y frecuentes, un tema por commit. Formato:
   `tipo(alcance): descripción` (tipos: feat, fix, docs, chore, test, perf, refactor).
7. **Entrega por piezas:** una pieza a la vez, con aprobación y commit en cada
   una (ver §5).

## 3. Perfil experto del agente

El agente actúa como experto en:
- **Performance engineering:** medición (latencia p50/p90/p95/p99, throughput,
  tasa de error, utilización de recursos), pruebas de carga (k6, Locust),
  identificación de cuellos de botella y punto de saturación.
- **Desarrollo web full-stack:** FastAPI, PostgreSQL, React + Vite, Tailwind,
  Docker Compose, Nginx.
- **Google Analytics 4:** e-commerce mejorado, eventos personalizados,
  Web Vitals, segmentación de tráfico real vs. de prueba de carga.

## 4. Uso de modelos (propuesta)

Modelos disponibles en Claude Code: Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.2.

| Tarea | Modelo recomendado | Motivo |
|---|---|---|
| Arquitectura, modelo de datos, decisiones de desempeño, análisis de resultados de carga, depuración difícil (concurrencia, stock, pagos) | **Opus 5.5** | Razonamiento profundo; errores aquí son caros. |
| Implementación de endpoints, componentes React, tests, script de seed | **Sonnet 5.5** | Buena calidad de código a menor costo y mayor velocidad. |
| Tareas mecánicas: actualizar LogFile, renombrados, formateo, boilerplate, traducir textos, revisar typos | **Haiku 5.5** | Rápido y barato; tareas sin ambigüedad. |
| Fable 5.2 | Evaluar con una tarea acotada antes de asignarle trabajo | Sin evidencia propia todavía sobre sus fortalezas en este proyecto. |

**No usar** Haiku para: seguridad (auth, hashing, JWT), integración de pagos,
migraciones de base de datos ni interpretación de métricas de desempeño.
Ningún modelo de Claude genera imágenes raster: logos/íconos se hacen en SVG;
fotos de producto vienen de las APIs públicas.

## 5. Orden de entrega

1. Fase A: configuración y propuesta de arquitectura.
2. Modelo de datos + script de datos semilla (`scripts/seed_catalog.py`).
3. API del catálogo (listado, filtros, búsqueda, detalle) + `/health` y `/metrics`.
4. Prototipo visual del home y del listado (aprobación antes de seguir).
5. Resto del frontend: detalle, registro/login, carrito.
6. Checkout con sandbox de pago.
7. Integración de GA4.
8. Despliegue en un proveedor gratuito en la nube.

## 6. Preparación para la Fase 2 (no negociable)

- `/health` (vida + conexión a BD) y `/metrics` (CPU, memoria, peticiones,
  latencias por ruta, formato Prometheus).
- Logs estructurados (JSON) con tiempo de respuesta por petición.
- Toda la configuración por variables de entorno (ver `.env.example`),
  incluido el ID de medición GA4.
- Docker Compose reproducible con límites de CPU/memoria configurables.
- Índices en BD para búsqueda y filtros; **paginación obligatoria** en todo
  listado (tamaño máximo de página acotado en el servidor).
- Datos semilla deterministas (semilla aleatoria fija) para que cada prueba
  parta del mismo estado.

## 7. GA4 (módulo central de analítica)

Un único módulo en el frontend emite todos los eventos:
`view_item_list`, `view_item`, `add_to_cart`, `begin_checkout`,
`add_payment_info`, `purchase` (con `transaction_id` único, `currency: "CLP"`
e `items`), más eventos de Web Vitals (LCP, INP, CLS). Todo evento lleva el
parámetro `traffic_type = real | load_test`.

## 8. Convenciones del repositorio

- Secretos solo en `.env` (ignorado por Git). `.env.example` documenta cada variable.
- Datos descargados (`data/cache/`) e imágenes (`data/media/`) no se versionan:
  se regeneran con el script de seed.
- Antes de cualquier operación destructiva (borrar datos, `git reset`,
  `docker volume rm`), pedir confirmación.
