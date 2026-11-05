"""Nhập liệu từ hệ thống nguồn (04 mục 5.2; US-INT-01..04).

Checkpoint − 2 phút; upsert theo (market_id, external_ref) và source_version; dòng lỗi → stg.sync_reject
(BAD_QTY, UNKNOWN_WAREHOUSE, BAD_DATE, MISSING_COORDS, UNKNOWN_SKU); sync_run ok|partial|failed; chỉ ghi
checkpoint khi ok/partial; failed → alert SYNC_FAILED. Đơn APPROVED đổi ở nguồn → KHÔNG ghi đè, alert
ORDER_CHANGED_AFTER_APPROVAL. Tồn kho ghi đè + as_of; quá stale_stock_min → STALE_DATA. Sản phẩm chưa ánh
xạ được nạp với mapping_status=pending (không phải dòng bị loại).

Owner: Dev 2 (B) — M2.
"""


async def run_entity(market_code: str, entity: str) -> int:
    """TODO(#ingest-run_entity)."""
    raise NotImplementedError


async def ingest_orders(market_code: str) -> int:
    """TODO(#ingest-ingest_orders)."""
    raise NotImplementedError


async def ingest_stock(market_code: str) -> int:
    """TODO(#ingest-ingest_stock)."""
    raise NotImplementedError


async def ingest_inbound(market_code: str) -> int:
    """TODO(#ingest-ingest_inbound)."""
    raise NotImplementedError


async def ingest_products(market_code: str) -> int:
    """TODO(#ingest-ingest_products)."""
    raise NotImplementedError


async def ingest_fleet(market_code: str) -> int:
    """TODO(#ingest-ingest_fleet)."""
    raise NotImplementedError
