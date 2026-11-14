"""Descarga y normalización de cartas desde las APIs públicas.

Fuentes (todas gratuitas y sin scraping):
- Magic: The Gathering -> Scryfall (https://scryfall.com/docs/api).
  Pide 50-100 ms entre peticiones y un User-Agent identificable.
- Pokémon TCG -> TCGdex (https://tcgdex.dev). Se eligió en lugar de la
  Pokémon TCG API porque esta respondió 500/502 en 3 de 5 sets al validar
  (2026-11-14); usar una sola fuente por juego mantiene el catálogo idéntico
  entre máquinas.
- Yu-Gi-Oh! -> YGOPRODeck (https://ygoprodeck.com/api-guide/). Límite de
  20 peticiones/s y pide descargar las imágenes en vez de enlazarlas.

Cada función devuelve (sets, cartas) ya normalizados. La selección de cartas
usa la semilla fija, así que con la misma semilla siempre se eligen las mismas.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Iterable
from typing import Any

from scripts.seed.http_client import PoliteClient
from scripts.seed.records import FoilMode, RawCard, RawSet

log = logging.getLogger("seed.sources")

# Sets elegidos por juego (códigos verificados contra cada API el 2026-11-14).
MAGIC_SETS = ("fdn", "dsk", "blb", "mh3", "otj")
POKEMON_SETS = ("sv08", "sv07", "sv06", "sv05", "sv03.5")
YUGIOH_SETS = (
    "Alliance Insight",
    "Supreme Darkness",
    "Rage of the Abyss",
    "The Infinite Forbidden",
    "Legacy of Destruction",
)

SCRYFALL = "https://api.scryfall.com"
TCGDEX = "https://api.tcgdex.net/v2/en"
YGOPRODECK = "https://db.ygoprodeck.com/api/v7"


def pick(items: list[Any], k: int, seed: int, salt: str) -> list[Any]:
    """Elige `k` elementos de forma determinista (misma semilla -> misma selección).

    La lista se espera ya ordenada por un criterio estable (p. ej. número de carta).
    """
    rng = random.Random(f"{seed}:{salt}")
    if len(items) <= k:
        return list(items)
    chosen = rng.sample(range(len(items)), k)
    return [items[i] for i in sorted(chosen)]


def _to_float(value: Any) -> float | None:
    """Convierte precios que llegan como string/None a float (> 0) o None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# =============================================================================
# Magic: The Gathering (Scryfall)
# =============================================================================
def _magic_foil_mode(finishes: Iterable[str]) -> FoilMode:
    finishes = set(finishes)
    if "foil" in finishes and "nonfoil" in finishes:
        return "optional"
    if "foil" in finishes or "etched" in finishes:
        return "always"
    return "never"


def fetch_magic(
    client: PoliteClient, per_set: int, seed: int
) -> tuple[list[RawSet], list[RawCard]]:
    """Obtiene sets y cartas de Magic desde Scryfall."""
    sets: list[RawSet] = []
    cards: list[RawCard] = []
    for code in MAGIC_SETS:
        info = client.get_json("scryfall", f"{SCRYFALL}/sets/{code}")
        sets.append(
            RawSet(
                game="magic",
                code=code.upper(),
                name=info["name"],
                release_date=info.get("released_at"),
                card_count=info.get("card_count"),
                source_api="scryfall",
                logo_url=info.get("icon_svg_uri"),
            )
        )
        # Primera página de la búsqueda (hasta 175 cartas de sobre), sin tierras básicas.
        page = client.get_json(
            "scryfall",
            f"{SCRYFALL}/cards/search",
            {"q": f"set:{code} is:booster lang:en -type:basic", "order": "set", "unique": "prints"},
        )
        pool = sorted(
            page["data"], key=lambda c: (len(c["collector_number"]), c["collector_number"])
        )
        for c in pick(pool, per_set, seed, f"magic:{code}"):
            face = (c.get("card_faces") or [{}])[0]
            images = c.get("image_uris") or face.get("image_uris") or {}
            prices = c.get("prices") or {}
            cards.append(
                RawCard(
                    game="magic",
                    set_code=code.upper(),
                    set_name=info["name"],
                    external_id=c["id"],
                    name=c["name"],
                    number=c["collector_number"],
                    rarity=c.get("rarity"),
                    card_type=c.get("type_line"),
                    usd_price=_to_float(prices.get("usd")),
                    usd_foil_price=_to_float(prices.get("usd_foil")),
                    foil_mode=_magic_foil_mode(c.get("finishes", [])),
                    image_url=images.get("normal"),
                    source_api="scryfall",
                    description=c.get("oracle_text") or face.get("oracle_text"),
                    attributes={
                        k: v
                        for k, v in {
                            "mana_cost": c.get("mana_cost") or face.get("mana_cost"),
                            "colors": c.get("colors"),
                            "artist": c.get("artist"),
                        }.items()
                        if v
                    },
                )
            )
    return sets, cards


# =============================================================================
# Pokémon TCG (TCGdex)
# =============================================================================
def _pokemon_prices(detail: dict[str, Any]) -> tuple[float | None, float | None, FoilMode]:
    """Extrae precio normal, precio foil y modo foil de una carta de TCGdex."""
    variants = detail.get("variants") or {}
    tcg = (detail.get("pricing") or {}).get("tcgplayer") or {}

    def market(key: str) -> float | None:
        return _to_float((tcg.get(key) or {}).get("marketPrice"))

    has_normal = bool(variants.get("normal"))
    has_foil = bool(variants.get("holo") or variants.get("reverse"))
    foil_price = market("holofoil") or market("reverse-holofoil")
    if has_normal and has_foil:
        mode: FoilMode = "optional"
    elif has_foil:
        mode = "always"
    else:
        mode = "never"
    normal_price = market("normal") or (foil_price if mode == "always" else None)
    return normal_price, foil_price, mode


def fetch_pokemon(
    client: PoliteClient, per_set: int, seed: int
) -> tuple[list[RawSet], list[RawCard]]:
    """Obtiene sets y cartas de Pokémon desde TCGdex (detalle por carta para rareza y precio)."""
    sets: list[RawSet] = []
    cards: list[RawCard] = []
    for code in POKEMON_SETS:
        info = client.get_json("tcgdex", f"{TCGDEX}/sets/{code}")
        logo = info.get("logo")
        sets.append(
            RawSet(
                game="pokemon",
                code=code.upper(),
                name=info["name"],
                release_date=info.get("releaseDate"),
                card_count=(info.get("cardCount") or {}).get("total"),
                source_api="tcgdex",
                logo_url=f"{logo}.png" if logo else None,
            )
        )
        pool = sorted(
            (c for c in info.get("cards", []) if c.get("image")),
            key=lambda c: (len(c["localId"]), c["localId"]),
        )
        for brief in pick(pool, per_set, seed, f"pokemon:{code}"):
            d = client.get_json("tcgdex", f"{TCGDEX}/cards/{brief['id']}")
            if not d:
                continue
            usd, usd_foil, mode = _pokemon_prices(d)
            category = d.get("category") or ""
            subtype = d.get("stage") or d.get("trainerType") or d.get("energyType") or ""
            attacks = d.get("attacks") or []
            description = (
                d.get("description")
                or d.get("effect")
                or (attacks[0].get("effect") if attacks else None)
            )
            cards.append(
                RawCard(
                    game="pokemon",
                    set_code=code.upper(),
                    set_name=info["name"],
                    external_id=d["id"],
                    name=d["name"],
                    number=d.get("localId", ""),
                    rarity=d.get("rarity"),
                    card_type=f"{category} {subtype}".strip() or None,
                    usd_price=usd,
                    usd_foil_price=usd_foil,
                    foil_mode=mode,
                    image_url=f"{d['image']}/high.webp",
                    source_api="tcgdex",
                    description=description,
                    attributes={
                        k: v
                        for k, v in {
                            "hp": d.get("hp"),
                            "types": d.get("types"),
                            "illustrator": d.get("illustrator"),
                        }.items()
                        if v
                    },
                )
            )
    return sets, cards


# =============================================================================
# Yu-Gi-Oh! (YGOPRODeck)
# =============================================================================
_YGO_NON_FOIL = {"Common", "Rare", "Short Print", "Super Short Print"}


def fetch_yugioh(
    client: PoliteClient, per_set: int, seed: int
) -> tuple[list[RawSet], list[RawCard]]:
    """Obtiene sets y cartas de Yu-Gi-Oh! desde YGOPRODeck."""
    all_sets = client.get_json("ygoprodeck", f"{YGOPRODECK}/cardsets.php")
    by_name = {s["set_name"]: s for s in all_sets}
    sets: list[RawSet] = []
    cards: list[RawCard] = []
    for set_name in YUGIOH_SETS:
        info = by_name[set_name]
        code = info["set_code"]
        sets.append(
            RawSet(
                game="yugioh",
                code=code,
                name=set_name,
                release_date=info.get("tcg_date"),
                card_count=info.get("num_of_cards"),
                source_api="ygoprodeck",
                logo_url=info.get("set_image"),
            )
        )
        resp = client.get_json("ygoprodeck", f"{YGOPRODECK}/cardinfo.php", {"cardset": set_name})
        pool = []
        for c in resp["data"] if resp else []:
            # Una carta puede aparecer en varios sets: tomamos su impresión en este set.
            entry = next((e for e in c.get("card_sets", []) if e["set_name"] == set_name), None)
            if entry and c.get("card_images"):
                pool.append((entry["set_code"], c, entry))
        pool.sort(key=lambda t: t[0])
        for number, c, entry in pick(pool, per_set, seed, f"yugioh:{code}"):
            rarity = entry.get("set_rarity")
            price = _to_float(entry.get("set_price")) or _to_float(
                (c.get("card_prices") or [{}])[0].get("tcgplayer_price")
            )
            foil = "never" if rarity in _YGO_NON_FOIL else "always"
            cards.append(
                RawCard(
                    game="yugioh",
                    set_code=code,
                    set_name=set_name,
                    external_id=f"{c['id']}-{number}",
                    name=c["name"],
                    number=number,
                    rarity=rarity,
                    card_type=c.get("humanReadableCardType") or c.get("type"),
                    usd_price=price,
                    usd_foil_price=None,
                    foil_mode=foil,  # type: ignore[arg-type]
                    image_url=c["card_images"][0]["image_url"],
                    source_api="ygoprodeck",
                    description=c.get("desc"),
                    attributes={
                        k: v
                        for k, v in {
                            "atk": c.get("atk"),
                            "def": c.get("def"),
                            "level": c.get("level"),
                            "attribute": c.get("attribute"),
                            "race": c.get("race"),
                        }.items()
                        if v is not None
                    },
                )
            )
    return sets, cards


FETCHERS = {
    "magic": fetch_magic,
    "pokemon": fetch_pokemon,
    "yugioh": fetch_yugioh,
}
