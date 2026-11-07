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

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import combinations

from app.engine.capacity import is_working_day
from app.engine.types import (
    CheckNameT,
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


_QTY = Decimal("0.001")  # order_line.qty_base numeric(12,3)
MAX_BUSY_SHIFTS = 10  # 04 mục 6.2 bước 2d: dời loading_start tối đa 10 lần


def order_load(order: OrderCtx) -> tuple[Decimal, Decimal]:
    """Tổng (kg, m³) của đơn theo đơn vị cơ sở."""
    kg = sum((ln.qty_base * ln.product.weight_kg for ln in order.lines), Decimal(0))
    m3 = sum((ln.qty_base * ln.product.volume_m3 for ln in order.lines), Decimal(0))
    return kg, m3


def _busy_all_day(vehicle: VehicleCtx, day: date) -> bool:
    for start, end in vehicle.busy:
        tz = start.tzinfo
        if start <= datetime.combine(day, time.min, tzinfo=tz) and end >= datetime.combine(
            day + timedelta(days=1), time.min, tzinfo=tz
        ):
            return True
    return False


def choose_vehicle_sets(
    order: OrderCtx, wh: WarehouseCtx, day: date, max_sets: int = 2
) -> tuple[tuple[VehicleCtx, ...], ...]:
    """Bộ xe ứng viên (bước 2d, v1.2): Σ kg ≥ tổng kg, Σ m³ ≥ tổng m³, **số xe ít nhất**; cùng số xe thì
    tổng tải nhỏ hơn (rồi tổng thể tích, rồi mã xe). Trả tối đa `max_sets` bộ: bộ tốt nhất và bộ thay thế
    (cùng số xe nếu có, nếu không thì bộ tốt nhất với thêm một xe). Rỗng → caller báo NO_TRUCK_FIT.

    Giới hạn MVP: mỗi xe trong bộ phải chở được MỌI nhóm hàng và năng lực của đơn (eligible_vehicles),
    nên phần chia hàng không phải ràng buộc theo nhóm. Xe bận cả ngày bị bỏ; trùng giờ cụ thể được xử lý
    khi xếp giờ (plan_delivery).
    """
    eligible, _ = eligible_vehicles(order, wh)
    pool = [v for v in eligible if not _busy_all_day(v, day)]
    need_kg, need_m3 = order_load(order)

    def key(vs: tuple[VehicleCtx, ...]) -> tuple[Decimal, Decimal, tuple[str, ...]]:
        return (
            sum((v.capacity_kg for v in vs), Decimal(0)),
            sum((v.capacity_m3 for v in vs), Decimal(0)),
            tuple(v.code for v in vs),
        )

    found: list[tuple[VehicleCtx, ...]] = []
    for size in range(1, len(pool) + 1):
        fits = sorted(
            (
                vs
                for vs in combinations(pool, size)
                if sum((v.capacity_kg for v in vs), Decimal(0)) >= need_kg
                and sum((v.capacity_m3 for v in vs), Decimal(0)) >= need_m3
            ),
            key=key,
        )
        found.extend(fits[: max_sets - len(found)])
        if len(found) >= max_sets or (found and size > len(found[0])):
            break
    return tuple(found[:max_sets])


def split_load(
    order: OrderCtx, vehicle_set: tuple[VehicleCtx, ...]
) -> tuple[tuple[tuple[int, Decimal], ...], ...]:
    """Chia dòng hàng cho các xe theo tải và thể tích (bước 2d): lần lượt lấp đầy từng xe theo thứ tự
    dòng; một dòng có thể tách qua nhiều xe (ví dụ 40 pallet chia 2 xe). `line_no` = vị trí dòng (1-based).
    Lượng làm tròn xuống 0,001 theo `qty_base`. Không xếp hết (giới hạn của cách lấp tham lam hai chiều) →
    trả `()`; caller thử bộ xe khác hoặc báo NO_TRUCK_FIT.
    """
    remaining = [ln.qty_base for ln in order.lines]
    loads: list[tuple[tuple[int, Decimal], ...]] = []
    for idx, vehicle in enumerate(vehicle_set):
        last = idx == len(vehicle_set) - 1
        kg_left, m3_left = vehicle.capacity_kg, vehicle.capacity_m3
        parts: list[tuple[int, Decimal]] = []
        for i, ln in enumerate(order.lines):
            qty = remaining[i]
            if qty <= 0:
                continue
            w, v = ln.product.weight_kg, ln.product.volume_m3
            fit = min(
                kg_left / w if w > 0 else qty,
                m3_left / v if v > 0 else qty,
                qty,
            )
            take = qty if fit >= qty else fit.quantize(_QTY, rounding=ROUND_FLOOR)
            if take <= 0:
                continue
            parts.append((i + 1, take))
            remaining[i] = qty - take
            kg_left -= take * w
            m3_left -= take * v
        if parts:
            loads.append(tuple(parts))
        elif not last:
            loads.append(())
    if any(q > 0 for q in remaining) or len(loads) != len(vehicle_set) or not all(loads):
        return ()
    return tuple(loads)


def _load_of(order: OrderCtx, parts: tuple[tuple[int, Decimal], ...]) -> tuple[Decimal, Decimal]:
    kg = sum((qty * order.lines[no - 1].product.weight_kg for no, qty in parts), Decimal(0))
    m3 = sum((qty * order.lines[no - 1].product.volume_m3 for no, qty in parts), Decimal(0))
    return kg, m3


def _check(name: CheckNameT, code: str, message: str, **detail: object) -> CheckResult:
    return CheckResult(name, code.endswith("_OK"), code, {"message": message, **detail})


def plan_delivery(
    order: OrderCtx,
    wh: WarehouseCtx,
    vehicle_set: tuple[VehicleCtx, ...],
    goods_ready_at: datetime,
    cfg: EngineConfig,
) -> tuple[DeliveryOption | None, tuple[CheckResult, ...]]:
    """Xếp giờ cho một bộ xe (bước 2d–2f, v1.2) và trả các check truck → site_date → safety.

    Lên hàng lần lượt từ `goods_ready_at` (mỗi xe `loading_min` theo tải của nó); nếu ngày giao muộn hơn
    ngày lên hàng thì lên hàng ngược từ giờ xuất phát của ngày giao (không chờ qua đêm); xe đụng lịch bận thì
    dời `loading_start` tới hết khoảng bận (tối đa 10 lần, quá → TRUCK_BUSY). Mọi xe tới CÙNG một ETA
    (xe lên hàng xong sớm chờ xuất phát), nên chênh lệch tới = 0 ≤ `max_arrival_spread_min`; ETA phương án =
    xe tới cuối. Mỗi xe một tài xế khác nhau (pick_driver): không ai → NO_DRIVER (truck); chỉ vướng giờ lái /
    hạn bằng → check safety. Hàm thuần.
    """
    loads = split_load(order, vehicle_set)
    if not loads:
        return None, (_check("truck", "NO_TRUCK_FIT", "Load cannot be split over this vehicle set.",
                             reason="combined_capacity"),)  # fmt: skip
    if wh.route is None:
        return None, (
            _check("truck", "TRUCK_OK", "Vehicles fit the load."),
            _check("site_date", "ROUTE_DATA_UNAVAILABLE", "No route data for this warehouse."),
        )
    drive = timedelta(minutes=wh.route.drive_min)
    weights = [_load_of(order, parts) for parts in loads]
    min_start = [goods_ready_at] * len(vehicle_set)
    for _attempt in range(MAX_BUSY_SHIFTS + 1):
        starts: list[datetime] = []
        ends: list[datetime] = []
        cursor = goods_ready_at
        for i, (kg, _) in enumerate(weights):
            start = max(cursor, min_start[i])
            end = start + timedelta(
                minutes=handling_minutes(kg, cfg.loading_base_min, cfg.loading_min_per_ton)
            )
            starts.append(start)
            ends.append(end)
            cursor = end
        arrival = place_arrival(order, max(e + drive for e in ends), cfg)
        if arrival.code != "DATE_OK" or arrival.eta_at is None or arrival.target_date is None:
            if _attempt > 0:  # đã phải dời vì lịch bận mà không còn ngày hợp lệ → nguyên nhân là xe bận
                busy = _check(
                    "truck", "TRUCK_BUSY", "Vehicles stay busy until no delivery day is left.",
                    vehicle_codes=[v.code for v in vehicle_set],
                )  # fmt: skip
                return None, (busy,)
            return None, (
                _check("truck", "TRUCK_OK", "Vehicles fit the load."),
                CheckResult("site_date", False, arrival.code, arrival.detail),
            )
        eta = arrival.eta_at
        if eta.date() > ends[-1].date():
            # Giao vào ngày sau: không để xe/tài xế "chờ qua đêm" — lên hàng lần lượt NGƯỢC từ giờ xuất phát
            # trong ngày giao (vẫn sau goods_ready_at và sau mốc dời do lịch bận).
            cursor = eta - drive
            for i in reversed(range(len(weights))):
                minutes = ends[i] - starts[i]
                start = max(cursor - minutes, min_start[i])
                starts[i], ends[i] = start, start + minutes
                cursor = start
        trip_ends = [
            eta
            + timedelta(minutes=handling_minutes(kg, cfg.unloading_base_min, cfg.unloading_min_per_ton))
            + drive
            for kg, _ in weights
        ]
        clash = next(
            (i for i, v in enumerate(vehicle_set) if not vehicle_free(v, starts[i], trip_ends[i])), None
        )
        if clash is None:
            break
        vehicle = vehicle_set[clash]
        min_start[clash] = max(
            b_end for b_start, b_end in vehicle.busy if b_start < trip_ends[clash] and starts[clash] < b_end
        )
    else:
        return None, (_check("truck", "TRUCK_BUSY", "Vehicles are busy on this day.",
                             vehicle_codes=[v.code for v in vehicle_set]),)  # fmt: skip

    assignments: list[VehicleAssignment] = []
    remaining_drivers = wh.drivers
    safety_code: str | None = None
    for i, vehicle in enumerate(vehicle_set):
        pool = replace(wh, drivers=remaining_drivers)
        chosen, problem = pick_driver(pool, vehicle, starts[i], trip_ends[i], cfg)
        if chosen is None:
            if problem == "NO_DRIVER":
                return None, (_check("truck", "NO_DRIVER", "No eligible driver is free for every vehicle.",
                                     vehicle_code=vehicle.code),)  # fmt: skip
            safety_code = safety_code or problem
            continue
        remaining_drivers = tuple(d for d in remaining_drivers if d.employee_id != chosen.employee_id)
        kg, m3 = weights[i]
        assignments.append(
            VehicleAssignment(
                seq=i + 1,
                vehicle_id=vehicle.id,
                vehicle_code=vehicle.code,
                capacity_kg=vehicle.capacity_kg,
                capacity_m3=vehicle.capacity_m3,
                driver_employee_id=chosen.employee_id,
                load_kg=kg,
                load_m3=m3,
                load_lines=loads[i],
                loading_start_at=starts[i],
                depart_at=eta - drive,
                eta_at=eta,
                trip_end_at=trip_ends[i],
            )
        )
    truck = _check("truck", "TRUCK_OK", f"{len(vehicle_set)} vehicle(s) fit the load.")
    site = CheckResult("site_date", True, "DATE_OK", arrival.detail)
    if safety_code is not None:
        return None, (
            truck,
            site,
            _check("safety", safety_code, "Driver hours or licence do not allow this trip."),
        )
    spread = max(a.eta_at for a in assignments) - min(a.eta_at for a in assignments)
    if spread > timedelta(minutes=cfg.max_arrival_spread_min):  # bất biến; cùng ETA nên không xảy ra
        return None, (
            truck,
            _check("site_date", "OUTSIDE_RECEIVING_HOURS", "Vehicles would not arrive together."),
        )
    option = DeliveryOption(tuple(assignments), arrival.target_date, planning_reserve_min(order, eta, cfg))
    return option, (truck, site, _check("safety", "SAFETY_OK", "Drivers and loads are within limits."))
