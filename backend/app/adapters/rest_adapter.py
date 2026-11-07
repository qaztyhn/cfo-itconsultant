"""RestMarketAdapter — gọi API hệ thống nguồn giả lập qua httpx (06 mục 16).

Đọc base_url và khóa từ ref.market (source_base_url, source_api_key_ref → env). Phân trang
page_size ≤ 500, thứ tự (updated_at, id). Lỗi HTTP 5xx → ném để ingest_service đánh dấu failed.

Owner: Dev 2 (luồng B) — M2.
"""

import json
from decimal import Decimal

import httpx
from pydantic import AwareDatetime, BaseModel, Field, ValidationError

from app.adapters.base import StockItemDTO, StockSnapshotDTO


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
