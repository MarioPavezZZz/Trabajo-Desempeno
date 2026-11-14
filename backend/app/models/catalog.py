"""Modelos del catálogo: juegos, sets/expansiones, productos e historial de precios.

Decisión de diseño (ver docs/propuesta-arquitectura.md §4): una sola tabla
`products` para cartas, sellados y accesorios, con columnas específicas
anulables. Así cualquier combinación de filtros del listado se resuelve sobre
una sola tabla, sin JOIN, con índices dedicados; la latencia bajo carga es
más predecible y los planes de ejecución son fáciles de explicar en el informe.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ---- Valores permitidos (se validan también con CHECK en la base) ----
PRODUCT_TYPES = ("carta", "sellado", "accesorio")
CONDITIONS = ("NM", "LP", "MP", "HP")
RARITY_TIERS = ("comun", "infrecuente", "rara", "epica", "legendaria")
SEALED_TYPES = ("sobre", "display", "caja_entrenador", "mazo_estructura")
ACCESSORY_TYPES = ("fundas", "carpeta", "deck_box", "playmat", "toploader")
LANGUAGES = ("EN", "ES", "JA")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    """Construye la expresión SQL `columna IN ('a', 'b', ...)` para un CHECK."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Game(Base):
    """Juego de cartas (Pokémon, Magic, Yu-Gi-Oh!)."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    sets: Mapped[list["CardSet"]] = relationship(back_populates="game")


class CardSet(Base):
    """Set o expansión de un juego. Sus productos sellados se generan a partir de él."""

    __tablename__ = "sets"
    __table_args__ = (UniqueConstraint("game_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    release_date: Mapped[date | None] = mapped_column(Date)
    logo_path: Mapped[str | None] = mapped_column(String(255))
    card_count: Mapped[int | None] = mapped_column(Integer)

    game: Mapped[Game] = relationship(back_populates="sets")


class Product(Base):
    """Producto vendible: carta suelta, producto sellado o accesorio.

    Precios en pesos chilenos como enteros (el CLP no usa decimales).
    `compare_at_price_clp` con valor indica que el producto está en oferta y
    guarda el precio anterior.
    """

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(_in_list("product_type", PRODUCT_TYPES), name="product_type"),
        CheckConstraint("price_clp > 0", name="price_positive"),
        CheckConstraint("stock >= 0", name="stock_non_negative"),
        CheckConstraint(
            "compare_at_price_clp IS NULL OR compare_at_price_clp > price_clp",
            name="offer_price",
        ),
        CheckConstraint(
            f"condition IS NULL OR {_in_list('condition', CONDITIONS)}", name="condition"
        ),
        CheckConstraint(
            f"rarity_tier IS NULL OR {_in_list('rarity_tier', RARITY_TIERS)}",
            name="rarity_tier",
        ),
        CheckConstraint(
            f"sealed_type IS NULL OR {_in_list('sealed_type', SEALED_TYPES)}",
            name="sealed_type",
        ),
        CheckConstraint(
            f"accessory_type IS NULL OR {_in_list('accessory_type', ACCESSORY_TYPES)}",
            name="accessory_type",
        ),
        # Coherencia por tipo de producto.
        CheckConstraint(
            "product_type <> 'carta' OR (condition IS NOT NULL AND rarity_tier IS NOT NULL"
            " AND language IS NOT NULL AND set_id IS NOT NULL)",
            name="card_fields",
        ),
        CheckConstraint(
            "product_type <> 'sellado' OR (sealed_type IS NOT NULL AND set_id IS NOT NULL)",
            name="sealed_fields",
        ),
        CheckConstraint(
            "product_type <> 'accesorio' OR accessory_type IS NOT NULL",
            name="accessory_fields",
        ),
        CheckConstraint("product_type = 'accesorio' OR game_id IS NOT NULL", name="game_required"),
        # ---- Índices para búsqueda y filtros (justificación en la propuesta, §4) ----
        # Búsqueda por palabras completas (full-text).
        Index("ix_products_search", "search_vector", postgresql_using="gin"),
        # Coincidencias parciales / tolerantes a errores en el nombre (ILIKE, similarity).
        Index(
            "ix_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        # Filtro más frecuente del listado + orden por precio.
        Index("ix_products_type_game_price", "product_type", "game_id", "price_clp"),
        # Novedades por tipo/juego (orden por fecha de ingreso).
        Index("ix_products_type_game_created", "product_type", "game_id", "created_at"),
        Index("ix_products_set_id", "set_id"),
        Index("ix_products_rarity_tier", "rarity_tier"),
        Index("ix_products_condition", "condition"),
        # Parcial: solo las filas en oferta (pocas), para la página /ofertas y el home.
        Index(
            "ix_products_offers",
            "product_type",
            "game_id",
            postgresql_where=text("compare_at_price_clp IS NOT NULL"),
        ),
        # Parcial: filtro de disponibilidad "solo con stock".
        Index(
            "ix_products_in_stock",
            "product_type",
            "game_id",
            "price_clp",
            postgresql_where=text("stock > 0"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    product_type: Mapped[str] = mapped_column(String(16))
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id"))
    set_id: Mapped[int | None] = mapped_column(ForeignKey("sets.id"))
    # Desnormalizado: el listado muestra el set sin JOIN y entra en la búsqueda.
    set_name: Mapped[str | None] = mapped_column(String(160))

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str] = mapped_column(String(255))
    thumb_path: Mapped[str] = mapped_column(String(255))

    price_clp: Mapped[int] = mapped_column(Integer)
    compare_at_price_clp: Mapped[int | None] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ---- Solo cartas ----
    rarity: Mapped[str | None] = mapped_column(String(64))  # rareza original del juego
    rarity_tier: Mapped[str | None] = mapped_column(String(16))  # escala común de la tienda
    condition: Mapped[str | None] = mapped_column(String(2))
    language: Mapped[str | None] = mapped_column(String(2))
    is_foil: Mapped[bool] = mapped_column(Boolean, default=False)
    card_number: Mapped[str | None] = mapped_column(String(32))
    card_type: Mapped[str | None] = mapped_column(String(120))
    source_api: Mapped[str | None] = mapped_column(String(24))
    external_id: Mapped[str | None] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    # ---- Solo sellados / accesorios ----
    sealed_type: Mapped[str | None] = mapped_column(String(24))
    accessory_type: Mapped[str | None] = mapped_column(String(24))
    units_per_item: Mapped[int | None] = mapped_column(Integer)

    # Columna generada por PostgreSQL: se mantiene sola al insertar/actualizar.
    # Configuración 'simple' (sin stemming) porque los nombres mezclan idiomas.
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple', coalesce(name, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(set_name, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(card_type, '') || ' ' || "
            "coalesce(rarity, '') || ' ' || coalesce(card_number, '')), 'C')",
            persisted=True,
        ),
    )

    game: Mapped[Game | None] = relationship()
    card_set: Mapped[CardSet | None] = relationship()


class PriceHistory(Base):
    """Precio diario de un producto, para la sección opcional "mayor variación de precio"."""

    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("product_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    price_clp: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[date] = mapped_column(Date)
