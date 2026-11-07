"""Bước 2b (xếp lịch chuẩn bị) + 2c (giờ cắt lên hàng) — 04 mục 6.2; US-PLN-02; 08 mục 6.2 hàng "lịch"."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.engine.schedule import schedule_preparation
from app.engine.types import DayCapacity, ShiftCapacity, WarehouseCtx
from tests.unit.engine_factory import CFG, WED, cfg

TZ = ZoneInfo("Europe/Stockholm")
MORNING = datetime(2026, 11, 4, 5, 0, tzinfo=TZ)  # trước ca 1


def _shift(start: int, end: int, staff: int, useful: str = "7") -> ShiftCapacity:
    return ShiftCapacity(f"{start:02d}-{end:02d}", time(start), time(end), staff, Decimal(useful))


def _wh(days: dict[date, DayCapacity], cutoff: time = time(14, 0)) -> WarehouseCtx:
    return WarehouseCtx(1, "WH", cutoff, Decimal(1), {}, (), days, (), (), None)


def _days(
    start: date, n: int, booked: dict[date, str] | None = None, staff: int = 8
) -> dict[date, DayCapacity]:
    booked = booked or {}
    return {
        start
        + timedelta(days=i): DayCapacity(
            start + timedelta(days=i),
            (_shift(6, 14, staff),),
            Decimal(booked.get(start + timedelta(days=i), "0")),
        )
        for i in range(n)
    }


def test_fits_in_one_day_goods_ready_within_shift_and_before_cutoff() -> None:
    # 8 người × 7 h × 0,9 = 50,4 h trên ca 8 giờ → 6,3 giờ công/giờ đồng hồ; 12,6 h → xong 08:00
    res = schedule_preparation(Decimal("12.6"), WED, MORNING, _wh(_days(WED, 3)), CFG)
    assert (res.check.code, res.check.passed) == ("PREP_OK", True)
    assert res.prep_by_day == {WED: Decimal("12.6")}
    assert res.goods_ready_at == datetime(2026, 11, 4, 8, 0, tzinfo=TZ)
    assert res.loading_start_at == res.goods_ready_at and not res.after_cutoff
    assert res.capacity_fill == Decimal("0.25")


def test_US_PLN_02_AC1_spills_to_next_working_day() -> None:
    # ngày D còn 4 giờ (50,4 − 46,4); việc 10,15 h → 4 h ngày D, 6,15 h ngày làm việc kế (Thứ Năm)
    days = _days(WED, 5, booked={WED: "46.4"})
    res = schedule_preparation(Decimal("10.15"), WED, MORNING, _wh(days), CFG)
    thu = WED + timedelta(days=1)
    assert res.prep_by_day == {WED: Decimal("4.0"), thu: Decimal("6.15")}
    assert res.goods_ready_at is not None and res.goods_ready_at.date() == thu
    # fill = (46,4 + 0 + 10,15) / (50,4 + 50,4)
    assert res.capacity_fill == (Decimal("46.4") + Decimal("10.15")) / Decimal("100.8")


def test_skips_weekend_and_holiday() -> None:
    fri = WED + timedelta(days=2)
    days = _days(fri, 4, booked={fri: "50.4"})  # Thứ Sáu kín, T7/CN nghỉ
    holiday_cfg = cfg(holidays=frozenset({fri + timedelta(days=3)}))  # Thứ Hai lễ
    res = schedule_preparation(
        Decimal("5"), fri, MORNING, _wh(days | _days(fri + timedelta(days=4), 1)), holiday_cfg
    )
    assert list(res.prep_by_day) == [fri + timedelta(days=4)]  # Thứ Ba


def test_US_PLN_02_AC2_goods_ready_1420_after_cutoff_1400_loads_next_working_day() -> None:
    # hai ca 06–14 và 14–22 (8 người, 6,3 giờ công/giờ); đặt trước 50,4 h = hết ca 1 → việc bắt đầu 14:00;
    # 2,1 h giờ công = 20 phút → goods_ready 14:20 > cutoff 14:00 → lên hàng 06:00 Thứ Năm
    two_shifts = {
        WED
        + timedelta(days=i): DayCapacity(
            WED + timedelta(days=i), (_shift(6, 14, 8), _shift(14, 22, 8)), Decimal("50.4" if i == 0 else "0")
        )
        for i in range(3)
    }
    res = schedule_preparation(Decimal("2.1"), WED, MORNING, _wh(two_shifts, cutoff=time(14, 0)), CFG)
    assert res.goods_ready_at == datetime(2026, 11, 4, 14, 20, tzinfo=TZ)
    assert res.after_cutoff and (res.check.code, res.check.passed) == ("PREP_AFTER_CUTOFF", True)
    assert res.loading_start_at == datetime(2026, 11, 5, 6, 0, tzinfo=TZ)


def test_goods_ready_after_cutoff_moves_loading_to_next_working_day() -> None:
    # đặt trước 37,8 h (tới 12:00); việc 12,6 h (2 giờ đồng hồ) → 14:00 = cutoff 13:00 bị vượt
    days = _days(WED, 3, booked={WED: "37.8"})
    res = schedule_preparation(Decimal("12.6"), WED, MORNING, _wh(days, cutoff=time(13, 0)), CFG)
    assert res.goods_ready_at == datetime(2026, 11, 4, 14, 0, tzinfo=TZ)
    assert res.after_cutoff and (res.check.code, res.check.passed) == ("PREP_AFTER_CUTOFF", True)
    assert res.loading_start_at == datetime(2026, 11, 5, 6, 0, tzinfo=TZ)


def test_today_only_counts_remaining_shift_time_after_now() -> None:
    now = datetime(2026, 11, 4, 12, 0, tzinfo=TZ)  # còn 2 giờ ca = 12,6 h
    res = schedule_preparation(Decimal("6.3"), WED, now, _wh(_days(WED, 3)), CFG)
    assert res.goods_ready_at == datetime(2026, 11, 4, 13, 0, tzinfo=TZ)


def test_shift_already_over_today_starts_next_working_day() -> None:
    now = datetime(2026, 11, 4, 15, 0, tzinfo=TZ)
    res = schedule_preparation(Decimal("6.3"), WED, now, _wh(_days(WED, 3)), CFG)
    assert list(res.prep_by_day) == [WED + timedelta(days=1)]


def test_no_capacity_within_horizon_fails_prep_no_capacity() -> None:
    days = _days(WED, 20, booked={WED + timedelta(days=i): "50.4" for i in range(20)})
    res = schedule_preparation(Decimal("1"), WED, MORNING, _wh(days), CFG)
    assert (res.check.code, res.check.passed) == ("PREP_NO_CAPACITY", False)
    assert res.goods_ready_at is None and "message" in res.check.detail


def test_horizon_comes_from_config() -> None:
    days = _days(WED, 20, booked={WED + timedelta(days=i): "50.4" for i in range(7)})
    assert schedule_preparation(Decimal("1"), WED, MORNING, _wh(days), cfg(search_days_max=5)).check.code == (
        "PREP_NO_CAPACITY"
    )
    assert schedule_preparation(Decimal("1"), WED, MORNING, _wh(days), CFG).check.code == "PREP_OK"
