"""Endpoints del carrito."""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import cart_cookie_id, current_user_id, get_session, traffic_type
from app.core.config import get_settings
from app.core.security import set_cookie
from app.schemas.account import AddItemIn, CartOut, UpdateItemIn
from app.services import cart as carts
from app.services.reference import get_reference

router = APIRouter(prefix="/api/cart", tags=["carrito"])


@router.get("", response_model=CartOut)
async def get_cart(
    user_id: int | None = Depends(current_user_id),
    cart_id: uuid.UUID | None = Depends(cart_cookie_id),
    session: AsyncSession = Depends(get_session),
):
    """Carrito actual (vacío si todavía no existe; leer nunca crea un carrito)."""
    cart = await carts.find_cart(session, user_id, cart_id)
    return await carts.cart_view(session, await get_reference(session), cart)


@router.post("/items", response_model=CartOut, status_code=201)
async def add_item(
    data: AddItemIn,
    response: Response,
    user_id: int | None = Depends(current_user_id),
    cart_id: uuid.UUID | None = Depends(cart_cookie_id),
    traffic: str = Depends(traffic_type),
    session: AsyncSession = Depends(get_session),
):
    """Agrega un producto. 409 si no hay stock suficiente; 404 si el producto no existe."""
    cart, created = await carts.get_or_create_cart(session, user_id, cart_id, traffic)
    await carts.add_item(session, cart, data.product_id, data.quantity)
    await session.commit()
    if created and user_id is None:
        settings = get_settings()
        set_cookie(response, settings.cart_cookie, str(cart.id), settings.cart_cookie_days * 86400)
    return await carts.cart_view(session, await get_reference(session), cart)


@router.patch("/items/{item_id}", response_model=CartOut)
async def update_item(
    item_id: int,
    data: UpdateItemIn,
    user_id: int | None = Depends(current_user_id),
    cart_id: uuid.UUID | None = Depends(cart_cookie_id),
    session: AsyncSession = Depends(get_session),
):
    """Cambia la cantidad de una línea del carrito propio."""
    cart = await carts.find_cart(session, user_id, cart_id)
    await carts.update_item(session, cart, item_id, data.quantity)
    await session.commit()
    return await carts.cart_view(session, await get_reference(session), cart)


@router.delete("/items/{item_id}", response_model=CartOut)
async def remove_item(
    item_id: int,
    user_id: int | None = Depends(current_user_id),
    cart_id: uuid.UUID | None = Depends(cart_cookie_id),
    session: AsyncSession = Depends(get_session),
):
    """Quita una línea del carrito propio."""
    cart = await carts.find_cart(session, user_id, cart_id)
    await carts.remove_item(session, cart, item_id)
    await session.commit()
    return await carts.cart_view(session, await get_reference(session), cart)
