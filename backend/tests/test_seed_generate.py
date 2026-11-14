"""Tests de la generación determinista del catálogo (sin red ni base de datos)."""

from collections import Counter
from datetime import date

import pytest

from app.models.catalog import (
    ACCESSORY_TYPES,
    CONDITIONS,
    LANGUAGES,
    PRODUCT_TYPES,
    RARITY_TIERS,
    SEALED_TYPES,
)
from scripts.seed.generate import (
    ACCESSORY_SPECS,
    PRICE_HISTORY_DAYS,
    SEALED_SPECS,
    build_catalog,
    rarity_tier,
    round_clp,
    slugify,
)
from tests.factories import sample_cards, sample_sets

BASE = date(2026, 11, 1)


def _catalog(seed: int = 8091):
    return build_catalog(sample_sets(), sample_cards(), seed=seed, base_date=BASE, usd_clp=950)


def test_misma_semilla_produce_mismo_catalogo():
    assert _catalog() == _catalog()


def test_otra_semilla_cambia_atributos_pero_no_los_productos():
    a, b = _catalog(1), _catalog(2)
    assert [p.name for p in a.products] == [p.name for p in b.products]
    assert [p.price_clp for p in a.products] != [p.price_clp for p in b.products]


def test_agregar_una_carta_no_altera_las_demas():
    """Cada producto tiene su propio RNG: el catálogo es estable ante cambios de la fuente."""
    cards = sample_cards()
    full = build_catalog(sample_sets(), cards, 8091, BASE, 950).products
    partial = build_catalog(sample_sets(), cards[1:], 8091, BASE, 950).products
    by_name = {p.name: p for p in full}
    for p in partial:
        assert by_name[p.name] == p


def test_sku_y_slug_unicos():
    products = _catalog().products
    assert len({p.sku for p in products}) == len(products)
    assert len({p.slug for p in products}) == len(products)


def test_valores_validos_segun_restricciones_de_la_base():
    for p in _catalog().products:
        assert p.product_type in PRODUCT_TYPES
        assert isinstance(p.price_clp, int) and p.price_clp > 0
        assert p.stock >= 0
        assert p.compare_at_price_clp is None or p.compare_at_price_clp > p.price_clp
        if p.product_type == "carta":
            assert p.condition in CONDITIONS
            assert p.rarity_tier in RARITY_TIERS
            assert p.language in LANGUAGES
            assert p.set_code
        if p.product_type == "sellado":
            assert p.sealed_type in SEALED_TYPES and p.set_code
        if p.product_type == "accesorio":
            assert p.accessory_type in ACCESSORY_TYPES and p.game is None


def test_precios_clp_terminan_en_90():
    assert all(p.price_clp % 100 == 90 for p in _catalog().products)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(1234, 1290), (1200, 1190), (1201, 1290), (10, 290), (0.5, 290)],
)
def test_round_clp(amount, expected):
    assert round_clp(amount) == expected


def test_sellados_por_juego_y_set():
    catalog = _catalog()
    sealed = [p for p in catalog.products if p.product_type == "sellado"]
    assert len(sealed) == sum(len(SEALED_SPECS[s.game]) for s in catalog.sets)
    for game, specs in SEALED_SPECS.items():
        expected = {t for t, *_ in specs}
        assert {p.sealed_type for p in sealed if p.game == game} == expected


def test_display_cuesta_mas_que_sobre_pero_menos_que_sobres_sueltos():
    sealed = [p for p in _catalog().products if p.product_type == "sellado"]
    for set_code in {p.set_code for p in sealed}:
        by_type = {p.sealed_type: p for p in sealed if p.set_code == set_code}
        pack, display = by_type["sobre"], by_type["display"]
        assert display.price_clp > pack.price_clp
        assert display.price_clp < pack.price_clp * display.units_per_item


def test_set_mas_reciente_queda_destacado():
    sealed = [p for p in _catalog().products if p.product_type == "sellado"]
    featured_sets = {p.set_code for p in sealed if p.is_featured}
    assert featured_sets == {"PO1", "MA1", "YU1"}  # los sets con fecha 2024-11-08


def test_set_sin_logo_usa_imagen_de_reemplazo():
    sealed = [p for p in _catalog().products if p.product_type == "sellado" and p.set_code == "PO0"]
    assert all(p.image_path.startswith("placeholders/") for p in sealed)


def test_cantidad_de_accesorios():
    accessories = [p for p in _catalog().products if p.product_type == "accesorio"]
    assert len(accessories) == sum(len(v) for *_, v in ACCESSORY_SPECS)


def test_foil_respeta_lo_que_existe_en_el_juego():
    cards = {c.external_id: c for c in sample_cards()}
    for p in _catalog().products:
        if p.product_type != "carta":
            continue
        mode = cards[p.external_id].foil_mode
        if mode == "never":
            assert not p.is_foil
        if mode == "always":
            assert p.is_foil


def test_distribucion_de_condiciones_es_razonable():
    conditions = Counter(p.condition for p in _catalog().products if p.product_type == "carta")
    assert conditions["NM"] > conditions["HP"]


def test_historial_de_precios():
    catalog = _catalog()
    n_cards = sum(1 for p in catalog.products if p.product_type == "carta")
    assert len(catalog.price_history) == n_cards * PRICE_HISTORY_DAYS
    prices = {p.sku: p.price_clp for p in catalog.products}
    for sku, day, price in catalog.price_history:
        if day == BASE:  # el último día coincide con el precio actual
            assert price == prices[sku]


@pytest.mark.parametrize(
    ("game", "rarity", "tier"),
    [
        ("magic", "mythic", "epica"),
        ("magic", "common", "comun"),
        ("pokemon", "Special Illustration Rare", "legendaria"),
        ("pokemon", "Double Rare", "epica"),
        ("pokemon", "Rare", "rara"),
        ("pokemon", "Uncommon", "infrecuente"),
        ("yugioh", "Starlight Rare", "legendaria"),
        ("yugioh", "Secret Rare", "epica"),
        ("yugioh", "Super Rare", "rara"),
        ("yugioh", "Rare", "infrecuente"),
        ("yugioh", None, "comun"),
    ],
)
def test_rarity_tier(game, rarity, tier):
    assert rarity_tier(game, rarity) == tier


def test_slugify():
    assert slugify("Pokémon: ¡Chispas Fulgurantes! 151") == "pokemon-chispas-fulgurantes-151"
