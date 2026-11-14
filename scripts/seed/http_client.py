"""Cliente HTTP "educado" para las APIs públicas, con caché en disco.

- Caché: cada respuesta JSON se guarda en `data/cache/json/<fuente>/`. Si el
  archivo existe, no se vuelve a pedir (idempotencia y respeto a las APIs).
- Ritmo: pausa mínima entre peticiones al mismo host (Scryfall pide 50-100 ms;
  usamos al menos 100 ms en todas).
- Reintentos: ante 429 o 5xx espera (respetando `Retry-After`) y reintenta.
- Identificación: User-Agent genérico del proyecto, sin datos personales.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

log = logging.getLogger("seed.http")

USER_AGENT = "TCGMASTER-seed/0.1 (proyecto academico INFB8091)"
MAX_RETRIES = 4


class PoliteClient:
    """Cliente HTTP con caché JSON, pausa por host y reintentos."""

    def __init__(self, cache_dir: Path, delay_ms: int = 120, timeout: float = 30.0) -> None:
        self.cache_dir = cache_dir
        self.delay = max(delay_ms, 100) / 1000.0
        self._last_call: dict[str, float] = {}
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json;q=0.9,*/*;q=0.8"},
            timeout=timeout,
            follow_redirects=True,
        )
        self.network_calls = 0

    def close(self) -> None:
        """Cierra las conexiones abiertas."""
        self._client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- internos
    def _wait_turn(self, url: str) -> None:
        """Duerme lo necesario para no superar el ritmo permitido por host."""
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last_call.get(host, 0.0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call[host] = time.monotonic()

    def _request(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET con reintentos ante 429/5xx y errores de red."""
        for attempt in range(1, MAX_RETRIES + 1):
            self._wait_turn(url)
            self.network_calls += 1
            try:
                resp = self._client.get(url, params=params)
            except httpx.TransportError as exc:
                log.warning("Error de red en %s (intento %d): %s", url, attempt, exc)
                time.sleep(2**attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("Retry-After", 2**attempt))
                log.warning("HTTP %d en %s; reintento en %.0fs", resp.status_code, url, wait)
                time.sleep(wait)
                continue
            return resp
        raise RuntimeError(f"No se pudo obtener {url} tras {MAX_RETRIES} intentos")

    # ----------------------------------------------------------------- público
    def get_json(self, source: str, url: str, params: dict[str, Any] | None = None) -> Any:
        """Devuelve el JSON de `url`, desde caché si ya fue descargado.

        Retorna `None` si la API responde 404 (recurso inexistente); ese
        resultado también se cachea para no repetir la petición.
        """
        full = url + ("?" + urlencode(sorted(params.items())) if params else "")
        key = hashlib.sha1(full.encode()).hexdigest()[:16]
        path = self.cache_dir / "json" / source / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["body"]

        resp = self._request(url, params)
        if resp.status_code == 404:
            body = None
        else:
            resp.raise_for_status()
            body = resp.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Se guarda también la URL para poder auditar de dónde salió cada archivo.
        path.write_text(json.dumps({"url": full, "body": body}, ensure_ascii=False), "utf-8")
        return body

    def download(self, url: str, dest: Path) -> bool:
        """Descarga un archivo binario a `dest` si no existe. Retorna True si quedó disponible."""
        if dest.exists() and dest.stat().st_size > 0:
            return True
        try:
            resp = self._request(url)
        except RuntimeError as exc:
            log.warning("%s", exc)
            return False
        if resp.status_code != 200:
            log.warning("No se pudo descargar %s (HTTP %d)", url, resp.status_code)
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(resp.content)
        tmp.replace(dest)  # escritura atómica: nunca queda un archivo a medias
        return True
