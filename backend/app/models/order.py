"""Modelos de pedidos y pagos.

`transaction_id` es el identificador único que se envía a GA4 en el evento
`purchase`. `traffic_type` permite separar en la base los pedidos generados
por las pruebas de carga de los pedidos de navegación real.
"""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ORDER_STATUSES = ("pendiente", "pagada", "rechazada", "anulada")
PAYMENT_PROVIDERS = ("webpay", "mock")
PAYMENT_STATUSES = ("iniciado", "autorizado", "rechazado", "anulado", "error")
TRAFFIC_TYPES = ("real", "load_test")


class Order(Base):
    """Pedido creado al iniciar el checkout."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('pendiente', 'pagada', 'rechazada', 'anulada')", name="status"),
        CheckConstraint("traffic_type IN ('real', 'load_test')", name="traffic_type"),
        CheckConstraint("total_clp > 0", name="total_positive"),
        Index("ix_orders_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(40), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="pendiente")
    total_clp: Mapped[int] = mapped_column(Integer)
    traffic_type: Mapped[str] = mapped_column(String(16), default="real")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
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
