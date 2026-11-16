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

    # ---- API ----
    api_page_size_default: int = 24
    api_page_size_max: int = 60
    # Segundos de Cache-Control en respuestas GET del catálogo. 0 = sin caché
    # (línea base de las pruebas de carga); activarlo es una mejora medible.
    api_cache_max_age: int = 0
    api_docs_enabled: bool = True
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    log_format: str = "json"  # json | console
    media_base_url: str = "/media"
    search_trgm_threshold: float = 0.45  # tolerancia a errores de tipeo en la búsqueda

    # ---- Autenticación y cookies ----
    jwt_secret: str = "solo-para-desarrollo-cambiar-en-produccion"
    jwt_expires_minutes: int = 120
    # Costo de bcrypt (2^n iteraciones). Cada +1 duplica la CPU por login/registro.
    password_hash_rounds: int = 10
    cookie_secure: bool = False  # True en producción (solo HTTPS)
    session_cookie: str = "tcg_session"
    cart_cookie: str = "tcg_cart"
    cart_cookie_days: int = 30

    # ---- Checkout y pagos ----
    public_base_url: str = "http://localhost:8080"  # base del return_url de Webpay
    payment_provider: str = "webpay"  # webpay | mock
    # Las peticiones con X-Traffic-Type: load_test usan el simulador aunque el
    # proveedor sea Webpay: nunca se genera carga sintética contra Transbank.
    load_test_use_mock: bool = True
    webpay_environment: str = "integration"  # integration | production
    # Credenciales PÚBLICAS del ambiente de integración (documentación de Transbank).
    webpay_commerce_code: str = "597055555532"
    webpay_api_key: str = "579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C"
    webpay_timeout_s: float = 10.0
    reservation_minutes: int = 15  # tiempo que un pedido pendiente retiene el stock
    mock_payment_latency_ms: int = 300  # latencia simulada de la pasarela
    mock_approval_rate: float = 0.9  # proporción de pagos aprobados en modo automático
    shipping_home_clp: int = 3990  # tarifa fija simulada de envío a domicilio

    @property
    def webpay_base_url(self) -> str:
        """Servidor de Transbank según el ambiente."""
        if self.webpay_environment == "production":
            return "https://webpay3g.transbank.cl"
        return "https://webpay3gint.transbank.cl"

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
    def cors_origin_list(self) -> list[str]:
        """Orígenes CORS permitidos como lista."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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
