"""Checkout: crea el pedido reservando stock, inicia el pago y lo confirma.

Decisiones (documentadas para el análisis de la Fase 2):

1. **El stock se reserva al crear el pedido**, no al pagar. Si se descontara al
   confirmar el pago, dos personas podrían pagar la última unidad y habría que
   reembolsar a una. La reserva usa `SELECT ... FOR UPDATE` sobre los productos,
   siempre en orden de id para que dos checkouts no se bloqueen mutuamente
   (deadlock). Es un punto de contención real bajo carga.
2. **La llamada a la pasarela ocurre fuera de esa transacción.** La reserva se
   confirma (COMMIT) antes de llamar a Transbank, así los bloqueos de productos
   duran milisegundos y no lo que tarde la red.
3. **Reservas vencidas**: un pedido `pendiente` que no se paga en
   `RESERVATION_MINUTES` se anula y devuelve su stock. El barrido se hace al
   inicio de cada checkout (`SKIP LOCKED`: nunca espera a otro checkout).
4. **Confirmación idempotente**: el pago se bloquea (`FOR UPDATE`) y solo se
   procesa si sigue `iniciado`; un retorno repetido no cobra ni descuenta dos veces.
5. **El monto lo calcula el servidor** y se verifica contra lo que confirma la pasarela.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Cart, CartItem, Order, OrderItem, Payment, Product, User
from app.payments.base import PaymentError, PaymentProvider
from app.schemas.checkout import CheckoutIn
from app.services.cart import find_cart
from app.services.catalog import media_url

log = get_logger("tcgmaster.checkout")

# Hora de Chile continental, solo para la fecha visible en el número de pedido.
CLT = timezone(timedelta(hours=-3))


def new_transaction_id() -> str:
    """Número de pedido y `buy_order` de Webpay (máx. 26 caracteres): TCG-AAMMDD-XXXXXXXXXX."""
    return f"TCG-{datetime.now(CLT):%y%m%d}-{secrets.token_hex(5).upper()}"


async def _restore_stock(session: AsyncSession, order_id: int) -> None:
    """Devuelve al stock las unidades reservadas por un pedido (un solo UPDATE ... FROM)."""
    await session.execute(
        update(Product)
        .where(Product.id == OrderItem.product_id, OrderItem.order_id == order_id)
        .values(stock=Product.stock + OrderItem.quantity)
    )


async def release_order(session: AsyncSession, order: Order, status: str) -> None:
    """Cierra un pedido pendiente sin pago: devuelve el stock y anula los pagos abiertos."""
    if order.status != "pendiente":
        return
    order.status = status
    await _restore_stock(session, order.id)
    await session.execute(
        update(Payment)
        .where(Payment.order_id == order.id, Payment.status == "iniciado")
        .values(status="anulado" if status == "anulada" else "rechazado")
    )


async def release_expired(session: AsyncSession, limit: int = 50) -> int:
    """Anula pedidos pendientes con la reserva vencida. Retorna cuántos liberó."""
    expired = (
        (
            await session.execute(
                select(Order)
                .where(Order.status == "pendiente", Order.expires_at < func.now())
                .order_by(Order.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for order in expired:
        await release_order(session, order, "anulada")
    if expired:
        log.info("reservas_vencidas_liberadas", cantidad=len(expired))
    return len(expired)


def _stock_message(name: str, available: int) -> str:
    if available == 0:
        return f"{name} se agotó mientras comprabas. Quítalo del carrito para continuar."
    return f"Solo quedan {available} unidades de {name}. Ajusta la cantidad en el carrito."


async def start_checkout(
    session: AsyncSession,
    *,
    user_id: int | None,
    cart_cookie: uuid.UUID | None,
    data: CheckoutIn,
    traffic_type: str,
    provider: PaymentProvider,
) -> dict:
    """Crea el pedido (reservando stock) e inicia el pago en el proveedor."""
    settings = get_settings()
    # El barrido se confirma en su propia transacción: si este checkout falla
    # después (carrito vacío, sin stock), la liberación de reservas no se pierde.
    if await release_expired(session):
        await session.commit()

    cart = await find_cart(session, user_id, cart_cookie)
    if cart is None:
        raise HTTPException(status_code=400, detail="Tu carrito está vacío")

    # Contacto: el de la cuenta, o el que entrega el invitado.
    if user_id is not None:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Inicia sesión para continuar")
        contact_name, contact_email = user.full_name, user.email
    else:
        if not (data.contact_name and data.contact_name.strip()) or not data.contact_email:
            raise HTTPException(
                status_code=422, detail="Escribe tu nombre y correo para recibir la confirmación"
            )
        contact_name, contact_email = data.contact_name.strip(), data.contact_email.lower()

    # Un nuevo intento de pago del mismo carrito anula el intento anterior (libera su stock).
    previous = (
        (
            await session.execute(
                select(Order)
                .where(Order.cart_id == cart.id, Order.status == "pendiente")
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for order in previous:
        await release_order(session, order, "anulada")

    lines = dict(
        (
            await session.execute(
                select(CartItem.product_id, CartItem.quantity).where(CartItem.cart_id == cart.id)
            )
        ).all()
    )
    if not lines:
        raise HTTPException(status_code=400, detail="Tu carrito está vacío")

    # Bloqueo de los productos en orden de id (evita deadlocks entre checkouts).
    products = (
        (
            await session.execute(
                select(Product).where(Product.id.in_(lines)).order_by(Product.id).with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for product in products:
        quantity = lines[product.id]
        if not product.is_active:
            raise HTTPException(
                status_code=409,
                detail=f"{product.name} ya no está disponible. Quítalo del carrito.",
            )
        if quantity > product.stock:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": _stock_message(product.name, product.stock),
                    "available": product.stock,
                },
            )
        product.stock -= quantity  # reserva

    subtotal = sum(p.price_clp * lines[p.id] for p in products)
    shipping = settings.shipping_home_clp if data.shipping_method == "domicilio" else 0
    address = (
        {
            "street": data.street.strip(),
            "comuna": data.comuna.strip(),
            "region": data.region.strip(),
            "phone": data.phone.strip(),
        }
        if data.shipping_method == "domicilio"
        else {}
    )
    order = Order(
        transaction_id=new_transaction_id(),
        access_key=secrets.token_urlsafe(24),
        user_id=user_id,
        cart_id=cart.id,
        guest_name=None if user_id else contact_name,
        guest_email=None if user_id else contact_email,
        status="pendiente",
        subtotal_clp=subtotal,
        shipping_clp=shipping,
        total_clp=subtotal + shipping,
        shipping_method=data.shipping_method,
        shipping_address=address,
        traffic_type=traffic_type,
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.reservation_minutes),
    )
    order.items = [
        OrderItem(
            product_id=p.id, name_snapshot=p.name, quantity=lines[p.id], unit_price_clp=p.price_clp
        )
        for p in products
    ]
    session.add(order)
    await session.commit()  # libera los bloqueos antes de llamar a la pasarela

    session_id = f"u{user_id}" if user_id else f"inv-{cart.id.hex[:20]}"
    return_url = f"{settings.public_base_url}/api/checkout/webpay/retorno"
    try:
        start = await provider.create(order.transaction_id, session_id, order.total_clp, return_url)
    except PaymentError as exc:
        log.warning("pasarela_no_disponible", proveedor=provider.name, error=str(exc))
        await session.refresh(order)
        await release_order(session, order, "anulada")
        await session.commit()
        raise HTTPException(
            status_code=502, detail="No pudimos conectar con el medio de pago. Inténtalo de nuevo."
        ) from None

    session.add(
        Payment(
            order_id=order.id,
            provider=provider.name,
            token=start.token,
            buy_order=order.transaction_id,
            amount_clp=order.total_clp,
            status="iniciado",
        )
    )
    await session.commit()
    return {
        "transaction_id": order.transaction_id,
        "access_key": order.access_key,
        "total_clp": order.total_clp,
        "provider": provider.name,
        "payment": {
            "url": start.url,
            "method": start.method,
            "token": start.token,
            "token_field": start.token_field,
        },
    }


async def confirm_payment(
    session: AsyncSession, provider: PaymentProvider, token: str, decision: str | None = None
) -> Order | None:
    """Confirma el pago del token (idempotente). Retorna el pedido o None si el token no existe."""
    payment = (
        await session.execute(
            select(Payment)
            .where(Payment.token == token, Payment.provider == provider.name)
            .with_for_update()
        )
    ).scalar()
    if payment is None:
        return None
    order = (
        await session.execute(select(Order).where(Order.id == payment.order_id).with_for_update())
    ).scalar_one()
    if payment.status != "iniciado":
        return order  # ya procesado: retorno repetido
    if order.status != "pendiente":
        # La reserva venció antes de volver: no se confirma (Transbank revierte lo no confirmado).
        payment.status = "anulado"
        await session.commit()
        return order

    result = await provider.commit(token, decision)
    if (
        result.approved
        and result.amount is not None
        and (result.amount != order.total_clp or result.buy_order != order.transaction_id)
    ):
        log.error(
            "pago_inconsistente",
            pedido=order.transaction_id,
            monto=result.amount,
            esperado=order.total_clp,
        )
        result.approved, result.status = False, "error"

    payment.status = result.status
    payment.authorization_code = result.authorization_code
    payment.raw_response = {**result.raw, "card_last4": result.card_last4}
    if result.approved:
        order.status = "pagada"
        order.paid_at = func.now()
        if order.cart_id:
            await session.execute(
                update(Cart).where(Cart.id == order.cart_id).values(status="convertido")
            )
    else:
        await release_order(session, order, "rechazada")
    await session.commit()
    await session.refresh(order)
    log.info(
        "pago_confirmado", pedido=order.transaction_id, estado=order.status, proveedor=provider.name
    )
    return order


async def abort_payment(
    session: AsyncSession, tbk_token: str | None, buy_order: str | None
) -> Order | None:
    """Pago anulado en Transbank (TBK_TOKEN) o tiempo agotado (solo TBK_ORDEN_COMPRA)."""
    order: Order | None = None
    if tbk_token:
        payment = (
            await session.execute(
                select(Payment).where(Payment.token == tbk_token).with_for_update()
            )
        ).scalar()
        if payment:
            order = await session.get(Order, payment.order_id, with_for_update=True)
    if order is None and buy_order:
        order = (
            await session.execute(
                select(Order).where(Order.transaction_id == buy_order).with_for_update()
            )
        ).scalar()
    if order is None:
        return None
    await release_order(session, order, "anulada")
    await session.commit()
    await session.refresh(order)
    return order


# ---------------------------------------------------------------- consultas
async def get_order(
    session: AsyncSession, transaction_id: str, user_id: int | None, key: str | None
) -> dict | None:
    """Pedido visible para quien lo pide: su dueño o quien tenga la clave. None si no."""
    order = (
        await session.execute(select(Order).where(Order.transaction_id == transaction_id))
    ).scalar()
    if order is None:
        return None
    is_owner = order.user_id is not None and order.user_id == user_id
    has_key = bool(key) and secrets.compare_digest(key, order.access_key)
    if not (is_owner or has_key):
        return None  # 404 en vez de 403: no se confirma que el pedido existe

    rows = (
        await session.execute(
            select(OrderItem, Product.slug, Product.thumb_path)
            .join(Product, Product.id == OrderItem.product_id)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.id)
        )
    ).all()
    payment = (
        await session.execute(
            select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()).limit(1)
        )
    ).scalar()
    if order.user_id:
        user = await session.get(User, order.user_id)
        contact_name, contact_email = user.full_name, user.email
    else:
        contact_name, contact_email = order.guest_name or "", order.guest_email or ""
    return {
        "transaction_id": order.transaction_id,
        "status": order.status,
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "shipping_method": order.shipping_method,
        "shipping_address": order.shipping_address,
        "subtotal_clp": order.subtotal_clp,
        "shipping_clp": order.shipping_clp,
        "total_clp": order.total_clp,
        "items": [
            {
                "product_id": item.product_id,
                "slug": slug,
                "thumb": media_url(thumb),
                "name": item.name_snapshot,
                "quantity": item.quantity,
                "unit_price_clp": item.unit_price_clp,
                "line_total_clp": item.unit_price_clp * item.quantity,
            }
            for item, slug, thumb in rows
        ],
        "payment": {
            "provider": payment.provider,
            "status": payment.status,
            "authorization_code": payment.authorization_code,
            "card_last4": (payment.raw_response or {}).get("card_last4"),
        }
        if payment
        else None,
    }


async def list_orders(session: AsyncSession, user_id: int, limit: int = 50) -> list[dict]:
    """Últimos pedidos de la cuenta."""
    rows = (
        await session.execute(
            select(
                Order.transaction_id,
                Order.status,
                Order.created_at,
                Order.total_clp,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("item_count"),
            )
            .outerjoin(OrderItem, OrderItem.order_id == Order.id)
            .where(Order.user_id == user_id)
            .group_by(Order.id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [dict(r._mapping) for r in rows]
