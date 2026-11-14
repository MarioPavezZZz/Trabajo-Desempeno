"""Generación determinista del catálogo a partir de los datos normalizados.

Funciones puras: no usan red ni base de datos, por eso se testean directamente.

Determinismo: cada producto usa su propio generador aleatorio sembrado con
`semilla + identificador del producto`. Así, agregar o quitar una carta no
cambia los atributos de las demás, y dos ejecuciones con la misma semilla
producen exactamente el mismo catálogo (requisito para repetir pruebas de carga).
"""

from __future__ import annotations

import math
import random
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone

from scripts.seed.images import PLACEHOLDER_CARD
from scripts.seed.records import Catalog, ProductRow, RawCard, RawSet, SetRow

# Hora de Chile continental (sin horario de verano, a propósito: fechas estables).
CLT = timezone(timedelta(hours=-3))

GAMES: list[tuple[str, str, int]] = [
    ("pokemon", "Pokémon TCG", 1),
    ("magic", "Magic: The Gathering", 2),
    ("yugioh", "Yu-Gi-Oh!", 3),
]

# ---- Parámetros de negocio (documentados para el informe) ----
CONDITION_WEIGHTS = {"NM": 0.60, "LP": 0.25, "MP": 0.10, "HP": 0.05}
CONDITION_FACTOR = {"NM": 1.00, "LP": 0.85, "MP": 0.70, "HP": 0.50}
LANGUAGE_WEIGHTS = {
    "magic": {"EN": 0.70, "ES": 0.25, "JA": 0.05},
    "pokemon": {"EN": 0.50, "ES": 0.25, "JA": 0.25},
    "yugioh": {"EN": 0.60, "ES": 0.35, "JA": 0.05},
}
# Precio de referencia (USD) por rareza cuando la API no entrega precio.
FALLBACK_USD_BY_TIER = {
    "comun": 0.15,
    "infrecuente": 0.30,
    "rara": 1.50,
    "epica": 6.00,
    "legendaria": 25.00,
}
FOIL_FACTOR_WITHOUT_PRICE = 1.5  # si es foil pero la API no da precio foil
OFFER_PROBABILITY = 0.10
SOLD_OUT_PROBABILITY = 0.10
MAX_STOCK_BY_TIER = {"comun": 12, "infrecuente": 10, "rara": 6, "epica": 3, "legendaria": 2}
NEW_ARRIVALS_WINDOW_DAYS = 60
PRICE_HISTORY_DAYS = 30
MIN_PRICE_CLP = 290

# Sellados por juego: (tipo, nombre visible, unidades, precio base CLP).
# Para el display el precio se calcula desde el sobre (ver build_sealed).
SEALED_SPECS: dict[str, list[tuple[str, str, int, int | None]]] = {
    "pokemon": [
        ("sobre", "Sobre", 10, 4990),
        ("display", "Display", 36, None),
        ("caja_entrenador", "Caja de entrenador", 9, 54990),
    ],
    "magic": [
        ("sobre", "Sobre", 14, 6490),
        ("display", "Display", 36, None),
        ("mazo_estructura", "Mazo preconstruido", 60, 39990),
    ],
    "yugioh": [
        ("sobre", "Sobre", 9, 2990),
        ("display", "Display", 24, None),
        ("mazo_estructura", "Mazo de estructura", 46, 12990),
    ],
}
DISPLAY_DISCOUNT = 0.85  # el display sale más barato por sobre que comprar sueltos

# Accesorios: (tipo, nombre, unidades, precio base CLP, [(variante, color hex)]).
ACCESSORY_SPECS: list[tuple[str, str, int | None, int, list[tuple[str, str]]]] = [
    (
        "fundas",
        "Fundas mate tamaño estándar (100 u.)",
        100,
        7990,
        [
            ("Negro", "#1f1f1f"),
            ("Azul", "#2d5d9f"),
            ("Rojo", "#a83232"),
            ("Verde", "#3f7d4f"),
            ("Blanco", "#d9d4c7"),
            ("Dorado", "#b8913a"),
        ],
    ),
    (
        "fundas",
        "Fundas tamaño japonés (60 u.)",
        60,
        4990,
        [("Negro", "#1f1f1f"), ("Celeste", "#5aa6c9"), ("Rosado", "#c96a8f")],
    ),
    (
        "fundas",
        "Fundas interiores ajustadas (100 u.)",
        100,
        3990,
        [("Transparente", "#9fb3b8"), ("Ahumado", "#55575a")],
    ),
    (
        "carpeta",
        "Carpeta de 9 bolsillos (360 cartas)",
        360,
        19990,
        [("Negro", "#1f1f1f"), ("Azul", "#2d5d9f"), ("Rojo", "#a83232"), ("Verde", "#3f7d4f")],
    ),
    (
        "carpeta",
        "Carpeta de 4 bolsillos (160 cartas)",
        160,
        12990,
        [("Negro", "#1f1f1f"), ("Morado", "#5b4a7a")],
    ),
    (
        "deck_box",
        "Deck box para 100+ cartas",
        1,
        6990,
        [
            ("Negro", "#1f1f1f"),
            ("Azul", "#2d5d9f"),
            ("Rojo", "#a83232"),
            ("Verde", "#3f7d4f"),
            ("Blanco", "#d9d4c7"),
        ],
    ),
    (
        "playmat",
        "Playmat de goma 60 x 35 cm",
        1,
        17990,
        [("Bosque", "#2f5d3a"), ("Océano", "#1f4e6b"), ("Volcán", "#7a2e1f"), ("Noche", "#22253a")],
    ),
    ("toploader", "Toploaders 35 pt (25 u.)", 25, 3990, [("Transparente", "#7c8a8f")]),
    (
        "toploader",
        "Toploaders 130 pt para cartas gruesas (10 u.)",
        10,
        4990,
        [("Transparente", "#7c8a8f")],
    ),
]


# =============================================================================
# Utilidades
# =============================================================================
def slugify(value: str) -> str:
    """Texto -> slug de URL en minúsculas, sin tildes ni símbolos."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def round_clp(amount: float) -> int:
    """Redondea hacia arriba a un precio "de vitrina" terminado en 90 (p. ej. 1.234 -> 1.290)."""
    value = int(math.ceil(amount / 100.0)) * 100 - 10
    return max(value, MIN_PRICE_CLP)


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    """Elige una clave según su peso."""
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def product_rng(seed: int, key: str) -> random.Random:
    """Generador aleatorio propio de un producto (aislado del resto)."""
    return random.Random(f"{seed}:{key}")


def rarity_tier(game: str, rarity: str | None) -> str:
    """Traduce la rareza original de cada juego a la escala común de la tienda.

    Escala: comun < infrecuente < rara < epica < legendaria.
    """
    r = (rarity or "").lower()
    if game == "magic":
        return {
            "common": "comun",
            "uncommon": "infrecuente",
            "rare": "rara",
            "mythic": "epica",
        }.get(r, "legendaria" if r in {"special", "bonus"} else "comun")
    if game == "pokemon":
        if any(k in r for k in ("special illustration", "hyper", "secret", "rainbow", "gold")):
            return "legendaria"
        if any(k in r for k in ("double rare", "ultra", "illustration", "ace spec", "shiny")):
            return "epica"
        if "rare" in r:
            return "rara"
        if "uncommon" in r:
            return "infrecuente"
        return "comun"
    # Yu-Gi-Oh!
    if any(k in r for k in ("starlight", "quarter century", "ghost", "collector", "prismatic")):
        return "legendaria"
    if "secret" in r or "ultimate" in r:
        return "epica"
    if "ultra" in r or "super" in r:
        return "rara"
    if r == "rare":
        return "infrecuente"
    return "comun"


def _created_at(rng: random.Random, base: datetime, max_days: int) -> datetime:
    """Fecha de ingreso al catálogo dentro de una ventana hacia atrás desde `base`."""
    return base - timedelta(minutes=rng.randint(0, max_days * 24 * 60))


def _maybe_offer(rng: random.Random, price: int) -> int | None:
    """Con probabilidad OFFER_PROBABILITY devuelve un precio anterior (producto en oferta)."""
    if rng.random() < OFFER_PROBABILITY:
        return round_clp(price * rng.uniform(1.15, 1.40))
    return None


# =============================================================================
# Constructores
# =============================================================================
def build_sets(raw_sets: list[RawSet]) -> list[SetRow]:
    """Convierte los sets normalizados en filas de la tabla `sets`."""
    rows = []
    for s in raw_sets:
        release = date.fromisoformat(s.release_date.replace("/", "-")) if s.release_date else None
        rows.append(SetRow(s.game, s.code, s.name, release, s.logo_path, s.card_count))
    return rows


def build_card(card: RawCard, seed: int, base: datetime, usd_clp: int) -> ProductRow:
    """Genera el producto de una carta: estado, idioma, foil, precio CLP y stock."""
    rng = product_rng(seed, f"card:{card.game}:{card.external_id}")
    tier = rarity_tier(card.game, card.rarity)
    condition = weighted_choice(rng, CONDITION_WEIGHTS)
    language = weighted_choice(rng, LANGUAGE_WEIGHTS[card.game])

    if card.foil_mode == "always":
        foil = True
    elif card.foil_mode == "optional":
        foil = rng.random() < 0.25
    else:
        foil = False

    # Precio base en USD: el de la API si existe; si no, el de referencia por rareza.
    if foil and card.usd_foil_price:
        usd = card.usd_foil_price
    else:
        usd = card.usd_price or FALLBACK_USD_BY_TIER[tier]
        if foil and card.foil_mode == "optional":
            usd *= FOIL_FACTOR_WITHOUT_PRICE
    price = round_clp(usd * usd_clp * CONDITION_FACTOR[condition])

    stock = 0 if rng.random() < SOLD_OUT_PROBABILITY else rng.randint(1, MAX_STOCK_BY_TIER[tier])
    offer = _maybe_offer(rng, price)
    created = _created_at(rng, base, NEW_ARRIVALS_WINDOW_DAYS)
    featured = tier == "legendaria" and rng.random() < 0.5

    foil_tag = "F" if foil else "N"
    sku = f"{card.game[:3].upper()}-{card.set_code}-{card.number}-{condition}-{language}-{foil_tag}"
    slug = slugify(f"{card.name} {card.set_code} {card.number}") + ("-foil" if foil else "")
    image, thumb = card.image_path or PLACEHOLDER_CARD, card.thumb_path or PLACEHOLDER_CARD

    return ProductRow(
        sku=sku,
        slug=slug,
        product_type="carta",
        game=card.game,
        set_code=card.set_code,
        set_name=card.set_name,
        name=card.name,
        description=card.description,
        image_path=image,
        thumb_path=thumb,
        price_clp=price,
        compare_at_price_clp=offer,
        stock=stock,
        is_featured=featured,
        created_at=created,
        rarity=card.rarity,
        rarity_tier=tier,
        condition=condition,
        language=language,
        is_foil=foil,
        card_number=card.number,
        card_type=card.card_type,
        source_api=card.source_api,
        external_id=card.external_id,
        attributes=card.attributes,
    )


def build_sealed(sets: list[RawSet], seed: int, base: datetime) -> list[ProductRow]:
    """Genera sobres, displays, cajas y mazos para cada set, con precios coherentes."""
    newest = {}  # set más reciente por juego -> sus sellados quedan destacados
    for s in sets:
        if s.release_date and s.release_date > newest.get(s.game, ""):
            newest[s.game] = s.release_date

    products = []
    for s in sets:
        rng = product_rng(seed, f"sealed:{s.game}:{s.code}")
        jitter = rng.uniform(0.92, 1.10)  # cada set tiene su propio nivel de precio
        pack_price = None
        for sealed_type, label, units, base_price in SEALED_SPECS[s.game]:
            if sealed_type == "display":
                assert pack_price is not None, "el sobre debe definirse antes que el display"
                price = round_clp(pack_price * units * DISPLAY_DISCOUNT)
                name = f"{label} {s.name} ({units} sobres)"
            else:
                price = round_clp(base_price * jitter)  # type: ignore[operator]
                name = f"{label} {s.name}"
            if sealed_type == "sobre":
                pack_price = price
            logo = s.logo_path or PLACEHOLDER_CARD
            stock = 0 if rng.random() < 0.08 else rng.randint(1, 30)
            products.append(
                ProductRow(
                    sku=f"{s.game[:3].upper()}-{s.code}-{sealed_type.upper()}",
                    slug=slugify(f"{label} {s.name} {s.game}"),
                    product_type="sellado",
                    game=s.game,
                    set_code=s.code,
                    set_name=s.name,
                    name=name,
                    description=f"Producto sellado de la expansión {s.name}.",
                    image_path=logo,
                    thumb_path=logo,
                    price_clp=price,
                    compare_at_price_clp=_maybe_offer(rng, price),
                    stock=stock,
                    is_featured=s.release_date == newest.get(s.game),
                    created_at=_created_at(rng, base, 90),
                    language=rng.choice(["ES", "EN"]),
                    sealed_type=sealed_type,
                    units_per_item=units,
                )
            )
    return products


def accessory_image_path(slug: str) -> str:
    """Ruta relativa del SVG de un accesorio."""
    return f"accessories/{slug}.svg"


def build_accessories(seed: int, base: datetime) -> list[ProductRow]:
    """Genera los accesorios (no dependen de ninguna API)."""
    products = []
    for acc_type, label, units, base_price, variants in ACCESSORY_SPECS:
        for variant, color in variants:
            name = f"{label} — {variant}"
            slug = slugify(name)
            rng = product_rng(seed, f"acc:{slug}")
            price = round_clp(base_price * rng.uniform(0.95, 1.05))
            path = accessory_image_path(slug)
            products.append(
                ProductRow(
                    sku=f"ACC-{slugify(label)[:30].upper()}-{slugify(variant).upper()}",
                    slug=slug,
                    product_type="accesorio",
                    game=None,
                    set_code=None,
                    set_name=None,
                    name=name,
                    description=f"{label}, color {variant.lower()}.",
                    image_path=path,
                    thumb_path=path,
                    price_clp=price,
                    compare_at_price_clp=_maybe_offer(rng, price),
                    stock=0 if rng.random() < 0.05 else rng.randint(3, 40),
                    is_featured=False,
                    created_at=_created_at(rng, base, 120),
                    accessory_type=acc_type,
                    units_per_item=units,
                    attributes={"color": variant, "color_hex": color},
                )
            )
    return products


def build_price_history(
    cards: list[ProductRow], seed: int, base_day: date
) -> list[tuple[str, date, int]]:
    """Historial diario simulado (caminata aleatoria hacia atrás desde el precio actual)."""
    history = []
    for p in cards:
        rng = product_rng(seed, f"hist:{p.sku}")
        volatility = 0.01 if p.rarity_tier in ("comun", "infrecuente") else 0.04
        price = float(p.price_clp)
        for d in range(PRICE_HISTORY_DAYS):
            history.append((p.sku, base_day - timedelta(days=d), max(MIN_PRICE_CLP, round(price))))
            price = price / (1 + rng.gauss(0, volatility))
    return history


def build_catalog(
    raw_sets: list[RawSet],
    raw_cards: list[RawCard],
    seed: int,
    base_date: date,
    usd_clp: int,
) -> Catalog:
    """Construye el catálogo completo (sets, cartas, sellados, accesorios, historial)."""
    base = datetime.combine(base_date, time(12, 0), tzinfo=CLT)
    cards = [build_card(c, seed, base, usd_clp) for c in raw_cards]
    sealed = build_sealed(raw_sets, seed, base)
    accessories = build_accessories(seed, base)
    return Catalog(
        games=GAMES,
        sets=build_sets(raw_sets),
        products=cards + sealed + accessories,
        price_history=build_price_history(cards, seed, base_date),
    )
