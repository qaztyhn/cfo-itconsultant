"""D1-B draft creation and optional idempotent POST retries; caller owns transaction."""

import hashlib
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import SourceOrderError, invalid
from app.models import Address, CreateRequest, Customer, Order, OrderLine, Product, Sales, Store
from app.order_payloads import OrderIn
from app.orders_read import OrderOut, _view


async def view(session: AsyncSession, order: Order) -> OrderOut:
    lines = (
        await session.scalars(
            select(OrderLine).where(OrderLine.order_id == order.id).order_by(OrderLine.line_no)
        )
    ).all()
    return _view(order, list(lines))


async def references(session: AsyncSession, payload: OrderIn) -> Address:
    if await session.get(Customer, payload.customer_id) is None:
        raise invalid("customer_id", "customer_not_found")
    address = await session.get(Address, payload.address_id)
    if address is None or address.customer_id != payload.customer_id:
        raise invalid("address_id", "address_customer_mismatch")
    if await session.get(Store, payload.store_code) is None:
        raise invalid("store_code", "value_error")
    if payload.sales_code is not None:
        sales = await session.get(Sales, payload.sales_code)
        if sales is None or sales.store_code != payload.store_code:
            raise invalid("sales_code", "value_error")
    keys = [line.line_no for line in payload.lines]
    if len(keys) != len(set(keys)):
        raise invalid("lines", "duplicate_line_no")
    skus = {line.sku for line in payload.lines}
    known = set((await session.scalars(select(Product.sku).where(Product.sku.in_(skus)))).all())
    if skus != known:
        raise invalid("lines", "unknown_sku")
    return address


def scalar_values(payload: OrderIn) -> dict[str, object]:
    values = payload.model_dump(exclude={"lines", "contact", "window_start", "window_end"})
    for field in ("window_start", "window_end"):
        raw = getattr(payload, field)
        try:
            values[field] = time.fromisoformat(raw) if raw is not None else None
        except ValueError:
            raise invalid(field, "invalid_receiving_window") from None
    contact = payload.contact
    values.update(
        contact_name=contact.name if contact else None,
        contact_phone=contact.phone if contact else None,
        contact_email=contact.email if contact else None,
    )
    return values


async def insert_lines(session: AsyncSession, order_id: str, payload: OrderIn, *, now: datetime) -> None:
    for line in payload.lines:
        session.add(
            OrderLine(
                order_id=order_id,
                line_no=line.line_no,
                sku=line.sku,
                qty=line.qty,
                unit_price=Decimal(line.unit_price),
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()


async def create(
    session: AsyncSession, payload: OrderIn, *, now: datetime, key: str | None = None
) -> OrderOut:
    if now.tzinfo is None:
        raise ValueError("Order timestamp must be aware")
    digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    if key:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": "source-create:" + key}
        )
        previous = await session.get(CreateRequest, key)
        if previous is not None:
            if previous.request_hash != digest:
                raise SourceOrderError(409, "IDEMPOTENCY_CONFLICT", "Idempotency key has different content.")
            existing = (await session.scalars(select(Order).where(Order.id == previous.order_id))).one()
            return await view(session, existing)
    address = await references(session, payload)
    order = Order(
        id=str(uuid4()),
        version=1,
        status="DRAFT",
        address=address.address,
        lat=address.lat,
        lon=address.lon,
        created_at=now,
        updated_at=now,
        **scalar_values(payload),
    )
    session.add(order)
    await session.flush()
    await insert_lines(session, order.id, payload, now=now)
    if key:
        session.add(
            CreateRequest(key=key, request_hash=digest, order_id=order.id, created_at=now, updated_at=now)
        )
    return await view(session, order)
