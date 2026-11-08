"""M7 forecast evidence guards, DST correctness and negative-slack contracts."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.engine.forecast import (
    MilestoneState,
    assess_risk,
    ceil_to_step,
    forecast_eta,
    order_forecast,
)


def test_US_RSK_01_AC1_nonexistent_vehicle_eta_is_not_a_verified_order_forecast() -> None:
    with pytest.raises(ValueError, match="No verified vehicle"):
        order_forecast([])


def test_US_RSK_01_AC4_missing_planned_prep_start_is_not_inferred() -> None:
    start = datetime(2026, 11, 10, 8, tzinfo=UTC)
    state = MilestoneState(
        planned_goods_ready=start + timedelta(hours=1),
        planned_start_prep=None,
        planned_depart=start + timedelta(hours=2),
        drive_min=60,
        loading_min=20,
        actual_start_prep=start,
    )
    with pytest.raises(ValueError, match="Approved planned prep start"):
        forecast_eta(state, start, 15, 10)


def test_US_RSK_01_AC4_unstarted_prep_needs_no_invented_start_time() -> None:
    start = datetime(2026, 11, 10, 8, tzinfo=UTC)
    state = MilestoneState(
        planned_goods_ready=start + timedelta(hours=1),
        planned_start_prep=None,
        planned_depart=start + timedelta(hours=2),
        drive_min=60,
        loading_min=20,
    )
    assert forecast_eta(state, start, 15, 10) == start + timedelta(hours=3)


def test_US_RSK_01_AC4_dst_fall_back_rounding_uses_real_utc_instant() -> None:
    stockholm = ZoneInfo("Europe/Stockholm")
    # Twice-occurring 02:07 at the 2026-10-25 autumn DST switch.
    first = datetime(2026, 10, 25, 2, 7, tzinfo=stockholm, fold=0)
    second = datetime(2026, 10, 25, 2, 7, tzinfo=stockholm, fold=1)
    assert ceil_to_step(first, 15) == datetime(2026, 10, 25, 0, 15, tzinfo=UTC)
    assert ceil_to_step(second, 15) == datetime(2026, 10, 25, 1, 15, tzinfo=UTC)
    assert ceil_to_step(first, 15) != ceil_to_step(second, 15)


def test_US_RSK_02_AC4_invalid_or_naive_time_evidence_fails_closed() -> None:
    now = datetime(2026, 11, 10, 8, tzinfo=UTC)
    with pytest.raises(ValueError, match="offset-aware"):
        assess_risk(now.replace(tzinfo=None), now, now, now, 0, 33, 66, 30, 2)
    with pytest.raises(ValueError, match="risk thresholds"):
        assess_risk(now, now, now, now, 0, 80, 66, 30, 2)
    with pytest.raises(ValueError, match="positive"):
        ceil_to_step(now, 0)
