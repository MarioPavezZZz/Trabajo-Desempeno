"""Webpay Plus (Transbank), API REST v1.2, ambiente de integración.

Se usa la API REST con httpx asíncrono en lugar del SDK oficial: el SDK hace
llamadas síncronas que bloquearían el event loop del worker mientras espera
a Transbank, deteniendo a todas las demás peticiones de ese proceso.

Flujo:
1. `create`: POST /transactions -> {token, url}. El navegador envía un
   formulario POST a `url` con el campo `token_ws`.
2. La persona paga en Transbank (tarjetas de prueba publicadas por Transbank).
3. Transbank devuelve al navegador a `return_url` con `token_ws` (pago
   terminado), `TBK_TOKEN` (pago anulado) o solo `TBK_ORDEN_COMPRA` (tiempo
   agotado). Esos casos se resuelven en el servicio de checkout.
4. `commit`: PUT /transactions/{token} confirma y entrega el resultado.

Documentación: https://www.transbankdevelopers.cl/referencia/webpay
"""

from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.payments.base import PaymentError, PaymentResult, PaymentStart

API_PATH = "/rswebpaytransaction/api/webpay/v1.2/transactions"

_client: httpx.AsyncClient | None = None


def _shared_client(timeout: float) -> httpx.AsyncClient:
    """Cliente HTTP compartido por el worker (reutiliza conexiones TLS con Transbank)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=timeout)
    return _client


class WebpayProvider:
    """Proveedor Webpay Plus."""

    name = "webpay"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or _shared_client(self.settings.webpay_timeout_s)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Tbk-Api-Key-Id": self.settings.webpay_commerce_code,
            "Tbk-Api-Key-Secret": self.settings.webpay_api_key,
            "Content-Type": "application/json",
        }

    async def _call(self, method: str, path: str, json: dict | None = None) -> httpx.Response:
        url = f"{self.settings.webpay_base_url}{API_PATH}{path}"
        try:
            return await self.client.request(method, url, json=json, headers=self._headers)
        except httpx.HTTPError as exc:
            raise PaymentError(f"No se pudo conectar con Webpay: {exc}") from exc

    async def create(
        self, buy_order: str, session_id: str, amount: int, return_url: str
    ) -> PaymentStart:
        """Crea la transacción y devuelve a dónde enviar al navegador."""
        resp = await self._call(
            "POST",
            "",
            {
                "buy_order": buy_order,
                "session_id": session_id,
                "amount": amount,
                "return_url": return_url,
            },
        )
        if resp.status_code != 200:
            raise PaymentError(
                f"Webpay rechazó la creación ({resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        return PaymentStart(
            token=data["token"], url=data["url"], method="POST", token_field="token_ws"
        )

    async def commit(self, token: str, decision: str | None = None) -> PaymentResult:
        """Confirma la transacción. Aprobada solo si status=AUTHORIZED y response_code=0."""
        resp = await self._call("PUT", f"/{token}")
        if resp.status_code != 200:
            # p. ej. 422 si el token ya fue confirmado o la transacción fue anulada.
            return PaymentResult(
                approved=False,
                status="error",
                raw={"http_status": resp.status_code, "body": resp.text[:500]},
            )
        data = resp.json()
        approved = data.get("status") == "AUTHORIZED" and data.get("response_code") == 0
        card = (data.get("card_detail") or {}).get("card_number")
        return PaymentResult(
            approved=approved,
            status="autorizado" if approved else "rechazado",
            amount=data.get("amount"),
            buy_order=data.get("buy_order"),
            authorization_code=data.get("authorization_code"),
            card_last4=str(card)[-4:] if card else None,
            raw=data,
        )
