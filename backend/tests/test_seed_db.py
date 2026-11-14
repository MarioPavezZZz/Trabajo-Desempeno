"""Tests de integración con PostgreSQL: migración aplicada e idempotencia del loader.

Usan una base temporal propia (`<db>_test`) que se crea y borra en cada
ejecución, para no tocar los datos de desarrollo. Se omiten si no hay conexión.
"""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.models import PriceHistory, Product
from scripts.seed.generate import build_catalog
from scripts.seed.loader import load_catalog
from tests.factories import sample_cards, sample_sets

# Todos los tests del módulo comparten el bucle de eventos del fixture `engine`
# (un motor asyncpg no puede usarse desde otro bucle).
pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

TEST_DB = f"{get_settings().postgres_db}_test"


def _url(db: str) -> str:
    s = get_settings()
    return f"postgresql+asyncpg://{s.postgres_user}:{s.postgres_password}@{s.postgres_host}:{s.postgres_port}/{db}"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def engine():
    admin = create_async_engine(_url(get_settings().postgres_db), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    except OSError:
        pytest.skip("PostgreSQL no disponible")
    eng = create_async_engine(_url(TEST_DB))
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
    await admin.dispose()


def _catalog():
    return build_catalog(sample_sets(), sample_cards(), 8091, date(2026, 11, 1), 950)


async def _snapshot(engine):
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(Product.id, Product.sku, Product.price_clp).order_by(Product.id)
            )
        ).all()
        history = await conn.scalar(select(func.count()).select_from(PriceHistory))
    return rows, history


async def test_carga_inicial(engine):
    counts = await load_catalog(engine, _catalog())
    assert counts["productos_activos"] == len(_catalog().products)
    assert counts["juegos"] == 3


async def test_carga_es_idempotente(engine):
    before = await _snapshot(engine)
    await load_catalog(engine, _catalog())
    after = await _snapshot(engine)
    assert before == after  # mismos ids, SKU, precios y misma cantidad de historial


async def test_busqueda_full_text_usa_columna_generada(engine):
    async with engine.connect() as conn:
        found = await conn.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.search_vector.op("@@")(func.plainto_tsquery("simple", "carta pokemon")))
        )
    assert found and found > 0


async def test_check_rechaza_carta_sin_estado(engine):
    async with engine.connect() as conn:
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
