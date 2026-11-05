"""Test hạ tầng đã hiện thực: clock, làm tròn ETA, MarketConfig, bảng chuyển trạng thái."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core import clock
from app.core.config import MarketConfig
from app.core.numbers import ceil_to_minutes
from app.domain.enums import OrderStatus as S
from app.domain.transitions import is_allowed


def test_clock_frozen_at_demo_now(frozen_clock: datetime) -> None:
    assert clock.now() == frozen_clock


def test_eta_rounds_up_to_15_minutes() -> None:
    ts = datetime.fromisoformat("2026-11-10T12:01:00+01:00")
    assert ceil_to_minutes(ts, 15).minute == 15
    exact = datetime.fromisoformat("2026-11-10T12:15:00+01:00")
    assert ceil_to_minutes(exact, 15) == exact


def test_US_ADM_02_AC1_delivery_share_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        MarketConfig(delivery_share=1.5)


def test_market_config_defaults_match_doc_04() -> None:
    cfg = MarketConfig()
    assert cfg.hold.ttl_min == 15 and cfg.hold.max_extensions == 2
    assert cfg.rank.w_km == 0.5 and cfg.risk.yellow_pct == 33 and cfg.routing.allow_fallback


def test_US_APR_04_manual_planning_can_go_external() -> None:
    assert is_allowed(S.MANUAL_PLANNING, S.HANDLED_EXTERNALLY)
    assert not is_allowed(S.PLANNED, S.HANDLED_EXTERNALLY)
