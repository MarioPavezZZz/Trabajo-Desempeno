# Pruebas de carga — TCGMASTER (Fase 1.2)

Generadores de carga con **k6** (ejecutado en Docker: no hay que instalar nada).

## Ejecutar

Windows (PowerShell), desde la raíz del repositorio:

```powershell
.\loadtest\run.ps1 -Perfil humo                 # verificación rápida (1 sesión de cada tipo)
.\loadtest\run.ps1 -Perfil normal -Reiniciar    # carga sostenida partiendo de un estado limpio
.\loadtest\run.ps1 -Perfil pico -Rate 30        # pico con 30 sesiones/s en la meseta
.\loadtest\run.ps1 -Perfil estres -BaseUrl https://<sitio-desplegado> -Remoto
```

Linux / macOS: `REINICIAR=1 loadtest/run.sh normal` (mismas opciones como variables).

Mientras corre, el dashboard en vivo está en <http://localhost:5665>.

## Comportamientos (escenarios)

Cada sesión empieza sin cookies y hace pausas aleatorias entre acciones
(1–6 s, escalables con `-Think`). Las peticiones son las mismas que hace el
frontend en cada página, incluidas las imágenes (desactivable con `-SinImagenes`).

| Comportamiento | % | Recorrido |
|---|---|---|
| navegante | 45 | home → listado con filtros al azar → 1 a 3 productos → a veces página 2 |
| buscador | 25 | home → 1 o 2 búsquedas (incluye errores de tipeo) → abre un resultado |
| abandono | 15 | listado → producto → agrega 1–2 productos → ve el carrito → se va |
| comprador_invitado | 10 | home → listado → producto → agrega → carrito → checkout → pago simulado |
| comprador_cuenta | 5 | registro → listado → producto → agrega → checkout → cierra e inicia sesión → mis pedidos |

Todas las peticiones llevan `X-Traffic-Type: load_test`: la API usa el
simulador de pago (nunca Transbank) y marca pedidos y carritos como prueba.

## Perfiles

Modelo **abierto** (`ramping-arrival-rate`): llegan N sesiones nuevas por
unidad de tiempo aunque el servidor se demore, como en un sitio real; así se
observa el punto de saturación.

| Perfil | Carga | Duración | Uso |
|---|---|---|---|
| humo | 1 sesión de cada tipo | < 1 min | validar que todo funciona |
| baja | 1 sesión/s | 5 min (1 de ramp-up) | línea base |
| normal | 5 sesiones/s | 15 min (2 de ramp-up) | carga sostenida |
| pico | 1 → 20 sesiones/s en 30 s, 2 min, y vuelve | 5 min | peak |
| estres | 5 → 10 → 20 → 40 → 80 sesiones/s (2 min c/u) | hasta ~13 min | punto de quiebre (aborta con > 10 % de errores) |
| navegadores | 2 Chromium reales (`-Navegadores N`) | 5 min | eventos GA4 y Web Vitals bajo carga (correr junto a otro perfil) |

Parámetros: `-Rate` (sesiones/s de la meseta), `-Duration`, `-Ramp`,
`-MaxVus`, `-Think` (0 = sin pausas), `-SinImagenes`.

**Umbrales** (el reporte indica si se cumplen): errores < 1 % (estrés: aborta
sobre 10 %), p95 de navegación y carrito < 800 ms, p95 de checkout < 1,5 s,
checks > 98 %. Un 409 por falta de stock no cuenta como error.

## Resultados

`loadtest/results/<perfil>-<fecha>/` (no se versiona):

| Archivo | Contenido |
|---|---|
| report.html | Dashboard de k6: latencia, throughput y errores en el tiempo |
| resumen.txt / summary.json | avg, mediana, p90, p95, p99 y máx. por endpoint, grupo y comportamiento; compras aprobadas/rechazadas; sin stock |
| server-metrics.csv | Cada 5 s: CPU (% del límite), memoria, pool de BD, peticiones en curso, req/s, 5xx/s, latencia promedio, p95 y p99 del servidor |
| docker-stats.csv | CPU y memoria de cada contenedor (incluida PostgreSQL) — solo local |
| pg_stat_statements.csv | 25 consultas SQL con más tiempo total en la corrida — solo local |
| parametros.txt | Perfil y parámetros usados (metodología del informe) |

## Reiniciar el estado

`-Reiniciar` ejecuta `scripts/reset_load_test.py` antes de la corrida:
borra pedidos, carritos y usuarios de prueba, devuelve el stock reservado,
recarga stock y precios del seed y reinicia `pg_stat_statements`. Nunca toca
datos de tráfico real. Manual:

```bash
docker compose exec api python scripts/reset_load_test.py --estadisticas
```

## Contra el sitio desplegado

Usar `-Remoto` (no hay acceso local a Docker del servidor). Para registrar
métricas del servidor, abrir antes un túnel SSH y dejar el valor por defecto
de `-MetricsUrl`:

```bash
ssh -N -L 8000:127.0.0.1:8000 usuario@servidor
```

Las pruebas se lanzan desde un equipo distinto al servidor (si no, k6 compite
por la misma CPU y distorsiona los resultados).
