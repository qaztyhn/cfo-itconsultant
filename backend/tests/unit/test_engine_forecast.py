"""Dự báo ETA và phân loại rủi ro — 04 mục 6.3; US-RSK-01 AC4, US-RSK-02 AC1–AC7; 08 mục 6.2."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.forecast import MilestoneState, RiskAssessment, assess_risk, forecast_eta, order_forecast

D = datetime(2026, 11, 12, tzinfo=UTC)


def at(h: int, m: int = 0) -> datetime:
    return D + timedelta(hours=h, minutes=m)


BASE = MilestoneState(
    planned_goods_ready=at(9), planned_start_prep=at(6), planned_depart=at(10), drive_min=45, loading_min=26
)


def fc(state: MilestoneState, now: datetime) -> datetime:
    return forecast_eta(state, now, eta_round_min=15, after_loaded_min=10)


def test_on_plan_before_prep_equals_planned_eta() -> None:
    assert fc(BASE, at(5)) == at(10, 45)


def test_US_RSK_01_AC4_prep_delay_absorbed_by_planned_departure() -> None:
    # bắt đầu muộn 20' → goods_ready 09:20, lên hàng 26' → 09:46 < depart kế hoạch 10:00 → ETA không đổi
    state = BASE.__class__(**{**BASE.__dict__, "actual_start_prep": at(6, 20)})
    assert fc(state, at(7)) == at(10, 45)


def test_prep_delay_beyond_slack_pushes_eta_and_rounds_up_15() -> None:
    state = BASE.__class__(**{**BASE.__dict__, "actual_start_prep": at(7, 0)})  # +60' → ready 10:00
    # depart = 10:00 + 26' = 10:26; + 45' = 11:11 → làm tròn lên 11:15
    assert fc(state, at(8)) == at(11, 15)


def test_goods_ready_overdue_uses_now_as_lower_bound() -> None:
    # 09:31 chưa có GOODS_READY (kế hoạch 09:00) → goods_ready_f ≥ now
    assert fc(BASE, at(9, 31)) == at(10, 45)
    late = fc(BASE, at(10, 0))  # now 10:00 → depart 10:26 → 11:11 → 11:15
    assert late == at(11, 15)


def test_paused_prep_uses_now_as_lower_bound_even_before_planned_ready() -> None:
    state = BASE.__class__(**{**BASE.__dict__, "actual_start_prep": at(6), "paused": True})
    assert fc(state, at(9, 50)) == at(11, 15)  # 09:50 + 26' = 10:16 + 45' = 11:01 → 11:15


def test_after_cutoff_moves_forecast_loading_to_next_shift() -> None:
    state = BASE.__class__(
        **{**BASE.__dict__, "actual_start_prep": at(8), "cutoff_at": at(10, 30), "next_shift_start": at(30)}
    )  # sẵn sàng 11:00 > cutoff 10:30 → lên hàng 06:00 hôm sau → 06:26 + 45' = 07:11 → 07:15
    assert fc(state, at(9)) == at(31, 15)


def test_after_loaded_uses_loaded_plus_after_loaded_min() -> None:
    state = BASE.__class__(**{**BASE.__dict__, "goods_ready_at": at(9), "loaded_at": at(10, 30)})
    assert fc(state, at(10, 31)) == at(11, 30)  # 10:40 + 45' = 11:25 → 11:30


def test_after_dispatch_without_gps_uses_actual_departure() -> None:
    state = BASE.__class__(**{**BASE.__dict__, "departed_at": at(10, 5)})
    assert fc(state, at(10, 10)) == at(11, 0)  # 10:50 → 11:00


def test_with_gps_uses_recorded_at_plus_remaining() -> None:
    state = BASE.__class__(
        **{**BASE.__dict__, "departed_at": at(10), "gps_recorded_at": at(10, 30), "gps_remaining_min": 50}
    )
    assert fc(state, at(10, 31)) == at(11, 30)  # 11:20 → 11:30


def test_multi_vehicle_order_forecast_is_latest_vehicle() -> None:
    assert order_forecast([at(11), at(11, 30), at(10, 45)]) == at(11, 30)


# --- rủi ro ------------------------------------------------------------------------------------------


PLANNED, PROMISE = at(8), at(10)


def risk(
    forecast: datetime,
    *,
    now: datetime | None = None,
    prev: int = 0,
    planned: datetime = PLANNED,
    promise: datetime = PROMISE,
) -> RiskAssessment:
    return assess_risk(
        planned,
        forecast,
        promise,
        now or PLANNED,
        prev,
        yellow_pct=33,
        orange_pct=66,
        min_reserve_min=30,
        consecutive_needed=2,
    )


def test_US_RSK_02_AC1_29_percent_on_track_green() -> None:
    r = risk(at(8, 35))
    assert (r.risk_status, r.risk_color, r.reserve_total_min, r.slack_min) == ("ON_TRACK", "green", 120, 85)
    assert r.consumption_pct == Decimal("29.17")


def test_US_RSK_02_AC2_50_percent_yellow() -> None:
    r = risk(at(9))
    assert (r.risk_status, r.risk_color, r.consumption_pct) == ("AT_RISK", "yellow", Decimal("50.00"))


def test_US_RSK_02_AC3_75_percent_orange() -> None:
    r = risk(at(9, 30))
    assert (r.risk_status, r.risk_color, r.consumption_pct) == ("AT_RISK", "orange", Decimal("75.00"))


def test_US_RSK_02_AC5_first_negative_slack_is_orange() -> None:
    r = risk(at(10, 20))
    assert (r.risk_status, r.risk_color, r.slack_min, r.consecutive_negative) == ("AT_RISK", "orange", -20, 1)


def test_US_RSK_02_AC4_second_consecutive_negative_slack_predicted_late() -> None:
    r = risk(at(10, 20), prev=1)
    assert (r.risk_status, r.risk_color, r.consecutive_negative) == ("PREDICTED_LATE", "red", 2)


def test_positive_slack_resets_consecutive_counter() -> None:
    assert risk(at(8, 35), prev=1).consecutive_negative == 0


def test_US_RSK_02_AC6_overdue_when_now_after_promise_end() -> None:
    r = risk(at(10, 20), now=at(10, 1))
    assert (r.risk_status, r.risk_color) == ("OVERDUE", "red")


def test_US_RSK_02_AC7_minimum_reserve_30_minutes() -> None:
    r = risk(at(9, 55), planned=at(9, 50), promise=at(10))  # reserve thật 10' → dùng 30'
    assert r.reserve_total_min == 30 and r.consumption_pct == Decimal("16.67") and r.risk_color == "green"


@pytest.mark.parametrize(
    ("minutes", "color"), [(39, "green"), (40, "yellow"), (79, "yellow"), (80, "orange"), (81, "orange")]
)
def test_threshold_boundaries(minutes: int, color: str) -> None:
    # reserve 120': 39' = 32,5% xanh; 40' = 33,33% vàng; 79' = 65,83% vàng; 80' = 66,67% > 66 cam
    assert risk(at(8) + timedelta(minutes=minutes)).risk_color == color


def test_consumption_never_negative_when_ahead_of_plan() -> None:
    assert risk(at(7, 45)).consumption_pct == Decimal("0.00")
