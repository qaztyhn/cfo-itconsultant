"""Bước 2d + 2e + 2f — bộ xe, tài xế, ngày giao, cửa sổ nhận hàng, dự trữ (04 mục 6.2;
BR-DEL-01..05; US-PLN-03/04/05, US-ORD-05).

v1.2 — NHIỀU XE: chọn bộ xe hợp lệ (cùng kho, available, nhóm hàng cho phép, đủ capabilities crane/dump)
rảnh cùng ngày với Σ kg ≥ tổng kg, Σ m³ ≥ tổng m³, SỐ XE ÍT NHẤT; cùng số xe thì tổng tải nhỏ hơn.
Không giới hạn số xe. Chia hàng theo tải/thể tích (một dòng được tách). Mỗi xe một tài xế: cùng kho,
có mặt, bằng ≥ yêu cầu và còn hạn, ≤ driver_max_hours_day, không trùng giờ. Lên hàng lần lượt; mọi xe
tới trong cửa sổ, chênh ≤ max_arrival_spread_min. Không có bộ xe → NO_TRUCK_FIT (detail.reason =
capability | combined_capacity) / TRUCK_BUSY / NO_DRIVER. Không ghép đơn.
Ngày: exact không sớm hơn; range từ date_from; latest ≤ date_to; ngoài cửa sổ → ngày làm việc kế.
ETA làm tròn lên eta_round_min; ETA phương án = xe tới cuối. planning_reserve = close(window(date_to))
− earliest_feasible_eta.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal

from app.engine.capacity import is_working_day
from app.engine.types import (
    CheckResult,
    DriverCtx,
    EngineConfig,
    OrderCtx,
    VehicleAssignment,
    VehicleCtx,
    WarehouseCtx,
)

LICENCE_RANK = {"B": 1, "C": 2, "CE": 3}  # CE ≥ C ≥ B


@dataclass(frozen=True)
class DeliveryOption:
    vehicles: tuple[VehicleAssignment, ...]
    target_date: date
    planning_reserve_min: int


@dataclass(frozen=True)
class ArrivalResult:
    """Kết quả chọn ngày giao/ETA cho một thời điểm tới sớm nhất (bước 2e)."""

    code: str  # DATE_OK | DATE_AFTER_DEADLINE | NON_WORKING_DAY
    target_date: date | None
    eta_at: datetime | None
    detail: dict[str, object]


def eligible_vehicles(order: OrderCtx, wh: WarehouseCtx) -> tuple[tuple[VehicleCtx, ...], str | None]:
    """Xe của kho chở được MỌI nhóm hàng của đơn và có đủ năng lực (crane/dump…) — chưa xét tải.

    `wh.vehicles` chỉ gồm xe `status = 'available'` (service lọc). Không xe nào hợp lệ → lý do `capability`
    (dùng cho `NO_TRUCK_FIT.detail.reason`). Đơn tách hàng qua nhiều xe theo nhóm là phần chọn bộ xe (2d).
    """
    groups = {ln.product.group.code for ln in order.lines}
    required: set[str] = set()
    for ln in order.lines:
        required |= ln.product.group.vehicle_requirement
    eligible = tuple(
        v
        for v in sorted(wh.vehicles, key=lambda v: v.code)
        if (not v.allowed_group_codes or groups <= v.allowed_group_codes) and required <= v.capabilities
    )
    return eligible, (None if eligible else "capability")


def _overlaps(busy: tuple[tuple[datetime, datetime], ...], start: datetime, end: datetime) -> bool:
    return any(b_start < end and start < b_end for b_start, b_end in busy)  # khoảng nửa mở


def vehicle_free(vehicle: VehicleCtx, start: datetime, end: datetime) -> bool:
    """Xe không bận (giữ chỗ của đơn khác / lịch bảo trì) trong [start, end)."""
    return not _overlaps(vehicle.busy, start, end)


def pick_driver(
    wh: WarehouseCtx, vehicle: VehicleCtx, start: datetime, end: datetime, cfg: EngineConfig
) -> tuple[DriverCtx | None, str | None]:
    """Tài xế đầu tiên (id tăng) đủ điều kiện cho chuyến [start, end) của xe.

    Điều kiện: có mặt ngày đó, hạng bằng ≥ yêu cầu, không trùng giờ, bằng còn hạn tới ngày chuyến,
    tổng giờ trong ngày + chuyến ≤ driver_max_hours_day. Không ai đạt: DRIVER_HOURS_EXCEEDED nếu có tài xế
    chỉ vướng giờ lái; LICENCE_EXPIRED nếu có tài xế vướng hạn bằng; còn lại NO_DRIVER.
    """
    day = start.date()
    trip_hours = Decimal(int((end - start).total_seconds())) / 3600
    hours_only = expired_seen = False
    for driver in sorted(wh.drivers, key=lambda d: d.employee_id):
        if day not in driver.available_days or _overlaps(driver.busy, start, end):
            continue
        if LICENCE_RANK[driver.licence_class] < LICENCE_RANK[vehicle.required_licence]:
            continue
        expired = driver.licence_expires_on < day
        over = driver.booked_hours_by_day.get(day, Decimal(0)) + trip_hours > cfg.driver_max_hours_day
        if not expired and not over:
            return driver, None
        hours_only |= over and not expired
        expired_seen |= expired
    if hours_only:
        return None, "DRIVER_HOURS_EXCEEDED"
    return None, ("LICENCE_EXPIRED" if expired_seen else "NO_DRIVER")


def handling_minutes(load_kg: Decimal, base_min: int, min_per_ton: int) -> int:
    """Phút lên/dỡ hàng = base + per_ton × tấn, làm tròn lên phút (04 mục 6.2 bước 2c, 2e)."""
    extra = (Decimal(min_per_ton) * load_kg / 1000).to_integral_value(rounding=ROUND_CEILING)
    return base_min + int(extra)


def receiving_window(order: OrderCtx, cfg: EngineConfig) -> tuple[time, time]:
    """Cửa sổ khách yêu cầu nếu có, nếu không `default_receiving_hours` (US-PLN-04 AC5)."""
    return order.window or cfg.default_receiving_hours


def candidate_days(order: OrderCtx, earliest: date, cfg: EngineConfig) -> tuple[date, ...]:
    """Ngày giao được phép theo dạng ngày, không sớm hơn `earliest`.

    exact: chỉ date_to; range: ngày làm việc trong [date_from, date_to]; latest: ngày làm việc ≤ date_to.
    """
    if order.date_mode == "exact":
        return (order.date_to,) if order.date_to >= earliest else ()
    first = max(earliest, order.date_from) if order.date_mode == "range" and order.date_from else earliest
    days: list[date] = []
    d = first
    while d <= order.date_to:
        if is_working_day(d, cfg):
            days.append(d)
        d += timedelta(days=1)
    return tuple(days)


def _ceil_step(ts: datetime, step_min: int) -> datetime:
    base = ts.replace(second=0, microsecond=0)
    minutes = base.hour * 60 + base.minute + (1 if (ts.second or ts.microsecond) else 0)
    return base.replace(hour=0, minute=0) + timedelta(minutes=-(-minutes // step_min) * step_min)


def place_arrival(order: OrderCtx, earliest_arrival: datetime, cfg: EngineConfig) -> ArrivalResult:
    """Chọn ngày giao T và ETA từ thời điểm tới sớm nhất (bước 2e).

    Không giao sớm hơn ngày khách chọn: tới sớm thì ETA = giờ mở cửa sổ của T (xuất phát muộn lại);
    ETA làm tròn lên `eta_round_min`; vượt giờ đóng → ngày làm việc kế trong tập cho phép;
    hết ngày → DATE_AFTER_DEADLINE.
    """
    if order.date_mode == "exact" and not is_working_day(order.date_to, cfg):
        return ArrivalResult(
            "NON_WORKING_DAY", None, None, {"message": f"{order.date_to} is not a working day."}
        )
    open_t, close_t = receiving_window(order, cfg)
    tz = earliest_arrival.tzinfo
    for d in candidate_days(order, earliest_arrival.date(), cfg):
        opens = datetime.combine(d, open_t, tzinfo=tz)
        eta = _ceil_step(max(earliest_arrival, opens), cfg.eta_round_min)
        if eta <= datetime.combine(d, close_t, tzinfo=tz):
            return ArrivalResult("DATE_OK", d, eta, {"message": f"Delivery on {d} at {eta:%H:%M}."})
    return ArrivalResult(
        "DATE_AFTER_DEADLINE",
        None,
        None,
        {"message": f"Cannot arrive within the receiving window by {order.date_to}."},
    )


def planning_reserve_min(order: OrderCtx, earliest_feasible_eta: datetime, cfg: EngineConfig) -> int:
    """Dự trữ = giờ đóng cửa sổ của date_to − ETA khả thi sớm nhất (phút, có thể âm) — bước 2f."""
    close = datetime.combine(
        order.date_to, receiving_window(order, cfg)[1], tzinfo=earliest_feasible_eta.tzinfo
    )
    return int((close - earliest_feasible_eta).total_seconds()) // 60


def choose_vehicle_sets(
    order: OrderCtx, wh: WarehouseCtx, day: date, max_sets: int = 2
) -> tuple[tuple[VehicleCtx, ...], ...]:
    """Các bộ xe rảnh trong ngày đủ tổng kg/m³, sắp theo (số xe, tổng tải) tăng dần. TODO(#M4-delivery)."""
    raise NotImplementedError


def split_load(
    order: OrderCtx, vehicle_set: tuple[VehicleCtx, ...]
) -> tuple[tuple[tuple[int, Decimal], ...], ...]:
    """Chia dòng hàng cho các xe theo tải và thể tích; một dòng có thể tách. TODO(#M4-delivery)."""
    raise NotImplementedError


def plan_delivery(
    order: OrderCtx,
    wh: WarehouseCtx,
    vehicle_set: tuple[VehicleCtx, ...],
    goods_ready_at: datetime,
    cfg: EngineConfig,
) -> tuple[DeliveryOption | None, tuple[CheckResult, ...]]:
    """Gán tài xế, xếp giờ lên hàng/xuất phát để các xe tới cùng lúc; trả check truck/site_date/safety.
    TODO(#M4-delivery)."""
    raise NotImplementedError
