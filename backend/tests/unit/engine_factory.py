"""Dữ liệu dựng sẵn cho test engine thuần (không DB). Giá trị mặc định = MarketConfig 04 mục 8."""

from dataclasses import replace
from datetime import date, time
from decimal import Decimal

from app.engine.types import EngineConfig, HandlingGroupCtx, LineCtx, ProductCtx

CFG = EngineConfig(
    working_days=frozenset({1, 2, 3, 4, 5}),
    default_receiving_hours=(time(7, 0), time(16, 0)),
    holidays=frozenset(),
    search_days_max=14,
    reserve_safe_days=2,
    eta_round_min=15,
    delivery_share=Decimal("0.90"),
    final_inspection_hours=Decimal("0.5"),
    flag_multiplier_cap=Decimal("2.0"),
    loading_base_min=20,
    loading_min_per_ton=6,
    unloading_base_min=20,
    unloading_min_per_ton=6,
    driver_max_hours_day=Decimal(9),
    receiving_lead_days=1,
    max_arrival_spread_min=30,
    w_km=Decimal("0.5"),
    w_fill=Decimal("0.5"),
    dz_km_abs=Decimal(2),
    dz_km_pct=Decimal("0.05"),
    dz_fill=Decimal("0.05"),
    tie_eps=Decimal("0.001"),
    allow_route_fallback=True,
)

# Định mức mẫu 05 mục 11
N1 = HandlingGroupCtx("N1", "line", Decimal(0), Decimal("0.05"))
N2 = HandlingGroupCtx("N2", "pallet", Decimal("0.25"), Decimal("0.40"))
N3 = HandlingGroupCtx("N3", "pallet", Decimal("0.25"), Decimal("0.15"))
N4 = HandlingGroupCtx("N4", "m3", Decimal("0.50"), Decimal("0.10"), frozenset({"dump"}))
N6 = HandlingGroupCtx("N6", "package", Decimal("0.25"), Decimal("0.60"))

FRAGILE, HAZARDOUS, SPECIAL_STORAGE, FAR_OR_OUTDOOR = (
    Decimal("1.25"),
    Decimal("1.30"),
    Decimal("1.15"),
    Decimal("1.20"),
)


def line(
    group: HandlingGroupCtx,
    qty: str,
    per_prep_unit: str | None = None,
    *,
    product_id: int = 1,
    flags: tuple[Decimal, ...] = (),
    weight_kg: str = "25",
    volume_m3: str = "0.02",
) -> LineCtx:
    product = ProductCtx(
        product_id,
        group,
        Decimal(per_prep_unit) if per_prep_unit else None,
        flags,
        Decimal(weight_kg),
        Decimal(volume_m3),
    )
    return LineCtx(product, Decimal(qty))


def cfg(**overrides: object) -> EngineConfig:
    return replace(CFG, **overrides)  # type: ignore[arg-type]


WED = date(2026, 11, 4)  # Thứ Tư — ngày demo (08 mục 5)
