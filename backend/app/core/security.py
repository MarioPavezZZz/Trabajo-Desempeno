"""Contraseñas (bcrypt) y sesión (JWT en cookie httpOnly).

Decisiones:
- bcrypt es lento a propósito (costo `PASSWORD_HASH_ROUNDS`). Calcularlo en el
  event loop bloquearía a todas las peticiones del worker, por eso se ejecuta
  en un hilo aparte (`run_in_threadpool`). Aun así consume CPU: en la Fase 2
  el login/registro es candidato a punto de saturación.
- La sesión es un JWT firmado (HS256) con el id del usuario. Validarlo no
  requiere consultar la base, lo que mantiene barata cada petición autenticada.
- Si el correo no existe, igual se verifica contra un hash ficticio: así el
  tiempo de respuesta no revela qué correos están registrados.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Response
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

ALGORITHM = "HS256"
BCRYPT_MAX_BYTES = 72  # bcrypt ignora lo que pase de 72 bytes; se trunca explícitamente


def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def _hash_sync(password: str) -> str:
    rounds = get_settings().password_hash_rounds
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt(rounds=rounds)).decode()


def _verify_sync(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(password), hashed.encode())
    except ValueError:  # hash con formato inválido
        return False


# Hash de una contraseña aleatoria, usado cuando el correo no existe.
_DUMMY_HASH = _hash_sync("contraseña-que-nadie-usa-para-igualar-tiempos")


async def hash_password(password: str) -> str:
    """Calcula el hash bcrypt en un hilo aparte (no bloquea el event loop)."""
    return await run_in_threadpool(_hash_sync, password)


async def verify_password(password: str, hashed: str | None) -> bool:
    """Compara la contraseña con el hash; con `None` compara contra un hash ficticio."""
    ok = await run_in_threadpool(_verify_sync, password, hashed or _DUMMY_HASH)
    return ok and hashed is not None


def create_session_token(user_id: int) -> str:
    """JWT con el id del usuario y su vencimiento."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def read_session_token(token: str | None) -> int | None:
    """Id del usuario si el token es válido y vigente; si no, None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    """Cookie httpOnly (inaccesible desde JavaScript) y SameSite=Lax (mitiga CSRF)."""
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )


def set_session_cookie(response: Response, user_id: int) -> None:
    """Inicia la sesión del usuario en el navegador."""
    settings = get_settings()
    set_cookie(
        response,
        settings.session_cookie,
        create_session_token(user_id),
        max_age=settings.jwt_expires_minutes * 60,
    )


def clear_cookie(response: Response, name: str) -> None:
    """Borra una cookie con los mismos atributos con que se creó."""
    response.delete_cookie(
        name, path="/", httponly=True, samesite="lax", secure=get_settings().cookie_secure
    )
