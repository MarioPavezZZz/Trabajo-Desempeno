"""Imágenes servidas por nosotros (`data/media/`).

- Cartas: se descarga el original a `data/cache/images/` y se generan dos
  WebP: uno grande (detalle) y una miniatura (listados). La miniatura liviana
  es clave para el LCP del listado.
- Logos de set: SVG (Scryfall) se copia tal cual; PNG/JPG se pasa a WebP.
  Si la API no entrega logo, se genera un SVG propio con el nombre del set.
- Accesorios: SVG propios, simples y livianos (no hay API de accesorios).

Todas las rutas que se guardan en la base son relativas a `data/media/`.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
from pathlib import Path

from PIL import Image

from scripts.seed.http_client import PoliteClient

log = logging.getLogger("seed.images")

CARD_WIDTH = 488  # ancho del detalle (las cartas miden 63x88 mm -> ~488x680 px)
THUMB_WIDTH = 244  # ancho de la miniatura del listado
LOGO_WIDTH = 480
WEBP_QUALITY = 80

PLACEHOLDER_CARD = "placeholders/carta.svg"


def safe_name(value: str) -> str:
    """Convierte un id externo en un nombre de archivo seguro y estable."""
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    if len(clean) > 80:  # ids muy largos: se acortan con un hash para no chocar
        clean = clean[:60] + "-" + hashlib.sha1(value.encode()).hexdigest()[:10]
    return clean


def card_paths(game: str, external_id: str) -> tuple[str, str]:
    """Rutas relativas (detalle, miniatura) de la imagen de una carta."""
    base = f"cards/{game}/{safe_name(external_id)}"
    return f"{base}.webp", f"{base}_thumb.webp"


def _resize_to_webp(src: Path, dest: Path, width: int, keep_alpha: bool) -> None:
    """Redimensiona manteniendo proporción (sin agrandar) y guarda como WebP."""
    with Image.open(src) as img:
        img = img.convert("RGBA" if keep_alpha else "RGB")
        if img.width > width:
            height = round(img.height * width / img.width)
            img = img.resize((width, height), Image.Resampling.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "WEBP", quality=WEBP_QUALITY, method=6)


def ensure_card_image(
    client: PoliteClient, cache_dir: Path, media_dir: Path, game: str, external_id: str, url: str
) -> tuple[str, str] | None:
    """Descarga y convierte la imagen de una carta. Idempotente.

    Retorna las rutas relativas (detalle, miniatura) o None si falló la descarga.
    """
    image_path, thumb_path = card_paths(game, external_id)
    big, small = media_dir / image_path, media_dir / thumb_path
    if big.exists() and small.exists():
        return image_path, thumb_path
    ext = Path(url.split("?")[0]).suffix or ".img"
    raw = cache_dir / "images" / game / f"{safe_name(external_id)}{ext}"
    if not client.download(url, raw):
        return None
    try:
        _resize_to_webp(raw, big, CARD_WIDTH, keep_alpha=False)
        _resize_to_webp(raw, small, THUMB_WIDTH, keep_alpha=False)
    except OSError as exc:  # imagen corrupta: se borra para reintentar en la próxima ejecución
        log.warning("Imagen inválida %s: %s", raw, exc)
        raw.unlink(missing_ok=True)
        return None
    return image_path, thumb_path


def ensure_set_logo(
    client: PoliteClient,
    cache_dir: Path,
    media_dir: Path,
    game: str,
    code: str,
    name: str,
    url: str | None,
) -> str:
    """Obtiene el logo del set (o genera uno propio). Retorna la ruta relativa."""
    base = f"sets/{game}/{safe_name(code)}"
    if url:
        if url.lower().split("?")[0].endswith(".svg"):
            rel = f"{base}.svg"
            if (media_dir / rel).exists() or client.download(url, media_dir / rel):
                return rel
        else:
            rel = f"{base}.webp"
            if (media_dir / rel).exists():
                return rel
            ext = Path(url.split("?")[0]).suffix or ".img"
            raw = cache_dir / "images" / "sets" / f"{game}-{safe_name(code)}{ext}"
            if client.download(url, raw):
                try:
                    _resize_to_webp(raw, media_dir / rel, LOGO_WIDTH, keep_alpha=True)
                    return rel
                except OSError as exc:
                    log.warning("Logo inválido %s: %s", raw, exc)
    # Sin logo disponible: SVG tipográfico propio.
    rel = f"{base}_generado.svg"
    write_text(media_dir / rel, set_logo_svg(name, code))
    return rel


def write_text(path: Path, content: str) -> None:
    """Escribe un archivo de texto solo si cambió (idempotente, sin tocar fechas)."""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- SVG propios
def set_logo_svg(name: str, code: str) -> str:
    """Logo tipográfico simple para sets sin imagen oficial."""
    title = html.escape(name)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 200" role="img" '
        f'aria-label="{title}">'
        '<rect width="480" height="200" rx="12" fill="#1c1a17"/>'
        '<rect x="8" y="8" width="464" height="184" rx="8" fill="none" '
        'stroke="#c9a24a" stroke-width="2"/>'
        f'<text x="240" y="105" text-anchor="middle" font-family="Georgia, serif" '
        f'font-size="34" fill="#f2e6c8">{title}</text>'
        f'<text x="240" y="150" text-anchor="middle" font-family="monospace" '
        f'font-size="20" fill="#c9a24a">{html.escape(code)}</text>'
        "</svg>"
    )


# Íconos geométricos mínimos por tipo de accesorio (formas simples = archivos pequeños).
_ACCESSORY_SHAPES = {
    "fundas": '<rect x="70" y="40" width="120" height="170" rx="6" fill="{c}"/>'
    '<rect x="90" y="30" width="120" height="170" rx="6" fill="{c}" opacity=".7"/>',
    "carpeta": '<rect x="50" y="40" width="160" height="180" rx="8" fill="{c}"/>'
    '<rect x="62" y="56" width="136" height="148" rx="4" fill="none" stroke="#fff" '
    'stroke-opacity=".5" stroke-width="3"/>',
    "deck_box": '<rect x="70" y="70" width="120" height="150" rx="6" fill="{c}"/>'
    '<rect x="70" y="50" width="120" height="34" rx="6" fill="{c}" opacity=".75"/>',
    "playmat": '<rect x="25" y="85" width="210" height="110" rx="10" fill="{c}"/>'
    '<rect x="40" y="100" width="40" height="56" rx="3" fill="#fff" fill-opacity=".35"/>',
    "toploader": '<rect x="80" y="40" width="100" height="160" rx="4" fill="{c}" '
    'fill-opacity=".35" stroke="{c}" stroke-width="4"/>',
}


def accessory_svg(accessory_type: str, color_hex: str, label: str) -> str:
    """SVG de producto para un accesorio (fondo neutro + forma con el color del producto)."""
    shape = _ACCESSORY_SHAPES[accessory_type].format(c=color_hex)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 260" role="img" '
        f'aria-label="{html.escape(label)}">'
        '<rect width="260" height="260" fill="#efe9dc"/>'
        f"{shape}</svg>"
    )


def placeholder_card_svg() -> str:
    """Imagen de reemplazo para cartas cuya imagen no se pudo descargar."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 244 340" role="img" '
        'aria-label="Imagen no disponible">'
        '<rect width="244" height="340" rx="12" fill="#2a2724"/>'
        '<rect x="10" y="10" width="224" height="320" rx="8" fill="none" '
        'stroke="#c9a24a" stroke-dasharray="6 6"/>'
        '<text x="122" y="175" text-anchor="middle" font-family="Georgia, serif" '
        'font-size="18" fill="#c9a24a">Sin imagen</text></svg>'
    )
