"""Motor asíncrono y fábrica de sesiones.

El tamaño del pool (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`) es por proceso
worker: con N workers, el máximo de conexiones a PostgreSQL es
N * (pool_size + max_overflow). Es una de las variables a observar al buscar
el punto de saturación en la Fase 2.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Crea el motor asíncrono con el pool y el timeout de sentencias configurados."""
    settings = settings or get_settings()
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={
            # Corta consultas desbocadas en vez de dejar que acaparen conexiones bajo carga.
            "server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)},
        },
    )


engine = create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
