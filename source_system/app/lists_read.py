"""Paginated, incremental source reads other than orders (06 section 16.1, DEC-SRC-D1-001 D1-A).

Envelope `{items,page,page_size,total}` + `X-Total-Count`; `updated_since` is inclusive (`updated_at >=`) and
rows are ordered by `(updated_at, natural key)` so rows with equal timestamps are never skipped between pages.
Offset paging is not a frozen snapshot under concurrent writes: the reader keeps a checkpoint and overlaps.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, BaseModel, field_serializer
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import Address, Customer, Inbound, Product, VehicleCalendar
from app.orders_read import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


class Paging:
    """Common query parameters of every list endpoint."""

    def __init__(
        self,
        request: Request,
        response: Response,
        updated_since: AwareDatetime | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ) -> None:
        self.engine: AsyncEngine = request.app.state.engine
        self.response = response
        self.updated_since, self.page, self.page_size = updated_since, page, page_size


async def fetch_page(
    paging: Paging, query: Select[Any], updated_at: Any, *order: Any
) -> tuple[list[Any], int]:
    if paging.updated_since is not None:
        query = query.where(updated_at >= paging.updated_since)
    async with AsyncSession(paging.engine, expire_on_commit=False) as session:
        total = int((await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
        rows = (
            (
                await session.execute(
                    query.order_by(updated_at, *order)
                    .limit(paging.page_size)
                    .offset((paging.page - 1) * paging.page_size)
                )
            )
            .scalars()
            .all()
        )
    paging.response.headers["X-Total-Count"] = str(total)
    return list(rows), total


class CustomerOut(BaseModel):
    id: str
    name: str
    email: str | None
    phone: str | None
    type: str
    updated_at: datetime


class CustomerPage(BaseModel):
    items: list[CustomerOut]
    page: int
    page_size: int
    total: int


class ProductOut(BaseModel):
    sku: str
    name: str
    category: str | None
    gtin: str | None
    sale_unit: str
    units_to_base: Decimal
    unit_price: Decimal
    weight_kg: Decimal
    volume_m3: Decimal
    updated_at: datetime

    @field_serializer("units_to_base", "weight_kg", "volume_m3")
    def _numeric(self, value: Decimal) -> int | float:
        return _number(value)

    @field_serializer("unit_price")
    def _money(self, value: Decimal) -> str:
        return format(value, "f")


class ProductPage(BaseModel):
    items: list[ProductOut]
    page: int
    page_size: int
    total: int


class InboundOut(BaseModel):
    inbound_ref: str
    warehouse_code: str
    sku: str
    qty: Decimal
    eta_date: date
    confirmed: bool
    received: bool
    updated_at: datetime

    @field_serializer("qty")
    def _qty(self, value: Decimal) -> int | float:
        return _number(value)


class InboundPage(BaseModel):
    items: list[InboundOut]
    page: int
    page_size: int
    total: int


class FleetPage(BaseModel):
    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


class AddressOut(BaseModel):
    id: str
    customer_id: str
    address: str
    lat: Decimal | None
    lon: Decimal | None
    updated_at: datetime

    @field_serializer("lat", "lon")
    def _coordinate(self, value: Decimal | None) -> float | None:
        return None if value is None else float(value)


class AddressPage(BaseModel):
    items: list[AddressOut]
    page: int
    page_size: int
    total: int


def _page(paging: Paging, items: list[Any], total: int) -> dict[str, Any]:
    return {"items": items, "page": paging.page, "page_size": paging.page_size, "total": total}


async def customers(paging: Paging) -> CustomerPage:
    rows, total = await fetch_page(paging, select(Customer), Customer.updated_at, Customer.id)
    return CustomerPage(
        **_page(paging, [CustomerOut.model_validate(r, from_attributes=True) for r in rows], total)
    )


async def products(paging: Paging) -> ProductPage:
    rows, total = await fetch_page(paging, select(Product), Product.updated_at, Product.sku)
    return ProductPage(
        **_page(paging, [ProductOut.model_validate(r, from_attributes=True) for r in rows], total)
    )


async def inbound(paging: Paging) -> InboundPage:
    rows, total = await fetch_page(
        paging, select(Inbound), Inbound.updated_at, Inbound.inbound_ref, Inbound.warehouse_code, Inbound.sku
    )
    return InboundPage(
        **_page(paging, [InboundOut.model_validate(r, from_attributes=True) for r in rows], total)
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def addresses(paging: Paging, customer_id: str | None, q: str | None) -> AddressPage:
    query = select(Address)
    if customer_id:
        query = query.where(Address.customer_id == customer_id)
    if q and q.strip():
        query = query.where(Address.address.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
    rows, total = await fetch_page(paging, query, Address.updated_at, Address.id)
    return AddressPage(
        **_page(paging, [AddressOut.model_validate(r, from_attributes=True) for r in rows], total)
    )


async def fleet_calendar(paging: Paging, start: datetime | None, end: datetime | None) -> FleetPage:
    """Busy intervals overlapping the half-open range `[from, to)`; either bound may be omitted."""
    if start is not None and end is not None and not start < end:
        raise RequestValidationError(
            [{"type": "invalid_range", "loc": ("query", "to"), "msg": "to must be after from", "input": None}]
        )
    query = select(VehicleCalendar)
    if end is not None:
        query = query.where(VehicleCalendar.from_ts < end)
    if start is not None:
        query = query.where(VehicleCalendar.to_ts > start)
    rows, total = await fetch_page(
        paging,
        query,
        VehicleCalendar.updated_at,
        VehicleCalendar.vehicle_code,
        VehicleCalendar.from_ts,
        VehicleCalendar.to_ts,
    )
    items = [
        {
            "vehicle_code": r.vehicle_code,
            "from": r.from_ts.isoformat(),
            "to": r.to_ts.isoformat(),
            "kind": r.kind,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]
    return FleetPage(**_page(paging, items, total))


PagingDep = Annotated[Paging, Depends()]
