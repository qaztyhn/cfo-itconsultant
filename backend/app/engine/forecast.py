"""Dự báo ETA và rủi ro (04 mục 6.3; BR-RSK-01; US-RSK-01/02).

Đơn nhiều xe: tính từng xe, forecast của đơn = xe tới muộn nhất. Đang PREP_PAUSED: cận dưới now.
forecast_eta theo mốc: trước GOODS_READY (cận dưới now nếu quá giờ), sau LOADED (+after_loaded_min),
sau DISPATCHED (depart thực + drive), có GPS (recorded_at + thời gian còn lại). Làm tròn lên 15'.
reserve_total = max(min_reserve_min, promise_end − planned_eta); consumption% → green/yellow/orange;
slack < 0 hai lần liên tiếp (cách ≥ 5') → PREDICTED_LATE; now > promise_end chưa giao → OVERDUE.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
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
    gps_recorded_at: datetime | None = None  # chỉ truyền khi điểm GPS chưa quá gps.lost_min (service lọc)
    gps_remaining_min: int | None = None
    paused: bool = False  # đang PREP_PAUSED
    cutoff_at: datetime | None = None  # giờ cắt lên hàng của ngày lên hàng kế hoạch
    next_shift_start: datetime | None = None  # đầu ca ngày làm việc kế (nếu quá giờ cắt)


@dataclass(frozen=True)
class RiskAssessment:
    forecast_eta: datetime
    reserve_total_min: int
    slack_min: int
    consumption_pct: Decimal
    consecutive_negative: int
    risk_status: Literal["ON_TRACK", "AT_RISK", "PREDICTED_LATE", "OVERDUE"]
    risk_color: Literal["green", "yellow", "orange", "red"]


def ceil_to_step(ts: datetime, step_min: int) -> datetime:
    """Làm tròn LÊN tới bội số `step_min` phút (giây lẻ cũng làm tròn lên)."""
    if step_min <= 0:
        raise ValueError("step_min must be positive")
    base = ts.replace(second=0, microsecond=0)
    minutes = base.hour * 60 + base.minute + (1 if (ts.second or ts.microsecond) else 0)
    rounded = -(-minutes // step_min) * step_min
    return base.replace(hour=0, minute=0) + timedelta(minutes=rounded)


def _pre_loaded_depart(state: MilestoneState, now: datetime) -> datetime:
    """Trước LOADED: goods_ready_f → loading_start_f (theo cutoff) → depart_f."""
    if state.goods_ready_at is not None:
        goods_ready = state.goods_ready_at
    else:
        delay = timedelta(0)
        if state.actual_start_prep is not None:
            delay = max(timedelta(0), state.actual_start_prep - state.planned_start_prep)
        goods_ready = state.planned_goods_ready + delay
        if state.paused or now > goods_ready:
            goods_ready = max(goods_ready, now)  # MVP không theo dõi tiến độ bên trong: cận dưới
    loading_start = goods_ready
    if state.cutoff_at is not None and state.next_shift_start is not None and goods_ready > state.cutoff_at:
        loading_start = state.next_shift_start
    return max(state.planned_depart, loading_start + timedelta(minutes=state.loading_min))


def forecast_eta(state: MilestoneState, now: datetime, eta_round_min: int, after_loaded_min: int) -> datetime:
    """ETA dự báo theo mốc hiện có (một xe), làm tròn lên `eta_round_min` (04 mục 6.3)."""
    if state.gps_recorded_at is not None and state.gps_remaining_min is not None:
        eta = state.gps_recorded_at + timedelta(minutes=state.gps_remaining_min)
    elif state.departed_at is not None:
        eta = state.departed_at + timedelta(minutes=state.drive_min)
    else:
        if state.loaded_at is not None:
            depart = max(state.planned_depart, state.loaded_at + timedelta(minutes=after_loaded_min))
        else:
            depart = _pre_loaded_depart(state, now)
        eta = depart + timedelta(minutes=state.drive_min)
    return ceil_to_step(eta, eta_round_min)


def order_forecast(vehicle_etas: list[datetime]) -> datetime:
    """Đơn nhiều xe: forecast của đơn = xe tới muộn nhất."""
    return max(vehicle_etas)


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
    """Phân loại rủi ro (04 mục 6.3).

    `prev_consecutive_negative` là bộ đếm của lần tính trước. Service chỉ tăng bộ đếm khi lần trước cách lần
    này ≥ `risk.consecutive_min_gap_min` (US-RSK-02 AC4); nếu quá gần, service không gọi lại để đếm.
    OVERDUE chỉ áp dụng cho đơn chưa giao (service không gọi cho đơn đã DELIVERED).
    """
    reserve_total = max(min_reserve_min, _minutes(promise_end - planned_eta))
    slack = _minutes(promise_end - forecast)
    consumption = max(
        Decimal(0), Decimal(_seconds(forecast - planned_eta)) / Decimal(reserve_total * 60) * 100
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    consecutive = prev_consecutive_negative + 1 if slack < 0 else 0
    status: Literal["ON_TRACK", "AT_RISK", "PREDICTED_LATE", "OVERDUE"]
    color: Literal["green", "yellow", "orange", "red"]
    if now > promise_end:
        status, color = "OVERDUE", "red"
    elif slack < 0 and consecutive >= consecutive_needed:
        status, color = "PREDICTED_LATE", "red"
    elif slack < 0 or consumption > orange_pct:
        status, color = "AT_RISK", "orange"
    elif consumption >= yellow_pct:
        status, color = "AT_RISK", "yellow"
    else:
        status, color = "ON_TRACK", "green"
    return RiskAssessment(forecast, reserve_total, slack, consumption, consecutive, status, color)


def _seconds(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _minutes(delta: timedelta) -> int:
    """Phút nguyên (làm tròn xuống về phía âm vô cùng để slack âm luôn âm)."""
    return _seconds(delta) // 60
