"""Configuración de la aplicación leída desde variables de entorno.

Toda la configuración vive en el entorno (ver `.env.example` en la raíz). Esto
permite cambiar parámetros que afectan el desempeño (workers, pool de
conexiones, tamaño de página) entre escenarios de carga sin tocar el código.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros de ejecución del backend.

    Los nombres de los campos coinciden con las variables de entorno sin
    distinguir mayúsculas (por ejemplo, `POSTGRES_HOST` -> `postgres_host`).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- General ----
    app_env: str = "development"
    app_name: str = "TCGMASTER"
    log_level: str = "INFO"

    # ---- Base de datos ----
    postgres_db: str = "tcgmaster"
    postgres_user: str = "tcgmaster"
    postgres_password: str = "tcgmaster"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_statement_timeout_ms: int = 5000

    # ---- Datos semilla ----
    data_dir: Path = Path("/data")
    seed_random_seed: int = 8091
    seed_base_date: str = "2026-11-01"
    seed_usd_clp: int = 950
    seed_http_delay_ms: int = 120

    @property
    def database_url(self) -> str:
        """URL de conexión asíncrona (driver asyncpg) para SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def media_dir(self) -> Path:
        """Carpeta de imágenes servidas por nosotros (no versionada)."""
        return self.data_dir / "media"

    @property
    def cache_dir(self) -> Path:
        """Carpeta de respuestas JSON e imágenes originales descargadas."""
        return self.data_dir / "cache"


@lru_cache
def get_settings() -> Settings:
    """Devuelve una única instancia de configuración por proceso."""
    return Settings()
