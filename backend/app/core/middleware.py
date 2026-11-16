"""Middleware de observabilidad: métricas, log por petición y encabezados.

Se implementa como middleware ASGI "puro" (no `BaseHTTPMiddleware`) porque
este último agrega una tarea y colas extra por petición, un sobrecosto que
se notaría justamente en las pruebas de carga.

Por cada petición:
- mide la duración y la registra en el histograma por plantilla de ruta
  (`/api/products/{slug}`, no la URL real, para no crear una serie por producto);
- escribe una línea de log JSON con método, ruta, estado, duración,
  request_id y traffic_type;
- agrega `X-Request-ID`, `Server-Timing` y, en GET del catálogo, `Cache-Control`.
"""

from __future__ import annotations

import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger
from app.core.metrics import DB_POOL_IN_USE, IN_PROGRESS, LATENCY, REQUESTS

log = get_logger("tcgmaster.http")

# Rutas que no se registran en el log (Prometheus las consulta cada pocos segundos).
_QUIET_PATHS = {"/metrics"}
# Respuestas con datos personales: nunca se guardan en cachés compartidas.
_PRIVATE_PREFIXES = ("/api/cart", "/api/auth", "/api/orders", "/api/checkout")
_PRIVATE_CACHE = b"private, no-store"
_VALID_TRAFFIC = {"real", "load_test"}


def _header(scope: Scope, name: bytes) -> str | None:
    """Lee un encabezado de la petición (los nombres llegan en minúsculas)."""
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


class ObservabilityMiddleware:
    """Mide y registra cada petición HTTP."""

    def __init__(self, app: ASGIApp, cache_max_age: int = 0, pool_status=None) -> None:
        self.app = app
        self.cache_control = (
            f"public, max-age={cache_max_age}".encode() if cache_max_age > 0 else b"no-cache"
        )
        # Función que devuelve las conexiones ocupadas del pool (inyectada para testear).
        self.pool_status = pool_status

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method = scope["method"]
        path = scope["path"]
        request_id = (_header(scope, b"x-request-id") or uuid.uuid4().hex)[:64]
        traffic = _header(scope, b"x-traffic-type")
        traffic_type = traffic if traffic in _VALID_TRAFFIC else "real"
        status_code = 500
        private = path.startswith(_PRIVATE_PREFIXES)
        cache_control = _PRIVATE_CACHE if private else self.cache_control

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                elapsed_ms = (time.perf_counter() - start) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                headers.append((b"server-timing", f"app;dur={elapsed_ms:.1f}".encode()))
                if private:
                    headers.append((b"cache-control", cache_control))
                elif method == "GET" and path.startswith("/api/") and status_code == 200:
                    headers.append((b"cache-control", cache_control))
                message["headers"] = headers
            await send(message)

        IN_PROGRESS.labels(method).inc()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            IN_PROGRESS.labels(method).dec()
            duration = time.perf_counter() - start
            # FastAPI deja la ruta resuelta en el scope; si no hubo coincidencia, es 404.
            route_obj = scope.get("route")
            route = getattr(route_obj, "path", None) or "sin_ruta"
            REQUESTS.labels(method, route, str(status_code)).inc()
            LATENCY.labels(method, route).observe(duration)
            if self.pool_status is not None:
                DB_POOL_IN_USE.set(self.pool_status())
            if path not in _QUIET_PATHS:
                log.info(
                    "request",
                    method=method,
                    route=route,
                    path=path,
                    query=scope.get("query_string", b"").decode("latin-1")[:300],
                    status=status_code,
                    duration_ms=round(duration * 1000, 2),
                    request_id=request_id,
                    traffic_type=traffic_type,
                )
