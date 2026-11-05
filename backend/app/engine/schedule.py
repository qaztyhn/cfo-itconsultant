"""Bước 2b (phần 2) + 2c — xếp lịch chuẩn bị và lên hàng (04 mục 6.2; BR-PRP-04; US-PLN-02).

Tiến tới sớm nhất từ start_day ≥ stock_ready_date; mỗi ngày a_L = min(L còn lại, free(d));
goods_ready_at ở ngày cuối theo ca; quá cutoff → lên hàng đầu ca ngày làm việc kế
(PREP_AFTER_CUTOFF, complexity +1); không đủ trong chân trời → PREP_NO_CAPACITY.
capacity_fill = (booked + giờ đơn) / Σ labour_cap trên các ngày chuẩn bị, kẹp [0,1].

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.engine.types import CheckResult, EngineConfig, WarehouseCtx


@dataclass(frozen=True)
class PrepSchedule:
    check: CheckResult
    prep_by_day: dict[date, Decimal]
    goods_ready_at: datetime | None
    loading_start_at: datetime | None
    capacity_fill: Decimal
    after_cutoff: bool


def schedule_preparation(
    labour_hours: Decimal, start_day: date, now: datetime, wh: WarehouseCtx, cfg: EngineConfig
) -> PrepSchedule:
    """Xếp giờ công vào các ngày và tính giờ lên hàng. TODO(#M4-schedule)."""
    raise NotImplementedError
