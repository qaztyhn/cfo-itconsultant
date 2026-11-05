"""Gợi ý chuyển kho bằng quy tắc (04 mục 6.4; BR-ATP-05; US-ATP-02).

Khi mọi kho STOCK_SHORT: kho nguồn s ≠ w đủ điều kiện nếu tồn sẵn có ≥ phần thiếu mọi dòng
(không dựa hàng nhập). Sắp theo lead_days tăng rồi khoảng cách tăng; tối đa 3.

Owner: Dev 1 (luồng A).
"""

from decimal import Decimal

from app.engine.types import TransferSuggestion, WarehouseCtx


def suggest_transfers(
    target: WarehouseCtx,
    shortage: dict[int, Decimal],
    others: list[WarehouseCtx],
    lead_days: dict[tuple[int, int], int],
    distance_km: dict[tuple[int, int], Decimal],
    default_lead_days: int,
) -> tuple[TransferSuggestion, ...]:
    """Tối đa 3 gợi ý chuyển kho. TODO(#M4-transfer)."""
    raise NotImplementedError
