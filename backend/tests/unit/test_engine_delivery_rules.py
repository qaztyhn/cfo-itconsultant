"""Bước 2d (phần không phụ thuộc chọn bộ nhiều xe) + 2e + 2f — 04 mục 6.2.

US-PLN-03 AC2–AC5 (xe/tài xế), US-PLN-04 AC1–AC5 (ngày, cửa sổ), US-PLN-05 AC1–AC3 (dự trữ).
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.engine.delivery import (
    candidate_days,
    eligible_vehicles,
    handling_minutes,
    pick_driver,
    place_arrival,
    planning_reserve_min,
    receiving_window,
    vehicle_free,
)
from app.engine.types import DateModeT, DriverCtx, OrderCtx, VehicleCtx, WarehouseCtx
from tests.unit.engine_factory import CFG, N1, N3, N4, cfg, line

TZ = ZoneInfo("Europe/Stockholm")
NOW = datetime(2026, 11, 4, 10, 5, tzinfo=TZ)
THU12, FRI13, MON16, WED18 = date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 18)


def at(d: date, h: int, m: int = 0) -> datetime:
    return datetime.combine(d, time(h, m), tzinfo=TZ)


def order(
    mode: DateModeT = "latest",
    date_from: date | None = None,
    date_to: date = WED18,
    window: tuple[time, time] | None = None,
    lines: tuple[object, ...] | None = None,
) -> OrderCtx:
    return OrderCtx(1, 1, 59.0, 18.0, mode, date_from, date_to, window, lines or (line(N3, "40", "40"),), NOW)  # type: ignore[arg-type]


def vehicle(
    code: str = "V1",
    caps: frozenset[str] = frozenset(),
    groups: frozenset[str] = frozenset(),
    licence: str = "C",
) -> VehicleCtx:
    return VehicleCtx(1, code, Decimal(6000), Decimal(40), caps, licence, groups, ())  # type: ignore[arg-type]


def driver(
    eid: int = 1,
    licence: str = "C",
    expires: date = date(2027, 1, 1),
    days: frozenset[date] = frozenset({THU12}),
    booked: str = "0",
    busy: tuple[tuple[datetime, datetime], ...] = (),
    shifts: tuple[tuple[datetime, datetime], ...] | None = None,
) -> DriverCtx:
    # ca thực tế mặc định 06:00–20:00 mỗi ngày có mặt (Q12, 04 mục 6.7)
    windows = tuple((at(d, 6), at(d, 20)) for d in sorted(days)) if shifts is None else shifts
    return DriverCtx(
        eid, licence, expires, days, {THU12: Decimal(booked)}, busy, windows,  # type: ignore[arg-type]
        history_complete=True,
    )  # fmt: skip


def wh(vehicles: tuple[VehicleCtx, ...] = (), drivers: tuple[DriverCtx, ...] = ()) -> WarehouseCtx:
    return WarehouseCtx(1, "WH", time(15), Decimal(1), {}, (), {}, vehicles, drivers, None)


# --- xe ----------------------------------------------------------------------------------------------


def test_US_PLN_03_AC2_vehicle_without_group_not_eligible() -> None:
    o = order(lines=(line(N4, "5"),))
    tipper = vehicle("TIP", caps=frozenset({"dump"}), groups=frozenset({"N4"}))
    no_n4 = vehicle("T12", caps=frozenset({"dump"}), groups=frozenset({"N1", "N3"}))
    any_group = vehicle("ANY", caps=frozenset({"dump"}))  # rỗng = mọi nhóm
    eligible, reason = eligible_vehicles(o, wh((tipper, no_n4, any_group)))
    assert [v.code for v in eligible] == ["ANY", "TIP"] and reason is None  # sắp theo mã (xác định)


def test_vehicle_requirement_capability_needed() -> None:
    o = order(lines=(line(N4, "5"), line(N1, "1")))
    eligible, reason = eligible_vehicles(o, wh((vehicle("T12"),)))
    assert eligible == () and reason == "capability"


def test_vehicle_busy_interval_overlap() -> None:
    v = VehicleCtx(
        1, "V", Decimal(1), Decimal(1), frozenset(), "C", frozenset(), ((at(THU12, 8), at(THU12, 10)),)
    )
    assert not vehicle_free(v, at(THU12, 9), at(THU12, 11))
    assert vehicle_free(v, at(THU12, 10), at(THU12, 12))  # khoảng nửa mở [start, end)


# --- tài xế ------------------------------------------------------------------------------------------


def test_US_PLN_03_AC3_licence_class_too_low_is_not_eligible() -> None:
    d, code = pick_driver(
        wh(drivers=(driver(licence="C"),)), vehicle(licence="CE"), at(THU12, 7), at(THU12, 11), CFG
    )
    assert d is None and code == "NO_DRIVER"
    ok, code = pick_driver(
        wh(drivers=(driver(licence="CE"),)), vehicle(licence="C"), at(THU12, 7), at(THU12, 11), CFG
    )
    assert ok is not None and code is None  # CE ≥ C


def test_US_PLN_03_AC3_licence_expired_before_trip() -> None:
    d, code = pick_driver(
        wh(drivers=(driver(expires=THU12 - timedelta(days=1)),)), vehicle(), at(THU12, 7), at(THU12, 11), CFG
    )
    assert d is None and code == "LICENCE_EXPIRED"


def test_US_PLN_03_AC4_driver_hours_over_nine() -> None:
    d, code = pick_driver(wh(drivers=(driver(booked="6"),)), vehicle(), at(THU12, 7), at(THU12, 11), CFG)
    assert d is None and code == "DRIVER_HOURS_EXCEEDED"
    d, code = pick_driver(wh(drivers=(driver(booked="5"),)), vehicle(), at(THU12, 7), at(THU12, 11), CFG)
    assert d is not None  # 5 + 4 = 9 ≤ 9


def test_US_PLN_03_AC5_driver_busy_for_other_order() -> None:
    busy = driver(busy=((at(THU12, 9), at(THU12, 12)),))
    d, code = pick_driver(wh(drivers=(busy,)), vehicle(), at(THU12, 7), at(THU12, 11), CFG)
    assert d is None and code == "NO_DRIVER"


def test_driver_must_be_present_that_day_and_choice_is_deterministic() -> None:
    absent = driver(eid=1, days=frozenset())
    d, code = pick_driver(
        wh(drivers=(driver(eid=3), absent, driver(eid=2))), vehicle(), at(THU12, 7), at(THU12, 9), CFG
    )
    assert d is not None and d.employee_id == 2


# --- cửa sổ, ngày ------------------------------------------------------------------------------------


def test_US_PLN_04_AC5_default_receiving_hours_when_no_window() -> None:
    assert receiving_window(order(), CFG) == (time(7), time(16))
    assert receiving_window(order(window=(time(7), time(9))), CFG) == (time(7), time(9))


def test_candidate_days_by_mode() -> None:
    assert candidate_days(order("exact", FRI13, FRI13, None), THU12, CFG) == (FRI13,)
    assert candidate_days(order("range", FRI13, MON16), THU12, CFG) == (FRI13, MON16)  # bỏ T7, CN
    assert candidate_days(order("latest", None, MON16), THU12, CFG) == (THU12, FRI13, MON16)


def test_US_PLN_04_AC1_exact_never_earlier_eta_at_window_open() -> None:
    o = order("exact", FRI13, FRI13, (time(7), time(9)))
    res = place_arrival(o, at(THU12, 9), CFG)
    assert res.code == "DATE_OK" and res.target_date == FRI13 and res.eta_at == at(FRI13, 7)


def test_US_PLN_04_AC2_latest_earliest_working_day() -> None:
    res = place_arrival(order("latest", None, WED18), at(THU12, 10, 2), CFG)
    assert (res.code, res.target_date, res.eta_at) == (
        "DATE_OK",
        THU12,
        at(THU12, 10, 15),
    )  # làm tròn lên 15'


def test_US_PLN_04_AC3_range_not_before_date_from() -> None:
    res = place_arrival(order("range", FRI13, date(2026, 11, 15)), at(THU12, 8), CFG)
    assert (res.target_date, res.eta_at) == (FRI13, at(FRI13, 7))


def test_US_PLN_04_AC4_after_window_close_moves_to_next_allowed_day_or_fails() -> None:
    o = order("latest", None, MON16)
    res = place_arrival(o, at(FRI13, 16, 40), CFG)
    assert (res.target_date, res.eta_at) == (MON16, at(MON16, 7))
    exact = place_arrival(order("exact", FRI13, FRI13), at(FRI13, 16, 40), CFG)
    assert (exact.code, exact.target_date) == ("DATE_AFTER_DEADLINE", None)


def test_exact_on_non_working_day() -> None:
    sat = date(2026, 11, 14)
    assert place_arrival(order("exact", sat, sat), at(THU12, 8), CFG).code == "NON_WORKING_DAY"


def test_holiday_skipped_for_latest() -> None:
    res = place_arrival(order("latest", None, MON16), at(FRI13, 17), cfg(holidays=frozenset({MON16})))
    assert res.code == "DATE_AFTER_DEADLINE"


# --- dự trữ ------------------------------------------------------------------------------------------


def test_US_PLN_05_AC1_safe_reserve_about_6_days_8_hours() -> None:
    # hạn cuối 18/11 16:00, ETA khả thi sớm nhất 12/11 08:00
    assert planning_reserve_min(order("latest", None, WED18), at(THU12, 8), CFG) == 6 * 1440 + 8 * 60


def test_US_PLN_05_AC2_tight_and_AC3_negative() -> None:
    o = order("latest", None, WED18)
    assert planning_reserve_min(o, at(date(2026, 11, 17), 10), CFG) == 1440 + 6 * 60
    assert planning_reserve_min(o, at(date(2026, 11, 19), 8), CFG) < 0


@pytest.mark.parametrize(("kg", "minutes"), [("0", 20), ("1000", 26), ("4200", 46)])
def test_loading_minutes_base_plus_per_ton_rounded_up(kg: str, minutes: int) -> None:
    assert handling_minutes(Decimal(kg), CFG.loading_base_min, CFG.loading_min_per_ton) == minutes
