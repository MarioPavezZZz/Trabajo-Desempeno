"""Script de datos semilla de TCGMASTER (idempotente y determinista).

Fases:
  fetch  Descarga sets y cartas de las APIs públicas (con caché en
         data/cache/), descarga y convierte imágenes a data/media/ y escribe
         data/cache/normalized.json. Solo usa la red la primera vez.
  load   Lee normalized.json, genera el catálogo con la semilla fija
         (precio CLP, estado, idioma, foil, stock, sellados, accesorios) y lo
         inserta/actualiza en PostgreSQL. No usa la red.
  all    fetch + load.

Uso (dentro del contenedor):
  python scripts/seed_catalog.py all
  python scripts/seed_catalog.py load --seed 8091

Variables de entorno: SEED_RANDOM_SEED, SEED_CARDS_PER_GAME, SEED_BASE_DATE,
SEED_USD_CLP, SEED_HTTP_DELAY_MS, DATA_DIR (ver .env.example).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Permite ejecutar el archivo directamente (`python scripts/seed_catalog.py`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from scripts.seed import images  # noqa: E402
from scripts.seed.generate import CLT, build_accessories, build_catalog  # noqa: E402
from scripts.seed.http_client import PoliteClient  # noqa: E402
from scripts.seed.records import RawCard, RawSet  # noqa: E402
from scripts.seed.sources import FETCHERS  # noqa: E402

log = logging.getLogger("seed")

NORMALIZED_VERSION = 1


def _normalized_path(cache_dir: Path) -> Path:
    return cache_dir / "normalized.json"


def fetch(cards_per_game: int, seed: int) -> Path:
    """Fase 1: descarga (con caché) y normaliza datos e imágenes."""
    settings = get_settings()
    cache, media = settings.cache_dir, settings.media_dir
    all_sets: list[RawSet] = []
    all_cards: list[RawCard] = []

    with PoliteClient(cache, delay_ms=settings.seed_http_delay_ms) as client:
        for game, fetcher in FETCHERS.items():
            per_set = max(1, cards_per_game // 5)
            log.info("[%s] obteniendo %d cartas por set...", game, per_set)
            sets, cards = fetcher(client, per_set, seed)

            for s in sets:
                s.logo_path = images.ensure_set_logo(
                    client, cache, media, s.game, s.code, s.name, s.logo_url
                )
            missing = 0
            for i, c in enumerate(cards, 1):
                paths = (
                    images.ensure_card_image(
                        client, cache, media, c.game, c.external_id, c.image_url
                    )
                    if c.image_url
                    else None
                )
                if paths:
                    c.image_path, c.thumb_path = paths
                else:
                    missing += 1
                if i % 50 == 0:
                    log.info("[%s] imágenes %d/%d", game, i, len(cards))
            log.info(
                "[%s] %d sets, %d cartas (%d sin imagen)", game, len(sets), len(cards), missing
            )
            all_sets += sets
            all_cards += cards
        log.info("Peticiones de red realizadas: %d", client.network_calls)

    # Imágenes propias: reemplazo de carta y accesorios.
    images.write_text(media / images.PLACEHOLDER_CARD, images.placeholder_card_svg())
    # La fecha no influye en la imagen; solo se necesitan tipo, color y nombre.
    for acc in build_accessories(seed, datetime(2000, 1, 1, tzinfo=CLT)):
        svg = images.accessory_svg(acc.accessory_type, acc.attributes["color_hex"], acc.name)
        images.write_text(media / acc.image_path, svg)

    out = _normalized_path(cache)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": NORMALIZED_VERSION,
        "seed": seed,
        "sets": [s.__dict__ for s in all_sets],
        "cards": [c.to_dict() for c in all_cards],
    }
    images.write_text(out, json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    log.info("Normalizado: %s (%d sets, %d cartas)", out, len(all_sets), len(all_cards))
    return out


def read_normalized(cache_dir: Path) -> tuple[list[RawSet], list[RawCard]]:
    """Lee el archivo normalizado producido por `fetch`."""
    path = _normalized_path(cache_dir)
    if not path.exists():
        raise SystemExit(f"No existe {path}. Ejecuta primero: python scripts/seed_catalog.py fetch")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != NORMALIZED_VERSION:
        raise SystemExit("normalized.json tiene otra versión; vuelve a ejecutar 'fetch'.")
    return [RawSet(**s) for s in data["sets"]], [RawCard(**c) for c in data["cards"]]


async def load(seed: int) -> dict[str, int]:
    """Fase 2: genera el catálogo determinista y lo carga en la base."""
    from app.db.session import engine
    from scripts.seed.loader import load_catalog

    settings = get_settings()
    raw_sets, raw_cards = read_normalized(settings.cache_dir)
    catalog = build_catalog(
        raw_sets,
        raw_cards,
        seed=seed,
        base_date=date.fromisoformat(settings.seed_base_date),
        usd_clp=settings.seed_usd_clp,
    )
    try:
        return await load_catalog(engine, catalog)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    """Punto de entrada de la línea de comandos."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("fase", choices=["fetch", "load", "all"])
    parser.add_argument("--seed", type=int, default=settings.seed_random_seed)
    parser.add_argument(
        "--cards-per-game", type=int, default=int(os.getenv("SEED_CARDS_PER_GAME", "150"))
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # una línea por petición es demasiado
    if args.fase in ("fetch", "all"):
        fetch(args.cards_per_game, args.seed)
    if args.fase in ("load", "all"):
        counts = asyncio.run(load(args.seed))
        print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
