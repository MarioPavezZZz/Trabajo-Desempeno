"""Estructuras de datos del seed.

`RawSet` y `RawCard` son la forma normalizada de lo que entregan las APIs
(una sola forma para los tres juegos). Se guardan en
`data/cache/normalized.json`; la fase `load` trabaja solo con ese archivo, sin
red, lo que hace la carga 100 % reproducible.

`ProductRow` y `SetRow` son lo que se inserta en la base.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal

FoilMode = Literal["never", "optional", "always"]


@dataclass
class RawSet:
    """Set/expansión tal como se obtuvo de la API, ya normalizado."""

    game: str
    code: str
    name: str
    release_date: str | None
    card_count: int | None
    source_api: str
    logo_url: str | None = None
    # Ruta relativa a data/media; la completa la fase fetch.
    logo_path: str | None = None


@dataclass
class RawCard:
    """Carta normalizada desde cualquiera de las tres APIs."""

    game: str
    set_code: str
    set_name: str
    external_id: str
    name: str
    number: str
    rarity: str | None
    card_type: str | None
    usd_price: float | None
    usd_foil_price: float | None
    foil_mode: FoilMode
    image_url: str | None
    source_api: str
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    # Rutas relativas a data/media; las completa la fase fetch.
    image_path: str | None = None
    thumb_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict (para guardar en JSON)."""
        return asdict(self)


@dataclass
class SetRow:
    """Fila de la tabla `sets` lista para insertar."""

    game: str
    code: str
    name: str
    release_date: date | None
    logo_path: str | None
    card_count: int | None


@dataclass
class ProductRow:
    """Fila de la tabla `products` lista para insertar (sin ids resueltos).

    `game` y `set_code` se traducen a `game_id` y `set_id` en el loader.
    """

    sku: str
    slug: str
    product_type: str
    game: str | None
    set_code: str | None
    set_name: str | None
    name: str
    description: str | None
    image_path: str
    thumb_path: str
    price_clp: int
    compare_at_price_clp: int | None
    stock: int
    is_featured: bool
    created_at: datetime
    rarity: str | None = None
    rarity_tier: str | None = None
    condition: str | None = None
    language: str | None = None
    is_foil: bool = False
    card_number: str | None = None
    card_type: str | None = None
    source_api: str | None = None
    external_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    sealed_type: str | None = None
    accessory_type: str | None = None
    units_per_item: int | None = None


@dataclass
class Catalog:
    """Resultado completo de la generación: lo que el loader escribe en la base."""

    games: list[tuple[str, str, int]]  # (slug, nombre, orden)
    sets: list[SetRow]
    products: list[ProductRow]
    # (sku, fecha, precio) para la tabla price_history.
    price_history: list[tuple[str, date, int]]
