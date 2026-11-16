"""Caché en memoria de datos de referencia (juegos y sets).

Juegos y sets casi no cambian, pero se necesitan en casi todas las
respuestas (slug del juego, nombre del set). Tenerlos en memoria de cada
worker evita un JOIN o una consulta extra por petición. Se recargan cada
`TTL_SECONDS` para tomar cambios del seed sin reiniciar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CardSet, Game

TTL_SECONDS = 300


@dataclass(frozen=True)
class GameRef:
    id: int
    slug: str
    name: str


@dataclass(frozen=True)
class SetRef:
    id: int
    game_id: int
    code: str
    name: str
    release_date: object
    logo_path: str | None


@dataclass
class Reference:
    """Juegos y sets indexados por id y por slug."""

    games_by_id: dict[int, GameRef]
    games_by_slug: dict[str, GameRef]
    sets_by_id: dict[int, SetRef]
    loaded_at: float


_cache: Reference | None = None


async def get_reference(session: AsyncSession) -> Reference:
    """Devuelve los datos de referencia, recargándolos si expiraron."""
    global _cache
    if _cache is None or time.monotonic() - _cache.loaded_at > TTL_SECONDS:
        games = (await session.execute(select(Game).order_by(Game.sort_order))).scalars().all()
        sets = (await session.execute(select(CardSet))).scalars().all()
        g = [GameRef(x.id, x.slug, x.name) for x in games]
        _cache = Reference(
            games_by_id={x.id: x for x in g},
            games_by_slug={x.slug: x for x in g},
            sets_by_id={
                s.id: SetRef(s.id, s.game_id, s.code, s.name, s.release_date, s.logo_path)
                for s in sets
            },
            loaded_at=time.monotonic(),
        )
    return _cache


def clear_reference_cache() -> None:
    """Fuerza la recarga en la próxima petición (usado por los tests)."""
    global _cache
    _cache = None
