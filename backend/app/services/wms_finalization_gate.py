"""Fail-closed final WMS approval preflight. Never authorizes APPROVED.

CFO's existing stock_snapshot lacks reservation-specific WMS batch inclusion and
verified native SKU mapping provenance. An ACK or ledger 'refreshed' alone is not
authority to complete approval, even in an isolated synthetic demo.
"""
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.wms_reservation import AckLine, ReservationAck, ReservationMismatch, verify_ack
from app.domain.models.ops import CustomerOrder, OrderLine
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.wms import WmsReservationIntent
from app.services.wms_intent import _request


@dataclass(frozen=True)
class WmsGateState:
    status: str
    reason: str


async def inspect_wms_gate(
    session: AsyncSession, order: CustomerOrder, plan: FulfilmentPlan
) -> WmsGateState:
    """Check persisted evidence inside caller's locked approval transaction."""
    intent = await session.scalar(
        select(WmsReservationIntent)
        .where(WmsReservationIntent.order_id == order.id)
        .with_for_update()
    )
    if intent is None:
        return WmsGateState("awaiting_wms", "WMS_INTENT_MISSING")
    if (
        intent.market_id != order.market_id
        or intent.plan_id != plan.id
        or intent.order_version != order.version
        or intent.source_version != order.source_version
        or not intent.is_synthetic
    ):
        return WmsGateState("rejected", "WMS_INTENT_STALE_OR_UNTRUSTED")
    if intent.status in ("pending", "unknown"):
        return WmsGateState(
            "uncertain" if intent.status == "unknown" else "awaiting_wms",
            "WMS_ACK_NOT_CONFIRMED",
        )
    if intent.status in ("released", "rejected"):
        return WmsGateState("rejected", "WMS_RESERVATION_CLOSED")
    if intent.status not in ("acked", "refreshed") or not intent.ack_payload:
        return WmsGateState("rejected", "WMS_ACK_MISSING")
    payload = intent.request_payload
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != intent.request_digest:
        return WmsGateState("rejected", "WMS_INTENT_MUTATED")
    try:
        request = _request(intent)
        originals = (
            await session.scalars(select(OrderLine).where(OrderLine.order_id == order.id))
        ).all()
        if (
            len(originals) != len(request.lines)
            or {(row.id, row.local_sku) for row in originals}
            != {(row.order_line_id, row.pos_sku) for row in request.lines}
            or any(not row.mapping_version or not row.wms_unit for row in request.lines)
        ):
            return WmsGateState("rejected", "WMS_LINE_PROVENANCE_INVALID")
        ack_data = intent.ack_payload
        ack = ReservationAck(
            reservation_id=str(ack_data["reservation_id"]),
            revision=str(ack_data["revision"]),
            status=str(ack_data["status"]),
            idempotency_key=str(ack_data["idempotency_key"]),
            lines=tuple(
                AckLine(
                    str(row["wms_sku"]),
                    str(row["warehouse_code"]),
                    Decimal(str(row["quantity"])),
                )
                for row in ack_data["lines"]
            ),
            reflected_in_batch_id=intent.reflected_in_batch_id,
        )
        verify_ack(request, ack)
    except (KeyError, TypeError, ValueError, ReservationMismatch):
        return WmsGateState("rejected", "WMS_ACK_MISMATCH")
    if ack.reservation_id != intent.reservation_id or ack.revision != intent.ack_revision:
        return WmsGateState("rejected", "WMS_ACK_MISMATCH")
    if (
        intent.status != "refreshed"
        or intent.reflected_in_batch_id is None
        or intent.refreshed_batch_id is None
        or intent.refreshed_batch_id < intent.reflected_in_batch_id
    ):
        return WmsGateState("awaiting_stock", "WMS_STOCK_INCLUSION_MISSING")
    # Ledger batch ID is *not* evidence of a trustworthy Source/CFO stock link.
    return WmsGateState("awaiting_provenance", "WMS_CFO_STOCK_BATCH_LINK_UNVERIFIED")
