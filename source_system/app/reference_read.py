"""D1-A paginated reference feeds (US-SRC-02); read-only, inclusive checkpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, BaseModel, ConfigDict, field_serializer
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Address, Base, Customer, Inbound, Product, VehicleCalendar

router = APIRouter()


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int


class Paging:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=500)] = 50,
        updated_since: AwareDatetime | None = None,
    ) -> None:
        self.page, self.page_size, self.updated_since = page, page_size, updated_since


Params = Annotated[Paging, Depends()]


class Row(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    updated_at: datetime


class CustomerOut(Row):
    id: str
    name: str
    email: str | None
    phone: str | None
    type: str


class AddressOut(Row):
    id: str
    customer_id: str
    address: str
    lat: Decimal | None
    lon: Decimal | None

    @field_serializer("lat", "lon")
    def coordinate(self, value: Decimal | None) -> float | None:
        return None if value is None else float(value)


class ProductOut(Row):
    sku: str
    name: str
    category: str | None
    gtin: str | None
    sale_unit: str
    units_to_base: Decimal
    unit_price: Decimal
    weight_kg: Decimal
    volume_m3: Decimal

    @field_serializer("unit_price")
    def money(self, value: Decimal) -> str:
        return format(value, ".2f")

    @field_serializer("units_to_base", "weight_kg", "volume_m3")
    def number(self, value: Decimal) -> int | float:
        return int(value) if value == value.to_integral_value() else float(value)


class InboundOut(Row):
    inbound_ref: str
    warehouse_code: str
    sku: str
    qty: Decimal
    eta_date: date
    confirmed: bool
    received: bool

    @field_serializer("qty")
    def number(self, value: Decimal) -> int | float:
        return int(value) if value == value.to_integral_value() else float(value)


class FleetOut(Row):
    vehicle_code: str
    from_ts: datetime
    to_ts: datetime
    kind: str


async def read_page[T: Base, V: Row](
    request: Request, response: Response, params: Paging, query: Select[tuple[T]], view: type[V]
) -> Page[V]:
    # Count and rows share a PostgreSQL snapshot; offset pages across requests are not frozen.
    async with request.app.state.engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="REPEATABLE READ")
        async with AsyncSession(bind=connection) as session, session.begin():
            total = int((await session.scalar(select(func.count()).select_from(query.subquery()))) or 0)
            rows = await session.scalars(
                query.limit(params.page_size).offset((params.page - 1) * params.page_size)
            )
            items = [view.model_validate(row) for row in rows]
    response.headers["X-Total-Count"] = str(total)
    return Page(items=items, page=params.page, page_size=params.page_size, total=total)


def feed[T: Base](model: type[T], params: Paging) -> Select[tuple[T]]:
    # Every source reference model has timestamps and its declared natural primary key.
    query = cast(Select[tuple[T]], select(model))  # SQLAlchemy cannot infer a generic mapped class.
    updated_at = model.__table__.c.updated_at
    if params.updated_since is not None:
        query = query.where(updated_at >= params.updated_since)
    return query.order_by(updated_at, *model.__table__.primary_key)


@router.get("/customers", response_model=Page[CustomerOut])
async def customers(request: Request, response: Response, params: Params) -> Page[CustomerOut]:
    return await read_page(request, response, params, feed(Customer, params), CustomerOut)


@router.get("/products", response_model=Page[ProductOut])
async def products(request: Request, response: Response, params: Params) -> Page[ProductOut]:
    return await read_page(request, response, params, feed(Product, params), ProductOut)


@router.get("/inbound", response_model=Page[InboundOut])
async def inbound(request: Request, response: Response, params: Params) -> Page[InboundOut]:
    return await read_page(request, response, params, feed(Inbound, params), InboundOut)


@router.get("/addresses", response_model=Page[AddressOut])
async def addresses(
    request: Request, response: Response, params: Params, q: str = "", customer_id: str | None = None
) -> Page[AddressOut]:
    query = feed(Address, params)
    if customer_id is not None:
        query = query.where(Address.customer_id == customer_id)
    if q:
        # Literal substring, not a client-supplied SQL wildcard expression.
        query = query.join(Customer, Customer.id == Address.customer_id).where(
            or_(Address.address.icontains(q, autoescape=True), Customer.name.icontains(q, autoescape=True))
        )
    return await read_page(request, response, params, query, AddressOut)


@router.get("/fleet/calendar", response_model=Page[FleetOut])
async def fleet(
    request: Request,
    response: Response,
    params: Params,
    start: Annotated[AwareDatetime, Query(alias="from")],
    end: Annotated[AwareDatetime, Query(alias="to")],
) -> Page[FleetOut]:
    if start >= end:
        raise RequestValidationError(
            [{"loc": ("query", "to"), "type": "invalid_time_range", "msg": "Require from < to."}]
        )
    query = feed(VehicleCalendar, params).where(VehicleCalendar.from_ts < end, VehicleCalendar.to_ts > start)
    return await read_page(request, response, params, query, FleetOut)
