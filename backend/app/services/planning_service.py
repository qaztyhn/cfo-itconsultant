"""Lập kế hoạch (04 mục 7.1; US-PLN-01..08).

Nạp ngữ cảnh theo kho và chân trời 14 ngày → EngineConfig/OrderCtx/WarehouseCtx → engine.plan_order →
trong MỘT transaction: planning_run (+input_snapshot), fulfilment_plan + plan_vehicle, giữ chỗ
(ReservationService, KHÔNG khóa, cho phép vượt), đơn PLANNED/NO_FEASIBLE_DATE, PLAN_PROPOSED +
RESERVATION_HELD. Chạy lại bắt buộc lý do (CRITERIA_CHANGED_RERUN), giữ chỗ cũ released. suggest_replan():
4 tín hiệu (source_change, plan_invalidated, vehicle_issue, delivery_failed) →
planning_run(kind='replan_suggestion'), cộng lại tài nguyên của kế hoạch cũ của chính đơn vào ngữ cảnh,
KHÔNG giữ chỗ, alert REPLAN_SUGGESTED (06 mục 6.6; US-APR-04).

Owner: Dev 1 (A) — M4.
"""

from collections.abc import Iterable
from datetime import date, time
from decimal import Decimal

from app.core.config import MarketConfig
from app.engine.types import EngineConfig


def _dec(value: float | int) -> Decimal:
    """float của JSON cấu hình → Decimal qua chuỗi (tránh sai số nhị phân)."""
    return Decimal(str(value))


def _receiving_hours(cfg: MarketConfig) -> tuple[time, time]:
    windows = {tuple(v) for v in cfg.default_receiving_hours.values()}
    if len(windows) != 1:
        raise ValueError("default_receiving_hours must define one window (engine supports a single window)")
    opens, closes = next(iter(windows))
    return time.fromisoformat(opens), time.fromisoformat(closes)


def engine_config(cfg: MarketConfig, holidays: Iterable[date]) -> EngineConfig:
    """Chuyển MarketConfig của market (04 mục 8) + ngày lễ (ref.market_holiday) sang EngineConfig thuần.

    Mọi số cấu hình đến từ `ref.market.config` (09 bất biến 20); engine không đọc Pydantic/env (bất biến 6).
    """
    return EngineConfig(
        working_days=frozenset(cfg.working_days),
        default_receiving_hours=_receiving_hours(cfg),
        holidays=frozenset(holidays),
        search_days_max=cfg.search_days_max,
        reserve_safe_days=cfg.reserve_safe_days,
        eta_round_min=cfg.eta_round_min,
        delivery_share=_dec(cfg.delivery_share),
        final_inspection_hours=_dec(cfg.final_inspection_hours),
        flag_multiplier_cap=_dec(cfg.flag_multiplier_cap),
        loading_base_min=cfg.loading.base_min,
        loading_min_per_ton=cfg.loading.min_per_ton,
        unloading_base_min=cfg.unloading.base_min,
        unloading_min_per_ton=cfg.unloading.min_per_ton,
        driver_max_hours_day=_dec(cfg.driver_max_hours_day),
        receiving_lead_days=cfg.receiving_lead_days,
        max_arrival_spread_min=cfg.multi_vehicle.max_arrival_spread_min,
        w_km=_dec(cfg.rank.w_km),
        w_fill=_dec(cfg.rank.w_fill),
        dz_km_abs=_dec(cfg.rank.dz_km_abs),
        dz_km_pct=_dec(cfg.rank.dz_km_pct),
        dz_fill=_dec(cfg.rank.dz_fill),
        tie_eps=_dec(cfg.rank.tie_eps),
        allow_route_fallback=cfg.routing.allow_fallback,
    )


async def plan(order_id: int, actor: object | None, params: dict[str, object] | None = None) -> int:
    """TODO(#planning-plan)."""
    raise NotImplementedError


async def suggest_replan(order_id: int, trigger: str) -> int | None:
    """TODO(#planning-suggest_replan)."""
    raise NotImplementedError


async def get_run(run_id: int) -> dict[str, object]:
    """TODO(#planning-get_run)."""
    raise NotImplementedError
