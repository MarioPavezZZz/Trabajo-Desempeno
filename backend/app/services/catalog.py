"""Consultas del catálogo: listado con filtros, búsqueda, facetas, detalle y home.

Notas de desempeño (útiles para el informe de la Fase 2):
- Se usa SQLAlchemy Core (filas, no objetos ORM) en listados: menos CPU por fila.
- El juego se filtra por `game_id` (resuelto en memoria desde el slug), sin JOIN.
- La búsqueda combina full-text con prefijos (índice GIN `ix_products_search`)
  y similitud por trigramas sobre el nombre (índice GIN `ix_products_name_trgm`).
- Las facetas se calculan en UNA sola consulta con GROUPING SETS.
- El total del listado es un `count(*)` exacto: barato con cientos de filas,
  costoso con millones (punto a discutir en el análisis de cuellos de botella).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    func,
    literal,
    or_,
    select,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import PriceHistory, Product
from app.services.reference import Reference, SetRef

SortOption = Literal["relevance", "newest", "price_asc", "price_desc", "name"]
ProductType = Literal["carta", "sellado", "accesorio"]

LANGUAGE_LABELS = {"EN": "Inglés", "ES": "Español", "JA": "Japonés"}
CONDITION_LABELS = {
    "NM": "Near Mint (NM)",
    "LP": "Lightly Played (LP)",
    "MP": "Moderately Played (MP)",
    "HP": "Heavily Played (HP)",
}
RARITY_LABELS = {
    "comun": "Común",
    "infrecuente": "Infrecuente",
    "rara": "Rara",
    "epica": "Épica",
    "legendaria": "Legendaria",
}
TYPE_LABELS = {"carta": "Cartas", "sellado": "Sellados", "accesorio": "Accesorios"}

# Columnas de una tarjeta de listado (lo mínimo para dibujarla).
SUMMARY_COLUMNS = (
    Product.id,
    Product.slug,
    Product.name,
    Product.product_type,
    Product.game_id,
    Product.set_name,
    Product.thumb_path,
    Product.price_clp,
    Product.compare_at_price_clp,
    Product.stock,
    Product.rarity,
    Product.rarity_tier,
    Product.condition,
    Product.language,
    Product.is_foil,
    Product.sealed_type,
    Product.accessory_type,
    Product.created_at,
)


@dataclass
class ProductFilters:
    """Filtros del listado (todos opcionales; las listas se combinan con OR)."""

    product_type: ProductType | None = None
    games: list[str] = field(default_factory=list)
    set_ids: list[int] = field(default_factory=list)
    rarity_tiers: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    foil: bool | None = None
    min_price: int | None = None
    max_price: int | None = None
    in_stock: bool = False
    on_sale: bool = False
    q: str | None = None


# =============================================================================
# Utilidades
# =============================================================================
def media_url(path: str | None) -> str | None:
    """Ruta relativa en data/media -> URL pública."""
    if not path:
        return None
    return f"{get_settings().media_base_url}/{path}"


def prefix_tsquery(text: str) -> str | None:
    """Convierte texto libre en un tsquery con prefijos: "chari ex" -> "chari:* & ex:*".

    Solo se conservan caracteres de palabra, así el texto del usuario nunca
    puede inyectar operadores de tsquery.
    """
    tokens = re.findall(r"\w+", text.lower())[:8]
    return " & ".join(f"{t}:*" for t in tokens) or None


def _search_parts(q: str) -> tuple[ColumnElement[bool], ColumnElement[float]] | None:
    """Condición de búsqueda y puntaje de relevancia para el texto `q`."""
    tsq_text = prefix_tsquery(q)
    if not tsq_text:
        return None
    tsq = func.to_tsquery("simple", tsq_text)
    q_lit = literal(q)
    # `q <% name`: similitud por palabra (tolera errores de tipeo). Se aplica sobre
    # `name` sin transformar para que use el índice trigram (pg_trgm ya ignora mayúsculas).
    condition = or_(Product.search_vector.op("@@")(tsq), q_lit.op("<%")(Product.name))
    score = func.ts_rank(Product.search_vector, tsq) + func.word_similarity(q_lit, Product.name)
    return condition, score


def _discount(price: int, compare_at: int | None) -> int | None:
    if not compare_at:
        return None
    return round((1 - price / compare_at) * 100)


def summary_dict(row, ref: Reference) -> dict:
    """Fila de SUMMARY_COLUMNS -> dict compatible con ProductSummary."""
    game = ref.games_by_id.get(row.game_id) if row.game_id else None
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "product_type": row.product_type,
        "game": game.slug if game else None,
        "set_name": row.set_name,
        "thumb": media_url(row.thumb_path),
        "price_clp": row.price_clp,
        "compare_at_price_clp": row.compare_at_price_clp,
        "discount_pct": _discount(row.price_clp, row.compare_at_price_clp),
        "stock": row.stock,
        "rarity": row.rarity,
        "rarity_tier": row.rarity_tier,
        "condition": row.condition,
        "language": row.language,
        "is_foil": row.is_foil,
        "sealed_type": row.sealed_type,
        "accessory_type": row.accessory_type,
        "created_at": row.created_at,
    }


def set_dict(s: SetRef, ref: Reference) -> dict:
    """SetRef -> dict compatible con SetOut."""
    return {
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "game": ref.games_by_id[s.game_id].slug,
        "release_date": s.release_date,
        "logo": media_url(s.logo_path),
    }


# =============================================================================
# Listado y facetas
# =============================================================================
def _filter_conditions(f: ProductFilters, ref: Reference) -> list[ColumnElement[bool]]:
    """Traduce los filtros a condiciones SQL."""
    conds: list[ColumnElement[bool]] = [Product.is_active.is_(True)]
    if f.product_type:
        conds.append(Product.product_type == f.product_type)
    if f.games:
        ids = [ref.games_by_slug[g].id for g in f.games if g in ref.games_by_slug]
        conds.append(Product.game_id.in_(ids or [-1]))  # juego inexistente -> sin resultados
    if f.set_ids:
        conds.append(Product.set_id.in_(f.set_ids))
    if f.rarity_tiers:
        conds.append(Product.rarity_tier.in_(f.rarity_tiers))
    if f.conditions:
        conds.append(Product.condition.in_(f.conditions))
    if f.languages:
        conds.append(Product.language.in_(f.languages))
    if f.foil is not None:
        conds.append(Product.is_foil.is_(f.foil))
    if f.min_price is not None:
        conds.append(Product.price_clp >= f.min_price)
    if f.max_price is not None:
        conds.append(Product.price_clp <= f.max_price)
    if f.in_stock:
        conds.append(Product.stock > 0)
    if f.on_sale:
        conds.append(Product.compare_at_price_clp.is_not(None))
    if f.q:
        search = _search_parts(f.q)
        if search:
            conds.append(search[0])
    return conds


def _order_by(sort: SortOption, f: ProductFilters) -> list:
    """Orden del listado; siempre termina en `id` para que la paginación sea estable."""
    if sort == "relevance":
        search = _search_parts(f.q) if f.q else None
        if search:
            return [search[1].desc(), Product.id]
        sort = "newest"
    return {
        "newest": [Product.created_at.desc(), Product.id.desc()],
        "price_asc": [Product.price_clp.asc(), Product.id],
        "price_desc": [Product.price_clp.desc(), Product.id],
        "name": [Product.name.asc(), Product.id],
    }[sort]


async def list_products(
    session: AsyncSession,
    ref: Reference,
    f: ProductFilters,
    sort: SortOption,
    page: int,
    page_size: int,
) -> dict:
    """Página de productos + total de resultados."""
    conds = _filter_conditions(f, ref)
    total = await session.scalar(select(func.count()).select_from(Product).where(*conds)) or 0
    stmt: Select = (
        select(*SUMMARY_COLUMNS)
        .where(*conds)
        .order_by(*_order_by(sort, f))
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "items": [summary_dict(r, ref) for r in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


FACET_COLUMNS = (
    Product.product_type,
    Product.game_id,
    Product.set_id,
    Product.rarity_tier,
    Product.condition,
    Product.language,
    Product.is_foil,
)


async def product_facets(session: AsyncSession, ref: Reference, f: ProductFilters) -> dict:
    """Conteos por filtro en una sola consulta (GROUPING SETS).

    Cada fila del resultado pertenece a uno de los conjuntos de agrupación; la
    función GROUPING() indica cuál (0 = la columna es parte del grupo).
    """
    conds = _filter_conditions(f, ref)
    grouping_flags = [func.grouping(c).label(f"g{i}") for i, c in enumerate(FACET_COLUMNS)]
    stmt = (
        select(
            *FACET_COLUMNS,
            *grouping_flags,
            func.count().label("n"),
            func.min(Product.price_clp).label("pmin"),
            func.max(Product.price_clp).label("pmax"),
        )
        .where(*conds)
        .group_by(func.grouping_sets(*(tuple_(c) for c in FACET_COLUMNS)))
    )
    rows = (await session.execute(stmt)).all()

    buckets: dict[str, list[dict]] = {
        k: [] for k in ("type", "game", "set", "rar", "cond", "lang", "foil")
    }
    keys = list(buckets)
    total, pmin, pmax = 0, None, None
    for r in rows:
        flags = [getattr(r, f"g{i}") for i in range(len(FACET_COLUMNS))]
        idx = flags.index(0)
        value = r[idx]
        if idx == 0:  # por tipo de producto: cada producto cae en exactamente un grupo
            total += r.n
            pmin = r.pmin if pmin is None else min(pmin, r.pmin)
            pmax = r.pmax if pmax is None else max(pmax, r.pmax)
        if value is None:
            continue  # p. ej. accesorios sin set o sin rareza
        buckets[keys[idx]].append({"value": value, "n": r.n})

    def fv(items: list[dict], label) -> list[dict]:
        return [
            {"value": str(i["value"]), "label": label(i["value"]), "count": i["n"]} for i in items
        ]

    # Los juegos se exponen por slug (es lo que recibe el filtro `game`), no por id.
    games_sorted = [
        {"value": ref.games_by_id[i["value"]].slug, "n": i["n"]}
        for i in sorted(buckets["game"], key=lambda i: i["value"])
    ]
    sets_sorted = sorted(
        buckets["set"],
        key=lambda i: str(ref.sets_by_id[i["value"]].release_date or ""),
        reverse=True,
    )
    return {
        "total": total,
        "product_types": fv(buckets["type"], lambda v: TYPE_LABELS.get(v, v)),
        "games": fv(games_sorted, lambda v: ref.games_by_slug[v].name),
        "sets": fv(sets_sorted, lambda v: ref.sets_by_id[v].name),
        "rarity_tiers": fv(
            sorted(buckets["rar"], key=lambda i: list(RARITY_LABELS).index(i["value"])),
            lambda v: RARITY_LABELS.get(v, v),
        ),
        "conditions": fv(
            sorted(buckets["cond"], key=lambda i: list(CONDITION_LABELS).index(i["value"])),
            lambda v: CONDITION_LABELS.get(v, v),
        ),
        "languages": fv(buckets["lang"], lambda v: LANGUAGE_LABELS.get(v, v)),
        "foil": fv(
            sorted(buckets["foil"], key=lambda i: not i["value"]),
            lambda v: "Foil" if v else "Normal",
        ),
        "price": {"min": pmin, "max": pmax},
    }


# =============================================================================
# Detalle y relacionados
# =============================================================================
async def get_product(session: AsyncSession, ref: Reference, slug: str) -> dict | None:
    """Producto activo por slug, con datos del set y del juego."""
    stmt = select(
        *SUMMARY_COLUMNS,
        Product.set_id,
        Product.image_path,
        Product.description,
        Product.card_number,
        Product.card_type,
        Product.units_per_item,
        Product.attributes,
    ).where(Product.slug == slug, Product.is_active.is_(True))
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    data = summary_dict(row, ref)
    s = ref.sets_by_id.get(row.set_id) if row.set_id else None
    game = ref.games_by_id.get(row.game_id) if row.game_id else None
    data.update(
        image=media_url(row.image_path),
        description=row.description,
        card_number=row.card_number,
        card_type=row.card_type,
        units_per_item=row.units_per_item,
        attributes=row.attributes or {},
        set=set_dict(s, ref) if s else None,
        game_name=game.name if game else None,
        _set_id=row.set_id,
    )
    return data


async def related_products(
    session: AsyncSession, ref: Reference, product: dict, limit: int = 8
) -> list[dict]:
    """Relacionados con stock: mismo set con precio parecido; si faltan, mismo juego y rareza."""
    base = [Product.is_active.is_(True), Product.stock > 0, Product.id != product["id"]]
    closeness = func.abs(Product.price_clp - product["price_clp"])
    if product["product_type"] == "accesorio":
        first = and_(*base, Product.accessory_type == product["accessory_type"])
    else:
        first = and_(*base, Product.set_id == product["_set_id"])
    rows = (
        await session.execute(
            select(*SUMMARY_COLUMNS).where(first).order_by(closeness, Product.id).limit(limit)
        )
    ).all()
    if len(rows) < limit and product["game"]:
        seen = [r.id for r in rows] or [-1]
        game_id = ref.games_by_slug[product["game"]].id
        extra = and_(
            *base,
            Product.id.not_in(seen),
            Product.game_id == game_id,
            Product.product_type == product["product_type"],
        )
        if product["rarity_tier"]:
            extra = and_(extra, Product.rarity_tier == product["rarity_tier"])
        rows += (
            await session.execute(
                select(*SUMMARY_COLUMNS)
                .where(extra)
                .order_by(closeness, Product.id)
                .limit(limit - len(rows))
            )
        ).all()
    return [summary_dict(r, ref) for r in rows]


# =============================================================================
# Home
# =============================================================================
async def new_arrivals(
    session: AsyncSession, ref: Reference, game: str | None, limit: int = 12
) -> list[dict]:
    """Últimas cartas ingresadas con stock, opcionalmente de un juego."""
    conds = [Product.is_active.is_(True), Product.product_type == "carta", Product.stock > 0]
    if game:
        g = ref.games_by_slug.get(game)
        conds.append(Product.game_id == (g.id if g else -1))
    stmt = (
        select(*SUMMARY_COLUMNS)
        .where(*conds)
        .order_by(Product.created_at.desc(), Product.id.desc())
        .limit(limit)
    )
    return [summary_dict(r, ref) for r in (await session.execute(stmt)).all()]


async def home(session: AsyncSession, ref: Reference) -> dict:
    """Arma todos los bloques del home (6 consultas cortas, secuenciales)."""
    active = Product.is_active.is_(True)

    # Lanzamientos: set más reciente de cada juego + sus sellados.
    latest_sets: dict[int, SetRef] = {}
    for s in ref.sets_by_id.values():
        cur = latest_sets.get(s.game_id)
        if s.release_date and (cur is None or s.release_date > cur.release_date):
            latest_sets[s.game_id] = s
    hero_sets = sorted(latest_sets.values(), key=lambda s: s.release_date, reverse=True)
    sealed_rows = (
        await session.execute(
            select(*SUMMARY_COLUMNS, Product.set_id)
            .where(active, Product.product_type == "sellado")
            .where(Product.set_id.in_([s.id for s in hero_sets] or [-1]))
            .order_by(Product.price_clp)
        )
    ).all()
    hero = [
        {
            "set": set_dict(s, ref),
            "products": [summary_dict(r, ref) for r in sealed_rows if r.set_id == s.id],
        }
        for s in hero_sets
    ]

    # Mosaicos de juegos con conteo de productos activos.
    counts = dict(
        (
            await session.execute(
                select(Product.game_id, func.count()).where(active).group_by(Product.game_id)
            )
        ).all()
    )
    games = [
        {
            "slug": g.slug,
            "name": g.name,
            "product_count": counts.get(g.id, 0),
            "logo": media_url(latest_sets[g.id].logo_path) if g.id in latest_sets else None,
        }
        for g in ref.games_by_id.values()
    ]

    featured = (
        await session.execute(
            select(*SUMMARY_COLUMNS)
            .where(active, Product.product_type == "sellado", Product.stock > 0)
            .order_by(Product.is_featured.desc(), Product.created_at.desc(), Product.id)
            .limit(8)
        )
    ).all()

    discount = (
        (Product.compare_at_price_clp - Product.price_clp) * 1.0 / Product.compare_at_price_clp
    )
    offers = (
        await session.execute(
            select(*SUMMARY_COLUMNS)
            .where(active, Product.compare_at_price_clp.is_not(None), Product.stock > 0)
            .order_by(discount.desc(), Product.id)
            .limit(12)
        )
    ).all()

    return {
        "hero": hero,
        "games": games,
        "new_arrivals": await new_arrivals(session, ref, None),
        "featured_sealed": [summary_dict(r, ref) for r in featured],
        "offers": [summary_dict(r, ref) for r in offers],
        "price_movers": await price_movers(session, ref),
    }


async def price_movers(session: AsyncSession, ref: Reference, limit: int = 8) -> list[dict]:
    """Cartas con mayor variación entre el primer y el último día del historial.

    Es la consulta más pesada del home (autounión sobre price_history), útil
    como contraste de "carga de datos" frente a las consultas simples.
    """
    bounds = select(
        func.min(PriceHistory.recorded_at).label("first_day"),
        func.max(PriceHistory.recorded_at).label("last_day"),
    ).subquery()
    old = PriceHistory.__table__.alias("old")
    new = PriceHistory.__table__.alias("new")
    change = (new.c.price_clp - old.c.price_clp) * 1.0 / old.c.price_clp
    stmt = (
        select(*SUMMARY_COLUMNS, old.c.price_clp.label("old_price"), change.label("change"))
        .select_from(new)
        .join(bounds, new.c.recorded_at == bounds.c.last_day)
        .join(
            old,
            and_(old.c.product_id == new.c.product_id, old.c.recorded_at == bounds.c.first_day),
        )
        .join(Product, Product.id == new.c.product_id)
        .where(Product.is_active.is_(True), Product.stock > 0)
        .order_by(func.abs(change).desc(), Product.id)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "product": summary_dict(r, ref),
            "old_price_clp": r.old_price,
            "change_pct": round(float(r.change) * 100, 1),
        }
        for r in rows
    ]
