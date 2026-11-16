"""Esquemas del checkout y de los pedidos."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class CheckoutIn(BaseModel):
    """Datos del checkout. Nombre y correo son obligatorios solo para invitados."""

    contact_name: str | None = Field(default=None, max_length=120)
    contact_email: EmailStr | None = None
    shipping_method: Literal["retiro", "domicilio"] = "retiro"
    street: str | None = Field(default=None, max_length=160)
    comuna: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _address_for_delivery(self) -> "CheckoutIn":
        if self.shipping_method == "domicilio":
            missing = [
                f
                for f in ("street", "comuna", "region", "phone")
                if not (getattr(self, f) or "").strip()
            ]
            if missing:
                raise ValueError(
                    "Para envío a domicilio completa dirección, comuna, región y teléfono"
                )
        return self


class PaymentRedirect(BaseModel):
    """A dónde enviar al navegador para pagar."""

    url: str
    method: Literal["GET", "POST"]
    token: str
    token_field: str | None


class CheckoutStartOut(BaseModel):
    """Pedido creado (stock reservado) y datos para ir a pagar."""

    transaction_id: str
    access_key: str
    total_clp: int
    provider: str
    payment: PaymentRedirect


class CheckoutOptions(BaseModel):
    """Datos que el formulario de checkout necesita del servidor."""

    provider: str
    shipping_home_clp: int
    reservation_minutes: int


class OrderLine(BaseModel):
    """Línea del pedido (nombre y precio copiados al momento de comprar)."""

    product_id: int
    slug: str | None
    thumb: str | None
    name: str
    quantity: int
    unit_price_clp: int
    line_total_clp: int


class OrderPayment(BaseModel):
    """Resumen del pago (nunca incluye datos completos de la tarjeta)."""

    provider: str
    status: str
    authorization_code: str | None
    card_last4: str | None


class OrderOut(BaseModel):
    """Pedido completo para la página de resultado y "Mis pedidos"."""

    transaction_id: str
    status: Literal["pendiente", "pagada", "rechazada", "anulada"]
    created_at: datetime
    paid_at: datetime | None
    contact_name: str
    contact_email: str
    shipping_method: str
    shipping_address: dict
    subtotal_clp: int
    shipping_clp: int
    total_clp: int
    items: list[OrderLine]
    payment: OrderPayment | None


class OrderSummary(BaseModel):
    """Pedido en la lista de "Mis pedidos"."""

    transaction_id: str
    status: str
    created_at: datetime
    total_clp: int
    item_count: int
