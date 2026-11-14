"""Modelos ORM. Importarlos aquí registra todas las tablas en `Base.metadata`
(necesario para que Alembic las detecte)."""

from app.models.cart import Cart, CartItem
from app.models.catalog import CardSet, Game, PriceHistory, Product
from app.models.order import Order, OrderItem, Payment
from app.models.user import User

__all__ = [
    "Cart",
    "CartItem",
    "CardSet",
    "Game",
    "Order",
    "OrderItem",
    "Payment",
    "PriceHistory",
    "Product",
    "User",
]
