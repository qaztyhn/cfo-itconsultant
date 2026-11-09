"""Disposable synthetic WMS contract double, never a production HTTP adapter.

Use only in APP_ENV=test + DEMO_DISPOSABLE=1 with frozen APP_NOW. In-memory
simulation is for deterministic failure tests; an actual restart-safe demo
requires Dev 2's persistent disposable WMS service. Never claims real WMS ACK.
"""

import os
from decimal import Decimal

from app.adapters.wms_reservation import (
    AckLine,
    ReservationAck,
    ReservationRequest,
    WmsRejected,
)
from app.core.config import get_settings

DEMO_NOW = "2026-11-04T10:05:00+01:00"


class SyntheticWmsPort:
    def __init__(self, quantities: dict[tuple[str, str], Decimal]) -> None:
        settings = get_settings()
        if (
            settings.app_env != "test"
            or settings.app_now != DEMO_NOW
            or os.environ.get("DEMO_DISPOSABLE") != "1"
        ):
            raise RuntimeError("Synthetic WMS is restricted to the disposable demo")
        self._available = dict(quantities)
        self._acks: dict[str, ReservationAck] = {}
        self._requests: dict[str, ReservationRequest] = {}
        self._batch = 1
        self.reserve_count = 0

    async def reserve(self, request: ReservationRequest) -> ReservationAck:
        old = self._acks.get(request.idempotency_key)
        if old is not None:
            if self._requests[request.idempotency_key] != request:
                raise WmsRejected("key_conflict")
            return old
        needed: dict[tuple[str, str], Decimal] = {}
        for line in request.lines:
            key = (line.warehouse_code, line.wms_sku)
            needed[key] = needed.get(key, Decimal(0)) + line.quantity
        if not needed or any(
            quantity <= 0 or self._available.get(key, Decimal(0)) < quantity
            for key, quantity in needed.items()
        ):
            raise WmsRejected("insufficient_stock")
        for key, quantity in needed.items():
            self._available[key] -= quantity
        self._batch += 1
        self.reserve_count += 1
        ack = ReservationAck(
            reservation_id=f"SYNTHETIC-{self.reserve_count}",
            status="accepted",
            lines=tuple(
                AckLine(sku, warehouse, quantity)
                for (warehouse, sku), quantity in sorted(needed.items())
            ),
            revision=f"synthetic-revision-{self._batch}",
            reflected_in_batch_id=self._batch,
            idempotency_key=request.idempotency_key,
        )
        self._acks[request.idempotency_key] = ack
        self._requests[request.idempotency_key] = request
        return ack

    async def status(self, market: str, idempotency_key: str) -> ReservationAck | None:
        request = self._requests.get(idempotency_key)
        if request is not None and request.market != market:
            raise WmsRejected("market_conflict")
        return self._acks.get(idempotency_key)

    async def release(self, market: str, reservation_id: str, idempotency_key: str) -> ReservationAck:
        # This contract double deliberately refuses unsupported release semantics.
        raise WmsRejected("release_not_implemented")
