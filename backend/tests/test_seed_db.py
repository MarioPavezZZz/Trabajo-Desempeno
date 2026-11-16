"""Tests de integración con PostgreSQL: carga e idempotencia del loader.

Usan la base temporal del fixture `db_engine` (ver conftest.py).
"""

import pytest
from sqlalchemy import func, select, text

from app.models import PriceHistory, Product
from scripts.seed.loader import load_catalog
from tests.conftest import sample_catalog

# Todos los tests comparten el bucle de eventos del fixture de base
# (un motor asyncpg no puede usarse desde otro bucle).
pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


async def _snapshot(engine):
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(Product.id, Product.sku, Product.price_clp).order_by(Product.id)
            )
        ).all()
        history = await conn.scalar(select(func.count()).select_from(PriceHistory))
    return rows, history


async def test_carga_inicial(db_engine):
    counts = await load_catalog(db_engine, sample_catalog())
    assert counts["productos_activos"] == len(sample_catalog().products)
    assert counts["juegos"] == 3


async def test_carga_es_idempotente(db_engine):
    await load_catalog(db_engine, sample_catalog())
    before = await _snapshot(db_engine)
    await load_catalog(db_engine, sample_catalog())
    after = await _snapshot(db_engine)
    assert before == after  # mismos ids, SKU, precios y misma cantidad de historial


async def test_busqueda_full_text_usa_columna_generada(db_engine):
    await load_catalog(db_engine, sample_catalog())
    async with db_engine.connect() as conn:
        found = await conn.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.search_vector.op("@@")(func.plainto_tsquery("simple", "carta pokemon")))
        )
    assert found and found > 0


async def test_check_rechaza_carta_sin_estado(db_engine):
    await load_catalog(db_engine, sample_catalog())
    async with db_engine.connect() as conn:
        with pytest.raises(Exception, match="ck_products_card_fields"):
            await conn.execute(
                text(
                    "INSERT INTO products (sku, slug, product_type, game_id, set_id, name,"
                    " image_path, thumb_path, price_clp, stock, is_featured, is_active, is_foil,"
                    " rarity_tier, language) SELECT 'X', 'x', 'carta', g.id, s.id, 'x', 'a', 'a',"
                    " 1000, 1, false, true, false, 'comun', 'EN'"
                    " FROM games g JOIN sets s ON s.game_id = g.id LIMIT 1"
                )
            )
