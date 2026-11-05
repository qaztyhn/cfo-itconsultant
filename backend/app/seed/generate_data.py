"""Sinh dữ liệu seed CFO (08 mục 5). Random seed cố định 20261104; chạy lại cho kết quả giống nhau.

3 kho (GBG, STO, MLM; cut-off 15:00), 25 cửa hàng, ~100 SKU phủ N1–N6 (3 SKU chưa ánh xạ), 8–10 xe
(gồm STO-CR-01 crane 8 t, tipper MLM), 10 tài xế (1 bằng hết hạn), ~150 nhân viên, ~40 khách, ngày lễ SE,
đơn kịch bản (000123, 137, 141, 138, 129, 131, 144, 152, 118, 146–155, 156), 48 đơn đã đóng cho KPI.
KHÔNG seed thiết bị kho (v1.1). Business owner can_view_revenue = true; Project lead = false.

Owner: Dev 2 (luồng B) — M1, M4, M8.
"""

RANDOM_SEED = 20261104


def main() -> None:
    """Điểm vào `make seed`. TODO(#M1-seed)."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
