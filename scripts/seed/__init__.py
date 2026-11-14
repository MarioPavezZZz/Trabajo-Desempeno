"""Paquete del script de datos semilla.

Módulos:
- `records`: estructuras normalizadas (independientes de cada API).
- `http_client`: cliente HTTP con caché en disco, pausas y reintentos.
- `sources`: descarga y normalización desde Scryfall, TCGdex y YGOPRODeck.
- `images`: descarga/conversión de imágenes y generación de SVG propios.
- `generate`: generación determinista de productos (precio, estado, stock...).
- `loader`: inserción idempotente en PostgreSQL.
"""
