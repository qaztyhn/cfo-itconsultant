"""Thêm một nước mới KHÔNG sửa lõi (US-INT-04; 07 mục 16): tạo dòng ref.market (shadow_mode = true),
bảng ref.product_<cc>, tái tạo view ref.v_product_local. Không file nào trong backend/app/engine thay đổi.

Dùng: python tools/add_market.py DK
Owner: Dev 2 (luồng B) — M1.
"""
import sys


def main(code: str) -> None:
    """TODO(#M1-add-market)."""
    raise NotImplementedError


if __name__ == "__main__":
    main(sys.argv[1])
