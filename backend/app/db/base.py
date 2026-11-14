"""Base declarativa de SQLAlchemy y convención de nombres de restricciones.

La convención de nombres hace que índices, claves foráneas y CHECK tengan
nombres estables y legibles; así las migraciones de Alembic son
reproducibles y los planes de `EXPLAIN` del informe muestran nombres claros.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Clase base de todos los modelos ORM."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
