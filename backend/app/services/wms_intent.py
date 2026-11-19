"""Durable, transaction-separated WMS intent/ACK recovery primitives.

CALLER MUST COMMIT begin_intent BEFORE any external side effect. External reserve
is never made inside a SQL transaction. An ACK is persisted in a NEW transaction
before any CFO approval attempt. These primitives do not approve orders and do
not configure the production DisabledWmsPort.
"""

import hashlib
import json
import os
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.synthetic_wms import ALLOWED_DEMO_CLOCKS
from app.adapters.wms_reservation import (
    ReservationAck,
    ReservationRequest,
    verify_ack,
)
from app.adapters.wms_sku import ReservationLine
from app.core.config import get_settings
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder, OrderLine, OrderRouting
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.ref import Location, Market
from app.domain.models.wms import WmsReservationIntent


def _ensure_synthetic_scope(intent_is_synthetic: bool) -> None:
    if not intent_is_synthetic:
        return
    settings = get_settings()
    if (
        settings.app_env != "test"
        or settings.app_now not in ALLOWED_DEMO_CLOCKS
        or os.environ.get("DEMO_DISPOSABLE") != "1"
    ):
        raise DomainError("FORBIDDEN", "Synthetic WMS evidence is restricted to the disposable demo.")


def _payload(req: ReservationRequest) -> dict[str, object]:
    return {
        "market": req.market,
        "order_id": req.order_id,
        "plan_id": req.plan_id,
        "idempotency_key": req.idempotency_key,
        "lines": [
            {
                "order_line_id": line.order_line_id,
                "pos_sku": line.pos_sku,
                "wms_sku": line.wms_sku,
                "warehouse_code": line.warehouse_code,
                "quantity": str(line.quantity),
                "wms_unit": line.wms_unit,
                "mapping_version": line.mapping_version,
            }
            for line in req.lines
        ],
    }


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _request(intent: WmsReservationIntent) -> ReservationRequest:
    data = intent.request_payload
    lines = tuple(
        ReservationLine(
            order_line_id=int(line["order_line_id"]),
            pos_sku=str(line["pos_sku"]),
            wms_sku=str(line["wms_sku"]),
            warehouse_code=str(line["warehouse_code"]),
            quantity=Decimal(str(line["quantity"])),
            wms_unit=str(line["wms_unit"]),
            mapping_version=str(line["mapping_version"]),
        )
        for line in data["lines"]
    )
    return ReservationRequest(
        market=str(data["market"]),
        order_id=int(data["order_id"]),
        plan_id=int(data["plan_id"]),
        idempotency_key=str(data["idempotency_key"]),
        lines=lines,
    )


async def begin_intent(
    session: AsyncSession, request: ReservationRequest, *, synthetic: bool
) -> WmsReservationIntent:
    """Durably bind one order/plan/version/native-SKU request; never sends to WMS.

    request must come from the trusted confirmed-mapping resolver, after RBAC and
    five gates. Never call with client-supplied native SKU relations.
    """
    _ensure_synthetic_scope(synthetic)
    if not request.lines or any(
        not line.wms_sku.strip()
        or not line.wms_unit.strip()
        or not line.mapping_version.strip()
        or line.quantity <= 0
        or not line.quantity.is_finite()
        for line in request.lines
    ):
        raise DomainError("PLAN_NOT_APPROVABLE", "Unverified WMS-native reservation lines.")
    from app.adapters.wms_reservation import build_request

    if build_request(request.market, request.order_id, request.plan_id, request.lines) != request:
        raise DomainError("RESOURCE_CONFLICT", "Reservation identity was not derived from exact lines.")
    order = await session.scalar(
        select(CustomerOrder).where(CustomerOrder.id == request.order_id).with_for_update()
    )
    plan = await session.get(FulfilmentPlan, request.plan_id)
    market = await session.get(Market, order.market_id) if order else None
    if (
        order is None
        or plan is None
        or market is None
        or market.code != request.market
        or plan.order_id != order.id
        or plan.status != "proposed"
        or order.status != "PLANNED"
    ):
        raise DomainError("PLAN_NOT_APPROVABLE", "WMS intent requires a currently proposed plan.")
    route = await session.scalar(
        select(OrderRouting.route).where(
            OrderRouting.market_id == market.id,
            OrderRouting.external_ref == order.external_ref,
        )
    )
    warehouse = await session.get(Location, plan.warehouse_id)
    originals = (
        await session.scalars(select(OrderLine).where(OrderLine.order_id == order.id).order_by(OrderLine.id))
    ).all()
    expected = {(line.id, line.local_sku) for line in originals}
    requested = {(line.order_line_id, line.pos_sku) for line in request.lines}
    if (
        route != "cfo"
        or warehouse is None
        or warehouse.market_id != market.id
        or warehouse.code.strip() != request.lines[0].warehouse_code
        or len(originals) != len(request.lines)
        or expected != requested
        or any(line.warehouse_code != warehouse.code.strip() for line in request.lines)
    ):
        raise DomainError(
            "RESOURCE_CONFLICT", "WMS reservation differs from CFO routing, order or warehouse."
        )
    payload = _payload(request)
    digest = _digest(payload)
    found = await session.scalar(
        select(WmsReservationIntent).where(WmsReservationIntent.order_id == order.id).with_for_update()
    )
    if found is not None:
        if found.request_digest != digest or found.is_synthetic != synthetic:
            raise DomainError("RESOURCE_CONFLICT", "An immutable reservation intent already exists.")
        if found.order_version != order.version or found.source_version != order.source_version:
            raise DomainError("RESOURCE_CONFLICT", "Source/order version changed after WMS intent.")
        return found
    intent = WmsReservationIntent(
        market_id=market.id,
        order_id=order.id,
        plan_id=plan.id,
        order_version=order.version,
        source_version=order.source_version,
        request_key=request.idempotency_key,
        request_payload=payload,
        request_digest=digest,
        status="pending",
        is_synthetic=synthetic,
    )
    session.add(intent)
    await session.flush()
    return intent


async def record_ack(session: AsyncSession, request_key: str, ack: ReservationAck) -> WmsReservationIntent:
    """Verify exact ACK against persisted request, then commit in a separate transaction."""
    intent = await session.scalar(
        select(WmsReservationIntent).where(WmsReservationIntent.request_key == request_key).with_for_update()
    )
    if intent is None:
        raise DomainError("NOT_FOUND", "WMS intent not found.")
    _ensure_synthetic_scope(intent.is_synthetic)
    verify_ack(_request(intent), ack)
    if intent.status in ("rejected", "released"):
        raise DomainError("RESOURCE_CONFLICT", "Reservation has been closed.")
    if intent.reservation_id is not None and (
        intent.reservation_id != ack.reservation_id or intent.ack_revision != ack.revision
    ):
        raise DomainError("RESOURCE_CONFLICT", "Conflicting WMS ACK for the same key.")
    intent.reservation_id = ack.reservation_id
    intent.ack_revision = ack.revision
    intent.reflected_in_batch_id = ack.reflected_in_batch_id
    intent.ack_payload = {
        "status": ack.status,
        "idempotency_key": ack.idempotency_key,
        "reservation_id": ack.reservation_id,
        "revision": ack.revision,
        "lines": [
            {"warehouse_code": line.warehouse_code, "wms_sku": line.wms_sku, "quantity": str(line.quantity)}
            for line in ack.lines
        ],
    }
    if intent.status != "refreshed":
        intent.status = "acked"
    await session.flush()
    return intent


async def record_unknown(session: AsyncSession, request_key: str) -> None:
    """On no status evidence, keep a durable unresolved intent for same-key recovery."""
    intent = await session.scalar(
        select(WmsReservationIntent).where(WmsReservationIntent.request_key == request_key).with_for_update()
    )
    if intent is None:
        raise DomainError("NOT_FOUND", "WMS intent not found.")
    _ensure_synthetic_scope(intent.is_synthetic)
    if intent.status == "pending":
        intent.status = "unknown"


async def mark_refreshed(
    session: AsyncSession, request_key: str, *, batch_id: int, inclusion_proven: bool
) -> WmsReservationIntent:
    """Advance only with explicit matching inclusion proof, never later timestamp alone."""
    intent = await session.scalar(
        select(WmsReservationIntent).where(WmsReservationIntent.request_key == request_key).with_for_update()
    )
    if intent is None:
        raise DomainError("NOT_FOUND", "WMS intent not found.")
    _ensure_synthetic_scope(intent.is_synthetic)
    if (
        intent.status not in ("acked", "refreshed")
        or not inclusion_proven
        or intent.reflected_in_batch_id is None
        or batch_id < intent.reflected_in_batch_id
    ):
        raise DomainError("RESOURCE_CONFLICT", "WMS stock inclusion is not proven.")
    intent.status = "refreshed"
    intent.refreshed_batch_id = batch_id
    await session.flush()
    return intent
