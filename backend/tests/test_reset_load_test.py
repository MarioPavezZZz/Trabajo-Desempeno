"""Tests del origen de los carritos y del reinicio entre corridas de carga."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models import Cart, Order, Product, User
from scripts.reset_load_test import reset_load_test

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

LOAD = {"X-Traffic-Type": "load_test"}
GUEST = {"contact_name": "Usuario k6", "contact_email": "invitado-k6@example.com"}


@pytest.fixture
async def browser(client):
    from app.main import app

    opened = []

    async def make():
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        opened.append(c)
        return c

    yield make
    for c in opened:
        await c.aclose()


async def _in_stock(c, game):
    data = (
        await c.get("/api/products", params={"page_size": 60, "in_stock": "true", "game": game})
    ).json()
    return next(p for p in data["items"] if p["stock"] >= 2)


async def _count(engine, stmt):
    async with engine.connect() as conn:
        return await conn.scalar(stmt)


async def test_carrito_guarda_su_origen(browser, loaded_engine):
    real, k6 = await browser(), await browser()
    p = await _in_stock(real, "magic")
    await real.post("/api/cart/items", json={"product_id": p["id"]})
    await k6.post("/api/cart/items", json={"product_id": p["id"]}, headers=LOAD)
    real_id = real.cookies.get("tcg_cart")
    k6_id = k6.cookies.get("tcg_cart")
    async with loaded_engine.connect() as conn:
        rows = dict(
            (
                await conn.execute(
                    select(Cart.id, Cart.traffic_type).where(
                        Cart.id.in_([uuid.UUID(real_id), uuid.UUID(k6_id)])
                    )
                )
            ).all()
        )
    assert rows[uuid.UUID(real_id)] == "real"
    assert rows[uuid.UUID(k6_id)] == "load_test"


async def test_reinicio_borra_solo_lo_de_prueba_y_devuelve_stock(browser, loaded_engine):
    # Tráfico real: un carrito y un usuario que deben sobrevivir.
    real = await browser()
    p_real = await _in_stock(real, "pokemon")
    await real.post(
        "/api/auth/register",
        json={
            "email": f"real-{uuid.uuid4().hex[:6]}@example.com",
            "password": "clave-segura-1",
            "full_name": "Real",
        },
    )
    await real.post("/api/cart/items", json={"product_id": p_real["id"]})

    # Tráfico de carga: pedido pendiente (stock reservado) y usuario de prueba con carrito.
    k6 = await browser()
    p = await _in_stock(k6, "yugioh")
    async with loaded_engine.connect() as conn:
        stock_before = await conn.scalar(select(Product.stock).where(Product.id == p["id"]))
    await k6.post("/api/cart/items", json={"product_id": p["id"], "quantity": 2}, headers=LOAD)
    start = await k6.post("/api/checkout", json=GUEST, headers=LOAD)
    assert start.status_code == 201
    async with loaded_engine.connect() as conn:
        assert (
            await conn.scalar(select(Product.stock).where(Product.id == p["id"]))
            == stock_before - 2
        )

    k6_user = await browser()
    email = f"carga-k6-{uuid.uuid4().hex[:6]}@example.com"
    await k6_user.post(
        "/api/auth/register",
        json={"email": email, "password": "clave-segura-1", "full_name": "k6"},
        headers=LOAD,
    )
    await k6_user.post("/api/cart/items", json={"product_id": p_real["id"]}, headers=LOAD)

    real_users = await _count(
        loaded_engine, select(func.count()).select_from(User).where(~User.email.like("carga-k6-%"))
    )
    real_carts = await _count(
        loaded_engine, select(func.count()).select_from(Cart).where(Cart.traffic_type == "real")
    )

    result = await reset_load_test(loaded_engine)

    assert result["pedidos_borrados"] >= 1 and result["usuarios_borrados"] >= 1
    assert result["pedidos_de_prueba_restantes"] == 0
    async with loaded_engine.connect() as conn:
        assert await conn.scalar(select(Product.stock).where(Product.id == p["id"])) == stock_before
        assert (
            await conn.scalar(
                select(func.count()).select_from(Order).where(Order.traffic_type == "load_test")
            )
            == 0
        )
        assert (
            await conn.scalar(
                select(func.count()).select_from(Cart).where(Cart.traffic_type == "load_test")
            )
            == 0
        )
        assert (
            await conn.scalar(select(func.count()).select_from(User).where(User.email == email))
            == 0
        )
    # Lo real queda intacto.
    assert (
        await _count(
            loaded_engine,
            select(func.count()).select_from(User).where(~User.email.like("carga-k6-%")),
        )
        == real_users
    )
    assert (
        await _count(
            loaded_engine, select(func.count()).select_from(Cart).where(Cart.traffic_type == "real")
        )
        == real_carts
    )
    assert (await real.get("/api/cart")).json()["item_count"] == 1


async def test_reinicio_sin_datos_de_prueba_no_falla(loaded_engine):
    await reset_load_test(loaded_engine)
    result = await reset_load_test(loaded_engine)
    assert result["pedidos_borrados"] == 0 and result["usuarios_borrados"] == 0
