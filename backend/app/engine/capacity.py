"""Bước 2b (phần 1) — công suất giờ công theo ngày (04 mục 6.2; BR-PRP-02; US-WH-02).

labour_cap(d) = Σ_ca present_staff × useful_hours × delivery_share; free(d) = labour_cap − booked.
Ngày không làm việc / ngày lễ → 0. Không có thiết bị (v1.1).

Owner: Dev 1 (luồng A).
"""

from datetime import date
from decimal import Decimal

from app.engine.types import DayCapacity, EngineConfig


def labour_capacity(day: DayCapacity, cfg: EngineConfig) -> Decimal:
    """Giờ công khả dụng: Σ_ca present_staff × useful_hours_per_staff × delivery_share; ngày nghỉ/lễ → 0."""
    if not is_working_day(day.day, cfg):
        return Decimal(0)
    total = sum((s.present_staff * s.useful_hours_per_staff for s in day.shifts), Decimal(0))
    return total * cfg.delivery_share


def free_hours(day: DayCapacity, cfg: EngineConfig) -> Decimal:
    """Giờ công còn trống sau khi trừ giờ đã đặt (committed + held đơn khác); không âm."""
    return max(Decimal(0), labour_capacity(day, cfg) - day.booked_hours)


def is_working_day(d: date, cfg: EngineConfig) -> bool:
    """Ngày làm việc của market (bỏ ngày lễ)."""
    return d.isoweekday() in cfg.working_days and d not in cfg.holidays
