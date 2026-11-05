"""Kiểu dữ liệu vào/ra của engine (04 mục 6.1). Tất cả là frozen dataclass.

Cấu hình engine nhận dưới dạng EngineConfig (bản thuần của MarketConfig) để engine không phụ
thuộc Pydantic/app.core.

Owner: Dev 1 (luồng A) — M4.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

DateModeT = Literal["exact", "range", "latest"]
CheckNameT = Literal["stock", "preparation", "truck", "site_date", "safety"]
ResultT = Literal["feasible", "infeasible", "manual"]
ReserveClassT = Literal["safe", "tight", "infeasible"]
PrepUnitT = Literal["line", "pallet", "m3", "bundle", "package"]


@dataclass(frozen=True)
class EngineConfig:
    """Các tham số MarketConfig mà engine dùng (04 mục 8). Không hard-code (09 bất biến 20)."""

    working_days: frozenset[int]
    default_receiving_hours: tuple[time, time]
    holidays: frozenset[date]
    search_days_max: int
    reserve_safe_days: int
    eta_round_min: int
    delivery_share: Decimal
    final_inspection_hours: Decimal
    flag_multiplier_cap: Decimal
    loading_base_min: int
    loading_min_per_ton: int
    unloading_base_min: int
    unloading_min_per_ton: int
    driver_max_hours_day: Decimal
    receiving_lead_days: int
    w_km: Decimal
    w_fill: Decimal
    dz_km_abs: Decimal
    dz_km_pct: Decimal
    dz_fill: Decimal
    tie_eps: Decimal
    allow_route_fallback: bool


@dataclass(frozen=True)
class HandlingGroupCtx:
    """Định mức một nhóm N1–N6 (05 mục 11). Dùng chung mọi kho."""

    code: str
    prep_unit: PrepUnitT
    fixed_hours: Decimal
    labour_hours_per_unit: Decimal
    vehicle_requirement: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ProductCtx:
    global_product_id: int
    group: HandlingGroupCtx
    base_units_per_prep_unit: Decimal | None
    flag_multipliers: tuple[Decimal, ...]
    weight_kg: Decimal
    volume_m3: Decimal


@dataclass(frozen=True)
class LineCtx:
    product: ProductCtx
    qty_base: Decimal


@dataclass(frozen=True)
class OrderCtx:
    id: int
    version: int
    lat: float
    lon: float
    date_mode: DateModeT
    date_from: date | None
    date_to: date
    window: tuple[time, time] | None
    lines: tuple[LineCtx, ...]
    now: datetime


@dataclass(frozen=True)
class InboundCtx:
    global_product_id: int
    qty: Decimal
    eta_date: date
    inbound_ref: str


@dataclass(frozen=True)
class ShiftCapacity:
    name: str
    start: time
    end: time
    present_staff: int
    useful_hours_per_staff: Decimal


@dataclass(frozen=True)
class DayCapacity:
    """Công suất một ngày: ca, số người có mặt/planned, giờ đã đặt của đơn khác (không thiết bị)."""

    day: date
    shifts: tuple[ShiftCapacity, ...]
    booked_hours: Decimal


@dataclass(frozen=True)
class VehicleCtx:
    id: int
    code: str
    capacity_kg: Decimal
    capacity_m3: Decimal
    capabilities: frozenset[str]
    required_licence: Literal["B", "C", "CE"]
    allowed_group_codes: frozenset[str]
    busy: tuple[tuple[datetime, datetime], ...]


@dataclass(frozen=True)
class DriverCtx:
    employee_id: int
    licence_class: Literal["B", "C", "CE"]
    licence_expires_on: date
    available_days: frozenset[date]
    booked_hours_by_day: dict[date, Decimal]
    busy: tuple[tuple[datetime, datetime], ...]


@dataclass(frozen=True)
class RouteInfo:
    distance_km: Decimal
    drive_min: int
    provenance: Literal["ors", "fallback"]


@dataclass(frozen=True)
class WarehouseCtx:
    id: int
    name: str
    cutoff: time
    efficiency: Decimal
    stock_available: dict[int, Decimal]  # đã trừ wms_reserved + giữ chỗ đơn KHÁC (held còn hạn + committed)
    inbound: tuple[InboundCtx, ...]  # confirmed, chưa received
    capacity: dict[date, DayCapacity]
    vehicles: tuple[VehicleCtx, ...]
    drivers: tuple[DriverCtx, ...]
    route: RouteInfo | None


@dataclass(frozen=True)
class RankWeights:
    w_km: Decimal
    w_fill: Decimal


@dataclass(frozen=True)
class CheckResult:
    name: CheckNameT
    passed: bool
    code: str
    detail: dict[str, object] = field(default_factory=dict)  # luôn có "message" (06 Phụ lục A)


@dataclass(frozen=True)
class Workload:
    labour_hours: Decimal
    line_hours: tuple[Decimal, ...]


@dataclass(frozen=True)
class PlanCandidate:
    """Một phương án khả thi — ánh xạ sang plan.fulfilment_plan (05 mục 7)."""

    warehouse_id: int
    vehicle_id: int
    vehicle_code: str
    driver_employee_id: int
    target_date: date
    goods_ready_at: datetime
    loading_start_at: datetime
    depart_at: datetime
    eta_at: datetime
    trip_end_at: datetime
    distance_km: Decimal
    drive_min: int
    prep_hours: Decimal
    capacity_fill: Decimal
    complexity_points: int
    planning_reserve_min: int
    route_provenance: Literal["ors", "fallback"]
    checks: tuple[CheckResult, ...]
    prep_by_day: dict[date, Decimal]
    score: Decimal = Decimal(0)
    rank: int = 0
    reason_codes: tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True)
class RejectedCandidate:
    warehouse_id: int
    vehicle_code: str | None
    failed_check: CheckNameT
    code: str
    detail: dict[str, object]


@dataclass(frozen=True)
class TransferSuggestion:
    from_warehouse_id: int
    to_warehouse_id: int
    lines: tuple[tuple[int, Decimal], ...]
    lead_days: int
    distance_km: Decimal


@dataclass(frozen=True)
class PlanningResult:
    result: ResultT
    candidates: tuple[PlanCandidate, ...]  # tối đa 3, đã xếp hạng
    rejected: tuple[RejectedCandidate, ...]
    failed_check: CheckNameT | None
    earliest_feasible_date: date | None
    reserve_class: ReserveClassT | None
    planning_reserve_min: int | None
    transfer_suggestions: tuple[TransferSuggestion, ...]
    manual_reason: Literal["NEEDS_MULTI_VEHICLE", "NO_CAPABLE_VEHICLE"] | None = None
