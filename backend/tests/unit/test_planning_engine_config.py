"""MarketConfig (04 mục 8, ref.market.config) → EngineConfig thuần cho engine (09 bất biến 6, 20)."""

from datetime import date, time
from decimal import Decimal

import pytest

from app.core.config import MarketConfig
from app.services.planning_service import engine_config


def test_default_market_config_maps_every_engine_parameter() -> None:
    holidays = {date(2026, 12, 25)}
    ec = engine_config(MarketConfig.model_validate({}), holidays)
    assert ec.working_days == frozenset({1, 2, 3, 4, 5}) and ec.holidays == frozenset(holidays)
    assert ec.default_receiving_hours == (time(7, 0), time(16, 0))
    assert (ec.search_days_max, ec.reserve_safe_days, ec.eta_round_min) == (14, 2, 15)
    assert ec.delivery_share == Decimal("0.9") and ec.final_inspection_hours == Decimal("0.5")
    assert ec.flag_multiplier_cap == Decimal("2.0")
    assert (ec.loading_base_min, ec.loading_min_per_ton, ec.unloading_base_min, ec.unloading_min_per_ton) == (
        20,
        6,
        20,
        6,
    )
    assert ec.driver_max_hours_day == Decimal(9) and ec.receiving_lead_days == 1
    assert ec.max_arrival_spread_min == 30
    assert (ec.w_km, ec.w_fill, ec.dz_km_abs, ec.dz_km_pct, ec.dz_fill, ec.tie_eps) == (
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal(2),
        Decimal("0.05"),
        Decimal("0.05"),
        Decimal("0.001"),
    )
    assert ec.allow_route_fallback is True


def test_market_overrides_are_used_not_hard_coded_values() -> None:
    cfg = MarketConfig.model_validate(
        {
            "working_days": [1, 2, 3, 4, 5, 6],
            "default_receiving_hours": {"mon-fri": ["06:30", "15:00"]},
            "delivery_share": 0.85,
            "rank": {"w_km": 0.8, "w_fill": 0.2},
            "routing": {"allow_fallback": False},
        }
    )
    ec = engine_config(cfg, set())
    assert ec.working_days == frozenset(range(1, 7))
    assert ec.default_receiving_hours == (time(6, 30), time(15, 0))
    assert ec.delivery_share == Decimal("0.85") and (ec.w_km, ec.w_fill) == (Decimal("0.8"), Decimal("0.2"))
    assert ec.allow_route_fallback is False


def test_several_different_receiving_windows_are_rejected() -> None:
    cfg = MarketConfig.model_validate(
        {"default_receiving_hours": {"mon-thu": ["07:00", "16:00"], "fri": ["07:00", "12:00"]}}
    )
    with pytest.raises(ValueError, match="receiving"):
        engine_config(cfg, set())
