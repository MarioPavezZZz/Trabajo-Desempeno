"""Fixtures compartidos.

- Las métricas se usan en modo de un solo proceso durante los tests (la
  variable de multiproceso de la imagen Docker se quita antes de importar la app).
- `db_engine`: base temporal `<db>_test` creada con el esquema actual y
  borrada al final de la sesión. Si PostgreSQL no está disponible, los tests
  marcados con `db` se omiten.
- `client`: cliente HTTP contra la app (ASGI, sin red) usando la base temporal
  con el catálogo de ejemplo de `tests/factories.py`.
"""

import os

os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
os.environ["APP_ENV"] = "test"

from datetime import date  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.models  # noqa: E402,F401  (registra las tablas en Base.metadata antes de create_all)
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402

TEST_DB = f"{get_settings().postgres_db}_test"


def _url(db: str) -> str:
    s = get_settings()
    return (
        f"postgresql+asyncpg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{db}"
    )


def sample_catalog():
    """Catálogo de ejemplo determinista (mismo que usan los tests del seed)."""
    from scripts.seed.generate import build_catalog
    from tests.factories import sample_cards, sample_sets

    return build_catalog(sample_sets(), sample_cards(), 8091, date(2026, 11, 1), 950)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine():
    """Base temporal con el esquema creado (sin datos)."""
    admin = create_async_engine(_url(get_settings().postgres_db), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    except OSError:
        await admin.dispose()
        pytest.skip("PostgreSQL no disponible")
    from app.db.session import create_engine

    # Mismo motor y parámetros de sesión que la app, apuntando a la base temporal.
    engine = create_engine(url=_url(TEST_DB))
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
    await admin.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def loaded_engine(db_engine):
    """Base temporal con el catálogo de ejemplo cargado (la carga es idempotente)."""
    from scripts.seed.loader import load_catalog

    await load_catalog(db_engine, sample_catalog())
    return db_engine


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(loaded_engine):
    """Cliente HTTP en proceso contra la app, con la sesión apuntando a la base temporal."""
    from app.api.deps import get_session
    from app.main import app
    from app.services.reference import clear_reference_cache

    maker = async_sessionmaker(loaded_engine, expire_on_commit=False)

    async def override_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    clear_reference_cache()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    clear_reference_cache()
