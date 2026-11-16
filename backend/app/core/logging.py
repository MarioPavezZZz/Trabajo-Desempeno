"""Logs estructurados con structlog.

En formato `json` cada evento es una línea JSON en stdout (lo que Docker
recoge). Así los logs de una prueba de carga se pueden filtrar y agregar
con herramientas simples (jq, pandas) para calcular percentiles por ruta.
"""

import logging
import sys

import orjson
import structlog

from app.core.config import Settings


def _orjson_dumps(obj: object, default: object = None) -> str:
    """Serializador rápido para el renderer JSON (structlog espera un str)."""
    return orjson.dumps(obj, default=default).decode()


def configure_logging(settings: Settings) -> None:
    """Configura structlog y la librería estándar `logging` con un único formato."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.log_format == "console"
        else structlog.processors.JSONRenderer(serializer=_orjson_dumps)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        # La caché ahorra trabajo por evento; en tests se apaga para poder capturar logs.
        cache_logger_on_first_use=settings.app_env != "test",
    )
    # Logs de librerías (uvicorn, sqlalchemy) a stderr en texto simple. El log de
    # acceso de uvicorn se apaga: lo reemplaza nuestro middleware (más completo).
    logging.basicConfig(
        level=level, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str = "tcgmaster") -> structlog.stdlib.BoundLogger:
    """Devuelve un logger de structlog."""
    return structlog.get_logger(name)
