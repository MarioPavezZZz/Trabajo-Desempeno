"""Tests de registro, inicio y cierre de sesión."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_session_token, read_session_token

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


def _email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
async def fresh_client(client):
    """Cliente con cookies propias (sesión aislada por test), sobre la misma app y base.

    Depende de `client` para que la app ya apunte a la base temporal.
    """
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _register(c, email=None, password="clave-segura-1", name="Ana Pérez"):
    return await c.post(
        "/api/auth/register",
        json={"email": email or _email(), "password": password, "full_name": name},
    )


async def test_registro_inicia_sesion(fresh_client):
    email = _email()
    resp = await _register(fresh_client, email=email.upper())
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email  # se guarda en minúsculas
    assert "password" not in str(body) and "hash" not in str(body)
    cookie = resp.headers["set-cookie"]
    assert "tcg_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    me = await fresh_client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == email
    assert me.headers["cache-control"] == "private, no-store"


async def test_registro_duplicado_es_409(fresh_client):
    email = _email()
    assert (await _register(fresh_client, email=email)).status_code == 201
    resp = await _register(fresh_client, email=email.upper())
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "no-es-correo", "password": "clave-segura-1", "full_name": "Ana"},
        {"email": "a@example.com", "password": "corta", "full_name": "Ana"},
        {"email": "a@example.com", "password": "clave-segura-1", "full_name": " "},
        {"email": "a@example.com", "password": "x" * 73, "full_name": "Ana"},
    ],
)
async def test_registro_invalido_es_422(fresh_client, payload):
    assert (await fresh_client.post("/api/auth/register", json=payload)).status_code == 422


async def test_login_correcto_e_incorrecto(fresh_client):
    email = _email()
    await _register(fresh_client, email=email)
    await fresh_client.post("/api/auth/logout")

    bad = await fresh_client.post(
        "/api/auth/login", json={"email": email, "password": "otra-clave"}
    )
    unknown = await fresh_client.post(
        "/api/auth/login", json={"email": _email(), "password": "clave-segura-1"}
    )
    # Mismo código y mismo mensaje: no se revela si el correo existe.
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()

    ok = await fresh_client.post(
        "/api/auth/login", json={"email": email, "password": "clave-segura-1"}
    )
    assert ok.status_code == 200
    assert (await fresh_client.get("/api/auth/me")).status_code == 200


async def test_logout_cierra_la_sesion(fresh_client):
    await _register(fresh_client)
    resp = await fresh_client.post("/api/auth/logout")
    assert resp.status_code == 204
    me = await fresh_client.get("/api/auth/me")
    assert me.status_code == 200 and me.json() is None


async def test_me_sin_sesion_o_con_token_falso_responde_null_sin_error(fresh_client):
    """Sin sesión no es un error: 200 con null (un 401 inflaría la tasa de 4xx bajo carga)."""
    me = await fresh_client.get("/api/auth/me")
    assert me.status_code == 200 and me.json() is None
    fresh_client.cookies.set("tcg_session", "no-es-un-jwt")
    me = await fresh_client.get("/api/auth/me")
    assert me.status_code == 200 and me.json() is None


async def test_rutas_protegidas_siguen_exigiendo_sesion(fresh_client):
    assert (await fresh_client.get("/api/orders")).status_code == 401


async def test_token_firmado_y_verificable():
    token = create_session_token(42)
    assert read_session_token(token) == 42
    assert read_session_token(token[:-2] + "xx") is None  # firma alterada
    assert read_session_token(None) is None
