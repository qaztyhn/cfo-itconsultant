"""RestMarketAdapter — gọi API hệ thống nguồn giả lập qua httpx (06 mục 16).

Đọc base_url và khóa từ ref.market (source_base_url, source_api_key_ref → env). Phân trang
page_size ≤ 500, thứ tự (updated_at, id). Lỗi HTTP 5xx → ném để ingest_service đánh dấu failed.

Owner: Dev 2 (luồng B) — M2.
"""


class RestMarketAdapter:
    """Adapter REST chuẩn. TODO(#M2-adapter)."""

    def __init__(self, market_code: str, base_url: str, api_key: str) -> None:
        self.market_code = market_code
        self.base_url = base_url
        self._api_key = api_key
