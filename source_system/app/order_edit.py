"""D1-C versioned full replacement/cancellation. Source only; never changes CFO fulfilment."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import SourceOrderError, invalid
from app.models import OrderLine
from app.order_create import insert_lines, references, scalar_values, view
from app.order_payloads import CancelIn, OrderEditIn, OrderIn
from app.order_validation import locked_order, payload_from_order, validate_payload
from app.orders_read import OrderOut


def canonical(payload: OrderIn) -> tuple[dict[str, object], list[tuple[int, str, Decimal, Decimal]]]:
    return scalar_values(payload), sorted(
        (line.line_no, line.sku, line.qty, Decimal(line.unit_price)) for line in payload.lines
    )


async def update(session: AsyncSession, order_id: str, request: OrderEditIn, *, now: datetime) -> OrderOut:
    order = await locked_order(session, order_id)
    if order.status == "CANCELLED":
        raise SourceOrderError(409, "ILLEGAL_TRANSITION", "Cancelled source order cannot be edited.")
    if order.version != request.expected_version:
        raise SourceOrderError(409, "VERSION_CONFLICT", "Source order version has changed.")
    payload = OrderIn.model_validate(request.model_dump(exclude={"expected_version", "refresh_address"}))
    address = await references(session, payload)
    refresh = (
        request.refresh_address
        or payload.address_id != order.address_id
        or payload.customer_id != order.customer_id
    )
    snapshot = (
        (address.address, address.lat, address.lon) if refresh else (order.address, order.lat, order.lon)
    )
    if order.status == "SUBMITTED_FOR_PLANNING":
        await validate_payload(session, payload, lat=snapshot[1], lon=snapshot[2], now=now)
    try:
        unchanged = canonical(payload) == canonical(await payload_from_order(session, order))
    except SourceOrderError:
        unchanged = False  # A valid full replacement may repair an incomplete legacy source row.
    if unchanged and snapshot == (order.address, order.lat, order.lon):
        return await view(session, order)
    await session.execute(text("SELECT set_config('source.app_now',:now,true)"), {"now": now.isoformat()})
    for field, value in scalar_values(payload).items():
        setattr(order, field, value)
    order.address, order.lat, order.lon = snapshot
    order.status = "DRAFT" if order.status == "VALIDATED" else order.status
    order.version, order.updated_at = order.version + 1, now
    await session.execute(delete(OrderLine).where(OrderLine.order_id == order.id))
    await insert_lines(session, order.id, payload, now=now)
    await session.flush()
    return await view(session, order)


async def cancel(session: AsyncSession, order_id: str, request: CancelIn, *, now: datetime) -> OrderOut:
    order = await locked_order(session, order_id)
    reason_text = (request.reason_text or "").strip() or None
    if (request.reason_code == "other" and reason_text is None) or (
        reason_text and not reason_text.isprintable()
    ):
        raise invalid("reason_text", "value_error")
    reason: dict[str, object] = {"reason_code": request.reason_code, "reason_text": reason_text}
    if order.status == "CANCELLED":
        if order.cancel_reason == reason and request.expected_version in (order.version, order.version - 1):
            return await view(session, order)
        raise SourceOrderError(409, "ILLEGAL_TRANSITION", "Cancellation provenance cannot be replaced.")
    if order.version != request.expected_version:
        raise SourceOrderError(409, "VERSION_CONFLICT", "Source order version has changed.")
    await session.execute(text("SELECT set_config('source.app_now',:now,true)"), {"now": now.isoformat()})
    order.status, order.cancel_reason, order.cancelled_at = "CANCELLED", reason, now
    order.version, order.updated_at = order.version + 1, now
    await session.flush()
    return await view(session, order)
