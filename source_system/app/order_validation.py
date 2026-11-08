"""D1-B source-only validation and locked validate/submit lifecycle. Never reads CFO feasibility."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import SourceOrderError, invalid
from app.models import Customer, Order, ReceivingCalendar, Sales, Store
from app.order_create import references, view, window_times
from app.order_payloads import OrderIn
from app.orders_read import OrderOut
from app.receiving import CalendarConfig, ReceivingHours, day_error


async def locked_order(session: AsyncSession, order_id: str) -> Order:
    order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise SourceOrderError(404, "VALIDATION_ERROR", "Source order not found.")
    return order


async def payload_from_order(session: AsyncSession, order: Order) -> OrderIn:
    fields = (await view(session, order)).model_dump(
        exclude={
            "id",
            "version",
            "updated_at",
            "status",
            "address",
            "lat",
            "lon",
            "cancel_reason",
            "cancelled_at",
        }
    )
    try:
        return OrderIn.model_validate(fields)
    except ValidationError as exc:
        errors: list[dict[str, object]] = []
        for error in exc.errors():
            field = str(error["loc"][-1])
            kind = {
                "qty": "invalid_quantity",
                "unit_price": "invalid_price",
                "date_mode": "invalid_date_mode",
            }.get(field, "value_error")
            errors.append({"loc": ["body", *error["loc"]], "type": kind, "msg": "Order field is invalid."})
        raise SourceOrderError(422, "VALIDATION_ERROR", "Order validation failed.", errors) from None


async def validate_payload(
    session: AsyncSession, payload: OrderIn, *, lat: Decimal | None, lon: Decimal | None, now: datetime
) -> None:
    address = await references(session, payload)
    customer = await session.get(Customer, payload.customer_id)
    store = await session.get(Store, payload.store_code)
    sales = await session.get(Sales, payload.sales_code) if payload.sales_code else None
    if customer is None or not customer.is_active:
        raise invalid("customer_id", "customer_not_found")
    if store is None or not store.is_active:
        raise invalid("store_code", "value_error")
    if sales is None or not sales.is_active or sales.store_code != payload.store_code:
        raise invalid("sales_code", "value_error")
    if (
        lat is None
        or lon is None
        or not lat.is_finite()
        or not lon.is_finite()
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
    ):
        raise invalid("address_id", "missing_coordinates")
    contact = payload.contact
    if (
        contact is None
        or not (contact.name or "").strip()
        or not any((value or "").strip() for value in (contact.phone, contact.email))
    ):
        raise invalid("contact", "contact_required")
    if not payload.lines:
        raise invalid("lines", "lines_required")
    row = await session.get(ReceivingCalendar, "instance")
    if row is None or address.receiving_hours is None:
        raise invalid("address_id", "receiving_calendar_missing")
    try:
        calendar = CalendarConfig.model_validate(row)
        hours = ReceivingHours.model_validate({"days": address.receiving_hours})
    except (ValidationError, KeyError):
        raise invalid("address_id", "receiving_calendar_missing") from None
    if payload.date_mode == "exact":
        if payload.date_from is None or payload.date_to is not None:
            raise invalid("date_from", "invalid_date_range")
        first = last = payload.date_from
    elif payload.date_mode == "range":
        if payload.date_from is None or payload.date_to is None or payload.date_from > payload.date_to:
            raise invalid("date_from", "invalid_date_range")
        first, last = payload.date_from, payload.date_to
    else:
        if payload.date_to is None or payload.date_from is not None:
            raise invalid("date_to", "invalid_date_range")
        first, last = now.astimezone(ZoneInfo(calendar.timezone)).date(), payload.date_to
        if first > last:
            raise invalid("date_to", "invalid_date_range")
    if first < calendar.valid_from or last > calendar.valid_to:
        raise invalid("address_id", "receiving_calendar_missing")
    start, end = window_times(payload)
    # Date interval is bounded by the explicitly configured receiving-calendar coverage.
    for offset in range((last - first).days + 1):
        error = day_error(calendar, hours, first + timedelta(days=offset), start, end)
        if error is None:
            return
        if error in ("invalid_receiving_window", "receiving_calendar_missing"):
            raise invalid("window_start", error)
    raise invalid("window_start", "outside_receiving_hours")


async def validate_or_submit(
    session: AsyncSession, order_id: str, *, now: datetime, submit: bool
) -> OrderOut:
    order = await locked_order(session, order_id)
    if order.status == "CANCELLED" or (submit and order.status == "DRAFT"):
        raise SourceOrderError(409, "ILLEGAL_TRANSITION", "Source order transition is not permitted.")
    if submit and order.status == "SUBMITTED_FOR_PLANNING":
        return await view(session, order)
    payload = await payload_from_order(session, order)
    await validate_payload(session, payload, lat=order.lat, lon=order.lon, now=now)
    target = "SUBMITTED_FOR_PLANNING" if submit else "VALIDATED"
    if order.status == "DRAFT" or (submit and order.status == "VALIDATED"):
        await session.execute(text("SELECT set_config('source.app_now',:now,true)"), {"now": now.isoformat()})
        order.status, order.version, order.updated_at = target, order.version + 1, now
        await session.flush()
    return await view(session, order)
