"""Carritos: origen del tráfico (real | load_test).

Permite medir el abandono de carrito de las pruebas de carga por separado del
tráfico real y borrar los carritos de prueba entre corridas.

Revisión: 0003
Anterior: 0002
Creada: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Aplica la migración."""
    op.add_column(
        "carts",
        sa.Column("traffic_type", sa.String(16), nullable=False, server_default="real"),
    )
    op.create_check_constraint(
        op.f("ck_carts_traffic_type"), "carts", "traffic_type IN ('real', 'load_test')"
    )
    op.create_index("ix_carts_traffic_type", "carts", ["traffic_type"])


def downgrade() -> None:
    """Revierte la migración."""
    op.drop_index("ix_carts_traffic_type", table_name="carts")
    op.drop_constraint(op.f("ck_carts_traffic_type"), "carts", type_="check")
    op.drop_column("carts", "traffic_type")
