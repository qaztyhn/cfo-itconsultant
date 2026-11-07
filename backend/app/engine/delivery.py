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

Q12 / 04 mục 6.7 (đã duyệt 07/11/2026): lên hàng chỉ trong ca kho chính thức có người (`loading_windows`) và
trước `cutoff`; khoảng làm việc của từng tài xế [loading_start, trip_end] nằm trọn trong ca thực tế
(`DriverCtx.shifts`); thiếu dữ liệu ca → không có phương án (không mặc định 24/7). Ràng buộc nhóm/năng lực
theo dòng hàng trên từng xe; ghép tài xế–xe bằng quay lui.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import combinations, islice, permutations

from app.engine.capacity import is_working_day
from app.engine.types import (
    CheckNameT,
    CheckResult,
    DriverCtx,
    EngineConfig,
    LineCtx,
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


def within_shift(shifts: tuple[tuple[datetime, datetime], ...], start: datetime, end: datetime) -> bool:
    """[start, end] nằm TRỌN trong một ca (ca có thể qua nửa đêm). Không có ca → False."""
    return any(s_start <= start and end <= s_end for s_start, s_end in shifts)


def _rest_ok(driver: DriverCtx, start: datetime, end: datetime, cfg: EngineConfig) -> bool:
    """Nghỉ hằng ngày ≥ daily_rest_hours giữa chuyến và mọi kỳ làm việc khác, trừ khi cùng một ca (Q12b)."""
    rest = timedelta(hours=cfg.daily_rest_hours)
    for d_start, d_end in driver.duty_history:
        same_shift = any(
            s_start <= min(start, d_start) and max(end, d_end) <= s_end for s_start, s_end in driver.shifts
        )
        if same_shift:
            continue  # cùng kỳ làm việc; trùng giờ được kiểm riêng qua `busy`
        gap = start - d_end if d_end <= start else d_start - end
        if gap < rest:
            return False
    return True


def driver_problem(
    driver: DriverCtx,
    vehicle: VehicleCtx,
    start: datetime,
    end: datetime,
    cfg: EngineConfig,
    driving_min: int = 0,
) -> str | None:
    """Lý do tài xế KHÔNG chạy được chuyến [start, end) của xe; None = được.

    Thứ tự: `licence` (hạng bằng thấp), `busy` (trùng lịch đã nhận), `no_schedule` (không có ca nào),
    `outside_shift` (có ca nhưng không phủ trọn chuyến), `expired` (bằng hết hạn), `hours` (vượt giờ/ngày).
    """
    if LICENCE_RANK[driver.licence_class] < LICENCE_RANK[vehicle.required_licence]:
        return "licence"
    if _overlaps(driver.busy, start, end):
        return "busy"
    if not driver.shifts:
        return "no_schedule"
    if not within_shift(driver.shifts, start, end):
        return "outside_shift"
    day = start.date()
    if driver.licence_expires_on < day:
        return "expired"
    if not driver.history_complete:
        return "history"
    if not _rest_ok(driver, start, end, cfg):
        return "rest"
    trip_hours = Decimal(int((end - start).total_seconds())) / 3600
    if driver.booked_hours_by_day.get(day, Decimal(0)) + trip_hours > cfg.driver_max_hours_day:
        return "hours"  # tổng giờ làm việc, không phải giờ lái
    if vehicle.regulation_561 and (
        driver.driving_min_by_day.get(day, 0) + driving_min > cfg.driving_max_min_day
        or driver.driving_min_week + driving_min > cfg.weekly_driving_max_min
        or driver.driving_min_fortnight + driving_min > cfg.fortnight_driving_max_min
    ):
        return "driving"
    return None


_SAFETY_CODES = {
    "outside_shift": "OUTSIDE_DRIVER_SHIFT",
    "hours": "DRIVER_HOURS_EXCEEDED",
    "expired": "LICENCE_EXPIRED",
    "history": "DRIVER_HISTORY_MISSING",
    "rest": "DRIVER_REST_INSUFFICIENT",
    "driving": "DRIVING_TIME_EXCEEDED",
}


def _failure_code(problems: list[str]) -> tuple[str, str]:
    """(mã, lý do) khi không tài xế nào đạt: ưu tiên lỗi safety gần đạt nhất, sau đó NO_DRIVER kèm lý do."""
    for problem in ("driving", "hours", "rest", "history", "expired", "outside_shift"):
        if problem in problems:
            return _SAFETY_CODES[problem], problem
    reason = "no_schedule" if "no_schedule" in problems else ("busy" if "busy" in problems else "licence")
    return "NO_DRIVER", reason


def pick_driver(
    wh: WarehouseCtx,
    vehicle: VehicleCtx,
    start: datetime,
    end: datetime,
    cfg: EngineConfig,
    driving_min: int = 0,
) -> tuple[DriverCtx | None, str | None]:
    """Tài xế đầu tiên (id tăng) đủ điều kiện cho chuyến [start, end) của xe (04 mục 6.2 bước 2d, 6.7).

    Điều kiện: hạng bằng ≥ yêu cầu, không trùng lịch, **chuyến nằm trọn trong một ca thực tế** của tài xế
    (`DriverCtx.shifts`), bằng còn hạn, tổng giờ trong ngày + chuyến ≤ driver_max_hours_day. Không ai đạt →
    mã DRIVER_HOURS_EXCEEDED / LICENCE_EXPIRED / OUTSIDE_DRIVER_SHIFT (safety) hoặc NO_DRIVER.
    """
    problems: list[str] = []
    for driver in sorted(wh.drivers, key=lambda d: d.employee_id):
        problem = driver_problem(driver, vehicle, start, end, cfg, driving_min)
        if problem is None:
            return driver, None
        problems.append(problem)
    return None, _failure_code(problems)[0]


def assign_drivers(
    drivers: tuple[DriverCtx, ...],
    vehicles: tuple[VehicleCtx, ...],
    intervals: list[tuple[datetime, datetime]],
    cfg: EngineConfig,
    driving_min: int = 0,
) -> tuple[tuple[DriverCtx, ...] | None, str, str]:
    """Ghép mỗi xe một tài xế KHÁC nhau (bipartite, quay lui) — không tham lam (04 mục 6.7).

    Trả (tài xế theo thứ tự xe, mã, lý do). Thất bại: một xe không có ứng viên → mã theo lỗi của xe đó;
    mọi xe có ứng viên nhưng không đủ người khác nhau → NO_DRIVER / `not_enough_drivers`.
    """
    candidates: list[list[DriverCtx]] = []
    for vehicle, (start, end) in zip(vehicles, intervals, strict=True):
        ok: list[DriverCtx] = []
        problems: list[str] = []
        for driver in sorted(drivers, key=lambda d: d.employee_id):
            problem = driver_problem(driver, vehicle, start, end, cfg, driving_min)
            if problem is None:
                ok.append(driver)
            else:
                problems.append(problem)
        if not ok:
            code, reason = _failure_code(problems)
            return None, code, reason
        candidates.append(ok)
    order = sorted(range(len(vehicles)), key=lambda i: len(candidates[i]))  # ít ứng viên trước
    chosen: dict[int, DriverCtx] = {}

    def solve(k: int, used: frozenset[int]) -> bool:
        if k == len(order):
            return True
        idx = order[k]
        for driver in candidates[idx]:
            if driver.employee_id not in used:
                chosen[idx] = driver
                if solve(k + 1, used | {driver.employee_id}):
                    return True
        return False

    if not solve(0, frozenset()):
        # Không đủ người khác nhau: nếu tài xế còn lại bị loại vì giờ lái/hạn bằng/ca → báo lỗi safety đó.
        excluded = [
            problem
            for vehicle, (start, end) in zip(vehicles, intervals, strict=True)
            for driver in drivers
            if (problem := driver_problem(driver, vehicle, start, end, cfg, driving_min)) is not None
        ]
        code, reason = _failure_code(excluded)
        return None, code, ("not_enough_drivers" if code == "NO_DRIVER" else reason)
    return tuple(chosen[i] for i in range(len(vehicles))), "OK", ""


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


def can_carry(vehicle: VehicleCtx, ln: LineCtx) -> bool:
    """Xe chở được dòng này: nhóm hàng được phép (rỗng = mọi nhóm) và đủ năng lực của nhóm (04 mục 6.7)."""
    group = ln.product.group
    return (not vehicle.allowed_group_codes or group.code in vehicle.allowed_group_codes) and (
        group.vehicle_requirement <= vehicle.capabilities
    )


def choose_vehicle_sets(
    order: OrderCtx, wh: WarehouseCtx, day: date, max_sets: int = 2
) -> tuple[tuple[VehicleCtx, ...], ...]:
    """Bộ xe ứng viên (bước 2d, v1.2): xếp được TOÀN BỘ hàng (split_load thành công, ràng buộc nhóm/năng lực
    theo dòng trên từng xe), **số xe ít nhất**; cùng số xe thì tổng tải nhỏ hơn (rồi thể tích, mã xe). Trả tối
    đa `max_sets` bộ: tốt nhất và thay thế (có thể thêm một xe). Bỏ xe bận cả ngày; trùng giờ cụ thể xử lý ở
    plan_delivery. Rỗng → caller báo NO_TRUCK_FIT (`capability` nếu có dòng không xe nào chở được).
    """
    pool = [
        v
        for v in sorted(wh.vehicles, key=lambda v: v.code)
        if not _busy_all_day(v, day) and any(can_carry(v, ln) for ln in order.lines)
    ]
    need_kg, need_m3 = order_load(order)

    def key(vs: tuple[VehicleCtx, ...]) -> tuple[Decimal, Decimal, tuple[str, ...]]:
        return (
            sum((v.capacity_kg for v in vs), Decimal(0)),
            sum((v.capacity_m3 for v in vs), Decimal(0)),
            tuple(v.code for v in vs),
        )

    found: list[tuple[VehicleCtx, ...]] = []
    for size in range(1, len(pool) + 1):
        fits = [
            vs
            for vs in sorted(combinations(pool, size), key=key)
            if sum((v.capacity_kg for v in vs), Decimal(0)) >= need_kg
            and sum((v.capacity_m3 for v in vs), Decimal(0)) >= need_m3
            and all(any(can_carry(v, ln) for v in vs) for ln in order.lines)
            and split_load(order, vs)
        ]
        found.extend(fits[: max_sets - len(found)])
        if len(found) >= max_sets or (found and size > len(found[0])):
            break
    return tuple(found[:max_sets])


_MAX_ORDERINGS = 720  # tối đa 6! hoán vị xe


def _greedy(
    order: OrderCtx, vehicles: tuple[VehicleCtx, ...], line_order: list[int]
) -> list[tuple[tuple[int, Decimal], ...]] | None:
    remaining = [ln.qty_base for ln in order.lines]
    loads: list[tuple[tuple[int, Decimal], ...]] = []
    for vehicle in vehicles:
        kg_left, m3_left = vehicle.capacity_kg, vehicle.capacity_m3
        parts: list[tuple[int, Decimal]] = []
        for i in line_order:
            ln, qty = order.lines[i], remaining[i]
            if qty <= 0 or not can_carry(vehicle, ln):
                continue
            w, v = ln.product.weight_kg, ln.product.volume_m3
            fit = min(kg_left / w if w > 0 else qty, m3_left / v if v > 0 else qty, qty)
            take = qty if fit >= qty else fit.quantize(_QTY, rounding=ROUND_FLOOR)
            if take <= 0:
                continue
            parts.append((i + 1, take))
            remaining[i] = qty - take
            kg_left -= take * w
            m3_left -= take * v
        if not parts:
            return None  # xe thừa trong bộ → bộ không tối giản
        loads.append(tuple(sorted(parts)))
    return loads if all(q <= 0 for q in remaining) else None


def split_load(
    order: OrderCtx, vehicle_set: tuple[VehicleCtx, ...]
) -> tuple[tuple[tuple[int, Decimal], ...], ...]:
    """Chia dòng hàng cho các xe theo tải, thể tích và **nhóm/năng lực của từng dòng** (bước 2d): một dòng có
    thể tách qua nhiều xe; `line_no` = vị trí dòng (1-based); làm tròn xuống 0,001.

    Lấp tham lam hai chiều có thể bỏ sót cách xếp hợp lệ, nên thử nhiều thứ tự (hoán vị xe, dòng theo thứ tự
    gốc / nặng-trên-thể-tích giảm / tăng) trước khi kết luận không xếp được (`()`). Kết quả theo thứ tự xe
    của `vehicle_set`; mỗi xe phải chở ít nhất một phần.
    """
    n = len(order.lines)

    def density(i: int) -> Decimal:
        p = order.lines[i].product
        return p.weight_kg / p.volume_m3 if p.volume_m3 > 0 else Decimal(10**9)

    line_orders = [list(range(n)), sorted(range(n), key=density, reverse=True), sorted(range(n), key=density)]
    for perm in islice(permutations(range(len(vehicle_set))), _MAX_ORDERINGS):
        ordered = tuple(vehicle_set[i] for i in perm)
        for line_order in line_orders:
            loads = _greedy(order, ordered, line_order)
            if loads is not None:
                result: list[tuple[tuple[int, Decimal], ...]] = [()] * len(vehicle_set)
                for pos, idx in enumerate(perm):
                    result[idx] = loads[pos]
                return tuple(result)
    return ()


def _load_of(order: OrderCtx, parts: tuple[tuple[int, Decimal], ...]) -> tuple[Decimal, Decimal]:
    kg = sum((qty * order.lines[no - 1].product.weight_kg for no, qty in parts), Decimal(0))
    m3 = sum((qty * order.lines[no - 1].product.volume_m3 for no, qty in parts), Decimal(0))
    return kg, m3


def _check(name: CheckNameT, code: str, message: str, **detail: object) -> CheckResult:
    return CheckResult(name, code.endswith("_OK"), code, {"message": message, **detail})


def place_loading(wh: WarehouseCtx, earliest: datetime, minutes: int) -> datetime | None:
    """Giờ bắt đầu lên hàng sớm nhất ≥ `earliest` sao cho [t, t+minutes] nằm TRỌN trong một ca kho chính
    thức có người (`loading_windows`) và t ≤ `cutoff` của ngày đó (bước 2c, 04 mục 6.7). None = không có."""
    length = timedelta(minutes=minutes)
    for w_start, w_end in sorted(wh.loading_windows):
        start = max(earliest, w_start)
        while start + length <= w_end:
            if start <= datetime.combine(start.date(), wh.cutoff, tzinfo=start.tzinfo):
                return start
            # quá giờ cắt của ngày này: thử phần sau nửa đêm của cùng ca (ca qua đêm)
            start = datetime.combine(start.date() + timedelta(days=1), time.min, tzinfo=start.tzinfo)
    return None


def plan_delivery(
    order: OrderCtx,
    wh: WarehouseCtx,
    vehicle_set: tuple[VehicleCtx, ...],
    goods_ready_at: datetime,
    cfg: EngineConfig,
) -> tuple[DeliveryOption | None, tuple[CheckResult, ...]]:
    """Xếp giờ cho một bộ xe (bước 2c–2f, v1.2; 04 mục 6.7) và trả check truck → site_date → safety.

    - Lên hàng lần lượt, không trước `goods_ready_at`; mỗi xe lên hàng trọn trong một **ca kho chính thức có
      người** và trước `cutoff` (không có → NO_WAREHOUSE_SHIFT, check preparation).
    - Mọi xe tới CÙNG một ETA (xe xong sớm chờ xuất phát); ETA phương án = xe tới cuối.
    - Có xe lên hàng trước ngày giao → xếp lại lên hàng muộn nhất (xe cuối xong đúng giờ xuất phát), trong ca
      kho chính thức, không chờ qua đêm.
    - Xe đụng lịch bận → dời lên hàng tới hết khoảng bận (tối đa 10 lần, rồi TRUCK_BUSY; hết ngày cho phép
      sau khi đã dời cũng là TRUCK_BUSY).
    - Khoảng làm việc của tài xế = [loading_start, trip_end] của xe (gồm chờ, chạy, dỡ, quay về), phải nằm
      trọn trong ca thực tế của tài xế; ghép tài xế–xe bằng quay lui (assign_drivers).
    Hàm thuần.
    """
    loads = split_load(order, vehicle_set)
    if not loads:
        reason = (
            "capability"
            if any(not any(can_carry(v, ln) for v in vehicle_set) for ln in order.lines)
            else ("combined_capacity")
        )
        return None, (
            _check("truck", "NO_TRUCK_FIT", "Load cannot be placed on this vehicle set.", reason=reason),
        )
    no_shift = (
        _check("preparation", "NO_WAREHOUSE_SHIFT", "No official staffed warehouse shift for loading."),
    )
    if not wh.loading_windows:
        return None, no_shift
    if wh.route is None:
        return None, (
            _check("truck", "TRUCK_OK", "Vehicles fit the load."),
            _check("site_date", "ROUTE_DATA_UNAVAILABLE", "No route data for this warehouse."),
        )

    unknown_scope = [v.code for v in vehicle_set if v.regulation_561 is None]
    driving_min = 2 * wh.route.drive_min  # lái đi + lái về
    rule_failure: CheckResult | None = None
    if unknown_scope:  # Q12b: chưa biết xe có thuộc 561/2006 → không khẳng định tuân thủ
        rule_failure = _check("safety", "VEHICLE_SCOPE_UNKNOWN", "Driving-rule scope of vehicle is unknown.",
                              vehicle_codes=unknown_scope)  # fmt: skip
    elif any(v.regulation_561 for v in vehicle_set) and wh.route.drive_min > cfg.driving_break_after_min:
        no_break = "A continuous drive exceeds 4h30; MVP does not schedule in-trip breaks."
        rule_failure = _check("safety", "DRIVING_BREAK_REQUIRED", no_break)

    def busy(message: str) -> tuple[CheckResult, ...]:
        return (_check("truck", "TRUCK_BUSY", message, vehicle_codes=[v.code for v in vehicle_set]),)

    drive = timedelta(minutes=wh.route.drive_min)
    weights = [_load_of(order, parts) for parts in loads]
    load_min = [handling_minutes(kg, cfg.loading_base_min, cfg.loading_min_per_ton) for kg, _ in weights]
    Schedule = tuple[list[datetime], list[datetime], ArrivalResult]

    def schedule(anchor: datetime) -> Schedule | tuple[CheckResult, ...]:
        """Giờ lên hàng/kết thúc chuyến từ mốc `anchor` (≥ goods_ready_at); lỗi → tuple check."""
        min_start = [goods_ready_at] * len(vehicle_set)
        shifted = False
        for attempt in range(MAX_BUSY_SHIFTS + 3):
            starts: list[datetime] = []
            cursor = anchor
            for i in range(len(vehicle_set)):
                start = place_loading(wh, max(cursor, min_start[i]), load_min[i])
                if start is None:
                    return busy("Vehicles stay busy past the staffed shifts.") if shifted else no_shift
                starts.append(start)
                cursor = start + timedelta(minutes=load_min[i])
            ends = [st + timedelta(minutes=m) for st, m in zip(starts, load_min, strict=True)]
            arrival = place_arrival(order, max(e + drive for e in ends), cfg)
            if arrival.code != "DATE_OK" or arrival.eta_at is None or arrival.target_date is None:
                if shifted:
                    return busy("Vehicles stay busy until no delivery day is left.")
                return (
                    _check("truck", "TRUCK_OK", "Vehicles fit the load."),
                    CheckResult("site_date", False, arrival.code, arrival.detail),
                )
            eta = arrival.eta_at
            if eta.date() > starts[0].date():  # có xe lên hàng trước ngày giao (kể cả do qua giờ cắt)
                latest = latest_anchor(eta)  # không chờ qua đêm
                if anchor < latest:
                    anchor = latest
                    continue
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
                return starts, trip_ends, arrival
            if attempt >= MAX_BUSY_SHIFTS:
                break
            shifted = True
            vehicle = vehicle_set[clash]
            min_start[clash] = max(
                b_end
                for b_start, b_end in vehicle.busy
                if b_start < trip_ends[clash] and starts[clash] < b_end
            )
        return busy("Vehicles are busy on this day.")

    def latest_anchor(eta: datetime) -> datetime:
        """Mốc lên hàng muộn nhất để xe cuối xong đúng giờ xuất phát (vẫn ≥ goods_ready_at)."""
        return max(goods_ready_at, eta - drive - timedelta(minutes=sum(load_min)))

    result = schedule(goods_ready_at)
    if not isinstance(result[0], list):
        return None, result
    starts, trip_ends, arrival = result
    if rule_failure is not None:
        return None, (
            _check("truck", "TRUCK_OK", f"{len(vehicle_set)} vehicle(s) fit the load."),
            CheckResult("site_date", True, "DATE_OK", arrival.detail),
            rule_failure,
        )
    drivers, code, reason = assign_drivers(
        wh.drivers, vehicle_set, list(zip(starts, trip_ends, strict=True)), cfg, driving_min
    )
    if drivers is None and arrival.eta_at is not None and latest_anchor(arrival.eta_at) > starts[0]:
        # Bước 2c mặc định lên hàng sớm nhất (giữ dự trữ). Nếu thời gian chờ làm khoảng làm việc của tài xế
        # không vừa ca/giờ, thử lại một lần với lịch lên hàng sát giờ xuất phát trước khi kết luận.
        retry = schedule(latest_anchor(arrival.eta_at))
        if isinstance(retry[0], list):
            r_starts, r_ends, r_arrival = retry
            r_drivers, r_code, r_reason = assign_drivers(
                wh.drivers, vehicle_set, list(zip(r_starts, r_ends, strict=True)), cfg, driving_min
            )
            if r_drivers is not None:
                starts, trip_ends, arrival, drivers = r_starts, r_ends, r_arrival, r_drivers
    assert arrival.eta_at is not None and arrival.target_date is not None
    eta = arrival.eta_at
    truck = _check("truck", "TRUCK_OK", f"{len(vehicle_set)} vehicle(s) fit the load.")
    site = CheckResult("site_date", True, "DATE_OK", arrival.detail)
    if drivers is None:
        if code == "NO_DRIVER":
            return None, (_check("truck", "NO_DRIVER", "No eligible scheduled driver for every vehicle.",
                                 reason=reason),)  # fmt: skip
        return None, (
            truck,
            site,
            _check("safety", code, "Driver shift, hours or licence do not allow this trip."),
        )
    assignments = tuple(
        VehicleAssignment(
            seq=i + 1,
            vehicle_id=vehicle.id,
            vehicle_code=vehicle.code,
            capacity_kg=vehicle.capacity_kg,
            capacity_m3=vehicle.capacity_m3,
            driver_employee_id=drivers[i].employee_id,
            load_kg=weights[i][0],
            load_m3=weights[i][1],
            load_lines=loads[i],
            loading_start_at=starts[i],
            depart_at=eta - drive,
            eta_at=eta,
            trip_end_at=trip_ends[i],
        )
        for i, vehicle in enumerate(vehicle_set)
    )
    option = DeliveryOption(assignments, arrival.target_date, planning_reserve_min(order, eta, cfg))
    return option, (truck, site, _check("safety", "SAFETY_OK", "Drivers and loads are within limits."))
