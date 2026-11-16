"""Interfaz común de los proveedores de pago.

El checkout no conoce detalles de Transbank: crea una transacción, envía al
navegador a la URL que devuelve el proveedor y, al volver, la confirma.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


class PaymentError(Exception):
    """El proveedor no respondió o respondió con un error (no es un rechazo de tarjeta)."""


@dataclass
class PaymentStart:
    """Datos para enviar al navegador a la página de pago."""

    token: str
    url: str
    method: Literal["GET", "POST"]
    # Nombre del campo del formulario con el token (Webpay usa `token_ws`).
    token_field: str | None = None


@dataclass
class PaymentResult:
    """Resultado de confirmar (commit) una transacción."""

    approved: bool
    status: Literal["autorizado", "rechazado", "anulado", "error"]
    amount: int | None = None
    buy_order: str | None = None
    authorization_code: str | None = None
    card_last4: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    """Lo que el checkout necesita de un proveedor."""

    name: str

    async def create(
        self, buy_order: str, session_id: str, amount: int, return_url: str
    ) -> PaymentStart: ...

    async def commit(self, token: str, decision: str | None = None) -> PaymentResult: ...
