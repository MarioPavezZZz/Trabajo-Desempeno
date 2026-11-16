"""Checkout: datos de entrega, compra como invitado y reserva de stock.

Agrega a `orders`:
- access_key: clave aleatoria para consultar el pedido sin sesión (invitados).
- cart_id: carrito de origen (se marca como convertido al pagar).
- guest_name / guest_email: datos de contacto del invitado.
- subtotal_clp, shipping_clp, shipping_method, shipping_address: totales y entrega.
- expires_at: vencimiento de la reserva de stock de un pedido pendiente.
Restricción `buyer`: todo pedido tiene una cuenta o un correo de invitado.

Revisión: 0002
Anterior: 0001
Creada: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Aplica la migración."""
    # server_default solo para filas existentes; luego se quita (la app siempre envía el valor).
    op.add_column(
        "orders", sa.Column("access_key", sa.String(64), nullable=False, server_default="")
    )
    op.add_column("orders", sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("orders", sa.Column("guest_name", sa.String(120), nullable=True))
    op.add_column("orders", sa.Column("guest_email", sa.String(254), nullable=True))
    op.add_column(
        "orders", sa.Column("subtotal_clp", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "orders", sa.Column("shipping_clp", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "orders",
        sa.Column("shipping_method", sa.String(16), nullable=False, server_default="retiro"),
    )
    op.add_column(
        "orders",
        sa.Column(
            "shipping_address",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("orders", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    for column in ("access_key", "subtotal_clp", "shipping_clp", "shipping_method"):
        op.alter_column("orders", column, server_default=None)

    op.create_check_constraint(
        op.f("ck_orders_shipping_method"), "orders", "shipping_method IN ('retiro', 'domicilio')"
    )
    op.create_check_constraint(
        op.f("ck_orders_buyer"), "orders", "user_id IS NOT NULL OR guest_email IS NOT NULL"
    )
    op.create_index("ix_orders_status_expires", "orders", ["status", "expires_at"])
    op.create_index("ix_orders_cart_id", "orders", ["cart_id"])


def downgrade() -> None:
    """Revierte la migración."""
    op.drop_index("ix_orders_cart_id", table_name="orders")
    op.drop_index("ix_orders_status_expires", table_name="orders")
    op.drop_constraint(op.f("ck_orders_buyer"), "orders", type_="check")
    op.drop_constraint(op.f("ck_orders_shipping_method"), "orders", type_="check")
    for column in (
        "expires_at",
        "shipping_address",
        "shipping_method",
        "shipping_clp",
        "subtotal_clp",
        "guest_email",
        "guest_name",
        "cart_id",
        "access_key",
    ):
        op.drop_column("orders", column)
