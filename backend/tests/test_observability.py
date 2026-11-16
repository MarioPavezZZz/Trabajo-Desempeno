"""Tests de observabilidad: encabezados, métricas Prometheus y log por petición."""

import re

import pytest
from structlog.testing import capture_logs

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


async def test_encabezados_de_respuesta(client):
    resp = await client.get("/api/games", headers={"X-Request-ID": "prueba-123"})
    assert resp.headers["x-request-id"] == "prueba-123"
    assert re.fullmatch(r"app;dur=\d+\.\d", resp.headers["server-timing"])
    assert resp.headers["cache-control"] == "no-cache"  # API_CACHE_MAX_AGE=0 por defecto


async def test_request_id_se_genera_si_no_viene(client):
    resp = await client.get("/health")
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"])


async def test_metricas_agrupan_por_plantilla_de_ruta(client):
    slug = (await client.get("/api/products", params={"page_size": 1})).json()["items"][0]["slug"]
    await client.get(f"/api/products/{slug}")
    await client.get("/ruta-que-no-existe")
    body = (await client.get("/metrics")).text
    assert 'route="/api/products/{slug}"' in body
    assert slug not in body  # nunca la URL real (cardinalidad acotada)
    assert 'route="sin_ruta",status="404"' in body
    assert "http_request_duration_seconds_bucket" in body
    assert "http_requests_in_progress" in body


async def test_log_json_por_peticion(client):
    with capture_logs() as logs:
        await client.get(
            "/api/products", params={"game": "magic"}, headers={"X-Traffic-Type": "load_test"}
        )
    entry = next(e for e in logs if e.get("event") == "request")
    assert entry["route"] == "/api/products"
    assert entry["status"] == 200
    assert entry["traffic_type"] == "load_test"
    assert entry["query"] == "game=magic"
    assert isinstance(entry["duration_ms"], float)


async def test_traffic_type_desconocido_se_registra_como_real(client):
    with capture_logs() as logs:
        await client.get("/health", headers={"X-Traffic-Type": "otro"})
    assert next(e for e in logs if e.get("event") == "request")["traffic_type"] == "real"
