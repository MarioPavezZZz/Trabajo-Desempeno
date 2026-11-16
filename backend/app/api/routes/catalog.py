"""Endpoints del catálogo: juegos, sets, listado, facetas, detalle, relacionados y home."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import get_settings
from app.schemas.catalog import (
    Facets,
    GameOut,
    HomeOut,
    ProductDetail,
    ProductPage,
    ProductSummary,
    SetOut,
)
from app.services import catalog
from app.services.reference import get_reference

router = APIRouter(prefix="/api", tags=["catálogo"])
settings = get_settings()

RarityTier = Literal["comun", "infrecuente", "rara", "epica", "legendaria"]
Condition = Literal["NM", "LP", "MP", "HP"]
Language = Literal["EN", "ES", "JA"]


def product_filters(
    type: catalog.ProductType | None = Query(None, description="carta | sellado | accesorio"),  # noqa: A002
    game: list[str] = Query([], description="Slug del juego (repetible)"),
    set: list[int] = Query([], description="Id del set (repetible)"),  # noqa: A002
    rarity: list[RarityTier] = Query([]),
    condition: list[Condition] = Query([]),
    lang: list[Language] = Query([]),
    foil: bool | None = Query(None),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    in_stock: bool = Query(False, description="Solo productos con stock"),
    on_sale: bool = Query(False, description="Solo productos en oferta"),
    q: str | None = Query(None, min_length=1, max_length=100, description="Búsqueda por texto"),
) -> catalog.ProductFilters:
    """Convierte los parámetros de la URL en filtros.

    FastAPI los valida antes de llegar aquí: valores inválidos responden 422.
    """
    return catalog.ProductFilters(
        product_type=type,
        games=game,
        set_ids=set,
        rarity_tiers=list(rarity),
        conditions=list(condition),
        languages=list(lang),
        foil=foil,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        on_sale=on_sale,
        q=q.strip() if q else None,
    )


@router.get("/games", response_model=list[GameOut])
async def list_games(session: AsyncSession = Depends(get_session)):
    """Juegos disponibles."""
    ref = await get_reference(session)
    return [{"slug": g.slug, "name": g.name} for g in ref.games_by_id.values()]


@router.get("/sets", response_model=list[SetOut])
async def list_sets(game: str | None = Query(None), session: AsyncSession = Depends(get_session)):
    """Sets, del más reciente al más antiguo; opcionalmente de un juego."""
    ref = await get_reference(session)
    sets = [
        s
        for s in ref.sets_by_id.values()
        if game is None or ref.games_by_id[s.game_id].slug == game
    ]
    sets.sort(key=lambda s: str(s.release_date or ""), reverse=True)
    return [catalog.set_dict(s, ref) for s in sets]


@router.get("/products", response_model=ProductPage)
async def list_products(
    filters: catalog.ProductFilters = Depends(product_filters),
    sort: catalog.SortOption | None = Query(
        None,
        description="relevance (por defecto si hay q) | newest | price_asc | price_desc | name",
    ),
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(settings.api_page_size_default, ge=1, le=settings.api_page_size_max),
    session: AsyncSession = Depends(get_session),
):
    """Listado paginado con filtros, búsqueda y orden."""
    ref = await get_reference(session)
    effective_sort = sort or ("relevance" if filters.q else "newest")
    return await catalog.list_products(session, ref, filters, effective_sort, page, page_size)


@router.get("/products/facets", response_model=Facets)
async def product_facets(
    filters: catalog.ProductFilters = Depends(product_filters),
    session: AsyncSession = Depends(get_session),
):
    """Conteos por valor de cada filtro, aplicando los filtros activos."""
    ref = await get_reference(session)
    return await catalog.product_facets(session, ref, filters)


@router.get("/products/{slug}", response_model=ProductDetail)
async def product_detail(slug: str, session: AsyncSession = Depends(get_session)):
    """Detalle de un producto activo."""
    ref = await get_reference(session)
    product = await catalog.get_product(session, ref, slug)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


@router.get("/products/{slug}/related", response_model=list[ProductSummary])
async def product_related(slug: str, session: AsyncSession = Depends(get_session)):
    """Productos relacionados (hasta 8, con stock)."""
    ref = await get_reference(session)
    product = await catalog.get_product(session, ref, slug)
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return await catalog.related_products(session, ref, product)


@router.get("/home", response_model=HomeOut)
async def home(session: AsyncSession = Depends(get_session)):
    """Todos los bloques del home en una sola respuesta."""
    ref = await get_reference(session)
    return await catalog.home(session, ref)


@router.get("/home/new-arrivals", response_model=list[ProductSummary])
async def home_new_arrivals(
    game: str | None = Query(None), session: AsyncSession = Depends(get_session)
):
    """Novedades filtradas por juego (para el selector del home sin recargar todo)."""
    ref = await get_reference(session)
    return await catalog.new_arrivals(session, ref, game)
