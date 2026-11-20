"""Operational KPI date, missing-evidence and metric-key tests."""

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.core.errors import DomainError
from app.services.kpi_service import METRICS, Measure, Period, _day


def test_US_KPI_01_AC1_period_is_inclusive_at_366_days() -> None:
    period = Period.resolve(date(2026, 1, 1), date(2027, 1, 1), date(2026, 11, 10))
    assert len(period.days()) == 366
    assert period.days()[0] == date(2026, 1, 1)
    assert period.days()[-1] == date(2027, 1, 1)


def test_US_KPI_01_AC1_invalid_period_fails_422() -> None:
    with pytest.raises(DomainError) as error:
        Period.resolve(date(2026, 12, 1), date(2026, 11, 1), date(2026, 11, 10))
    assert error.value.http_status == 422
    with pytest.raises(DomainError):
        Period.resolve(date(2026, 1, 1), date(2027, 1, 2), date(2026, 11, 10))


def test_US_KPI_01_AC1_missing_denominator_is_not_zero_rate() -> None:
    data = Measure()
    assert data.value() is None
    data.add(None)
    data.add(Decimal(1))
    assert data.value() is None


def test_US_KPI_01_AC1_weighted_measure_uses_total_numerator_and_denominator() -> None:
    first = Measure()
    first.add(Decimal(2), Decimal(4))
    second = Measure()
    second.add(Decimal(6), Decimal(12))
    first.combine(second)
    assert first.value() == 0.5


def test_US_KPI_01_AC1_all_contract_metrics_have_unique_keys() -> None:
    assert METRICS == (
        "planning_time_min",
        "on_time_rate",
        "plan_acceptance_rate",
        "manual_intervention_rate",
        "eta_error_min",
    )
    assert len(METRICS) == len(set(METRICS))


def test_US_KPI_01_AC1_stockholm_dst_repeated_hour_is_same_local_day() -> None:
    stockholm = ZoneInfo("Europe/Stockholm")
    first = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    second = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    assert first.astimezone(stockholm).hour == second.astimezone(stockholm).hour == 2
    assert _day(first, stockholm) == _day(second, stockholm) == date(2026, 10, 25)
