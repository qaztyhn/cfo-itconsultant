"""Disposable synthetic WMS contract double, never a production HTTP adapter.

Use only in APP_ENV=test + DEMO_DISPOSABLE=1 with frozen APP_NOW. In-memory
simulation is for deterministic failure tests; an actual restart-safe demo
requires Dev 2's persistent disposable WMS service. Never claims real WMS ACK.
"""

import os
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from app.adapters.base import StockItemDTO, StockSnapshotDTO
from app.adapters.wms_reservation import (
    AckLine,
    ReservationAck,
    ReservationRequest,
    WmsRejected,
)
from app.core.config import get_settings

DEMO_NOW = "2026-11-04T10:05:00+01:00"
E0_04_DEMO_NOW = "2026-12-01T10:05:00+01:00"
ALLOWED_DEMO_CLOCKS = frozenset({DEMO_NOW, E0_04_DEMO_NOW})


class SyntheticWmsPort:
    def __init__(self, quantities: dict[tuple[str, str], Decimal]) -> None:
        settings = get_settings()
        if (
            settings.app_env != "test"
            or settings.app_now not in ALLOWED_DEMO_CLOCKS
            or os.environ.get("DEMO_DISPOSABLE") != "1"
        ):
            raise RuntimeError("Synthetic WMS is restricted to the disposable demo")
        self._as_of = datetime.fromisoformat(settings.app_now)
        self._initial = dict(quantities)
        self._available = dict(quantities)
        self._acks: dict[str, ReservationAck] = {}
        self._requests: dict[str, ReservationRequest] = {}
        self._batch = 1
        self.reserve_count = 0
        self._released: set[str] = set()

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
                AckLine(sku, warehouse, quantity) for (warehouse, sku), quantity in sorted(needed.items())
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

    async def fetch_stock(self) -> StockSnapshotDTO:
        """Complete synthetic stock batch; never real Source/WMS inventory."""
        rows = tuple(
            StockItemDTO(warehouse, sku, on_hand, on_hand - self._available[(warehouse, sku)])
            for (warehouse, sku), on_hand in sorted(self._initial.items())
        )
        return StockSnapshotDTO(
            as_of=self._as_of,
            items=rows,
            batch_id=self._batch,
            item_count=len(rows),
        )

    async def release(self, market: str, reservation_id: str, idempotency_key: str) -> ReservationAck:
        """Idempotent synthetic compensation, never physical issue/receipt."""
        matches = [
            key
            for key, ack in self._acks.items()
            if ack.reservation_id == reservation_id and self._requests[key].market == market
        ]
        if len(matches) != 1:
            raise WmsRejected("reservation_not_found")
        key = matches[0]
        if idempotency_key != f"{key}:release":
            raise WmsRejected("release_key_conflict")
        if key not in self._released:
            for line in self._requests[key].lines:
                self._available[(line.warehouse_code, line.wms_sku)] += line.quantity
            self._released.add(key)
            self._batch += 1
            self._acks[key] = replace(self._acks[key], status="released")
        return self._acks[key]
