"""Đưa batch tồn kho đã xác minh của WMS giả lập vào luồng nạp tồn kho T07 (E1).

Chỉ chuyển đổi và phục vụ dữ liệu có sẵn trong bộ nhớ: không gọi mạng, không ghi DB. Việc kiểm tra
scope/đơn vị/mapping vẫn do `ingest_stock.apply` thực hiện. SKU WMS được đổi sang SKU POS bằng quan hệ
do server cấu hình; hàng không có trong quan hệ bị bỏ (ngoài scope, không bao giờ chặn).
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.base import StockItemDTO, StockSnapshotDTO
from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError


class WmsBatchRejected(Exception):
    """Mã tĩnh, không chứa nội dung batch."""


def snapshot_from_wms_batch(
    batch: Mapping[str, Any], native_to_pos: Mapping[tuple[str, str], tuple[str, str]]
) -> StockSnapshotDTO:
    """native_to_pos: (kho, SKU WMS) -> (SKU POS, đơn vị WMS)."""
    try:
        batch_id = batch["batch_id"]
        raw_items = batch["items"]
        if (
            type(batch_id) is not int
            or batch_id < 1
            or batch["complete"] is not True
            or batch["item_count"] != len(raw_items)
        ):
            raise WmsBatchRejected("WMS_BATCH_INCOMPLETE")
        as_of = datetime.fromisoformat(str(batch["as_of"]))
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise WmsBatchRejected("WMS_BATCH_AS_OF_INVALID")
        items: list[StockItemDTO] = []
        seen: set[tuple[str, str]] = set()
        for row in raw_items:
            key = (str(row["warehouse_code"]), str(row["wms_sku"]))
            target = native_to_pos.get(key)
            if target is None:
                continue
            pos_sku, unit = target
            if str(row["wms_unit"]) != unit:
                raise WmsBatchRejected("WMS_UNIT_MISMATCH")
            if (key[0], pos_sku) in seen:
                raise WmsBatchRejected("WMS_BATCH_DUPLICATE_ROW")
            seen.add((key[0], pos_sku))
            items.append(
                StockItemDTO(key[0], pos_sku, Decimal(str(row["on_hand"])), Decimal(str(row["reserved"])))
            )
    except WmsBatchRejected:
        raise
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise WmsBatchRejected("WMS_BATCH_INVALID") from None
    ordered = tuple(sorted(items, key=lambda item: (item.warehouse_code, item.sku)))
    return StockSnapshotDTO(as_of=as_of, items=ordered, batch_id=batch_id, item_count=len(ordered))


class WmsBatchStockAdapter(RestMarketAdapter):
    """Phục vụ snapshot đã xác minh và danh mục đơn vị từ bộ nhớ cho `read_feed(..., "stock")`."""

    def __init__(
        self, market_code: str, snapshot: StockSnapshotDTO, products: Sequence[Mapping[str, object]]
    ) -> None:
        super().__init__(market_code, "http://wms-batch.invalid/", "unused-in-memory-adapter")
        self._snapshot = snapshot
        self._products = tuple(dict(row) for row in products)

    async def fetch_stock(self) -> StockSnapshotDTO:
        return self._snapshot

    async def raw_pages(
        self,
        entity: str,
        since: datetime | None,
        *,
        key_fields: tuple[str, ...],
        page_size: int = 50,
        filters: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        if entity != "products":
            raise SourceReadError("In-memory WMS batch adapter serves only the unit catalogue")
        for row in self._products:
            yield dict(row)
