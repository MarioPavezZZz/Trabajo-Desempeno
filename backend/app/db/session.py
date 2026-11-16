"""Motor asíncrono y fábrica de sesiones.

El tamaño del pool (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`) es por proceso
worker: con N workers, el máximo de conexiones a PostgreSQL es
N * (pool_size + max_overflow). Es una de las variables a observar al buscar
el punto de saturación en la Fase 2.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings


def server_settings(settings: Settings) -> dict[str, str]:
    """Parámetros de PostgreSQL aplicados a cada conexión al abrirla."""
    return {
        # Corta consultas desbocadas en vez de dejar que acaparen conexiones bajo carga.
        "statement_timeout": str(settings.db_statement_timeout_ms),
        # Umbral del operador `<%` de búsqueda tolerante a errores (por defecto 0.6,
        # demasiado estricto para nombres cortos: "plymat" vs "Playmat" = 0.5).
        "pg_trgm.word_similarity_threshold": str(settings.search_trgm_threshold),
    }


def create_engine(settings: Settings | None = None, url: str | None = None) -> AsyncEngine:
    """Crea el motor asíncrono con el pool y los parámetros de sesión configurados."""
    settings = settings or get_settings()
    return create_async_engine(
        url or settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={"server_settings": server_settings(settings)},
    )


engine = create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
