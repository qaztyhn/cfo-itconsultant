"""Bước 2d nhiều xe (04 mục 6.2 v1.2; 08 mục 6.2 "nhiều xe"; 09 bất biến 10; US-PLN-03).

Ít xe nhất, hòa thì xe nhỏ hơn; chia dòng qua nhiều xe; tới cùng lúc (chênh ≤ 30'); thiếu năng lực; kín xe;
mỗi xe một tài xế khác nhau.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.engine.delivery import choose_vehicle_sets, order_load, plan_delivery, split_load
from app.engine.types import DriverCtx, LineCtx, OrderCtx, RouteInfo, VehicleCtx, WarehouseCtx
from tests.unit.engine_factory import CFG, N3, N4, line

TZ = ZoneInfo("Europe/Stockholm")
NOW = datetime(2026, 11, 4, 10, 5, tzinfo=TZ)
THU12, WED18 = date(2026, 11, 12), date(2026, 11, 18)
READY = datetime(2026, 11, 12, 8, 0, tzinfo=TZ)


def at(h: int, m: int = 0, d: date = THU12) -> datetime:
    return datetime.combine(d, time(h, m), tzinfo=TZ)


def order(*lines: LineCtx) -> OrderCtx:
    return OrderCtx(1, 1, 59.0, 18.0, "latest", None, WED18, None, lines, NOW)


Busy = tuple[tuple[datetime, datetime], ...]


def truck(
    vid: int, tons: int, m3: int = 40, *, caps: frozenset[str] = frozenset(), busy: Busy = ()
) -> VehicleCtx:
    return VehicleCtx(vid, f"T{vid}-{tons}t", Decimal(tons * 1000), Decimal(m3), caps, "C", frozenset(), busy)


FRI13, MON16 = date(2026, 11, 13), date(2026, 11, 16)
DAYS = (THU12, FRI13, MON16)


def shifts(start: int = 6, end: int = 20, days: tuple[date, ...] = DAYS) -> Busy:
    return tuple((at(start, d=d), at(end, d=d)) for d in days)


def driver(eid: int, booked: str = "0", licence: str = "C", work: Busy | None = None) -> DriverCtx:
    """Tài xế có ca thực tế 06:00–20:00 các ngày làm việc (lịch chính thức Q12) trừ khi chỉ định khác."""
    return DriverCtx(
        eid, licence, date(2027, 1, 1), frozenset(DAYS), {THU12: Decimal(booked)}, (),  # type: ignore[arg-type]
        shifts() if work is None else work,
    )  # fmt: skip


def warehouse(
    vehicles: tuple[VehicleCtx, ...],
    drivers: tuple[DriverCtx, ...] = (),
    route: bool = True,
    loading: Busy | None = None,
) -> WarehouseCtx:
    return WarehouseCtx(
        id=7,
        name="WH",
        cutoff=time(15, 0),
        efficiency=Decimal(1),
        stock_available={},
        inbound=(),
        capacity={},
        vehicles=vehicles,
        drivers=drivers or (driver(1), driver(2), driver(3)),
        route=RouteInfo(Decimal(42), 60, "fallback") if route else None,
        loading_windows=shifts(6, 22) if loading is None else loading,  # ca kho chính thức có người
    )


BAGS_16T = line(N3, "640", "40")  # 640 bao × 25 kg = 16 000 kg, 12,8 m³


# --- chọn bộ xe ----------


def test_single_vehicle_smallest_that_fits() -> None:
    wh = warehouse((truck(1, 12), truck(2, 8), truck(3, 6)))
    sets = choose_vehicle_sets(order(line(N3, "200", "40")), wh, THU12)  # 5 000 kg
    assert [[v.code for v in s] for s in sets] == [["T3-6t"], ["T2-8t"]]  # hòa số xe → xe nhỏ hơn


def test_fewest_vehicles_then_smaller_total() -> None:
    wh = warehouse((truck(1, 8), truck(2, 8), truck(3, 12), truck(4, 6)))
    sets = choose_vehicle_sets(order(BAGS_16T), wh, THU12)
    assert [[v.code for v in s] for s in sets] == [["T1-8t", "T2-8t"], ["T3-12t", "T4-6t"]]


def test_alternative_set_may_have_one_more_vehicle() -> None:
    wh = warehouse((truck(1, 10), truck(2, 6), truck(3, 4)))
    sets = choose_vehicle_sets(order(BAGS_16T), wh, THU12)
    # chỉ một bộ 2 xe đủ → bộ thay thế là bộ tốt nhất có thêm một xe
    assert [[v.code for v in s] for s in sets] == [["T1-10t", "T2-6t"], ["T1-10t", "T2-6t", "T3-4t"]]
    wh = warehouse((truck(1, 10), truck(2, 4), truck(3, 4)))
    sets = choose_vehicle_sets(order(BAGS_16T), wh, THU12)
    assert [[v.code for v in s] for s in sets] == [["T1-10t", "T2-4t", "T3-4t"]]


def test_volume_also_limits_sets() -> None:
    wh = warehouse((truck(1, 20, m3=10), truck(2, 8, m3=10)))
    sets = choose_vehicle_sets(order(BAGS_16T), wh, THU12)  # 12,8 m³ > 10 m³
    assert [[v.code for v in s] for s in sets] == [["T1-20t", "T2-8t"]]


def test_combined_capacity_insufficient_returns_nothing() -> None:
    assert choose_vehicle_sets(order(BAGS_16T), warehouse((truck(1, 8), truck(2, 6))), THU12) == ()


def test_missing_capability_returns_nothing() -> None:
    gravel = line(N4, "10", "1", weight_kg="1500", volume_m3="1")  # N4 cần xe ben
    assert choose_vehicle_sets(order(gravel), warehouse((truck(1, 20),)), THU12) == ()
    dump = truck(2, 20, caps=frozenset({"dump"}))
    assert choose_vehicle_sets(order(gravel), warehouse((truck(1, 20), dump)), THU12) == ((dump,),)


def test_vehicle_busy_all_day_is_skipped() -> None:
    blocked = truck(1, 20, busy=((at(0), at(0, d=date(2026, 11, 13))),))
    sets = choose_vehicle_sets(order(BAGS_16T), warehouse((blocked, truck(2, 8), truck(3, 8))), THU12)
    assert [[v.code for v in s] for s in sets] == [["T2-8t", "T3-8t"]]


# --- chia hàng ----------


def test_split_one_line_over_two_vehicles() -> None:
    loads = split_load(order(BAGS_16T), (truck(1, 8), truck(2, 8)))
    assert loads == (((1, Decimal(320)),), ((1, Decimal(320)),))


def test_split_keeps_every_line_quantity() -> None:
    o = order(line(N3, "300", "40"), line(N3, "100", "40", product_id=2, weight_kg="50"))  # 7 500 + 5 000 kg
    loads = split_load(o, (truck(1, 8), truck(2, 6)))
    totals: dict[int, Decimal] = {}
    for parts in loads:
        for no, qty in parts:
            totals[no] = totals.get(no, Decimal(0)) + qty
    assert totals == {1: Decimal(300), 2: Decimal(100)}
    assert loads[0] == ((1, Decimal(300)), (2, Decimal(10)))  # xe 1 đầy 8 000 kg


def test_split_tries_other_orderings_before_giving_up() -> None:
    """Review #54 mục 3: lấp tham lam một thứ tự có thể sót; phải thử thứ tự khác trước khi báo không xếp."""
    dense = line(N3, "100", "40", weight_kg="100", volume_m3="0.01")
    bulky = line(N3, "30", "40", product_id=2, weight_kg="1", volume_m3="1")
    small = VehicleCtx(1, "S", Decimal(30), Decimal(30), frozenset(), "C", frozenset(), ())
    big = VehicleCtx(2, "B", Decimal(10030), Decimal(1), frozenset(), "C", frozenset(), ())
    for vehicles in ((big, small), (small, big)):
        loads = split_load(order(dense, bulky), vehicles)
        assert loads, vehicles
        by_code = dict(zip((v.code for v in vehicles), loads, strict=True))
        assert by_code == {"B": ((1, Decimal(100)),), "S": ((2, Decimal(30)),)}


def test_order_load_totals() -> None:
    assert order_load(order(BAGS_16T)) == (Decimal(16000), Decimal("12.80"))


# --- xếp giờ, tài xế, check ----------


def test_two_vehicles_arrive_together_with_distinct_drivers() -> None:
    o = order(BAGS_16T)
    option, checks = plan_delivery(
        o, warehouse((truck(1, 8), truck(2, 8))), (truck(1, 8), truck(2, 8)), READY, CFG
    )
    assert [c.code for c in checks] == ["TRUCK_OK", "DATE_OK", "SAFETY_OK"]
    assert option is not None and option.target_date == THU12
    first, second = option.vehicles
    # lên hàng lần lượt: 20 + 6×8 = 68 phút mỗi xe
    assert (first.loading_start_at, second.loading_start_at) == (at(8), at(9, 8))
    # xe 2 xong 10:16 + 60' lái = 11:16 → làm tròn 11:30; cả hai tới cùng lúc
    assert first.eta_at == second.eta_at == at(11, 30)
    assert first.depart_at == second.depart_at == at(10, 30)  # xe 1 chờ xuất phát để tới cùng lúc
    assert first.trip_end_at == at(11, 30) + timedelta(minutes=68 + 60)
    assert {first.driver_employee_id, second.driver_employee_id} == {1, 2}
    assert (first.load_lines, first.load_kg) == (((1, Decimal(320)),), Decimal(8000))
    assert option.planning_reserve_min > 0


def test_busy_vehicle_shifts_loading_start() -> None:
    busy = truck(2, 8, busy=((at(9), at(10)),))
    vehicles = (truck(1, 8), busy)
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles), vehicles, READY, CFG)
    assert option is not None, checks
    assert option.vehicles[1].loading_start_at == at(10)  # dời tới hết khoảng bận
    assert option.vehicles[0].eta_at == option.vehicles[1].eta_at


def test_busy_vehicle_can_move_delivery_to_a_later_allowed_day() -> None:
    """Bận dày đặc cả ngày 12/11 nhưng đơn `latest` còn ngày khác → phương án chuyển sang ngày sau."""
    slots = tuple((at(8) + timedelta(hours=k), at(8) + timedelta(hours=k, minutes=59)) for k in range(72))
    vehicles = (truck(1, 8), truck(2, 8, busy=slots))
    option, _ = plan_delivery(order(BAGS_16T), warehouse(vehicles), vehicles, READY, CFG)
    assert option is not None and option.target_date > THU12


def test_vehicle_busy_too_often_is_truck_busy() -> None:
    # bận gần như liên tục tới hết các ngày cho phép: dời mãi không còn ngày → TRUCK_BUSY, không phải lỗi ngày
    slots = tuple(
        (at(8) + timedelta(minutes=121 * k), at(8) + timedelta(minutes=121 * k + 120)) for k in range(80)
    )
    vehicles = (truck(1, 8), truck(2, 8, busy=slots))
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles), vehicles, READY, CFG)
    assert option is None and checks[0].code == "TRUCK_BUSY" and not checks[0].passed


def test_one_driver_for_two_vehicles_is_no_driver() -> None:
    vehicles = (truck(1, 8), truck(2, 8))
    wh = warehouse(vehicles, (driver(1),))
    option, checks = plan_delivery(order(BAGS_16T), wh, vehicles, READY, CFG)
    assert option is None and [c.code for c in checks] == ["NO_DRIVER"]


def test_driver_hours_fail_safety_check() -> None:
    vehicles = (truck(1, 8), truck(2, 8))
    drivers = (driver(1), driver(2, booked="8"))
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles, drivers), vehicles, READY, CFG)
    assert option is None
    assert [(c.name, c.code) for c in checks] == [
        ("truck", "TRUCK_OK"),
        ("site_date", "DATE_OK"),
        ("safety", "DRIVER_HOURS_EXCEEDED"),
    ]


def test_next_day_delivery_loads_inside_the_delivery_days_warehouse_shift() -> None:
    """Review #54 mục 1/5: không lên hàng 03:44 khi không có ca; xe 2 qua giờ cắt 15:00 → cả hai lên hàng
    trong ca kho 06:00 của ngày giao, không xe/tài xế nào chờ qua đêm."""
    late = datetime(2026, 11, 12, 14, 0, tzinfo=TZ)
    vehicles = (truck(1, 8), truck(2, 8))
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles), vehicles, late, CFG)
    assert option is not None, checks
    first, second = option.vehicles
    assert (first.loading_start_at, second.loading_start_at) == (at(6, d=FRI13), at(7, 8, d=FRI13))
    assert first.eta_at == second.eta_at == at(9, 30, d=FRI13)
    assert option.target_date == FRI13


def test_no_official_warehouse_shift_means_no_plan() -> None:
    vehicles = (truck(1, 20),)
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles, loading=()), vehicles, READY, CFG)
    assert option is None and [(c.name, c.code) for c in checks] == [("preparation", "NO_WAREHOUSE_SHIFT")]


def test_loading_waits_for_the_staffed_shift() -> None:
    early = datetime(2026, 11, 12, 4, 0, tzinfo=TZ)  # hàng sẵn 04:00 nhưng ca kho bắt đầu 06:00
    vehicles = (truck(1, 20),)
    option, _ = plan_delivery(order(BAGS_16T), warehouse(vehicles), vehicles, early, CFG)
    assert option is not None and option.vehicles[0].loading_start_at == at(6)


def test_goods_ready_after_cutoff_loads_next_working_day() -> None:
    after_cutoff = datetime(2026, 11, 12, 15, 30, tzinfo=TZ)
    vehicles = (truck(1, 20),)
    option, _ = plan_delivery(order(BAGS_16T), warehouse(vehicles), vehicles, after_cutoff, CFG)
    assert option is not None and option.vehicles[0].loading_start_at == at(6, d=FRI13)


def test_driver_without_schedule_is_not_available() -> None:
    vehicles = (truck(1, 20),)
    wh = warehouse(vehicles, (driver(1, work=()),))
    option, checks = plan_delivery(order(BAGS_16T), wh, vehicles, READY, CFG)
    assert option is None and checks[0].code == "NO_DRIVER" and checks[0].detail["reason"] == "no_schedule"


def test_duty_must_fit_inside_the_drivers_shift() -> None:
    vehicles = (truck(1, 20),)
    short = driver(1, work=shifts(6, 10))  # chuyến 08:00 → 12:xx vượt ca 06–10
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles, (short,)), vehicles, READY, CFG)
    assert option is None and checks[-1].code == "OUTSIDE_DRIVER_SHIFT" and checks[-1].name == "safety"
    option, _ = plan_delivery(order(BAGS_16T), warehouse(vehicles, (short, driver(2))), vehicles, READY, CFG)
    assert option is not None and option.vehicles[0].driver_employee_id == 2


def test_overnight_driver_shift_is_honoured() -> None:
    """Ca qua nửa đêm: tài xế làm 23:00 thứ Năm → 10:00 thứ Sáu phủ được chuyến lên hàng sau nửa đêm."""
    night = datetime(2026, 11, 12, 22, 0, tzinfo=TZ)
    vehicles = (truck(1, 20),)
    overnight = ((at(22), at(6, d=FRI13)),)  # ca kho đêm
    night_driver = driver(5, work=((at(23), at(10, d=FRI13)),))
    wh = warehouse(vehicles, (night_driver,), loading=overnight)
    option, checks = plan_delivery(order(BAGS_16T), wh, vehicles, night, CFG)
    assert option is not None, checks
    assignment = option.vehicles[0]
    # 116' lên hàng xong đúng 06:00 xuất phát (hết ca kho đêm), tới 07:00 khi mở cửa sổ nhận hàng
    assert assignment.loading_start_at == at(4, 4, d=FRI13) and assignment.eta_at == at(7, d=FRI13)
    assert assignment.depart_at == at(6, d=FRI13)
    assert assignment.driver_employee_id == 5


def test_driver_matching_is_not_greedy() -> None:
    """Review #54 mục 2: xe 1 cần bằng B, xe 2 cần C; tài xế 1 hạng C, tài xế 2 hạng B → phải ghép 1→xe 2."""
    b_van = VehicleCtx(1, "B1", Decimal(3500), Decimal(20), frozenset(), "B", frozenset(), ())
    c_truck = VehicleCtx(2, "C2", Decimal(14000), Decimal(40), frozenset(), "C", frozenset(), ())
    wh = warehouse((b_van, c_truck), (driver(1, licence="C"), driver(2, licence="B")))
    option, checks = plan_delivery(order(BAGS_16T), wh, (b_van, c_truck), READY, CFG)
    assert option is not None, checks
    assert [a.driver_employee_id for a in option.vehicles] == [2, 1]


def test_vehicle_groups_apply_to_lines_it_carries() -> None:
    """Review #54 mục 4: xe ben chỉ chở N4, xe sàn chỉ chở N3 → bộ hai xe hợp lệ, mỗi xe chở dòng của nó."""
    gravel = line(N4, "4", "1", product_id=2, weight_kg="1500", volume_m3="1")  # cần xe ben
    bags = line(N3, "200", "40")
    dump = VehicleCtx(1, "DUMP", Decimal(8000), Decimal(10), frozenset({"dump"}), "C", frozenset({"N4"}), ())
    flat = VehicleCtx(2, "FLAT", Decimal(8000), Decimal(40), frozenset(), "C", frozenset({"N3"}), ())
    o = order(bags, gravel)
    sets = choose_vehicle_sets(o, warehouse((dump, flat)), THU12)
    assert sets == ((dump, flat),)
    assert split_load(o, (dump, flat)) == (((2, Decimal(4)),), ((1, Decimal(200)),))
    assert choose_vehicle_sets(o, warehouse((flat,)), THU12) == ()  # không xe nào chở được sỏi


def test_missing_route_fails_site_date() -> None:
    vehicles = (truck(1, 20),)
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles, route=False), vehicles, READY, CFG)
    assert option is None and [c.code for c in checks] == ["TRUCK_OK", "ROUTE_DATA_UNAVAILABLE"]


def test_set_that_cannot_hold_the_load_is_no_truck_fit() -> None:
    vehicles = (truck(1, 8),)
    option, checks = plan_delivery(order(BAGS_16T), warehouse(vehicles), vehicles, READY, CFG)
    assert option is None and checks[0].code == "NO_TRUCK_FIT"
    assert checks[0].detail["reason"] == "combined_capacity"
