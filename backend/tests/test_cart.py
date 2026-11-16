"""Tests del carrito: visitantes, usuarios, stock, propiedad de líneas y fusión al iniciar sesión.

Cada test usa clientes con cookies propias (cada uno simula un navegador).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models import Cart

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
async def new_client(client):
    """Fábrica de clientes con cookies independientes (cada uno es un "navegador")."""
    from app.main import app

    opened = []

    async def make():
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        opened.append(c)
        return c

    yield make
    for c in opened:
        await c.aclose()


async def _product(client, min_stock=3, **params):
    """Un producto con al menos `min_stock` unidades."""
    data = (
        await client.get("/api/products", params={"page_size": 60, "in_stock": "true", **params})
    ).json()
    return next(p for p in data["items"] if p["stock"] >= min_stock)


async def _register(c):
    email = f"cart-{uuid.uuid4().hex[:10]}@example.com"
    resp = await c.post(
        "/api/auth/register",
        json={"email": email, "password": "clave-segura-1", "full_name": "Test"},
    )
    assert resp.status_code == 201
    return email


async def test_leer_carrito_no_crea_filas(new_client, loaded_engine):
    c = await new_client()
    async with loaded_engine.connect() as conn:
        before = await conn.scalar(select(func.count()).select_from(Cart))
    resp = await c.get("/api/cart")
    assert resp.json() == {"items": [], "item_count": 0, "subtotal_clp": 0, "warnings": []}
    assert "set-cookie" not in resp.headers
    async with loaded_engine.connect() as conn:
        assert await conn.scalar(select(func.count()).select_from(Cart)) == before


async def test_visitante_agrega_y_suma(new_client):
    c = await new_client()
    p = await _product(c)
    first = await c.post("/api/cart/items", json={"product_id": p["id"], "quantity": 1})
    assert first.status_code == 201
    assert "tcg_cart=" in first.headers["set-cookie"]
    second = (await c.post("/api/cart/items", json={"product_id": p["id"], "quantity": 2})).json()
    assert len(second["items"]) == 1
    assert second["item_count"] == 3
    assert second["subtotal_clp"] == p["price_clp"] * 3
    # El carrito persiste entre peticiones gracias a la cookie.
    assert (await c.get("/api/cart")).json()["item_count"] == 3


async def test_no_supera_el_stock(new_client):
    c = await new_client()
    p = await _product(c, min_stock=1)
    resp = await c.post("/api/cart/items", json={"product_id": p["id"], "quantity": p["stock"] + 1})
    assert resp.status_code == 409
    assert resp.json()["detail"]["available"] == p["stock"]
    ok = await c.post("/api/cart/items", json={"product_id": p["id"], "quantity": p["stock"]})
    assert ok.status_code == 201
    again = await c.post("/api/cart/items", json={"product_id": p["id"], "quantity": 1})
    assert again.status_code == 409 and again.json()["detail"]["available"] == 0


async def test_producto_agotado_o_inexistente(new_client):
    c = await new_client()
    sold_out = next(
        p
        for page in [
            (await c.get("/api/products", params={"page_size": 60, "sort": "name"})).json()
        ]
        for p in page["items"]
        if p["stock"] == 0
    )
    assert (await c.post("/api/cart/items", json={"product_id": sold_out["id"]})).status_code == 409
    assert (await c.post("/api/cart/items", json={"product_id": 999999})).status_code == 404


async def test_cambiar_cantidad_y_quitar(new_client):
    c = await new_client()
    p = await _product(c)
    cart = (await c.post("/api/cart/items", json={"product_id": p["id"]})).json()
    item_id = cart["items"][0]["id"]
    updated = await c.patch(f"/api/cart/items/{item_id}", json={"quantity": 2})
    assert updated.json()["item_count"] == 2
    too_many = await c.patch(f"/api/cart/items/{item_id}", json={"quantity": p["stock"] + 1})
    assert too_many.status_code == 409
    assert (await c.patch(f"/api/cart/items/{item_id}", json={"quantity": 0})).status_code == 422
    removed = await c.delete(f"/api/cart/items/{item_id}")
    assert removed.json()["items"] == []


async def test_no_se_puede_tocar_el_carrito_de_otro(new_client):
    owner, intruder = await new_client(), await new_client()
    p = await _product(owner)
    item_id = (await owner.post("/api/cart/items", json={"product_id": p["id"]})).json()["items"][
        0
    ]["id"]
    # El intruso con su propio carrito...
    await intruder.post("/api/cart/items", json={"product_id": p["id"]})
    assert (
        await intruder.patch(f"/api/cart/items/{item_id}", json={"quantity": 2})
    ).status_code == 404
    assert (await intruder.delete(f"/api/cart/items/{item_id}")).status_code == 404
    # ...y sin carrito.
    stranger = await new_client()
    assert (await stranger.delete(f"/api/cart/items/{item_id}")).status_code == 404
    assert (await owner.get("/api/cart")).json()["item_count"] == 1


async def test_carrito_anonimo_pasa_a_la_cuenta_al_registrarse(new_client):
    c = await new_client()
    p = await _product(c)
    await c.post("/api/cart/items", json={"product_id": p["id"], "quantity": 2})
    await _register(c)
    cart = (await c.get("/api/cart")).json()
    assert cart["item_count"] == 2


async def test_fusion_al_iniciar_sesion_suma_sin_superar_stock(new_client):
    browser_a = await new_client()
    email = await _register(browser_a)
    p = await _product(browser_a, min_stock=3)
    other = await _product(browser_a, min_stock=1, game="magic")
    await browser_a.post(
        "/api/cart/items", json={"product_id": p["id"], "quantity": p["stock"] - 1}
    )

    # Otro navegador, sin sesión, arma un carrito y luego inicia sesión en la misma cuenta.
    browser_b = await new_client()
    await browser_b.post("/api/cart/items", json={"product_id": p["id"], "quantity": 2})
    await browser_b.post("/api/cart/items", json={"product_id": other["id"], "quantity": 1})
    resp = await browser_b.post(
        "/api/auth/login", json={"email": email, "password": "clave-segura-1"}
    )
    assert resp.status_code == 200

    cart = (await browser_b.get("/api/cart")).json()
    by_id = {i["product"]["id"]: i["quantity"] for i in cart["items"]}
    assert by_id[p["id"]] == p["stock"]  # (stock - 1) + 2, recortado al stock
    assert by_id[other["id"]] == 1
    # Ambos navegadores ven el mismo carrito de la cuenta.
    assert (await browser_a.get("/api/cart")).json()["item_count"] == cart["item_count"]


async def test_cerrar_sesion_no_deja_el_carrito_visible(new_client):
    c = await new_client()
    await _register(c)
    p = await _product(c)
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    await c.post("/api/auth/logout")
    assert (await c.get("/api/cart")).json()["item_count"] == 0


async def test_aviso_de_cambio_de_precio(new_client, loaded_engine):
    from sqlalchemy import update

    from app.models import Product

    c = await new_client()
    p = await _product(c, game="yugioh")
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    async with loaded_engine.begin() as conn:
        await conn.execute(
            update(Product).where(Product.id == p["id"]).values(price_clp=p["price_clp"] + 1000)
        )
    try:
        cart = (await c.get("/api/cart")).json()
        assert cart["subtotal_clp"] == p["price_clp"] + 1000
        assert any("cambió" in w for w in cart["warnings"])
    finally:
        async with loaded_engine.begin() as conn:
            await conn.execute(
                update(Product).where(Product.id == p["id"]).values(price_clp=p["price_clp"])
            )
