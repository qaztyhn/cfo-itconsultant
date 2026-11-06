"""Bước 1 (khối lượng việc) và bước 2b phần 1 (công suất) — 04 mục 6.2; US-PLN-01, US-WH-02; 08 mục 6.2."""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from app.engine.capacity import free_hours, is_working_day, labour_capacity
from app.engine.types import DayCapacity, ShiftCapacity
from app.engine.workload import compute_workload, flag_multiplier, warehouse_labour_hours
from tests.unit.engine_factory import CFG, FAR_OR_OUTDOOR, FRAGILE, HAZARDOUS, N1, N2, N3, N6, WED, cfg, line

# --- workload ----------------------------------------------------------------------------------------


def test_US_PLN_01_AC1_example_order_is_10_15_hours() -> None:
    # 20 pallet xi măng = 800 bao (40 bao/pallet); 15 pallet gạch = 900 tấm (60 tấm/pallet); 3 dòng keo N1
    lines = (line(N3, "800", "40"), line(N2, "900", "60"), line(N1, "4"), line(N1, "1"), line(N1, "12"))
    wl = compute_workload(lines, CFG)
    assert wl.line_hours == (
        Decimal("3.25"),
        Decimal("6.25"),
        Decimal("0.05"),
        Decimal("0.05"),
        Decimal("0.05"),
    )
    assert wl.labour_hours == Decimal("10.15")


def test_US_PLN_01_AC2_flag_product_and_cap() -> None:
    assert flag_multiplier(line(N3, "1", flags=(FRAGILE, HAZARDOUS)), CFG.flag_multiplier_cap) == Decimal(
        "1.625"
    )
    capped = line(N3, "1", flags=(FRAGILE, HAZARDOUS, FAR_OR_OUTDOOR))  # 1,95 < 2,0
    assert flag_multiplier(capped, CFG.flag_multiplier_cap) == Decimal("1.95")
    over = line(N3, "1", flags=(FRAGILE, HAZARDOUS, FAR_OR_OUTDOOR, FAR_OR_OUTDOOR))  # 2,34 → 2,0
    assert flag_multiplier(over, CFG.flag_multiplier_cap) == Decimal("2.0")
    assert flag_multiplier(line(N3, "1"), CFG.flag_multiplier_cap) == Decimal(1)


def test_flag_multiplier_applies_to_whole_line_including_fixed_hours() -> None:
    wl = compute_workload((line(N3, "800", "40", flags=(FRAGILE, HAZARDOUS)),), CFG)
    assert wl.line_hours == (Decimal("3.25") * Decimal("1.625"),)
    assert wl.labour_hours == Decimal("3.25") * Decimal("1.625") + Decimal("0.5")


def test_US_PLN_01_AC3_same_hours_in_every_warehouse_default_efficiency() -> None:
    wl = compute_workload((line(N3, "20"),), CFG)
    assert warehouse_labour_hours(wl, Decimal("1.00")) == wl.labour_hours


def test_US_PLN_01_AC4_twenty_bags_line_hours() -> None:
    wl = compute_workload((line(N3, "20", "40"),), CFG)
    assert wl.line_hours == (Decimal("0.325"),)


def test_US_PLN_01_AC5_indivisible_quantity_rounds_up() -> None:
    wl = compute_workload((line(N6, "2.4"),), CFG)
    assert wl.line_hours == (Decimal("0.25") + 3 * Decimal("0.60"),)


def test_line_unit_counts_one_regardless_of_quantity() -> None:
    assert compute_workload((line(N1, "500"),), CFG).line_hours == (Decimal("0.05"),)


def test_final_inspection_from_config_not_hard_coded() -> None:
    wl = compute_workload((line(N1, "1"),), cfg(final_inspection_hours=Decimal("0.75")))
    assert wl.labour_hours == Decimal("0.80")


# --- capacity ----------------------------------------------------------------------------------------


def _day(d: date, *shifts: tuple[int, str], booked: str = "0") -> DayCapacity:
    return DayCapacity(
        d,
        tuple(ShiftCapacity(f"S{i}", time(6), time(14), n, Decimal(h)) for i, (n, h) in enumerate(shifts)),
        Decimal(booked),
    )


def test_US_WH_02_AC1_labour_cap_people_times_useful_hours_times_share() -> None:
    assert labour_capacity(_day(WED, (8, "7")), CFG) == Decimal("50.4")


def test_US_WH_02_AC2_free_hours_after_bookings() -> None:
    assert free_hours(_day(WED, (8, "7"), booked="30"), CFG) == Decimal("20.4")


def test_free_hours_never_negative_when_overbooked() -> None:
    # held vượt công suất được phép lúc lập kế hoạch (09 bất biến 11) → free = 0, không âm
    assert free_hours(_day(WED, (8, "7"), booked="60"), CFG) == Decimal(0)


def test_US_WH_02_AC3_holiday_has_zero_capacity() -> None:
    holiday_cfg = cfg(holidays=frozenset({WED}))
    assert not is_working_day(WED, holiday_cfg)
    assert labour_capacity(_day(WED, (8, "7")), holiday_cfg) == Decimal(0)
    assert free_hours(_day(WED, (8, "7")), holiday_cfg) == Decimal(0)


@pytest.mark.parametrize("offset", [3, 4])  # Thứ Bảy, Chủ Nhật
def test_weekend_has_zero_capacity(offset: int) -> None:
    assert labour_capacity(_day(WED + timedelta(days=offset), (8, "7")), CFG) == Decimal(0)


def test_capacity_sums_shifts_and_uses_configured_share() -> None:
    day = _day(WED, (8, "7"), (5, "7"))
    assert labour_capacity(day, CFG) == Decimal("81.9")
    assert labour_capacity(day, cfg(delivery_share=Decimal("0.80"))) == Decimal("72.8")
