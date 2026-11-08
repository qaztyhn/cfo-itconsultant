"""T13: exercise the pure planner with verified warehouse and driver fixtures."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from app.engine.planner import plan_order
from app.engine.types import (
    DayCapacity,
    DriverCtx,
    EngineConfig,
    HandlingGroupCtx,
    LineCtx,
    OrderCtx,
    ProductCtx,
    RankWeights,
    RouteInfo,
    ShiftCapacity,
    VehicleCtx,
    WarehouseCtx,
)

D = Decimal
TZ = UTC
DAY = date(2026, 11, 9)


def at(hour: int) -> datetime:
    return datetime.combine(DAY, time(hour), tzinfo=TZ)


def config() -> EngineConfig:
    return EngineConfig(
        working_days=frozenset(range(1, 6)),
        default_receiving_hours=(time(7), time(18)),
        holidays=frozenset(),
        search_days_max=14,
        reserve_safe_days=2,
        eta_round_min=15,
        delivery_share=D("0.9"),
        final_inspection_hours=D("0.5"),
        flag_multiplier_cap=D("2"),
        loading_base_min=20,
        loading_min_per_ton=6,
        unloading_base_min=20,
        unloading_min_per_ton=6,
        driver_max_hours_day=D("9"),
        receiving_lead_days=0,
        max_arrival_spread_min=30,
        w_km=D("0.5"),
        w_fill=D("0.5"),
        dz_km_abs=D("2"),
        dz_km_pct=D("0.05"),
        dz_fill=D("0.05"),
        tie_eps=D("0.001"),
        allow_route_fallback=True,
    )


def order(*, date_to: date = DAY) -> OrderCtx:
    group = HandlingGroupCtx("N3", "pallet", D("0.25"), D("0.15"))
    product = ProductCtx(1, group, D("40"), (), D("20"), D("0.05"))
    return OrderCtx(
        id=123,
        version=1,
        lat=60,
        lon=18,
        date_mode="exact",
        date_from=None,
        date_to=date_to,
        window=(time(7), time(18)),
        lines=(LineCtx(product, D("20")),),
        now=at(6),
    )


def warehouse(
    warehouse_id: int,
    *,
    stock: Decimal | None = None,
    distance: Decimal | None = None,
    driver_shift: bool = True,
) -> WarehouseCtx:
    vehicle = VehicleCtx(
        id=warehouse_id * 10,
        code=f"TR-{warehouse_id}",
        capacity_kg=D("3000"),
        capacity_m3=D("12"),
        capabilities=frozenset(),
        required_licence="B",
        allowed_group_codes=frozenset(),
        busy=(),
        regulation_561=False,
    )
    driver = DriverCtx(
        employee_id=warehouse_id * 10,
        licence_class="C",
        licence_expires_on=DAY + timedelta(days=30),
        available_days=frozenset({DAY}),
        booked_hours_by_day={},
        busy=(),
        shifts=((at(7), at(19)),) if driver_shift else (),
        history_complete=True,
    )
    return WarehouseCtx(
        id=warehouse_id,
        name=f"Warehouse {warehouse_id}",
        cutoff=time(15),
        efficiency=D("1"),
        stock_available={1: stock if stock is not None else D("100")},
        inbound=(),
        capacity={DAY: DayCapacity(DAY, (ShiftCapacity("early", time(7), time(15), 2, D("7")),), D("0"))},
        vehicles=(vehicle,),
        drivers=(driver,),
        route=RouteInfo(distance if distance is not None else D("10"), 30, "ors"),
        loading_windows=((at(7), at(15)),),
    )


def test_US_PLN_06_AC5_five_gates_explanation_and_deterministic_rank() -> None:
    result = plan_order(order(), [warehouse(2), warehouse(1)], config())
    reversed_input = plan_order(order(), [warehouse(1), warehouse(2)], config())
    assert result.result == "feasible"
    assert 1 <= len(result.candidates) <= 3
    assert result.candidates == reversed_input.candidates
    winner = result.candidates[0]
    assert winner.rank == 1
    assert winner.reason_codes[0] in (
        "ONLY_FEASIBLE",
        "LOWEST_SCORE_OF_2",
        "LOWEST_SCORE_OF_3",
    )
    assert tuple(check.name for check in winner.checks) == (
        "stock",
        "preparation",
        "truck",
        "site_date",
        "safety",
    )
    assert all(check.passed for check in winner.checks)
    assert winner.explanation
    assert winner.prep_hours == D("0.825")


def test_US_PLN_07_AC1_stock_short_is_fail_closed() -> None:
    result = plan_order(order(), [warehouse(1, stock=D("0"))], config())
    assert result.result == "infeasible"
    assert result.candidates == ()
    assert result.failed_check == "stock"
    assert result.rejected[0].code == "STOCK_SHORT"
    assert result.earliest_feasible_date is None
    assert result.transfer_suggestions == ()


def test_US_PLN_03_AC3_missing_official_driver_shift_fails_closed() -> None:
    result = plan_order(order(), [warehouse(1, driver_shift=False)], config())
    assert result.result == "infeasible"
    assert result.failed_check in ("truck", "safety")
    assert result.rejected[0].code in ("NO_DRIVER", "OUTSIDE_DRIVER_SHIFT")


def test_US_PLN_07_AC2_never_mutates_customer_promise() -> None:
    request = replace(order(), date_to=DAY - timedelta(days=1))
    result = plan_order(request, [warehouse(1)], config())
    assert result.result == "infeasible"
    assert request.date_to == DAY - timedelta(days=1)
    assert result.earliest_feasible_date is None or result.earliest_feasible_date >= DAY


def test_US_PLN_06_AC2_injected_weights_do_not_mutate_order() -> None:
    request = order()
    warehouses = [warehouse(1, distance=D("10")), warehouse(2, distance=D("40"))]
    before = plan_order(request, warehouses, config())
    after = plan_order(request, warehouses, config(), RankWeights(D("0.8"), D("0.2")))
    assert before.result == after.result == "feasible"
    assert request.version == 1
    assert after.candidates[0].rank == 1


def test_US_PLN_07_AC1_empty_warehouses_are_infeasible() -> None:
    result = plan_order(order(), [], config())
    assert result.result == "infeasible"
    assert result.candidates == ()
    assert result.failed_check is None
