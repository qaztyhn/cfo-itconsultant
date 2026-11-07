"""Bước 2b (phần 2) + 2c — xếp lịch chuẩn bị và lên hàng (04 mục 6.2; BR-PRP-04; US-PLN-02).

Tiến tới sớm nhất từ start_day ≥ stock_ready_date; mỗi ngày a_L = min(L còn lại, free(d));
goods_ready_at ở ngày cuối theo ca; quá cutoff → lên hàng đầu ca ngày làm việc kế
(PREP_AFTER_CUTOFF, complexity +1); không đủ trong chân trời → PREP_NO_CAPACITY.
capacity_fill = (booked + giờ đơn) / Σ labour_cap trên các ngày chuẩn bị, kẹp [0,1].

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from decimal import ROUND_CEILING, Decimal

from app.engine.capacity import is_working_day, labour_capacity
from app.engine.types import CheckResult, DayCapacity, EngineConfig, ShiftCapacity, WarehouseCtx


@dataclass(frozen=True)
class PrepSchedule:
    check: CheckResult
    prep_by_day: dict[date, Decimal]
    goods_ready_at: datetime | None
    loading_start_at: datetime | None
    capacity_fill: Decimal
    after_cutoff: bool


# --- dòng thời gian giờ công trong một ngày ------------------------------------------------------------
# Mỗi ca cung cấp present_staff × useful_hours × delivery_share giờ công, trải ĐỀU trên độ dài ca (ca không
# qua nửa đêm). Trong ngày, giờ đã đặt của đơn khác được tiêu thụ trước, rồi tới đơn này (04 mục 6.2 bước 4).


def _hours(a: time, b: time) -> Decimal:
    return Decimal((b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)) / 60


def _shift_capacity(shift: ShiftCapacity, cfg: EngineConfig) -> Decimal:
    return shift.present_staff * shift.useful_hours_per_staff * cfg.delivery_share


def _rate(shift: ShiftCapacity, cfg: EngineConfig) -> Decimal:
    """Giờ công tiêu thụ mỗi giờ đồng hồ trong ca."""
    return _shift_capacity(shift, cfg) / _hours(shift.start, shift.end)


def _position_at(day: DayCapacity, t: time, cfg: EngineConfig) -> Decimal:
    """Lượng giờ công của ngày đã trôi qua tới giờ `t`."""
    pos = Decimal(0)
    for shift in sorted(day.shifts, key=lambda s: s.start):
        if t >= shift.end:
            pos += _shift_capacity(shift, cfg)
        elif t > shift.start:
            pos += _rate(shift, cfg) * _hours(shift.start, t)
    return pos


def _datetime_at(day: DayCapacity, pos: Decimal, tz: tzinfo | None, cfg: EngineConfig) -> datetime:
    """Thời điểm trong ngày khi đạt `pos` giờ công (làm tròn lên giây)."""
    cumulative = Decimal(0)
    for shift in sorted(day.shifts, key=lambda s: s.start):
        cap = _shift_capacity(shift, cfg)
        if cap > 0 and pos <= cumulative + cap:
            seconds = ((pos - cumulative) / _rate(shift, cfg) * 3600).to_integral_value(
                rounding=ROUND_CEILING
            )
            start = datetime.combine(day.day, shift.start, tzinfo=tz)
            return start + timedelta(seconds=int(seconds))
        cumulative += cap
    last = max(day.shifts, key=lambda s: s.end)
    return datetime.combine(day.day, last.end, tzinfo=tz)


def _start_position(day: DayCapacity, now: datetime, cfg: EngineConfig) -> Decimal:
    """Vị trí bắt đầu được phép: sau giờ đã đặt và (với hôm nay) sau `now`."""
    if day.day == now.date():
        return max(day.booked_hours, _position_at(day, now.time(), cfg))
    return day.booked_hours


def _first_shift_start(d: date, wh: WarehouseCtx, cfg: EngineConfig, tz: tzinfo | None) -> datetime | None:
    """Đầu ca đầu tiên của ngày làm việc kế tiếp sau `d` (trong chân trời tìm kiếm)."""
    for offset in range(1, cfg.search_days_max + 1):
        nxt = d + timedelta(days=offset)
        day = wh.capacity.get(nxt)
        if day is not None and day.shifts and is_working_day(nxt, cfg):
            return datetime.combine(nxt, min(s.start for s in day.shifts), tzinfo=tz)
    return None


def _fail(message: str, reason: str) -> PrepSchedule:
    check = CheckResult("preparation", False, "PREP_NO_CAPACITY", {"message": message, "reason": reason})
    return PrepSchedule(check, {}, None, None, Decimal(0), False)


def schedule_preparation(
    labour_hours: Decimal, start_day: date, now: datetime, wh: WarehouseCtx, cfg: EngineConfig
) -> PrepSchedule:
    """Xếp giờ công vào các ngày (sớm nhất có thể) và tính giờ lên hàng theo giờ cắt.

    `start_day` = ngày hàng sẵn sàng (ATP); `now` mang múi giờ market. Quét `search_days_max` ngày lịch từ
    `start_day`, bỏ ngày nghỉ/lễ, ngày không có ca và phần ngày hôm nay đã qua.
    """
    tz = now.tzinfo
    remaining = labour_hours
    prep_by_day: dict[date, Decimal] = {}
    last_day: DayCapacity | None = None
    last_end_pos = Decimal(0)
    for offset in range(cfg.search_days_max):
        d = start_day + timedelta(days=offset)
        day = wh.capacity.get(d)
        if d < now.date() or day is None or not day.shifts or not is_working_day(d, cfg):
            continue
        start_pos = _start_position(day, now, cfg)
        free = max(Decimal(0), labour_capacity(day, cfg) - start_pos)
        allocated = min(remaining, free)
        if allocated <= 0:
            continue
        prep_by_day[d] = allocated
        remaining -= allocated
        last_day, last_end_pos = day, start_pos + allocated
        if remaining <= 0:
            break
    if remaining > 0 or last_day is None:
        return _fail("Not enough labour capacity within the search horizon.", "capacity")

    goods_ready_at = _datetime_at(last_day, last_end_pos, tz, cfg)
    booked = sum((wh.capacity[d].booked_hours for d in prep_by_day), Decimal(0))
    total_cap = sum((labour_capacity(wh.capacity[d], cfg) for d in prep_by_day), Decimal(0))
    fill = min(Decimal(1), max(Decimal(0), (booked + labour_hours) / total_cap))

    after_cutoff = goods_ready_at.time() > wh.cutoff
    if not after_cutoff:
        check = CheckResult(
            "preparation", True, "PREP_OK", {"message": "Goods ready before loading cut-off."}
        )
        return PrepSchedule(check, prep_by_day, goods_ready_at, goods_ready_at, fill, False)
    loading = _first_shift_start(last_day.day, wh, cfg, tz)
    if loading is None:
        return _fail("No shift after the loading cut-off within the search horizon.", "no_shift_after_cutoff")
    check = CheckResult(
        "preparation",
        True,
        "PREP_AFTER_CUTOFF",
        {
            "message": f"Goods ready after cut-off {wh.cutoff:%H:%M}; "
            f"loading moved to {loading:%Y-%m-%d %H:%M}."
        },
    )
    return PrepSchedule(check, prep_by_day, goods_ready_at, loading, fill, True)
