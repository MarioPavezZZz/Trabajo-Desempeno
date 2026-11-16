"""Carrito de compras guardado en la base.

Reglas:
- Un usuario autenticado tiene a lo más un carrito `activo`.
- Un visitante anónimo se identifica con la cookie `tcg_cart` (UUID). Solo se
  acepta si ese carrito sigue activo y no pertenece a una cuenta.
- Leer el carrito NUNCA crea filas: solo agregar un producto crea el carrito.
  Así la navegación simple (y las pruebas de carga de solo lectura) no
  generan escrituras en la base.
- La cantidad de una línea nunca supera el stock del producto (409 si se pide más).
- El carrito muestra el precio vigente; si cambió desde que se agregó, avisa.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cart, CartItem, Product
from app.services.catalog import SUMMARY_COLUMNS, summary_dict
from app.services.reference import Reference


def _stock_error(name: str, available: int) -> HTTPException:
    if available == 0:
        message = f"{name} está agotado"
    elif available == 1:
        message = f"Solo queda 1 unidad de {name}"
    else:
        message = f"Solo quedan {available} unidades de {name}"
    return HTTPException(status_code=409, detail={"message": message, "available": available})


async def find_cart(
    session: AsyncSession, user_id: int | None, cookie_id: uuid.UUID | None
) -> Cart | None:
    """Carrito activo del usuario, o el anónimo de la cookie. No crea nada."""
    if user_id is not None:
        stmt = select(Cart).where(Cart.user_id == user_id, Cart.status == "activo")
    elif cookie_id is not None:
        stmt = select(Cart).where(
            Cart.id == cookie_id, Cart.status == "activo", Cart.user_id.is_(None)
        )
    else:
        return None
    return (await session.execute(stmt.order_by(Cart.created_at.desc()).limit(1))).scalar()


async def get_or_create_cart(
    session: AsyncSession,
    user_id: int | None,
    cookie_id: uuid.UUID | None,
    traffic_type: str = "real",
) -> tuple[Cart, bool]:
    """Carrito existente o uno nuevo (marcado con su origen). Retorna (carrito, creado_ahora)."""
    cart = await find_cart(session, user_id, cookie_id)
    if cart is not None:
        return cart, False
    cart = Cart(id=uuid.uuid4(), user_id=user_id, status="activo", traffic_type=traffic_type)
    session.add(cart)
    await session.flush()
    return cart, True


async def _product_for_cart(session: AsyncSession, product_id: int) -> Product:
    product = await session.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


async def add_item(session: AsyncSession, cart: Cart, product_id: int, quantity: int) -> None:
    """Agrega unidades de un producto (suma si ya estaba), sin superar el stock."""
    product = await _product_for_cart(session, product_id)
    current = (
        await session.scalar(
            select(CartItem.quantity).where(
                CartItem.cart_id == cart.id, CartItem.product_id == product_id
            )
        )
        or 0
    )
    if current + quantity > product.stock:
        raise _stock_error(product.name, max(product.stock - current, 0))
    # Inserción o suma en una sola sentencia (clave única cart_id + product_id).
    stmt = insert(CartItem).values(
        cart_id=cart.id, product_id=product_id, quantity=quantity, unit_price_clp=product.price_clp
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["cart_id", "product_id"],
        set_={
            "quantity": CartItem.quantity + stmt.excluded.quantity,
            "unit_price_clp": stmt.excluded.unit_price_clp,
        },
    )
    await session.execute(stmt)
    await _touch(session, cart)


async def _owned_item(session: AsyncSession, cart: Cart | None, item_id: int) -> CartItem:
    """Línea del carrito indicado; 404 si no existe o es de otro carrito."""
    item = await session.get(CartItem, item_id)
    if cart is None or item is None or item.cart_id != cart.id:
        raise HTTPException(status_code=404, detail="Esa línea no está en tu carrito")
    return item


async def update_item(
    session: AsyncSession, cart: Cart | None, item_id: int, quantity: int
) -> None:
    """Cambia la cantidad de una línea, sin superar el stock."""
    item = await _owned_item(session, cart, item_id)
    product = await _product_for_cart(session, item.product_id)
    if quantity > product.stock:
        raise _stock_error(product.name, product.stock)
    item.quantity = quantity
    await _touch(session, cart)  # type: ignore[arg-type]


async def remove_item(session: AsyncSession, cart: Cart | None, item_id: int) -> None:
    """Quita una línea del carrito."""
    item = await _owned_item(session, cart, item_id)
    await session.delete(item)
    await _touch(session, cart)  # type: ignore[arg-type]


async def _touch(session: AsyncSession, cart: Cart) -> None:
    """Actualiza la fecha de modificación (sirve para detectar carritos abandonados)."""
    await session.execute(update(Cart).where(Cart.id == cart.id).values(updated_at=func.now()))


async def merge_anonymous_cart(
    session: AsyncSession, user_id: int, cookie_id: uuid.UUID | None
) -> None:
    """Al iniciar sesión, pasa el carrito anónimo de la cookie a la cuenta.

    Si la cuenta no tenía carrito, el anónimo pasa a ser suyo. Si tenía, se suman
    las cantidades (sin superar el stock) y el anónimo se elimina.
    """
    if cookie_id is None:
        return
    anon = await find_cart(session, None, cookie_id)
    if anon is None:
        return
    own = await find_cart(session, user_id, None)
    if own is None:
        anon.user_id = user_id
        return
    rows = (
        await session.execute(
            select(CartItem.product_id, CartItem.quantity, Product.stock, Product.price_clp)
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.cart_id == anon.id, Product.is_active.is_(True))
        )
    ).all()
    for product_id, quantity, stock, price in rows:
        current = (
            await session.scalar(
                select(CartItem.quantity).where(
                    CartItem.cart_id == own.id, CartItem.product_id == product_id
                )
            )
            or 0
        )
        merged = min(current + quantity, stock)
        if merged <= 0:
            continue
        stmt = insert(CartItem).values(
            cart_id=own.id, product_id=product_id, quantity=merged, unit_price_clp=price
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["cart_id", "product_id"], set_={"quantity": merged}
        )
        await session.execute(stmt)
    await session.execute(delete(Cart).where(Cart.id == anon.id))
    await _touch(session, own)


def _money(amount: int) -> str:
    return "$" + f"{amount:,}".replace(",", ".")


async def cart_view(session: AsyncSession, ref: Reference, cart: Cart | None) -> dict:
    """Carrito con productos, totales al precio vigente y avisos."""
    if cart is None:
        return {"items": [], "item_count": 0, "subtotal_clp": 0, "warnings": []}
    rows = (
        await session.execute(
            select(
                CartItem.id.label("item_id"),
                CartItem.quantity,
                CartItem.unit_price_clp.label("added_price"),
                Product.is_active,
                *SUMMARY_COLUMNS,
            )
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.cart_id == cart.id)
            .order_by(CartItem.added_at, CartItem.id)
        )
    ).all()
    items, warnings = [], []
    for r in rows:
        if not r.is_active:
            warnings.append(f"{r.name} ya no está disponible; quítalo para continuar")
        elif r.quantity > r.stock:
            warnings.append(
                f"{r.name}: pediste {r.quantity} y "
                + ("está agotado" if r.stock == 0 else f"solo quedan {r.stock}")
            )
        if r.added_price != r.price_clp:
            warnings.append(
                f"El precio de {r.name} cambió de {_money(r.added_price)} a {_money(r.price_clp)}"
            )
        items.append(
            {
                "id": r.item_id,
                "quantity": r.quantity,
                "unit_price_clp": r.price_clp,
                "added_price_clp": r.added_price,
                "line_total_clp": r.price_clp * r.quantity,
                "product": summary_dict(r, ref),
            }
        )
    return {
        "items": items,
        "item_count": sum(i["quantity"] for i in items),
        "subtotal_clp": sum(i["line_total_clp"] for i in items),
        "warnings": warnings,
    }
