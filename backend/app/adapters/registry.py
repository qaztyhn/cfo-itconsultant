"""Tra adapter theo market_code. Market chưa có adapter → lỗi cấu hình rõ ràng, không ảnh hưởng nước
khác (US-INT-04 AC2).

Owner: Dev 2 (luồng B) — M2.
"""


def get_adapter(market_code: str) -> object:
    """Trả adapter đã cấu hình cho market. TODO(#M2-adapter)."""
    raise NotImplementedError
