"""Bước 2a — time-phased ATP theo kho (04 mục 6.2; BR-ATP-01..04; US-ATP-01).

usable(w,p,d) = stock_available[p] + Σ inbound(confirmed, !received, eta + receiving_lead_days làm việc ≤ d).
stock_ready_date = ngày sớm nhất ≥ hôm nay mà mọi dòng đủ; không có trong search_days_max → STOCK_SHORT
và trả phần thiếu cho gợi ý chuyển kho. Dựa vào hàng nhập → complexity_points += 1.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from app.engine.types import EngineConfig, OrderCtx, WarehouseCtx


@dataclass(frozen=True)
class AtpResult:
    stock_ready_date: date | None
    classification: Literal["ready_now", "after_inbound", "short"]
    shortage: dict[int, Decimal]
    inbound_refs: tuple[str, ...]


def check_atp(order: OrderCtx, wh: WarehouseCtx, cfg: EngineConfig) -> AtpResult:
    """ATP của một kho cho mọi dòng. TODO(#M4-atp)."""
    raise NotImplementedError
