"""Tests del checkout: invitado y cuenta, Webpay (con Transbank falso), simulador,
reserva y liberación de stock, concurrencia, idempotencia y acceso a pedidos.

Ningún test llama a Transbank: Webpay usa `httpx.MockTransport` con un
servidor falso que imita la API REST v1.2.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models import Order, Product
from app.payments.mock import MockProvider
from app.payments.webpay import WebpayProvider

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

LOAD = {"X-Traffic-Type": "load_test"}  # usa el simulador
GUEST = {"contact_name": "Invitada Prueba", "contact_email": "invitada@example.com"}


class FakeTransbank:
    """Imita la API REST de Webpay Plus: crea y confirma transacciones en memoria."""

    def __init__(self):
        self.transactions: dict[str, dict] = {}
        self.commits: list[str] = []
        self.decline: set[str] = set()
        self.wrong_amount: set[str] = set()
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Tbk-Api-Key-Id"] == "597055555532"
        if self.down:
            return httpx.Response(500, text="servicio no disponible")
        if request.method == "POST":
            body = json.loads(request.content)
            token = f"tok-{uuid.uuid4().hex}"
            self.transactions[token] = body
            return httpx.Response(
                200,
                json={
                    "token": token,
                    "url": "https://webpay3gint.transbank.cl/webpayserver/initTransaction",
                },
            )
        token = request.url.path.rsplit("/", 1)[-1]
        self.commits.append(token)
        tx = self.transactions.get(token)
        if tx is None or tx.get("committed"):
            return httpx.Response(422, json={"error_message": "Invalid status"})
        tx["committed"] = True
        declined = token in self.decline
        return httpx.Response(
            200,
            json={
                "status": "FAILED" if declined else "AUTHORIZED",
                "response_code": -1 if declined else 0,
                "amount": tx["amount"] + (100 if token in self.wrong_amount else 0),
                "buy_order": tx["buy_order"],
                "authorization_code": None if declined else "1213",
                "card_detail": {"card_number": "6623"},
            },
        )


@pytest.fixture
async def fake_tbk(client):
    """Reemplaza los proveedores: Webpay contra el Transbank falso y simulador sin latencia."""
    from app.api.routes.checkout import get_providers
    from app.main import app

    fake = FakeTransbank()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    fast = get_settings().model_copy(
        update={"mock_payment_latency_ms": 0, "mock_approval_rate": 1.0}
    )
    providers = {"webpay": WebpayProvider(client=http), "mock": MockProvider(settings=fast)}
    app.dependency_overrides[get_providers] = lambda: providers
    yield fake
    app.dependency_overrides.pop(get_providers, None)
    await http.aclose()


@pytest.fixture
async def browser(client, fake_tbk):
    """Fábrica de clientes con cookies propias (cada uno es un navegador)."""
    from app.main import app

    opened = []

    async def make():
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        opened.append(c)
        return c

    yield make
    for c in opened:
        await c.aclose()


async def _product(c, min_stock=2, **params):
    data = (
        await c.get(
            "/api/products", params={"page_size": 60, "in_stock": "true", "sort": "name", **params}
        )
    ).json()
    return next(p for p in data["items"] if p["stock"] >= min_stock)


async def _stock(engine, product_id: int) -> int:
    async with engine.connect() as conn:
        return await conn.scalar(select(Product.stock).where(Product.id == product_id))


async def _set_stock(engine, product_id: int, stock: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(update(Product).where(Product.id == product_id).values(stock=stock))


async def _order(engine, tx: str) -> Order:
    async with engine.connect() as conn:
        return (await conn.execute(select(Order).where(Order.transaction_id == tx))).one()


def _location_parts(resp):
    loc = urlparse(resp.headers["location"])
    return loc.path, parse_qs(loc.query)


# =========================================================== invitado + simulador
async def test_invitado_compra_con_el_simulador(browser, loaded_engine):
    c = await browser()
    p = await _product(c, game="pokemon")
    before = await _stock(loaded_engine, p["id"])
    await c.post("/api/cart/items", json={"product_id": p["id"], "quantity": 2})

    resp = await c.post("/api/checkout", json=GUEST, headers=LOAD)
    assert resp.status_code == 201, resp.text
    start = resp.json()
    assert start["provider"] == "mock" and start["payment"]["method"] == "GET"
    assert start["total_clp"] == p["price_clp"] * 2
    assert await _stock(loaded_engine, p["id"]) == before - 2  # reservado

    done = await c.get(
        "/api/checkout/simulado/retorno",
        params={"token": start["payment"]["token"], "decision": "aprobar", "formato": "json"},
    )
    assert done.json()["status"] == "pagada"
    assert (await c.get("/api/cart")).json()["item_count"] == 0  # carrito convertido
    assert await _stock(loaded_engine, p["id"]) == before - 2  # el pago no descuenta de nuevo

    tx, key = start["transaction_id"], start["access_key"]
    order = await c.get(f"/api/orders/{tx}", params={"clave": key})
    assert order.status_code == 200
    body = order.json()
    assert body["contact_email"] == "invitada@example.com"
    assert body["payment"]["status"] == "autorizado" and body["items"][0]["quantity"] == 2
    assert (await _order(loaded_engine, tx)).traffic_type == "load_test"


async def test_pedido_de_invitado_requiere_la_clave(browser):
    c = await browser()
    p = await _product(c)
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (await c.post("/api/checkout", json=GUEST, headers=LOAD)).json()
    tx = start["transaction_id"]
    stranger = await browser()
    assert (await stranger.get(f"/api/orders/{tx}")).status_code == 404
    assert (
        await stranger.get(f"/api/orders/{tx}", params={"clave": "incorrecta"})
    ).status_code == 404
    assert (
        await stranger.get(f"/api/orders/{tx}", params={"clave": start["access_key"]})
    ).status_code == 200


async def test_invitado_sin_contacto_o_carrito_vacio(browser):
    c = await browser()
    assert (await c.post("/api/checkout", json=GUEST)).status_code == 400  # carrito vacío
    p = await _product(c)
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    assert (await c.post("/api/checkout", json={})).status_code == 422
    bad_email = {**GUEST, "contact_email": "no-es-correo"}
    assert (await c.post("/api/checkout", json=bad_email)).status_code == 422


async def test_envio_a_domicilio_exige_direccion_y_suma_tarifa(browser):
    c = await browser()
    p = await _product(c)
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    incomplete = {**GUEST, "shipping_method": "domicilio", "street": "Av. Siempre Viva 123"}
    assert (await c.post("/api/checkout", json=incomplete, headers=LOAD)).status_code == 422
    full = {**incomplete, "comuna": "Santiago", "region": "Metropolitana", "phone": "+56911111111"}
    start = (await c.post("/api/checkout", json=full, headers=LOAD)).json()
    assert start["total_clp"] == p["price_clp"] + get_settings().shipping_home_clp


async def test_pago_simulado_rechazado_devuelve_stock_y_conserva_carrito(browser, loaded_engine):
    c = await browser()
    p = await _product(c, game="magic")
    before = await _stock(loaded_engine, p["id"])
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (await c.post("/api/checkout", json=GUEST, headers=LOAD)).json()
    done = await c.get(
        "/api/checkout/simulado/retorno",
        params={"token": start["payment"]["token"], "decision": "rechazar", "formato": "json"},
    )
    assert done.json()["status"] == "rechazada"
    assert await _stock(loaded_engine, p["id"]) == before
    assert (await c.get("/api/cart")).json()["item_count"] == 1  # puede reintentar


# ================================================================= Webpay
async def test_webpay_aprobado_e_idempotente(browser, fake_tbk, loaded_engine):
    c = await browser()
    p = await _product(c, game="yugioh")
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (await c.post("/api/checkout", json=GUEST)).json()  # tráfico real -> Webpay
    assert start["provider"] == "webpay"
    assert start["payment"]["method"] == "POST" and start["payment"]["token_field"] == "token_ws"
    sent = fake_tbk.transactions[start["payment"]["token"]]
    assert sent["amount"] == start["total_clp"] and sent["buy_order"] == start["transaction_id"]
    assert len(sent["buy_order"]) <= 26
    assert sent["return_url"].endswith("/api/checkout/webpay/retorno")

    token = start["payment"]["token"]
    ret = await c.get("/api/checkout/webpay/retorno", params={"token_ws": token})
    assert ret.status_code == 303
    path, query = _location_parts(ret)
    assert path == f"/checkout/resultado/{start['transaction_id']}"
    assert query["clave"] == [start["access_key"]]
    assert (await _order(loaded_engine, start["transaction_id"])).status == "pagada"

    # Retorno repetido (recarga del navegador): no se confirma dos veces.
    again = await c.get("/api/checkout/webpay/retorno", params={"token_ws": token})
    assert again.status_code == 303
    assert fake_tbk.commits.count(token) == 1
    detail = (
        await c.get(f"/api/orders/{start['transaction_id']}", params={"clave": start["access_key"]})
    ).json()
    assert (
        detail["payment"]["authorization_code"] == "1213"
        and detail["payment"]["card_last4"] == "6623"
    )


async def test_webpay_rechazado_por_post_devuelve_stock(browser, fake_tbk, loaded_engine):
    c = await browser()
    p = await _product(c, game="pokemon", rarity="comun")
    before = await _stock(loaded_engine, p["id"])
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (await c.post("/api/checkout", json=GUEST)).json()
    fake_tbk.decline.add(start["payment"]["token"])
    ret = await c.post(
        "/api/checkout/webpay/retorno",
        content=f"token_ws={start['payment']['token']}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert ret.status_code == 303
    assert (await _order(loaded_engine, start["transaction_id"])).status == "rechazada"
    assert await _stock(loaded_engine, p["id"]) == before


@pytest.mark.parametrize("kind", ["anulado", "tiempo_agotado"])
async def test_webpay_anulado_o_tiempo_agotado(browser, loaded_engine, kind):
    c = await browser()
    p = await _product(c, game="magic", rarity="comun")
    before = await _stock(loaded_engine, p["id"])
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (await c.post("/api/checkout", json=GUEST)).json()
    params = (
        {"TBK_TOKEN": start["payment"]["token"], "TBK_ORDEN_COMPRA": start["transaction_id"]}
        if kind == "anulado"
        else {"TBK_ORDEN_COMPRA": start["transaction_id"], "TBK_ID_SESION": "x"}
    )
    ret = await c.get("/api/checkout/webpay/retorno", params=params)
    assert ret.status_code == 303
    assert (await _order(loaded_engine, start["transaction_id"])).status == "anulada"
    assert await _stock(loaded_engine, p["id"]) == before


async def test_monto_alterado_no_se_acepta(browser, fake_tbk, loaded_engine):
    c = await browser()
    p = await _product(c, game="yugioh", rarity="comun")
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (await c.post("/api/checkout", json=GUEST)).json()
    fake_tbk.wrong_amount.add(start["payment"]["token"])
    await c.get("/api/checkout/webpay/retorno", params={"token_ws": start["payment"]["token"]})
    assert (await _order(loaded_engine, start["transaction_id"])).status == "rechazada"


async def test_pasarela_caida_libera_la_reserva(browser, fake_tbk, loaded_engine):
    c = await browser()
    p = await _product(c, game="pokemon", rarity="infrecuente")
    before = await _stock(loaded_engine, p["id"])
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    fake_tbk.down = True
    resp = await c.post("/api/checkout", json=GUEST)
    assert resp.status_code == 502
    assert await _stock(loaded_engine, p["id"]) == before


async def test_token_desconocido_vuelve_al_carrito(browser):
    c = await browser()
    ret = await c.get("/api/checkout/webpay/retorno", params={"token_ws": "no-existe"})
    assert ret.status_code == 303 and ret.headers["location"].endswith("/carrito?pago=error")


# ============================================================ con cuenta
async def test_compra_con_cuenta_y_mis_pedidos(browser):
    c = await browser()
    email = f"compra-{uuid.uuid4().hex[:8]}@example.com"
    await c.post(
        "/api/auth/register",
        json={"email": email, "password": "clave-segura-1", "full_name": "Cliente Uno"},
    )
    p = await _product(c, game="magic", rarity="infrecuente")
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (
        await c.post("/api/checkout", json={}, headers=LOAD)
    ).json()  # sin contacto: usa la cuenta
    await c.get(
        "/api/checkout/simulado/retorno",
        params={"token": start["payment"]["token"], "decision": "aprobar", "formato": "json"},
    )
    detail = (await c.get(f"/api/orders/{start['transaction_id']}")).json()  # dueño: sin clave
    assert detail["contact_email"] == email and detail["status"] == "pagada"
    mine = (await c.get("/api/orders")).json()
    assert [o["transaction_id"] for o in mine] == [start["transaction_id"]]

    other = await browser()
    await other.post(
        "/api/auth/register",
        json={
            "email": f"otro-{uuid.uuid4().hex[:8]}@example.com",
            "password": "clave-segura-1",
            "full_name": "Otro",
        },
    )
    assert (await other.get(f"/api/orders/{start['transaction_id']}")).status_code == 404
    assert (await other.get("/api/orders")).json() == []
    assert (await (await browser()).get("/api/orders")).status_code == 401


# =========================================================== stock y concurrencia
async def test_dos_checkouts_por_la_ultima_unidad(browser, loaded_engine):
    a, b = await browser(), await browser()
    p = await _product(a, game="yugioh", rarity="infrecuente")
    original = await _stock(loaded_engine, p["id"])
    await _set_stock(loaded_engine, p["id"], 1)
    try:
        await a.post("/api/cart/items", json={"product_id": p["id"]})
        await b.post("/api/cart/items", json={"product_id": p["id"]})
        results = await asyncio.gather(
            a.post("/api/checkout", json=GUEST, headers=LOAD),
            b.post("/api/checkout", json=GUEST, headers=LOAD),
        )
        assert sorted(r.status_code for r in results) == [201, 409]
        assert await _stock(loaded_engine, p["id"]) == 0
    finally:
        await _set_stock(loaded_engine, p["id"], original)


async def test_reserva_vencida_devuelve_el_stock(browser, loaded_engine):
    c = await browser()
    p = await _product(c, game="pokemon", rarity="rara")
    before = await _stock(loaded_engine, p["id"])
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    start = (await c.post("/api/checkout", json=GUEST, headers=LOAD)).json()
    async with loaded_engine.begin() as conn:
        await conn.execute(
            update(Order)
            .where(Order.transaction_id == start["transaction_id"])
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    # Cualquier checkout posterior hace el barrido de reservas vencidas.
    other = await browser()
    await other.post(
        "/api/checkout", json=GUEST, headers=LOAD
    )  # 400 (carrito vacío) pero barre igual
    assert (await _order(loaded_engine, start["transaction_id"])).status == "anulada"
    assert await _stock(loaded_engine, p["id"]) == before
    # Volver de la pasarela después del vencimiento no confirma el pedido.
    late = await c.get(
        "/api/checkout/simulado/retorno",
        params={"token": start["payment"]["token"], "decision": "aprobar", "formato": "json"},
    )
    assert late.json()["status"] == "anulada"


async def test_reintento_anula_el_intento_anterior(browser, loaded_engine):
    c = await browser()
    p = await _product(c, game="magic", rarity="rara")
    before = await _stock(loaded_engine, p["id"])
    await c.post("/api/cart/items", json={"product_id": p["id"]})
    first = (await c.post("/api/checkout", json=GUEST, headers=LOAD)).json()
    second = (await c.post("/api/checkout", json=GUEST, headers=LOAD)).json()
    assert (await _order(loaded_engine, first["transaction_id"])).status == "anulada"
    assert (await _order(loaded_engine, second["transaction_id"])).status == "pendiente"
    assert await _stock(loaded_engine, p["id"]) == before - 1  # reservado una sola vez
