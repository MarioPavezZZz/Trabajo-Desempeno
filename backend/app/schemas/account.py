"""Esquemas de cuenta (registro, login) y carrito."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.catalog import ProductSummary


class RegisterIn(BaseModel):
    """Datos para crear una cuenta."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres")
        return value


class LoginIn(BaseModel):
    """Credenciales de inicio de sesión."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    """Usuario visible para sí mismo (nunca incluye el hash)."""

    id: int
    email: str
    full_name: str
    created_at: datetime


class AddItemIn(BaseModel):
    """Producto y cantidad a agregar al carrito."""

    product_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateItemIn(BaseModel):
    """Nueva cantidad de una línea del carrito."""

    quantity: int = Field(ge=1, le=99)


class CartLine(BaseModel):
    """Línea del carrito con el producto y su total al precio vigente."""

    id: int
    quantity: int
    unit_price_clp: int  # precio vigente
    added_price_clp: int  # precio cuando se agregó
    line_total_clp: int
    product: ProductSummary


class CartOut(BaseModel):
    """Carrito completo."""

    items: list[CartLine]
    item_count: int  # suma de unidades
    subtotal_clp: int
    warnings: list[str]
