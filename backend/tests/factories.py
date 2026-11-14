"""Datos normalizados mínimos de ejemplo (sin red) para probar la generación."""

from scripts.seed.records import RawCard, RawSet


def sample_sets() -> list[RawSet]:
    """Dos sets por juego, con y sin logo."""
    sets = []
    for game in ("pokemon", "magic", "yugioh"):
        for i, release in enumerate(("2024-03-22", "2024-11-08")):
            sets.append(
                RawSet(
                    game=game,
                    code=f"{game[:2].upper()}{i}",
                    name=f"Expansión {game} {i}",
                    release_date=release,
                    card_count=100,
                    source_api="test",
                    logo_path=f"sets/{game}/{i}.webp" if i else None,
                )
            )
    return sets


def sample_cards(n_per_game: int = 40) -> list[RawCard]:
    """Cartas variadas: con y sin precio, con los tres modos de foil y varias rarezas."""
    rarities = {
        "pokemon": ["Common", "Uncommon", "Rare", "Double Rare", "Special Illustration Rare"],
        "magic": ["common", "uncommon", "rare", "mythic", "special"],
        "yugioh": ["Common", "Rare", "Super Rare", "Secret Rare", "Starlight Rare"],
    }
    modes = ["never", "optional", "always"]
    cards = []
    for game, rlist in rarities.items():
        for i in range(n_per_game):
            cards.append(
                RawCard(
                    game=game,
                    set_code=f"{game[:2].upper()}{i % 2}",
                    set_name=f"Expansión {game} {i % 2}",
                    external_id=f"{game}-{i}",
                    name=f"Carta {game} número {i}",
                    number=str(i + 1),
                    rarity=rlist[i % len(rlist)],
                    card_type="Tipo",
                    usd_price=None if i % 4 == 0 else round(0.1 + i * 0.7, 2),
                    usd_foil_price=None if i % 3 else round(1 + i, 2),
                    foil_mode=modes[i % 3],  # type: ignore[arg-type]
                    image_url=None,
                    source_api="test",
                    image_path=f"cards/{game}/{i}.webp",
                    thumb_path=f"cards/{game}/{i}_thumb.webp",
                )
            )
    return cards
