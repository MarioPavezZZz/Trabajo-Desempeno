"""Endpoints operativos: /health y /metrics."""

import asyncio
import time

from fastapi import APIRouter, Depends, Response
from fastapi.responses import ORJSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.metrics import render_metrics
from app.schemas.catalog import HealthOut

router = APIRouter(tags=["operación"])

DB_CHECK_TIMEOUT_S = 2.0


@router.get("/health", response_model=HealthOut)
async def health(session: AsyncSession = Depends(get_session)) -> ORJSONResponse:
    """Vida del servicio y conexión a PostgreSQL. 503 si la base no responde a tiempo."""
    start = time.perf_counter()
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), DB_CHECK_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - cualquier falla de BD significa "no saludable"
        return ORJSONResponse(
            {"status": "degradado", "db": "error", "db_latency_ms": None}, status_code=503
        )
    latency = round((time.perf_counter() - start) * 1000, 2)
    return ORJSONResponse({"status": "ok", "db": "ok", "db_latency_ms": latency})


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Métricas en formato Prometheus (solo accesible dentro de la red de Docker)."""
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
