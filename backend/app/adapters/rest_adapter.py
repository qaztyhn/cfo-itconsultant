"""RestMarketAdapter — gọi API hệ thống nguồn giả lập qua httpx (06 mục 16).

Đọc base_url và khóa từ ref.market (source_base_url, source_api_key_ref → env). Phân trang
page_size ≤ 500, thứ tự (updated_at, id). Lỗi HTTP 5xx → ném để ingest_service đánh dấu failed.

Owner: Dev 2 (luồng B) — M2.
"""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import cast

import httpx
from pydantic import AwareDatetime, BaseModel, Field, ValidationError

from app.adapters.base import CustomerDTO, ProductDTO, StockItemDTO, StockSnapshotDTO


class _Customer(BaseModel):
    id: str = Field(min_length=1)
    type: str
    name: str
    email: str | None
    phone: str | None
    updated_at: AwareDatetime


class _Product(BaseModel):
    sku: str = Field(min_length=1)
    name: str
    category: str | None
    gtin: str | None
    sale_unit: str
    units_to_base: Decimal = Field(gt=0, allow_inf_nan=False)
    unit_price: Decimal = Field(ge=0, allow_inf_nan=False)
    weight_kg: Decimal | None = Field(ge=0, allow_inf_nan=False)
    volume_m3: Decimal | None = Field(ge=0, allow_inf_nan=False)
    updated_at: AwareDatetime


class _Page[T](BaseModel):
    items: list[T]
    page: int = Field(ge=1, strict=True)
    page_size: int = Field(ge=1, le=500, strict=True)
    total: int = Field(ge=0, strict=True)


class SourceReadError(RuntimeError):
    """Safe error for ingestion; never includes HTTP bodies, URLs or credentials."""


class _StockItem(BaseModel):
    warehouse_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    on_hand: Decimal = Field(allow_inf_nan=False)
    reserved: Decimal = Field(allow_inf_nan=False)


class _StockSnapshot(BaseModel):
    as_of: AwareDatetime
    items: list[_StockItem]


class RestMarketAdapter:
    """Read-only source adapter. Stock is implemented; other feeds remain M2 work."""

    def __init__(
        self,
        market_code: str,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_pages: int = 10000,
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

    async def _pages[T: _Customer | _Product](
        self, entity: str, since: datetime, model: type[T], *, key_field: str, page_size: int = 50
    ) -> AsyncIterator[T]:
        if since.tzinfo is None or since.utcoffset() is None or not 1 <= page_size <= 500:
            raise ValueError("Source checkpoint must be aware and page size in 1..500")
        seen: set[str] = set()
        last: tuple[datetime, str] | None = None
        total: int | None = None
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport, follow_redirects=False
        ) as client:
            for page in range(1, self._max_pages + 1):
                try:
                    response = await client.get(
                        self.base_url + entity,
                        headers={"X-API-Key": self._api_key},
                        params={"updated_since": since.isoformat(), "page": page, "page_size": page_size},
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
                    key = str(getattr(item, key_field))
                    current = (item.updated_at, key)
                    if key in seen or item.updated_at < since or (last is not None and current <= last):
                        raise SourceReadError("Source reference keys/checkpoint ordering is invalid")
                    seen.add(key)
                    last = current
                    yield cast(T, item)  # model_validate returns the runtime model passed above.
                if page * page_size >= total:
                    return
        raise SourceReadError("Source reference page safety limit exceeded")

    async def fetch_customers(self, updated_since: datetime) -> AsyncIterator[CustomerDTO]:
        async for item in self._pages("customers", updated_since, _Customer, key_field="id"):
            yield CustomerDTO(item.id, item.type, item.name, item.email, item.phone, item.updated_at)

    async def fetch_products(self, updated_since: datetime) -> AsyncIterator[ProductDTO]:
        async for item in self._pages("products", updated_since, _Product, key_field="sku"):
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
        """Fetch one complete snapshot; the caller owns persistence and sync status."""
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.get(self.base_url + "stock", headers={"X-API-Key": self._api_key})
                response.raise_for_status()
        except httpx.HTTPStatusError:
            raise SourceReadError("Source stock request returned an unsuccessful status") from None
        except httpx.RequestError:
            raise SourceReadError("Source stock request failed") from None
        try:
            # Parse JSON fractions as Decimal before validation, avoiding a float round-trip.
            snapshot = _StockSnapshot.model_validate(json.loads(response.content, parse_float=Decimal))
        except (ValueError, ValidationError):
            raise SourceReadError("Source stock response is invalid") from None
        keys = [(item.warehouse_code, item.sku) for item in snapshot.items]
        if len(keys) != len(set(keys)):
            raise SourceReadError("Source stock response contains duplicate item keys")
        return StockSnapshotDTO(
            as_of=snapshot.as_of,
            items=tuple(
                StockItemDTO(item.warehouse_code, item.sku, item.on_hand, item.reserved)
                for item in snapshot.items
            ),
        )
