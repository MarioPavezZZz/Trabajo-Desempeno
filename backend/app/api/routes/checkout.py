"""Endpoints del checkout, retorno de la pasarela y pedidos."""

import uuid
from functools import lru_cache
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    cart_cookie_id,
    current_user_id,
    get_session,
    require_user_id,
    traffic_type,
)
from app.core.config import get_settings
from app.models import Order
from app.payments.base import PaymentProvider
from app.payments.mock import MockProvider
from app.payments.webpay import WebpayProvider
from app.schemas.checkout import (
    CheckoutIn,
    CheckoutOptions,
    CheckoutStartOut,
    OrderOut,
    OrderSummary,
)
from app.services import checkout as svc

router = APIRouter(tags=["checkout"])


@lru_cache
def _default_providers() -> dict[str, PaymentProvider]:
    return {"webpay": WebpayProvider(), "mock": MockProvider()}


def get_providers() -> dict[str, PaymentProvider]:
    """Proveedores disponibles (los tests reemplazan esta dependencia)."""
    return _default_providers()


def choose_provider(providers: dict[str, PaymentProvider], traffic: str) -> PaymentProvider:
    """Proveedor para este checkout: el simulador si es carga sintética (nunca contra Transbank)."""
    settings = get_settings()
    if traffic == "load_test" and settings.load_test_use_mock:
        return providers["mock"]
    return providers[settings.payment_provider]


def _result_url(order: Order) -> str:
    base = get_settings().public_base_url
    return f"{base}/checkout/resultado/{order.transaction_id}?clave={quote(order.access_key)}"


def _failure_url() -> str:
    return f"{get_settings().public_base_url}/carrito?pago=error"


@router.get("/api/checkout/options", response_model=CheckoutOptions)
async def checkout_options(
    traffic: str = Depends(traffic_type),
    providers: dict[str, PaymentProvider] = Depends(get_providers),
):
    """Proveedor de pago activo, tarifa de envío y minutos de reserva."""
    settings = get_settings()
    return {
        "provider": choose_provider(providers, traffic).name,
        "shipping_home_clp": settings.shipping_home_clp,
        "reservation_minutes": settings.reservation_minutes,
    }


@router.post("/api/checkout", response_model=CheckoutStartOut, status_code=201)
async def start_checkout(
    data: CheckoutIn,
    user_id: int | None = Depends(current_user_id),
    cart_id: uuid.UUID | None = Depends(cart_cookie_id),
    traffic: str = Depends(traffic_type),
    providers: dict[str, PaymentProvider] = Depends(get_providers),
    session: AsyncSession = Depends(get_session),
):
    """Crea el pedido reservando stock e inicia el pago. Funciona con cuenta o como invitado."""
    return await svc.start_checkout(
        session,
        user_id=user_id,
        cart_cookie=cart_id,
        data=data,
        traffic_type=traffic,
        provider=choose_provider(providers, traffic),
    )


@router.api_route("/api/checkout/webpay/retorno", methods=["GET", "POST"], include_in_schema=False)
async def webpay_return(
    request: Request,
    providers: dict[str, PaymentProvider] = Depends(get_providers),
    session: AsyncSession = Depends(get_session),
):
    """Retorno desde Transbank (GET o POST). Confirma o anula y redirige al resultado.

    - `token_ws` solo: pago terminado -> confirmar (commit).
    - `TBK_TOKEN`: la persona anuló el pago en Transbank.
    - solo `TBK_ORDEN_COMPRA`: se agotó el tiempo en el formulario de pago.
    """
    params = dict(request.query_params)
    if request.method == "POST":
        # Formulario urlencoded leído a mano (evita depender de python-multipart).
        body = parse_qs((await request.body()).decode("utf-8", "replace"))
        params.update({k: v[0] for k, v in body.items() if v})

    token_ws, tbk_token = params.get("token_ws"), params.get("TBK_TOKEN")
    if token_ws and not tbk_token:
        order = await svc.confirm_payment(session, providers["webpay"], token_ws)
    else:
        order = await svc.abort_payment(session, tbk_token, params.get("TBK_ORDEN_COMPRA"))
    url = _result_url(order) if order else _failure_url()
    return RedirectResponse(url, status_code=303)


@router.get("/api/checkout/simulado/retorno", include_in_schema=False)
async def mock_return(
    token: str = Query(min_length=1, max_length=128),
    decision: str = Query("auto", pattern="^(aprobar|rechazar|auto)$"),
    formato: str = Query("redirect", pattern="^(redirect|json)$"),
    providers: dict[str, PaymentProvider] = Depends(get_providers),
    session: AsyncSession = Depends(get_session),
):
    """Retorno del pago simulado. Con `formato=json` responde el pedido (útil para k6)."""
    order = await svc.confirm_payment(session, providers["mock"], token, decision)
    if order is None:
        if formato == "json":
            raise HTTPException(status_code=404, detail="Pago no encontrado")
        return RedirectResponse(_failure_url(), status_code=303)
    if formato == "json":
        return {
            "transaction_id": order.transaction_id,
            "status": order.status,
            "total_clp": order.total_clp,
        }
    return RedirectResponse(_result_url(order), status_code=303)


@router.get("/api/orders", response_model=list[OrderSummary], tags=["pedidos"])
async def my_orders(
    user_id: int = Depends(require_user_id), session: AsyncSession = Depends(get_session)
):
    """Últimos pedidos de la cuenta conectada."""
    return await svc.list_orders(session, user_id)


@router.get("/api/orders/{transaction_id}", response_model=OrderOut, tags=["pedidos"])
async def order_detail(
    transaction_id: str,
    clave: str | None = Query(None, max_length=64),
    user_id: int | None = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Detalle de un pedido: visible para su dueño o con la clave del enlace (invitados)."""
    order = await svc.get_order(session, transaction_id, user_id, clave)
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order
