"""Registro, inicio y cierre de sesión."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import cart_cookie_id, current_user_id, get_session
from app.core.config import get_settings
from app.core.security import (
    clear_cookie,
    hash_password,
    set_session_cookie,
    verify_password,
)
from app.models import User
from app.schemas.account import LoginIn, RegisterIn, UserOut
from app.services.cart import merge_anonymous_cart

router = APIRouter(prefix="/api/auth", tags=["cuenta"])

INVALID_LOGIN = "Correo o contraseña incorrectos"


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at,
    }


def _after_login(response: Response, user_id: int) -> None:
    """Inicia la sesión y borra la cookie del carrito anónimo (ya se fusionó)."""
    set_session_cookie(response, user_id)
    clear_cookie(response, get_settings().cart_cookie)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    data: RegisterIn,
    response: Response,
    cart_id: uuid.UUID | None = Depends(cart_cookie_id),
    session: AsyncSession = Depends(get_session),
):
    """Crea la cuenta e inicia sesión. 409 si el correo ya está registrado."""
    email = data.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo")
    user = User(
        email=email, full_name=data.full_name, password_hash=await hash_password(data.password)
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:  # dos registros simultáneos con el mismo correo
        await session.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo") from None
    await merge_anonymous_cart(session, user.id, cart_id)
    await session.commit()
    await session.refresh(user)
    _after_login(response, user.id)
    return _user_out(user)


@router.post("/login", response_model=UserOut)
async def login(
    data: LoginIn,
    response: Response,
    cart_id: uuid.UUID | None = Depends(cart_cookie_id),
    session: AsyncSession = Depends(get_session),
):
    """Inicia sesión. 401 con mensaje genérico si el correo o la contraseña no coinciden."""
    user = (await session.execute(select(User).where(User.email == data.email.lower()))).scalar()
    if not await verify_password(data.password, user.password_hash if user else None):
        raise HTTPException(status_code=401, detail=INVALID_LOGIN)
    assert user is not None
    await merge_anonymous_cart(session, user.id, cart_id)
    await session.commit()
    _after_login(response, user.id)
    return _user_out(user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    """Cierra la sesión. El carrito queda guardado en la cuenta."""
    settings = get_settings()
    clear_cookie(response, settings.session_cookie)
    clear_cookie(response, settings.cart_cookie)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut | None)
async def me(
    user_id: int | None = Depends(current_user_id), session: AsyncSession = Depends(get_session)
):
    """Usuario conectado, o `null` si no hay sesión.

    Responde 200 también sin sesión: el frontend consulta este endpoint en cada
    visita, y un 401 por cada visitante anónimo inflaría la tasa de errores
    4xx que se mide en las pruebas de carga (no hay sesión no es un error).
    """
    if user_id is None:
        return None
    user = await session.get(User, user_id)
    return _user_out(user) if user else None
