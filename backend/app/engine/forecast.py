"""Dự báo ETA và rủi ro (04 mục 6.3; BR-RSK-01; US-RSK-01/02).

Đơn nhiều xe: tính từng xe, forecast của đơn = xe tới muộn nhất. Đang PREP_PAUSED: cận dưới now.
forecast_eta theo mốc: trước GOODS_READY (cận dưới now nếu quá giờ), sau LOADED (+after_loaded_min),
sau DISPATCHED (depart thực + drive), có GPS (recorded_at + thời gian còn lại). Làm tròn lên 15'.
reserve_total = max(min_reserve_min, promise_end − planned_eta); consumption% → green/yellow/orange;
slack < 0 hai lần liên tiếp (cách ≥ 5') → PREDICTED_LATE; now > promise_end chưa giao → OVERDUE.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class MilestoneState:
    planned_goods_ready: datetime
    planned_start_prep: datetime
    planned_depart: datetime
    drive_min: int
    loading_min: int
    actual_start_prep: datetime | None = None
    goods_ready_at: datetime | None = None
    loaded_at: datetime | None = None
    departed_at: datetime | None = None
    gps_recorded_at: datetime | None = None
    gps_remaining_min: int | None = None


@dataclass(frozen=True)
class RiskAssessment:
    forecast_eta: datetime
    reserve_total_min: int
    slack_min: int
    consumption_pct: Decimal
    consecutive_negative: int
    risk_status: Literal["ON_TRACK", "AT_RISK", "PREDICTED_LATE", "OVERDUE"]
    risk_color: Literal["green", "yellow", "orange", "red"]


def forecast_eta(state: MilestoneState, now: datetime, eta_round_min: int) -> datetime:
    """ETA dự báo theo mốc hiện có. TODO(#M7-forecast)."""
    raise NotImplementedError


def assess_risk(
    planned_eta: datetime,
    forecast: datetime,
    promise_end: datetime,
    now: datetime,
    prev_consecutive_negative: int,
    yellow_pct: int,
    orange_pct: int,
    min_reserve_min: int,
    consecutive_needed: int,
) -> RiskAssessment:
    """Phân loại rủi ro. TODO(#M7-forecast)."""
    raise NotImplementedError
