"""Bước 2b (phần 1) — công suất giờ công theo ngày (04 mục 6.2; BR-PRP-02; US-WH-02).

labour_cap(d) = Σ_ca present_staff × useful_hours × delivery_share; free(d) = labour_cap − booked.
Ngày không làm việc / ngày lễ → 0. Không có thiết bị (v1.1).

Owner: Dev 1 (luồng A).
"""

from datetime import date
from decimal import Decimal

from app.engine.types import DayCapacity, EngineConfig


def labour_capacity(day: DayCapacity, cfg: EngineConfig) -> Decimal:
    """Giờ công khả dụng của ngày. TODO(#M4-capacity)."""
    raise NotImplementedError


def free_hours(day: DayCapacity, cfg: EngineConfig) -> Decimal:
    """Giờ công còn trống sau khi trừ giờ đã đặt (không âm). TODO(#M4-capacity)."""
    raise NotImplementedError


def is_working_day(d: date, cfg: EngineConfig) -> bool:
    """Ngày làm việc của market (bỏ ngày lễ)."""
    return d.isoweekday() in cfg.working_days and d not in cfg.holidays
