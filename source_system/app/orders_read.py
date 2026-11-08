"""Read side of the source order contract (06 section 16; SRC-Q1/Q3/Q6/Q7 in DEC-SRC-001).

Incremental read: `updated_at >= updated_since` (inclusive, so ties at a checkpoint are not lost; the adapter
upserts idempotently), stable order `(updated_at, id)`, envelope `{items,page,page_size,total}` and
`X-Total-Count`. Address/contact fields are the snapshot stored on the order, never the live customer record.
"""

from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_serializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import Order, OrderLine

OrderStatus = Literal["DRAFT", "VALIDATED", "SUBMITTED_FOR_PLANNING", "CANCELLED"]
MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 50


def money(value: Decimal) -> str:
    """Money is a decimal string with exactly two decimals (DEC-SRC-D1-001), e.g. "95.00"."""
    return format(value.quantize(Decimal("0.01")), "f")


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


class Contact(BaseModel):
    name: str | None
    phone: str | None
    email: str | None


class OrderLineOut(BaseModel):
    line_no: int
    sku: str
    qty: Decimal
    unit_price: Decimal

    @field_serializer("qty")
    def _qty(self, value: Decimal) -> int | float:
        return _number(value)

    @field_serializer("unit_price")
    def _price(self, value: Decimal) -> str:
        return money(value)


class OrderOut(BaseModel):
    id: str
    version: int
    updated_at: datetime
    status: OrderStatus
    customer_id: str
    address_id: str
    address: str | None
    lat: Decimal | None
    lon: Decimal | None
    contact: Contact
    date_mode: str
    date_from: str | None
    date_to: str | None
    window_start: str | None
    window_end: str | None
    receiving_restrictions: str | None
    special_requirements: str | None
    sales_code: str | None
    store_code: str | None
    lines: list[OrderLineOut]

    @field_serializer("lat", "lon")
    def _coordinate(self, value: Decimal | None) -> float | None:
        return None if value is None else float(value)


class OrderPage(BaseModel):
    items: list[OrderOut]
    page: int
    page_size: int
    total: int


def _hhmm(value: time | None) -> str | None:
    return None if value is None else value.strftime("%H:%M")


def _view(order: Order, lines: list[OrderLine]) -> OrderOut:
    return OrderOut(
        id=order.id,
        version=order.version,
        updated_at=order.updated_at,
        status=order.status,  # type: ignore[arg-type]  # enforced by ck_src_order_status
        customer_id=order.customer_id,
        address_id=order.address_id,
        address=order.address,
        lat=order.lat,
        lon=order.lon,
        contact=Contact(name=order.contact_name, phone=order.contact_phone, email=order.contact_email),
        date_mode=order.date_mode,
        date_from=None if order.date_from is None else order.date_from.isoformat(),
        date_to=None if order.date_to is None else order.date_to.isoformat(),
        window_start=_hhmm(order.window_start),
        window_end=_hhmm(order.window_end),
        receiving_restrictions=order.receiving_restrictions,
        special_requirements=order.special_requirements,
        sales_code=order.sales_code,
        store_code=order.store_code,
        lines=[
            OrderLineOut(line_no=ln.line_no, sku=ln.sku, qty=ln.qty, unit_price=ln.unit_price) for ln in lines
        ],
    )


async def list_orders(
    engine: AsyncEngine,
    *,
    status: OrderStatus,
    updated_since: datetime | None,
    page: int,
    page_size: int,
) -> OrderPage:
    query = select(Order).where(Order.status == status)
    if updated_since is not None:
        query = query.where(Order.updated_at >= updated_since)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        total = int((await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
        orders = (
            (
                await session.execute(
                    query.order_by(Order.updated_at, Order.id).limit(page_size).offset((page - 1) * page_size)
                )
            )
            .scalars()
            .all()
        )
        by_order: dict[str, list[OrderLine]] = {o.id: [] for o in orders}
        if orders:
            lines = await session.execute(
                select(OrderLine)
                .where(OrderLine.order_id.in_(by_order))
                .order_by(OrderLine.order_id, OrderLine.line_no)
            )
            for line in lines.scalars():
                by_order[line.order_id].append(line)
    return OrderPage(
        items=[_view(o, by_order[o.id]) for o in orders], page=page, page_size=page_size, total=total
    )
