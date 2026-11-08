"""T15: PostgreSQL reservation lifecycle, expiry and exclusion tests."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.plan import FulfilmentPlan
from app.services import reservation_service as reservation
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration


def _route(no: int) -> str:
    return (
        "INSERT INTO ops.order_routing (market_id, external_ref, route, reason_code, decided_at, "
        "decided_source_version, decided_by_user_id, decided_by_role) "
        f"VALUES (1, 'EXT-{no}', 'cfo', 'all_confirmed', '2026-11-04T09:00Z', 1, 1, 'dispatcher')"
    )


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        rows.order_sql(2),
        _route(1),
        _route(2),
        "INSERT INTO ops.order_line (order_id, line_no, local_sku, global_product_id, qty_sale, "
        "qty_base, unit_price, line_total) VALUES (1, 1, 'SKU-1', 1, 20, 20, 1, 20), "
        "(2, 1, 'SKU-1', 1, 20, 20, 1, 20)",
        rows.run_sql(1, 1),
        rows.run_sql(2, 1),
        rows.plan_sql(1, 1, 1),
        rows.plan_sql(1, 1, 2),
        rows.plan_vehicle_sql(1, 1, 1, 1),
        rows.plan_vehicle_sql(2, 1, 2, 2),
        "UPDATE plan.fulfilment_plan SET workload = "
        """'{"prep_by_day":{"2026-11-10":"1.500"}}'::jsonb WHERE id = 1""",
        "UPDATE plan.fulfilment_plan SET workload = "
        """'{"prep_by_day":{"2026-11-10":"1.000","2026-11-11":"0.500"}}'::jsonb WHERE id = 2""",
    )
    yield empty_db


def _run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _rows(db: str, table: str, columns: str) -> list[tuple[Any, ...]]:
    return [
        tuple(r)
        for r in fetch(db, f"SELECT {columns} FROM plan.{table} ORDER BY id")
    ]


def _actor(role: str = "dispatcher", locations: tuple[int, ...] = (1,)) -> CurrentUser:
    return CurrentUser(id=1, employee_id=1, roles=(role,), market="ZZ", location_ids=locations)


def test_US_RES_01_AC1_hold_three_alternatives_once_and_idempotent(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))
    _run(db, lambda s: reservation.hold(1, session=s))
    stock = _rows(db, "stock_reservation", "warehouse_id, global_product_id, qty, status")
    prep = _rows(db, "prep_reservation", "warehouse_id, work_date, hours, status")
    vehicles = _rows(db, "vehicle_reservation", "plan_id, vehicle_id, driver_employee_id, status")
    assert stock == [(1, 1, Decimal("20.000"), "held")]
    assert prep == [
        (1, date(2026, 11, 10), Decimal("1.500"), "held"),
        (1, date(2026, 11, 11), Decimal("0.500"), "held"),
    ]
    assert len(vehicles) == 2 and {v[-1] for v in vehicles} == {"held"}
    assert len(fetch(db, "SELECT id FROM audit.decision_log WHERE action='RESERVATION_HELD'")) == 1


def test_US_RES_01_AC3_extend_max_two_and_no_third(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))
    initial = fetch(db, "SELECT hold_expires_at FROM plan.planning_run WHERE id=1")[0][0]
    _run(db, lambda s: reservation.extend(1, _actor(), session=s))
    _run(db, lambda s: reservation.extend(1, _actor(), session=s))
    with pytest.raises(DomainError) as caught:
        _run(db, lambda s: reservation.extend(1, _actor(), session=s))
    assert caught.value.code == "HOLD_EXTENSION_LIMIT"
    expiration, count = fetch(
        db, "SELECT hold_expires_at, hold_extensions FROM plan.planning_run WHERE id=1"
    )[0]
    assert expiration - initial == timedelta(minutes=30)
    assert count == 2
    assert len(fetch(db, "SELECT id FROM audit.decision_log WHERE action='HOLD_EXTENDED'")) == 2


def test_US_RES_01_AC4_expire_is_idempotent(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))
    clock.set_now(clock.now() + timedelta(minutes=16))
    assert _run(db, lambda s: reservation.expire_due(session=s)) == 1
    assert _run(db, lambda s: reservation.expire_due(session=s)) == 0
    for name in ("stock_reservation", "prep_reservation", "vehicle_reservation"):
        assert {r[0] for r in _rows(db, name, "status")} == {"expired"}
    assert _rows(db, "fulfilment_plan", "status") == [("expired",), ("expired",)]
    assert len(fetch(db, "SELECT id FROM audit.decision_log WHERE action='HOLD_EXPIRED'")) == 1


def test_US_RES_01_AC2_other_orders_cannot_hold_same_vehicle(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))
    execute(
        db,
        rows.plan_sql(2, 2, 1),
        rows.plan_vehicle_sql(3, 1, 1, 1),
        "UPDATE plan.fulfilment_plan SET workload = "
        """'{"prep_by_day":{"2026-11-10":"1.500"}}'::jsonb WHERE id=3""",
    )
    with pytest.raises(IntegrityError):
        _run(db, lambda s: reservation.hold(2, session=s))
    assert fetch(db, "SELECT count(*) FROM plan.vehicle_reservation WHERE run_id=2")[0][0] == 0
    assert fetch(db, "SELECT hold_expires_at FROM plan.planning_run WHERE id=2")[0][0] is None


def test_US_RES_01_AC6_provisional_holds_can_exceed_stock(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))
    execute(
        db,
        "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
        "VALUES (1, 'E3', 'Test', 'Three', 'TEST_POS', '2026-01-01')",
        "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, "
        "capacity_kg, capacity_m3, required_licence) "
        "VALUES (1, 'V-3', 'TST003', 'Truck 3', 8000, 30, 'C')",
        rows.plan_sql(2, 2, 1),
        rows.plan_vehicle_sql(3, 1, 3, 3),
        "UPDATE plan.fulfilment_plan SET workload = "
        """'{"prep_by_day":{"2026-11-10":"1.500"}}'::jsonb WHERE id=3""",
        "INSERT INTO ops.stock_snapshot (warehouse_id, global_product_id, on_hand, wms_reserved, as_of) "
        "VALUES (1,1,1,0,now())",
    )
    _run(db, lambda s: reservation.hold(2, session=s))
    assert fetch(db, "SELECT count(*) FROM plan.stock_reservation WHERE status='held'")[0][0] == 2
    assert fetch(db, "SELECT count(*) FROM plan.prep_reservation WHERE status='held'")[0][0] == 3


def test_US_RES_01_AC4_permissions_and_expired_hold(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))
    with pytest.raises(DomainError) as denied:
        _run(db, lambda s: reservation.extend(1, _actor("customer_service"), session=s))
    assert denied.value.code == "FORBIDDEN"
    with pytest.raises(DomainError) as hidden:
        _run(db, lambda s: reservation.extend(1, _actor("sales", (999,)), session=s))
    assert hidden.value.code == "NOT_FOUND"
    clock.set_now(clock.now() + timedelta(minutes=16))
    with pytest.raises(DomainError) as expired:
        _run(db, lambda s: reservation.extend(1, _actor(), session=s))
    assert expired.value.code == "HOLD_EXPIRED"


def test_US_RES_01_AC1_commit_selected_and_release_other_options(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))

    async def approve(session: AsyncSession) -> None:
        with pytest.raises(DomainError) as denied:
            await reservation.commit_plan(1, session=session)
        assert denied.value.code == "PLAN_NOT_APPROVABLE"
        plan = await session.get(FulfilmentPlan, 1)
        assert plan is not None
        plan.status = "approved"  # T16 will validate under locks before updating.
        await session.flush()
        await reservation.commit_plan(1, session=session, resources_validated=True)
        await reservation.commit_plan(1, session=session, resources_validated=True)

    _run(db, approve)
    assert {r[-1] for r in _rows(db, "stock_reservation", "status")} == {"committed"}
    assert _rows(db, "prep_reservation", "work_date, hours, status") == [
        (date(2026, 11, 10), Decimal("1.500"), "committed"),
        (date(2026, 11, 11), Decimal("0.500"), "released"),
    ]
    assert [r[-1] for r in _rows(db, "vehicle_reservation", "status")] == ["committed", "released"]
    assert len(fetch(db, "SELECT id FROM audit.decision_log WHERE action='RESERVATION_COMMITTED'")) == 1


def test_US_RES_01_AC4_release_is_idempotent_and_preserves_consumed(db: str) -> None:
    _run(db, lambda s: reservation.hold(1, session=s))
    execute(db, "UPDATE plan.stock_reservation SET status='consumed' WHERE order_id=1")
    _run(db, lambda s: reservation.release_order(1, session=s))
    _run(db, lambda s: reservation.release_order(1, session=s))
    assert {r[0] for r in _rows(db, "stock_reservation", "status")} == {"consumed"}
    assert {r[0] for r in _rows(db, "prep_reservation", "status")} == {"released"}
    assert {r[0] for r in _rows(db, "vehicle_reservation", "status")} == {"released"}
    assert len(fetch(db, "SELECT id FROM audit.decision_log WHERE action='RESERVATION_RELEASED'")) == 1


def test_US_RES_01_AC4_replan_suggestion_does_not_hold(db: str) -> None:
    execute(db, "UPDATE plan.planning_run SET kind='replan_suggestion' WHERE id=1")
    with pytest.raises(DomainError) as denied:
        _run(db, lambda s: reservation.hold(1, session=s))
    assert denied.value.code == "PLAN_NOT_APPROVABLE"
    assert fetch(db, "SELECT count(*) FROM plan.stock_reservation")[0][0] == 0
