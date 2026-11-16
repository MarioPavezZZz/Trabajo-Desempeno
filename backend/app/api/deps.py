"""Dependencias compartidas por las rutas."""

import uuid
from collections.abc import AsyncIterator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import read_session_token
from app.db.session import SessionLocal


async def get_session() -> AsyncIterator[AsyncSession]:
    """Sesión de base de datos por petición (la conexión vuelve al pool al terminar)."""
    async with SessionLocal() as session:
        yield session


def current_user_id(request: Request) -> int | None:
    """Id del usuario según la cookie de sesión, o None si no es válida (no consulta la BD)."""
    return read_session_token(request.cookies.get(get_settings().session_cookie))


def require_user_id(request: Request) -> int:
    """Como `current_user_id`, pero responde 401 si no hay sesión."""
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar")
    return user_id


def traffic_type(request: Request) -> str:
    """`load_test` si la petición lo declara (k6 envía X-Traffic-Type); si no, `real`."""
    return "load_test" if request.headers.get("x-traffic-type") == "load_test" else "real"


def cart_cookie_id(request: Request) -> uuid.UUID | None:
    """Id del carrito anónimo guardado en cookie (None si falta o no es un UUID válido)."""
    raw = request.cookies.get(get_settings().cart_cookie)
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None
