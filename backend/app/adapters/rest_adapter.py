"""RestMarketAdapter — gọi API hệ thống nguồn giả lập qua httpx (06 mục 16).

Đọc base_url và khóa từ ref.market (source_base_url, source_api_key_ref → env). Phân trang
page_size ≤ 500, thứ tự (updated_at, id). Lỗi HTTP 5xx → ném để ingest_service đánh dấu failed.

Owner: Dev 2 (luồng B) — M2.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.adapters.base import (
    AddressDTO,
    CancellationDTO,
    CustomerDTO,
    FleetBlockDTO,
    InboundDTO,
    OrderDTO,
    ProductDTO,
    StockItemDTO,
    StockSnapshotDTO,
)
from app.adapters.order_wire import SourceCancellation, SourceOrder
from app.adapters.reference_wire import (
    SourceAddress,
    SourceCustomer,
    SourceFleet,
    SourceInbound,
    SourceProduct,
)


class _Page[T](BaseModel):
    items: list[T]
    page: int = Field(ge=1, strict=True)
    page_size: int = Field(ge=1, le=500, strict=True)
    total: int = Field(ge=0, strict=True)


class SourceReadError(RuntimeError):
    """Safe error for ingestion; never includes HTTP bodies, URLs or credentials."""


class StockUnavailable(SourceReadError):
    """Source answered 503 STOCK_UNAVAILABLE: no complete published batch. Never means zero stock."""


class _StockItem(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a producer still sending pool identity is refused
    warehouse_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    on_hand: Decimal = Field(allow_inf_nan=False)
    reserved: Decimal = Field(allow_inf_nan=False)


class _StockSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: AwareDatetime
    batch_id: int = Field(gt=0, strict=True)
    item_count: int = Field(ge=0, strict=True)
    items: list[_StockItem]


class RestMarketAdapter:
    """Read-only D1 source feeds; persistence/routing/checkpoints belong to ingestion."""

    def __init__(
        self,
        market_code: str,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_pages: int = 10000,
        market_timezone: str | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Source API key is required")
        try:
            url = httpx.URL(base_url)
        except httpx.InvalidURL:
            raise ValueError("Invalid source base URL") from None
        if url.scheme not in ("http", "https") or not url.host or url.userinfo or url.query or url.fragment:
            raise ValueError("Source base URL must be HTTP(S) without credentials, query or fragment")
        if not 0 < timeout_seconds < float("inf"):
            raise ValueError("Source timeout must be finite and positive")
        self.market_code = market_code
        self.base_url = str(url).rstrip("/") + "/"
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        if max_pages <= 0:
            raise ValueError("Page safety limit must be positive")
        self._max_pages = max_pages
        try:
            self._zone = ZoneInfo(market_timezone) if market_timezone else None
        except KeyError:
            raise ValueError("Invalid source market timezone") from None

    async def _pages[
        T: SourceCustomer
        | SourceProduct
        | SourceOrder
        | SourceCancellation
        | SourceAddress
        | SourceInbound
        | SourceFleet
    ](
        self,
        entity: str,
        since: datetime | None,
        model: type[T],
        *,
        key_fields: tuple[str, ...],
        page_size: int = 50,
        filters: dict[str, str] | None = None,
    ) -> AsyncIterator[T]:
        if (
            since is not None and (since.tzinfo is None or since.utcoffset() is None)
        ) or not 1 <= page_size <= 500:
            raise ValueError("Source checkpoint must be aware and page size in 1..500")
        seen: set[tuple[str, ...]] = set()
        last: tuple[datetime, tuple[str, ...]] | None = None
        total: int | None = None
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport, follow_redirects=False
        ) as client:
            for page in range(1, self._max_pages + 1):
                try:
                    response = await client.get(
                        self.base_url + entity,
                        headers={"X-API-Key": self._api_key},
                        params={
                            **({"updated_since": since.isoformat()} if since is not None else {}),
                            "page": page,
                            "page_size": page_size,
                            **(filters or {}),
                        },
                    )
                    response.raise_for_status()
                    # JSON document is an external boundary; fractions are parsed without a float round-trip.
                    raw: object = json.loads(response.content, parse_float=Decimal)
                    batch = _Page[dict[str, object]].model_validate(raw)
                    header_total = int(response.headers["X-Total-Count"])
                except (httpx.HTTPError, ValueError, KeyError):
                    raise SourceReadError("Source reference page is unavailable or invalid") from None
                if (
                    batch.page != page
                    or batch.page_size != page_size
                    or header_total != batch.total
                    or (total is not None and batch.total != total)
                ):
                    raise SourceReadError("Source reference pagination changed; retry the feed")
                total = batch.total
                expected = min(page_size, max(0, total - (page - 1) * page_size))
                if len(batch.items) != expected:
                    raise SourceReadError("Source reference page is incomplete")
                for row in batch.items:
                    try:
                        item = model.model_validate(row)
                    except ValueError:
                        raise SourceReadError("Source reference item is invalid") from None
                    parts = [getattr(item, field) for field in key_fields]
                    key = tuple(
                        value.astimezone(UTC).isoformat() if isinstance(value, datetime) else str(value)
                        for value in parts
                    )
                    current = (item.updated_at, key)
                    if (
                        key in seen
                        or (since is not None and item.updated_at < since)
                        or (last is not None and current <= last)
                    ):
                        raise SourceReadError("Source reference keys/checkpoint ordering is invalid")
                    seen.add(key)
                    last = current
                    yield cast(T, item)  # model_validate returns the runtime model passed above.
                if page * page_size >= total:
                    return
        raise SourceReadError("Source reference page safety limit exceeded")

    async def fetch_customers(self, updated_since: datetime) -> AsyncIterator[CustomerDTO]:
        async for item in self._pages("customers", updated_since, SourceCustomer, key_fields=("id",)):
            yield CustomerDTO(item.id, item.type, item.name, item.email, item.phone, item.updated_at)

    async def fetch_addresses(self, updated_since: datetime) -> AsyncIterator[AddressDTO]:
        async for item in self._pages("addresses", updated_since, SourceAddress, key_fields=("id",)):
            yield AddressDTO(
                item.id,
                item.customer_id,
                item.address,
                item.lat,
                item.lon,
                item.receiving_hours,
                item.updated_at,
            )

    async def fetch_inbound(self, *, updated_since: datetime | None = None) -> list[InboundDTO]:
        return [
            InboundDTO(
                item.inbound_ref,
                item.warehouse_code,
                item.sku,
                item.qty,
                item.eta_date,
                item.confirmed,
                item.received,
                item.updated_at,
            )
            async for item in self._pages(
                "inbound", updated_since, SourceInbound, key_fields=("inbound_ref", "warehouse_code", "sku")
            )
        ]

    async def fetch_fleet(
        self, date_from: date, date_to: date, *, updated_since: datetime | None = None
    ) -> list[FleetBlockDTO]:
        """Date bounds are half-open market-local midnights; callers must supply an exclusive end date."""
        if self._zone is None:
            raise SourceReadError("Source fleet market timezone must be configured")
        if date_from >= date_to:
            raise ValueError("Fleet dates require a half-open ordered range")
        begin, end = datetime.combine(date_from, time.min, self._zone), datetime.combine(
            date_to, time.min, self._zone
        )
        if any(
            point.replace(fold=0).utcoffset() != point.replace(fold=1).utcoffset() for point in (begin, end)
        ):
            raise SourceReadError("Fleet boundary requires explicit timezone resolution")
        return [
            FleetBlockDTO(item.vehicle_code, item.start, item.end, item.kind, item.updated_at)
            async for item in self._pages(
                "fleet/calendar",
                updated_since,
                SourceFleet,
                key_fields=("vehicle_code", "start", "end"),
                filters={"from": begin.isoformat(), "to": end.isoformat()},
            )
        ]

    async def fetch_orders(self, updated_since: datetime, page_size: int = 200) -> AsyncIterator[OrderDTO]:
        async for item in self._pages(
            "orders",
            updated_since,
            SourceOrder,
            key_fields=("id",),
            page_size=page_size,
            filters={"status": "SUBMITTED_FOR_PLANNING"},
        ):
            yield item.dto()

    async def fetch_cancelled_orders(
        self, updated_since: datetime, page_size: int = 200
    ) -> AsyncIterator[CancellationDTO]:
        async for item in self._pages(
            "orders",
            updated_since,
            SourceCancellation,
            key_fields=("id",),
            page_size=page_size,
            filters={"status": "CANCELLED"},
        ):
            yield item.dto()

    async def fetch_products(self, updated_since: datetime) -> AsyncIterator[ProductDTO]:
        async for item in self._pages("products", updated_since, SourceProduct, key_fields=("sku",)):
            yield ProductDTO(
                item.sku,
                item.name,
                item.category,
                item.gtin,
                item.sale_unit,
                item.units_to_base,
                item.unit_price,
                item.weight_kg,
                item.volume_m3,
                item.updated_at,
            )

    async def fetch_stock(self) -> StockSnapshotDTO:
        """Fetch the latest complete published batch; the caller owns persistence and sync status.

        `503 STOCK_UNAVAILABLE` raises `StockUnavailable`: keep the previous snapshot, never replace it with
        an empty one. A legacy `{as_of, items}` body without batch markers is refused (no completeness proof).
        """
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.get(self.base_url + "stock", headers={"X-API-Key": self._api_key})
        except httpx.RequestError:
            raise SourceReadError("Source stock request failed") from None
        if response.status_code == 503 and _error_code(response) == "STOCK_UNAVAILABLE":
            raise StockUnavailable("Source stock snapshot is unavailable")
        if response.status_code != 200:
            raise SourceReadError("Source stock request returned an unsuccessful status")
        try:
            # Parse JSON fractions as Decimal before validation, avoiding a float round-trip.
            snapshot = _StockSnapshot.model_validate(json.loads(response.content, parse_float=Decimal))
        except (ValueError, ValidationError):
            raise SourceReadError("Source stock response is invalid") from None
        if snapshot.item_count != len(snapshot.items):
            raise SourceReadError("Source stock batch is incomplete")
        keys = [(item.warehouse_code, item.sku) for item in snapshot.items]
        if len(keys) != len(set(keys)):
            raise SourceReadError("Source stock response contains duplicate item keys")
        return StockSnapshotDTO(
            as_of=snapshot.as_of,
            items=tuple(
                StockItemDTO(item.warehouse_code, item.sku, item.on_hand, item.reserved)
                for item in snapshot.items
            ),
            batch_id=snapshot.batch_id,
            item_count=snapshot.item_count,
        )


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = json.loads(response.content)
        code = body["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None
    return code if isinstance(code, str) else None
