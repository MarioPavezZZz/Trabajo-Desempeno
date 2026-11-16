"""Modelos de pedidos y pagos.

`transaction_id` es el identificador único que se envía a GA4 en el evento
`purchase`. `traffic_type` permite separar en la base los pedidos generados
por las pruebas de carga de los pedidos de navegación real.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ORDER_STATUSES = ("pendiente", "pagada", "rechazada", "anulada")
PAYMENT_PROVIDERS = ("webpay", "mock")
PAYMENT_STATUSES = ("iniciado", "autorizado", "rechazado", "anulado", "error")
TRAFFIC_TYPES = ("real", "load_test")


SHIPPING_METHODS = ("retiro", "domicilio")


class Order(Base):
    """Pedido creado al iniciar el checkout (con cuenta o como invitado).

    Ciclo de vida: `pendiente` (stock reservado, esperando el pago) ->
    `pagada` | `rechazada` | `anulada` (pago abortado o reserva vencida).
    Un pedido de invitado no tiene `user_id`; se consulta con `access_key`.
    """

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('pendiente', 'pagada', 'rechazada', 'anulada')", name="status"),
        CheckConstraint("traffic_type IN ('real', 'load_test')", name="traffic_type"),
        CheckConstraint("total_clp > 0", name="total_positive"),
        CheckConstraint("shipping_method IN ('retiro', 'domicilio')", name="shipping_method"),
        CheckConstraint("user_id IS NOT NULL OR guest_email IS NOT NULL", name="buyer"),
        Index("ix_orders_user_created", "user_id", "created_at"),
        # Barrido de reservas vencidas: pedidos pendientes por fecha.
        Index("ix_orders_status_expires", "status", "expires_at"),
        Index("ix_orders_cart_id", "cart_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(40), unique=True)
    # Clave aleatoria para ver el pedido sin sesión (enlace de resultado del invitado).
    access_key: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cart_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    guest_name: Mapped[str | None] = mapped_column(String(120))
    guest_email: Mapped[str | None] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(16), default="pendiente")
    subtotal_clp: Mapped[int] = mapped_column(Integer)
    shipping_clp: Mapped[int] = mapped_column(Integer, default=0)
    total_clp: Mapped[int] = mapped_column(Integer)
    shipping_method: Mapped[str] = mapped_column(String(16), default="retiro")
    shipping_address: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    traffic_type: Mapped[str] = mapped_column(String(16), default="real")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")


class OrderItem(Base):
    """Línea de pedido con copia del nombre y precio al momento de la compra."""

    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name_snapshot: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_clp: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    """Intento de pago en el proveedor (Webpay integración o simulador local).

    `buy_order` se limita a 26 caracteres, el máximo que acepta Webpay Plus.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("provider IN ('webpay', 'mock')", name="provider"),
        CheckConstraint(
            "status IN ('iniciado', 'autorizado', 'rechazado', 'anulado', 'error')",
            name="status",
        ),
        Index("ix_payments_order_id", "order_id"),
        Index("ix_payments_token", "token", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    provider: Mapped[str] = mapped_column(String(16))
    token: Mapped[str | None] = mapped_column(String(128))
    buy_order: Mapped[str] = mapped_column(String(26))
    amount_clp: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="iniciado")
    authorization_code: Mapped[str | None] = mapped_column(String(16))
    raw_response: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    order: Mapped[Order] = relationship(back_populates="payments")
