"""T14 planning service: real PostgreSQL transactions, versioning and hold lifecycle."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.ops import CustomerOrder
from app.engine.types import (
    CheckResult,
    EngineConfig,
    HandlingGroupCtx,
    LineCtx,
    OrderCtx,
    PlanCandidate,
    PlanningResult,
    ProductCtx,
    VehicleAssignment,
)
from app.services import planning_service
from app.services.planning_inputs import PlanningInputs
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
TARGET = date(2026, 11, 10)
D = Decimal


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    clock.set_now(NOW)
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        "UPDATE ops.customer_order SET origin_store_id=2 WHERE id=1",
        "INSERT INTO ops.order_line (order_id,line_no,local_sku,global_product_id,qty_sale,qty_base,"
        "unit_price,line_total) VALUES (1,1,'SKU-1',1,20,20,1,20)",
        "INSERT INTO ops.order_routing (market_id,external_ref,route,reason_code,decided_at,"
        "decided_source_version,decided_by_user_id,decided_by_role) "
        "VALUES (1,'EXT-1','cfo','all_confirmed','2026-11-04T09:00Z',1,1,'dispatcher')",
    )
    try:
        yield empty_db
    finally:
        clock.set_now(None)


def _actor(role: str = "dispatcher", *, store_ids: tuple[int, ...] = (2,)) -> CurrentUser:
    return CurrentUser(id=1, employee_id=1, roles=(role,), market="SE", location_ids=store_ids)


def _run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _config() -> EngineConfig:
    return planning_service.engine_config(
        __import__("app.core.config", fromlist=["MarketConfig"]).MarketConfig(), ()
    )


async def _loader(
    session: AsyncSession, order: CustomerOrder, market: object, *, now: datetime, params: dict[str, object]
) -> PlanningInputs:
    product = ProductCtx(
        1,
        HandlingGroupCtx("N1", "line", D("0"), D("0.075")),
        None,
        (),
        D("1"),
        D("0.01"),
    )
    ctx = OrderCtx(
        id=order.id,
        version=order.version,
        lat=59.0,
        lon=18.0,
        date_mode="exact",
        date_from=TARGET,
        date_to=TARGET,
        window=None,
        lines=(LineCtx(product, D(20)),),
        now=now,
    )
    return PlanningInputs(
        ctx,
        (),
        _config(),
        {
            "order_version": ctx.version,
            "source_version": order.source_version,
            "as_of": now.isoformat(),
        },
    )


def _feasible(
    order: OrderCtx, _warehouses: list[object], cfg: EngineConfig, weights: object
) -> PlanningResult:
    checks = tuple(
        CheckResult(name, True, name.upper() + "_OK", {"message": "verified"})
        for name in ("stock", "preparation", "truck", "site_date", "safety")
    )
    vehicle = VehicleAssignment(
        seq=1,
        vehicle_id=1,
        vehicle_code="V-1",
        capacity_kg=D("8000"),
        capacity_m3=D("30"),
        driver_employee_id=1,
        load_kg=D("20"),
        load_m3=D("0.20"),
        load_lines=((1, D(20)),),
        loading_start_at=datetime(2026, 11, 10, 6, 30, tzinfo=UTC),
        depart_at=datetime(2026, 11, 10, 7, tzinfo=UTC),
        eta_at=datetime(2026, 11, 10, 9, tzinfo=UTC),
        trip_end_at=datetime(2026, 11, 10, 11, tzinfo=UTC),
    )
    candidate = PlanCandidate(
        warehouse_id=1,
        vehicles=(vehicle,),
        target_date=TARGET,
        goods_ready_at=datetime(2026, 11, 10, 6, tzinfo=UTC),
        loading_start_at=vehicle.loading_start_at,
        depart_at=vehicle.depart_at,
        eta_at=vehicle.eta_at,
        trip_end_at=vehicle.trip_end_at,
        distance_km=D("20"),
        drive_min=60,
        prep_hours=D("1.500"),
        capacity_fill=D("0.5"),
        complexity_points=0,
        planning_reserve_min=2880,
        route_provenance="ors",
        checks=checks,
        prep_by_day={TARGET: D("1.500")},
        planned_start_prep=datetime(2026, 11, 10, 5, 0, tzinfo=UTC),
        rank=1,
        reason_codes=("ONLY_FEASIBLE", "STOCK_OK"),
        explanation="One safe feasible option.",
    )
    return PlanningResult("feasible", (candidate,), (), None, None, "safe", 2880, ())


def _infeasible(
    order: OrderCtx, _warehouses: list[object], cfg: EngineConfig, weights: object
) -> PlanningResult:
    return PlanningResult("infeasible", (), (), "truck", None, "infeasible", None, ())


def _request(
    db: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    actor: CurrentUser | None = None,
    params: dict[str, object] | None = None,
    feasible: bool = True,
) -> int:
    monkeypatch.setattr(planning_service, "plan_order", _feasible if feasible else _infeasible)
    return _run(
        db,
        lambda s: planning_service.plan(1, actor or _actor(), params, session=s, inputs_loader=_loader),
    )


def test_US_PLN_08_AC1_initial_transaction_persists_plan_vehicle_and_hold(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = _request(db, monkeypatch)
    assert run_id == 1
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
    assert fetch(db, "SELECT run_no,kind,result,reserve_class FROM plan.planning_run")[0] == (
        1,
        "initial",
        "feasible",
        "safe",
    )
    assert fetch(db, "SELECT workload->>'planned_start_prep' FROM plan.fulfilment_plan")[0][0] == (
        "2026-11-10T05:00:00+00:00"
    )
    assert fetch(db, "SELECT count(*) FROM plan.plan_vehicle")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM plan.stock_reservation WHERE status='held'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM plan.prep_reservation WHERE status='held'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM plan.vehicle_reservation WHERE status='held'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_PROPOSED'")[0][0] == 1


def test_US_PLN_08_AC2_double_click_returns_existing_run(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _request(db, monkeypatch) == 1
    assert _request(db, monkeypatch) == 1
    assert fetch(db, "SELECT count(*) FROM plan.planning_run")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM plan.stock_reservation")[0][0] == 1


def test_DEC_HOLD_001_plan_again_same_order_new_run(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _request(db, monkeypatch) == 1
    clock.set_now(NOW + timedelta(minutes=16))
    assert _request(db, monkeypatch, params={"reason_code": "criteria_change"}) == 2
    assert fetch(db, "SELECT count(*) FROM ops.customer_order WHERE id=1")[0][0] == 1
    assert [
        tuple(x)
        for x in fetch(db, "SELECT run_no,kind FROM plan.planning_run WHERE order_id=1 ORDER BY run_no")
    ] == [(1, "initial"), (2, "rerun")]
    assert fetch(db, "SELECT status FROM plan.fulfilment_plan WHERE run_id=1")[0][0] == "superseded"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "released"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=2")[0][0] == "held"
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
    count = fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='CRITERIA_CHANGED_RERUN'")
    assert count[0][0] == 1


def test_US_PLN_08_AC3_infeasible_no_hold(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = _request(db, monkeypatch, feasible=False)
    assert run_id == 1
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "NO_FEASIBLE_DATE"
    assert fetch(db, "SELECT count(*) FROM plan.vehicle_reservation")[0][0] == 0
    assert fetch(db, "SELECT failed_check FROM plan.planning_run WHERE id=1")[0][0] == "truck"


def test_US_PLN_08_AC4_fail_closed_mapping_is_atomic(db: str) -> None:
    with pytest.raises(DomainError) as exc:
        _run(db, lambda s: planning_service.plan(1, _actor(), {}, session=s))
    assert exc.value.code == "PLAN_NOT_APPROVABLE"
    assert fetch(db, "SELECT count(*) FROM plan.planning_run")[0][0] == 0
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "SUBMITTED"


def test_US_APR_05_AC4_sales_store_scope_and_custom_criteria(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(DomainError) as out:
        _request(db, monkeypatch, actor=_actor("sales", store_ids=(999,)))
    assert out.value.code == "NOT_FOUND"
    assert _request(db, monkeypatch, actor=_actor("sales"), params={"target_date": "2026-11-10"}) == 1
    run = _run(db, lambda s: planning_service.get_run(1, _actor("sales"), session=s))
    assert run["plans"][0]["rank"] == 1
    assert run["plans"][0]["warehouse"]["id"] == 1
    assert run["plans"][0]["checks"]["stock"]["passed"] is True
    assert "score" not in run["plans"][0]
    assert "driver_employee_id" not in run["plans"][0]["vehicles"][0]
    assert "rejected_candidates" not in run


def test_US_APR_05_AC4_sales_can_plan_again_and_audit_actor(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _request(db, monkeypatch)
    clock.set_now(NOW + timedelta(minutes=16))
    assert _request(db, monkeypatch, actor=_actor("sales"), params={"reason_code": "criteria_change"}) == 2
    assert fetch(db, "SELECT count(*) FROM ops.customer_order WHERE id=1")[0][0] == 1
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "released"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=2")[0][0] == "held"
    audit = fetch(
        db, "SELECT actor_role, reason_code FROM audit.decision_log " "WHERE action='CRITERIA_CHANGED_RERUN'"
    )[0]
    assert tuple(audit) == ("sales", "criteria_change")
    run = _run(db, lambda s: planning_service.get_run(2, _actor("sales"), session=s))
    assert run["kind"] == "rerun" and run["sales_approvable"] is True


def test_US_PLN_08_AC7_plan_again_reason_required(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _request(db, monkeypatch)
    clock.set_now(NOW + timedelta(minutes=16))
    with pytest.raises(DomainError) as refused:
        _request(db, monkeypatch)
    assert refused.value.code == "REASON_REQUIRED"
    assert fetch(db, "SELECT count(*) FROM plan.planning_run")[0][0] == 1


def test_US_PLN_08_AC8_infeasible_plan_again_requires_reason(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _request(db, monkeypatch, feasible=False)
    with pytest.raises(DomainError) as refused:
        _request(db, monkeypatch, feasible=False)
    assert refused.value.code == "REASON_REQUIRED"
    _request(db, monkeypatch, feasible=False, params={"reason_text": "Try again"})
    assert fetch(db, "SELECT count(*) FROM plan.planning_run WHERE order_id=1")[0][0] == 2


def test_US_APR_04_unheld_replan_suggestion_preserves_approved_resources(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _request(db, monkeypatch)
    execute(
        db,
        "UPDATE plan.fulfilment_plan SET status='approved' WHERE id=1",
        "UPDATE plan.stock_reservation SET status='committed' WHERE run_id=1",
        "UPDATE plan.prep_reservation SET status='committed' WHERE run_id=1",
        "UPDATE plan.vehicle_reservation SET status='committed' WHERE run_id=1",
        "UPDATE ops.customer_order SET status='APPROVED',approved_plan_id=1 WHERE id=1",
    )
    new_run = _run(
        db,
        lambda s: planning_service.suggest_replan(1, "vehicle_issue", session=s, inputs_loader=_loader),
    )
    assert new_run == 2
    assert (
        _run(
            db,
            lambda s: planning_service.suggest_replan(1, "vehicle_issue", session=s, inputs_loader=_loader),
        )
        == 2
    )
    assert fetch(db, "SELECT hold_expires_at FROM plan.planning_run WHERE id=2")[0][0] is None
    assert fetch(db, "SELECT kind FROM plan.planning_run WHERE id=2")[0][0] == "replan_suggestion"
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "APPROVED"
    assert fetch(db, "SELECT status FROM plan.fulfilment_plan WHERE id=1")[0][0] == "approved"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "committed"
    assert fetch(db, "SELECT count(*) FROM plan.stock_reservation WHERE run_id=2")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='REPLAN_SUGGESTED'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='REPLAN_SUGGESTED'")[0][0] == 1
