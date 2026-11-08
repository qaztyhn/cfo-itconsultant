"""Pure revenue value and CSV safety regression tests (US-REV-01)."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.services.revenue_service import Period, _csv_safe, _pct


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("=1+2", "'=1+2"),
        ("+SUM(1)", "'+SUM(1)"),
        ("-1+2", "'-1+2"),
        ("@SUM(1)", "'@SUM(1)"),
        ("   =1+2", "'   =1+2"),
        ("\t=1+2", "'\t=1+2"),
        ("\n@SUM(1)", "'\n@SUM(1)"),
        ("Stockholm DC", "Stockholm DC"),
        ("ST-021", "ST-021"),
        ("", ""),
    ],
)
def test_US_REV_01_AC8_csv_formula_safety(label: str, expected: str) -> None:
    assert _csv_safe(label) == expected


def test_US_REV_01_AC7_market_share_rounding_and_empty_total() -> None:
    assert _pct(Decimal("1500.50"), Decimal("1850.50")) == Decimal("81.1")
    assert _pct(Decimal("0"), Decimal("0")) is None
    assert _pct(Decimal("1"), Decimal("3")) == Decimal("33.3")


def test_US_REV_01_AC5_period_inclusive_boundaries() -> None:
    today = date(2026, 11, 20)
    thirty = Period.resolve(None, None, today)
    assert thirty.start == date(2026, 10, 22)
    assert thirty.end == today
    assert len(thirty.days()) == 30
    boundary = Period.resolve(date(2026, 1, 1), date(2027, 1, 1), today)
    assert len(boundary.days()) == 366
    with pytest.raises(DomainError) as caught:
        Period.resolve(date(2026, 1, 1), date(2027, 1, 2), today)
    assert caught.value.http_status == 422
