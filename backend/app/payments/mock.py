"""Simulador de pasarela de pago (para pruebas de carga y pruebas rápidas).

- Una persona ve una página con "Aprobar" / "Rechazar" (`/checkout/simulado`).
- Un script de carga llama directo al retorno con `decision=auto`: se aprueba
  con probabilidad `MOCK_APPROVAL_RATE`.
- Cada confirmación espera `MOCK_PAYMENT_LATENCY_MS` (sin bloquear el event
  loop), para que el checkout bajo carga se parezca a uno con pasarela real.
"""

from __future__ import annotations

import asyncio
import random
import uuid

from app.core.config import Settings, get_settings
from app.payments.base import PaymentResult, PaymentStart

DECISIONS = ("aprobar", "rechazar", "auto")


class MockProvider:
    """Proveedor de pago simulado."""

    name = "mock"

    def __init__(self, settings: Settings | None = None, rng: random.Random | None = None):
        self.settings = settings or get_settings()
        self.rng = rng or random.Random()

    async def create(
        self, buy_order: str, session_id: str, amount: int, return_url: str
    ) -> PaymentStart:
        """Genera un token propio y envía al navegador a la página de pago simulado."""
        token = f"MOCK-{uuid.uuid4().hex}"
        url = f"{self.settings.public_base_url}/checkout/simulado?token={token}"
        return PaymentStart(token=token, url=url, method="GET")

    async def commit(self, token: str, decision: str | None = None) -> PaymentResult:
        """Resuelve el pago según la decisión (o al azar con `auto`) tras la latencia simulada."""
        if self.settings.mock_payment_latency_ms > 0:
            await asyncio.sleep(self.settings.mock_payment_latency_ms / 1000)
        if decision == "auto" or decision is None:
            approved = self.rng.random() < self.settings.mock_approval_rate
        else:
            approved = decision == "aprobar"
        return PaymentResult(
            approved=approved,
            status="autorizado" if approved else "rechazado",
            authorization_code=f"{self.rng.randint(0, 999999):06d}" if approved else None,
            card_last4="6623" if approved else "0568",
            raw={"simulado": True, "decision": decision or "auto"},
        )
