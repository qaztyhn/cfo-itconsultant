"""CFO -> WMS reservation port and recovery logic (DEC-WMS-RESERVE-SYNC-20261109).

STATUS: ASSUMED capability, UNVERIFIED interface. The legacy WMS reserve/status/release API, its
authentication and credentials are unknown, so this module defines only a protocol (`WmsReservationPort`)
and the safe orchestration around it. There is NO HTTP implementation and the default port is
`DisabledWmsPort`: nothing can be sent to a real WMS until an owner-approved, reviewed adapter implements
the port. CFO never changes WMS on-hand, never receives or issues goods and never writes to the POS. A
plan is "guaranteed" only with a verified positive acknowledgement."""

import hashlib
import json
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.adapters.wms_sku import ReservationLine


class WmsError(Exception):
    """Base class; messages are static codes, never source content."""

    code = "WMS_ERROR"


class WmsDisabled(WmsError):
    code = "WMS_RESERVATION_DISABLED"


class WmsTimeout(WmsError):
    code = "WMS_TIMEOUT"


class WmsUnavailable(WmsError):
    code = "WMS_UNAVAILABLE"


class WmsRejected(WmsError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.code = "WMS_REJECTED"
        self.reason = reason


class ReservationUnknown(WmsError):
    """The final state could not be established: fail closed, reconcile later with the same key."""

    code = "WMS_RESERVATION_UNKNOWN"


class ReservationMismatch(WmsError):
    code = "WMS_RESERVATION_MISMATCH"


@dataclass(frozen=True)
class ReservationRequest:
    market: str
    order_id: int
    plan_id: int
    idempotency_key: str
    lines: tuple[ReservationLine, ...]


@dataclass(frozen=True)
class AckLine:
    wms_sku: str
    warehouse_code: str
    quantity: Decimal


@dataclass(frozen=True)
class ReservationAck:
    reservation_id: str
    status: str  # "accepted" | "partial" | "rejected" | "released"
    lines: tuple[AckLine, ...]
    revision: str
    reflected_in_batch_id: int | None = None  # stock batch known to include this reservation, if WMS says so


class WmsReservationPort(Protocol):
    """Proposed shape only (not a verified WMS API). All calls carry the stable idempotency key."""

    async def reserve(self, request: ReservationRequest) -> ReservationAck: ...

    async def status(self, market: str, idempotency_key: str) -> ReservationAck | None: ...

    async def release(self, market: str, reservation_id: str, idempotency_key: str) -> ReservationAck: ...


class DisabledWmsPort:
    """Default: no outbound WMS write exists until an approved, verified adapter is configured."""

    async def reserve(self, request: ReservationRequest) -> ReservationAck:
        raise WmsDisabled()

    async def status(self, market: str, idempotency_key: str) -> ReservationAck | None:
        raise WmsDisabled()

    async def release(self, market: str, reservation_id: str, idempotency_key: str) -> ReservationAck:
        raise WmsDisabled()


def idempotency_key(market: str, order_id: int, plan_id: int, lines: Sequence[ReservationLine]) -> str:
    """Stable per (market, order, plan, exact lines): retries and the 2nd vehicle of a plan reuse it."""
    payload = {
        "market": market,
        "order": order_id,
        "plan": plan_id,
        "lines": sorted(
            [
                line.order_line_id,
                line.pos_sku,
                line.wms_sku,
                line.warehouse_code,
                str(line.quantity),
                line.wms_unit,
            ]
            for line in lines
        ),
    }
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    return f"cfo-res-{digest[:40]}"


def build_request(
    market: str, order_id: int, plan_id: int, lines: Collection[ReservationLine]
) -> ReservationRequest:
    ordered = tuple(sorted(lines, key=lambda line: line.order_line_id))
    if not ordered:
        raise ReservationMismatch()
    return ReservationRequest(
        market, order_id, plan_id, idempotency_key(market, order_id, plan_id, ordered), ordered
    )


def _totals(items: Collection[tuple[str, str, Decimal]]) -> dict[tuple[str, str], Decimal]:
    out: dict[tuple[str, str], Decimal] = {}
    for sku, warehouse, qty in items:
        out[(warehouse, sku)] = out.get((warehouse, sku), Decimal(0)) + qty
    return out


def verify_ack(request: ReservationRequest, ack: ReservationAck) -> ReservationAck:
    """The ACK must be an accepted reservation of EXACTLY the requested SKU/warehouse/quantity."""
    if ack.status != "accepted" or not ack.reservation_id.strip() or not ack.revision.strip():
        raise ReservationMismatch()
    wanted = _totals([(line.wms_sku, line.warehouse_code, line.quantity) for line in request.lines])
    got = _totals([(a.wms_sku, a.warehouse_code, a.quantity) for a in ack.lines])
    if wanted != got:
        raise ReservationMismatch()
    return ack


async def reserve_with_recovery(
    port: WmsReservationPort,
    request: ReservationRequest,
    *,
    status_attempts: int = 3,
    pause: Callable[[int], Awaitable[None]] | None = None,
) -> ReservationAck:
    """Reserve once; on timeout/unavailable/lost ACK look the state up by key (never a blind duplicate).

    - accepted + exact match  -> verified ACK;
    - rejected                -> WmsRejected (no approval);
    - partial / mismatch      -> compensating release of what WMS holds, then ReservationMismatch;
    - state still unknown     -> ReservationUnknown (fail closed; caller retries the lookup later).
    """
    key, market = request.idempotency_key, request.market
    try:
        ack = await port.reserve(request)
    except (WmsTimeout, WmsUnavailable):
        found: ReservationAck | None = None
        for attempt in range(status_attempts):
            try:
                found = await port.status(market, key)
            except (WmsTimeout, WmsUnavailable):
                found = None
            if found is not None:
                break
            if pause is not None and attempt + 1 < status_attempts:
                await pause(attempt)
        if found is None:
            raise ReservationUnknown() from None
        ack = found
    if ack.status == "rejected":
        raise WmsRejected("rejected")
    try:
        return verify_ack(request, ack)
    except ReservationMismatch:
        if ack.reservation_id.strip() and ack.status in ("accepted", "partial"):
            try:
                await port.release(market, ack.reservation_id, f"{key}:release")
            except WmsError:
                raise ReservationUnknown() from None  # could not prove the compensation: reconcile
        raise
