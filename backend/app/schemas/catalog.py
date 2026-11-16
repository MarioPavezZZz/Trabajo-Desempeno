"""Esquemas de respuesta del catálogo (Pydantic).

Los precios van en CLP como enteros. Las imágenes se entregan como URL
listas para usar (prefijo `MEDIA_BASE_URL`, por defecto `/media`).
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class GameOut(BaseModel):
    """Juego con la cantidad de productos activos."""

    slug: str
    name: str
    product_count: int = 0
    logo: str | None = None  # logo del set más reciente (para el mosaico del home)


class SetOut(BaseModel):
    """Set o expansión."""

    id: int
    code: str
    name: str
    game: str
    release_date: date | None
    logo: str | None


class ProductSummary(BaseModel):
    """Producto en listados (liviano: solo lo que muestra una tarjeta)."""

    id: int
    slug: str
    name: str
    product_type: str
    game: str | None
    set_name: str | None
    thumb: str
    price_clp: int
    compare_at_price_clp: int | None
    discount_pct: int | None
    stock: int
    rarity: str | None
    rarity_tier: str | None
    condition: str | None
    language: str | None
    is_foil: bool
    sealed_type: str | None
    accessory_type: str | None
    created_at: datetime


class ProductDetail(ProductSummary):
    """Producto completo para la página de detalle."""

    image: str
    description: str | None
    card_number: str | None
    card_type: str | None
    units_per_item: int | None
    attributes: dict[str, Any]
    set: SetOut | None
    game_name: str | None


class ProductPage(BaseModel):
    """Página de resultados del listado."""

    items: list[ProductSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class FacetValue(BaseModel):
    """Un valor posible de un filtro con su cantidad de productos."""

    value: str
    label: str
    count: int


class PriceRange(BaseModel):
    """Precio mínimo y máximo de los resultados."""

    min: int | None
    max: int | None


class Facets(BaseModel):
    """Conteos por filtro, calculados con los filtros activos."""

    total: int
    product_types: list[FacetValue]
    games: list[FacetValue]
    sets: list[FacetValue]
    rarity_tiers: list[FacetValue]
    conditions: list[FacetValue]
    languages: list[FacetValue]
    foil: list[FacetValue]
    price: PriceRange


class HeroRelease(BaseModel):
    """Lanzamiento destacado: set reciente y sus productos sellados."""

    set: SetOut
    products: list[ProductSummary]


class PriceMover(BaseModel):
    """Carta con su variación de precio en el período del historial."""

    product: ProductSummary
    old_price_clp: int
    change_pct: float


class HomeOut(BaseModel):
    """Todos los bloques del home en una respuesta."""

    hero: list[HeroRelease]
    games: list[GameOut]
    new_arrivals: list[ProductSummary]
    featured_sealed: list[ProductSummary]
    offers: list[ProductSummary]
    price_movers: list[PriceMover]


class HealthOut(BaseModel):
    """Estado del servicio."""

    status: str
    db: str
    db_latency_ms: float | None
