"""Test engine đã hiện thực ở khung: đơn vị nhỏ nhất (US-PLN-01 AC4/AC5) và giờ nhân công thực tế
(US-WH-04 AC6/AC7)."""

from datetime import datetime, timedelta
from decimal import Decimal

from app.engine.actuals import LabourSegment, actual_labour_hours, allocate_to_groups
from app.engine.types import HandlingGroupCtx, LineCtx, ProductCtx
from app.engine.workload import prep_quantity

N3 = HandlingGroupCtx("N3", "pallet", Decimal("0.25"), Decimal("0.15"))
N6 = HandlingGroupCtx("N6", "package", Decimal("0.25"), Decimal("0.60"))
N1 = HandlingGroupCtx("N1", "line", Decimal(0), Decimal("0.05"))


def _line(group: HandlingGroupCtx, qty: str, per_unit: str | None) -> LineCtx:
    product = ProductCtx(1, group, Decimal(per_unit) if per_unit else None, (), Decimal(25), Decimal("0.02"))
    return LineCtx(product, Decimal(qty))


def test_US_PLN_01_AC4_twenty_bags_is_half_pallet() -> None:
    assert prep_quantity(_line(N3, "20", "40")) == Decimal("0.5")


def test_US_PLN_01_AC5_indivisible_rounds_up() -> None:
    assert prep_quantity(_line(N6, "2.4", None)) == Decimal(3)


def test_line_unit_is_always_one() -> None:
    assert prep_quantity(_line(N1, "500", None)) == Decimal(1)


def test_US_WH_04_AC6_actual_labour_hours_over_paused_segments() -> None:
    t0 = datetime.fromisoformat("2026-11-12T07:00:00+01:00")
    segs = [
        LabourSegment(t0, t0 + timedelta(hours=2), 3),
        LabourSegment(t0 + timedelta(hours=6), t0 + timedelta(hours=7, minutes=30), 2),
    ]
    assert actual_labour_hours(segs) == Decimal("9")


def test_US_WH_04_AC7_allocate_by_planned_share_then_per_base_unit() -> None:
    res = {
        g.group_code: g
        for g in allocate_to_groups(
            Decimal("9"), {"N3": Decimal("6"), "N1": Decimal("3")}, {"N3": Decimal("800"), "N1": Decimal("3")}
        )
    }
    assert res["N3"].hours == Decimal("6")
    assert res["N3"].hours_per_unit == Decimal("0.0075")
