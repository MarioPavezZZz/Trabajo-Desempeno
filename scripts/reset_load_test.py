"""Reinicia el estado de la tienda entre corridas de pruebas de carga.

Cada corrida debe partir del mismo estado para que los resultados sean
comparables. Este script:
1. Devuelve al stock lo reservado por pedidos de prueba pendientes.
2. Borra pagos, pedidos (con sus líneas) y carritos con traffic_type = load_test.
3. Borra los usuarios de prueba (correo carga-k6-N@example.com) y sus carritos.
4. Recarga el catálogo con la semilla fija: stock y precios vuelven a los del
   seed (las compras de la corrida anterior ya no afectan a la siguiente).
5. Opcional (--estadisticas): reinicia pg_stat_statements, para que el
   reporte de consultas SQL corresponda solo a la próxima corrida.

Nunca toca pedidos, carritos ni usuarios de tráfico real.

Uso (dentro del contenedor de la API):
  python scripts/reset_load_test.py
  python scripts/reset_load_test.py --sin-catalogo --estadisticas
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, delete, func, or_, select, text, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: E402

from app.models import Cart, Order, OrderItem, Payment, Product, User  # noqa: E402

# Patrón de correo de los usuarios que crea k6 (ver loadtest/k6/lib/config.js).
LOADTEST_EMAIL_LIKE = "carga-k6-%@example.com"


async def reset_load_test(engine: AsyncEngine) -> dict[str, int]:
    """Borra todo lo generado por pruebas de carga. Retorna conteos de lo eliminado."""
    async with engine.begin() as conn:
        loadtest_users = select(User.id).where(User.email.like(LOADTEST_EMAIL_LIKE))
        loadtest_orders = select(Order.id).where(
            or_(Order.traffic_type == "load_test", Order.user_id.in_(loadtest_users))
        )

        # 1) Stock reservado por pedidos de prueba que quedaron pendientes.
        restored = await conn.execute(
            update(Product)
            .where(
                Product.id == OrderItem.product_id,
                OrderItem.order_id == Order.id,
                Order.status == "pendiente",
                Order.id.in_(loadtest_orders),
            )
            .values(stock=Product.stock + OrderItem.quantity)
        )

        # 2) Pagos -> pedidos (las líneas se borran en cascada) -> carritos.
        payments = await conn.execute(delete(Payment).where(Payment.order_id.in_(loadtest_orders)))
        orders = await conn.execute(delete(Order).where(Order.id.in_(loadtest_orders)))
        carts = await conn.execute(
            delete(Cart).where(
                or_(Cart.traffic_type == "load_test", Cart.user_id.in_(loadtest_users))
            )
        )

        # 3) Usuarios de prueba (ya sin pedidos ni carritos que los referencien).
        users = await conn.execute(delete(User).where(User.email.like(LOADTEST_EMAIL_LIKE)))

        remaining = await conn.scalar(
            select(func.count()).select_from(Order).where(and_(Order.traffic_type == "load_test"))
        )

    return {
        "lineas_de_stock_devueltas": restored.rowcount or 0,
        "pagos_borrados": payments.rowcount or 0,
        "pedidos_borrados": orders.rowcount or 0,
        "carritos_borrados": carts.rowcount or 0,
        "usuarios_borrados": users.rowcount or 0,
        "pedidos_de_prueba_restantes": remaining or 0,
    }


async def reset_statistics(engine: AsyncEngine) -> None:
    """Reinicia pg_stat_statements (si la extensión está disponible)."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_stat_statements_reset()"))


async def main_async(reload_catalog: bool, statistics: bool) -> dict:
    from app.db.session import engine

    try:
        result: dict = await reset_load_test(engine)
        if reload_catalog:
            from scripts.seed_catalog import load

            result["catalogo"] = await load(_seed())
        if statistics:
            await reset_statistics(engine)
            result["pg_stat_statements"] = "reiniciado"
        return result
    finally:
        await engine.dispose()


def _seed() -> int:
    from app.core.config import get_settings

    return get_settings().seed_random_seed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--sin-catalogo", action="store_true", help="no recargar stock y precios desde el seed"
    )
    parser.add_argument("--estadisticas", action="store_true", help="reiniciar pg_stat_statements")
    args = parser.parse_args(argv)
    result = asyncio.run(main_async(not args.sin_catalogo, args.estadisticas))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
