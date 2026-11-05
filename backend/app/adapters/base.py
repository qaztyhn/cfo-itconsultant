"""MarketAdapter Protocol và DTO chuẩn (04 mục 5.1).

Mọi nước dùng cùng hợp đồng (06 mục 16). Đặc thù một nước chỉ nằm trong lớp con adapter,
không có `if market == "SE"` trong lõi (09 bất biến 15).

Owner: Dev 2 (luồng B) — M2.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class OrderLineDTO:
    line_no: int
    sku: str
    qty: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class OrderDTO:
    external_ref: str
    version: int
    updated_at: datetime
    status: str
    customer_ref: str
    address: str
    lat: float
    lon: float
    contact: dict[str, str | None]
    date_mode: str
    date_from: date | None
    date_to: date
    window_start: str | None
    window_end: str | None
    receiving_restrictions: str | None
    special_requirements: str | None
    sales_code: str | None
    store_code: str | None
    lines: tuple[OrderLineDTO, ...]


@dataclass(frozen=True)
class CustomerDTO:
    external_ref: str
    type: str
    name: str
    email: str | None
    phone: str | None
    updated_at: datetime


@dataclass(frozen=True)
class ProductDTO:
    sku: str
    name: str
    category: str
    gtin: str | None
    sale_unit: str
    units_to_base: Decimal
    unit_price: Decimal
    weight_kg: Decimal | None
    volume_m3: Decimal | None
    updated_at: datetime


@dataclass(frozen=True)
class StockItemDTO:
    warehouse_code: str
    sku: str
    on_hand: Decimal
    reserved: Decimal


@dataclass(frozen=True)
class StockSnapshotDTO:
    as_of: datetime
    items: tuple[StockItemDTO, ...]


@dataclass(frozen=True)
class InboundDTO:
    inbound_ref: str
    warehouse_code: str
    sku: str
    qty: Decimal
    eta_date: date
    confirmed: bool


@dataclass(frozen=True)
class FleetBlockDTO:
    vehicle_code: str
    start: datetime
    end: datetime
    kind: str


class MarketAdapter(Protocol):
    """Giao diện adapter một nước."""

    market_code: str

    def fetch_orders(self, updated_since: datetime, page_size: int = 200) -> AsyncIterator[OrderDTO]: ...
    def fetch_customers(self, updated_since: datetime) -> AsyncIterator[CustomerDTO]: ...
    def fetch_products(self, updated_since: datetime) -> AsyncIterator[ProductDTO]: ...
    async def fetch_stock(self) -> StockSnapshotDTO: ...
    async def fetch_inbound(self) -> list[InboundDTO]: ...
    async def fetch_fleet(self, date_from: date, date_to: date) -> list[FleetBlockDTO]: ...
