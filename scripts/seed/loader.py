"""Carga idempotente del catálogo en PostgreSQL.

Usa `INSERT ... ON CONFLICT DO UPDATE` sobre claves naturales (slug del juego,
(juego, código) del set, SKU del producto). Ejecutarlo N veces deja la base
igual que ejecutarlo una vez, y los `id` de los productos no cambian entre
ejecuciones (las URLs que usen los scripts de carga siguen siendo válidas).
Todo ocurre en una sola transacción: o se carga completo o no se carga nada.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import asdict
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.models import CardSet, Game, PriceHistory, Product
from scripts.seed.records import Catalog

log = logging.getLogger("seed.loader")

CHUNK = 500  # filas por INSERT: equilibrio entre ida y vuelta y tamaño del paquete


def _chunks(
    rows: Sequence[dict[str, Any]], size: int = CHUNK
) -> Iterator[Sequence[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


async def _upsert(
    conn: AsyncConnection,
    model: type,
    rows: Sequence[dict[str, Any]],
    conflict: list[str],
    returning: list[str],
) -> list[Any]:
    """INSERT ... ON CONFLICT (conflict) DO UPDATE de todas las columnas recibidas."""
    results: list[Any] = []
    for chunk in _chunks(rows):
        stmt = insert(model).values(list(chunk))
        update_cols = {c: stmt.excluded[c] for c in chunk[0] if c not in conflict}
        stmt = stmt.on_conflict_do_update(index_elements=conflict, set_=update_cols)
        stmt = stmt.returning(*(getattr(model, c) for c in returning))
        results.extend((await conn.execute(stmt)).all())
    return results


async def load_catalog(engine: AsyncEngine, catalog: Catalog) -> dict[str, int]:
    """Inserta o actualiza todo el catálogo. Retorna conteos para el resumen."""
    async with engine.begin() as conn:
        game_rows = [{"slug": s, "name": n, "sort_order": o} for s, n, o in catalog.games]
        game_ids = dict(
            (slug, gid)
            for gid, slug in await _upsert(conn, Game, game_rows, ["slug"], ["id", "slug"])
        )

        set_rows = [
            {
                "game_id": game_ids[s.game],
                "code": s.code,
                "name": s.name,
                "release_date": s.release_date,
                "logo_path": s.logo_path,
                "card_count": s.card_count,
            }
            for s in catalog.sets
        ]
        set_ids = {
            (gid, code): sid
            for sid, gid, code in await _upsert(
                conn, CardSet, set_rows, ["game_id", "code"], ["id", "game_id", "code"]
            )
        }

        product_rows = []
        for p in catalog.products:
            row = asdict(p)
            game, set_code = row.pop("game"), row.pop("set_code")
            row["game_id"] = game_ids[game] if game else None
            row["set_id"] = set_ids[(game_ids[game], set_code)] if set_code else None
            row["is_active"] = True
            product_rows.append(row)
        sku_ids = dict(
            (sku, pid)
            for pid, sku in await _upsert(conn, Product, product_rows, ["sku"], ["id", "sku"])
        )

        # Productos que ya no están en el catálogo generado: se desactivan, no se borran
        # (podrían estar referenciados por pedidos de pruebas anteriores).
        deactivated = await conn.execute(
            update(Product)
            .where(Product.sku.not_in(list(sku_ids)), Product.is_active.is_(True))
            .values(is_active=False)
        )

        history_rows = [
            {"product_id": sku_ids[sku], "recorded_at": day, "price_clp": price}
            for sku, day, price in catalog.price_history
        ]
        await _upsert(conn, PriceHistory, history_rows, ["product_id", "recorded_at"], ["id"])

        total = (await conn.execute(select(Product.id).where(Product.is_active))).all()

    counts = {
        "juegos": len(game_ids),
        "sets": len(set_ids),
        "productos_cargados": len(sku_ids),
        "productos_activos": len(total),
        "productos_desactivados": deactivated.rowcount or 0,
        "historial_precios": len(history_rows),
    }
    log.info("Carga completa: %s", counts)
    return counts
