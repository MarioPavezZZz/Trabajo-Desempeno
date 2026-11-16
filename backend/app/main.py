"""Punto de entrada de la API de TCGMASTER.

Ejecución en contenedor: `gunicorn -c gunicorn.conf.py app.main:app`.
Ejecución local simple: `uvicorn app.main:app --reload`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.routes import auth, cart, catalog, checkout, health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import ObservabilityMiddleware
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Libera las conexiones del pool al apagar el worker."""
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Construye la aplicación con middlewares y rutas."""
    settings = get_settings()
    configure_logging(settings)
    docs = settings.api_docs_enabled
    app = FastAPI(
        title="TCGMASTER API",
        version="0.3.0",
        description="API del catálogo de TCGMASTER (INFB8091 — Desempeño de Sistemas).",
        default_response_class=ORJSONResponse,  # orjson: serialización más rápida
        docs_url="/api/docs" if docs else None,
        openapi_url="/api/openapi.json" if docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Server-Timing"],
    )
    # Se agrega al final para quedar como capa externa: mide todo, incluido CORS.
    app.add_middleware(
        ObservabilityMiddleware,
        cache_max_age=settings.api_cache_max_age,
        pool_status=engine.pool.checkedout,
    )
    app.include_router(health.router)
    app.include_router(catalog.router)
    app.include_router(auth.router)
    app.include_router(cart.router)
    app.include_router(checkout.router)
    return app


app = create_app()
