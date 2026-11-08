"""T16: real-PostgreSQL approval transaction and concurrency regression tests."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.services import approval_service, reservation_service
from app.services.approval_service import RecheckProof
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
GATES = '{"stock":{"passed":true},"preparation":{"passed":true},"truck":{"passed":true},' \
        '"site_date":{"passed":true},"safety":{"passed":true}}'


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    clock.set_now(NOW)
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        "UPDATE ops.customer_order SET origin_store_id=2 WHERE id=1",
        "INSERT INTO ops.order_routing (market_id, external_ref, route, reason_code, decided_at, "
        "decided_source_version, decided_by_user_id, decided_by_role) "
        "VALUES (1,'EXT-1','cfo','all_confirmed','2026-11-04T09:00Z',1,1,'dispatcher')",
        "INSERT INTO ops.order_line (order_id,line_no,local_sku,global_product_id,qty_sale,qty_base,"
        "unit_price,line_total) VALUES (1,1,'SKU1',1,20,20,1,20)",
        "INSERT INTO ops.stock_snapshot (warehouse_id,global_product_id,on_hand,wms_reserved,as_of) "
        "VALUES (1,1,40,0,'2026-11-04T09:05Z')",
        "INSERT INTO hr.warehouse_staff (employee_id,role,counts_in_capacity) "
        "VALUES (1,'operator',true)",
        "INSERT INTO hr.driver_staff (employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES (1,1,'C','2027-01-01')",
        "INSERT INTO hr.shift_template "
        "(warehouse_id,weekday,start_time,end_time,useful_hours_per_staff,expected_staff) "
        "VALUES (1,2,'06:00','16:00',7,1)",
        "INSERT INTO hr.employee_shift_schedule "
        "(employee_id,warehouse_id,work_date,shift_template_id,status,assigned_by,assigned_at) "
        "VALUES (1,1,'2026-11-10',1,'scheduled',1,'2026-11-04T08:00Z')",
        "INSERT INTO hr.attendance (employee_id,work_date,shift_template_id,status) "
        "VALUES (1,'2026-11-10',1,'planned')",
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1),
        rows.plan_vehicle_sql(1, 1, 1, 1),
        "UPDATE plan.fulfilment_plan SET workload = "
        """'{"prep_by_day":{"2026-11-10":"1.500"}}'::jsonb""",
        f"UPDATE plan.fulfilment_plan SET checks='{GATES}'::jsonb WHERE id=1",
        "UPDATE plan.planning_run SET reserve_class='safe' WHERE id=1",
    )
    try:
        yield empty_db
    finally:
        clock.set_now(None)


def _actor(role: str = "dispatcher", locations: tuple[int, ...] = (2,)) -> CurrentUser:
    return CurrentUser(id=1, employee_id=1, roles=(role,), market="SE", location_ids=locations)


def _run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


async def _recheck(session: AsyncSession, plan_id: int) -> RecheckProof:
    """Deterministic trusted adapter fixture; T14 supplies the real engine recheck."""
    return RecheckProof(
        plan_id=plan_id,
        order_version=1,
        source_version=1,
        gates={name: True for name in ("stock", "preparation", "truck", "site_date", "safety")},
        checked_at=clock.now(),
    )


def _hold(db: str, run_id: int = 1) -> None:
    _run(db, lambda s: reservation_service.hold(run_id, session=s))
    execute(db, f"UPDATE ops.customer_order SET status='PLANNED' WHERE id={run_id}")


def test_US_APR_01_AC1_commit_selected_and_idempotency(db: str) -> None:
    _hold(db)

    async def approve(session: AsyncSession) -> dict[str, object]:
        return await approval_service.approve(
            1, _actor(), {}, "approval-once", session=session, recheck=_recheck
        )

    first = _run(db, approve)
    again = _run(db, approve)
    assert first == again
    assert first["order"]["status"] == "APPROVED"
    assert first["trip_ids"] and len(first["trip_ids"]) == 1
    assert fetch(db, "SELECT approved_plan_id FROM ops.customer_order WHERE id=1")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 1
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "committed"


def test_US_APR_01_AC2_changed_request_reusing_key_conflicts(db: str) -> None:
    _hold(db)
    _run(
        db,
        lambda s: approval_service.approve(
            1, _actor(), {}, "same-key", session=s, recheck=_recheck
        ),
    )
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {"note": "changed"}, "same-key", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "IDEMPOTENCY_CONFLICT"


def test_DEC_HOLD_001_reject_expired_even_before_sweeper(db: str) -> None:
    _hold(db)
    clock.set_now(NOW + timedelta(minutes=16))
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "expired", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "HOLD_EXPIRED"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0


def test_US_APR_01_AC3_missing_recheck_fails_closed(db: str) -> None:
    _hold(db)
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(1, _actor(), {}, "no-recheck", session=s),
        )
    assert got.value.code == "PLAN_NOT_APPROVABLE"
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 0


def test_US_APR_01_AC4_sales_rank_one_verified(db: str) -> None:
    _hold(db)
    result = _run(
        db,
        lambda s: approval_service.approve(
            1, _actor("sales"), {}, "sales-rank1", session=s, recheck=_recheck
        ),
    )
    assert result["plan"]["rank"] == 1
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "APPROVED"


def test_US_APR_01_AC4_sales_wrong_store_hidden(db: str) -> None:
    _hold(db)
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor("sales", (999,)), {}, "wrong-store", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "NOT_FOUND"


def test_US_APR_01_AC4_sales_not_safe_rejected(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE plan.planning_run SET reserve_class='tight' WHERE id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor("sales"), {}, "sales-tight", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "PLAN_NOT_APPROVABLE"


def test_US_APR_01_AC5_stock_conflict_rolls_back(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE ops.stock_snapshot SET on_hand=1 WHERE warehouse_id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "stock-too-low", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "RESOURCE_CONFLICT"
    assert got.value.details["conflict"] == "stock"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "held"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0


def test_US_APR_01_AC5_labour_conflict_rolls_back(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE plan.prep_reservation SET hours=20 WHERE run_id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "labour-too-low", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "RESOURCE_CONFLICT"
    assert got.value.details["conflict"] == "labour"


def test_US_APR_01_AC4_no_driver_swap_without_replan(db: str) -> None:
    _hold(db)
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1,
                _actor(),
                {"drivers": [{"seq": 1, "driver_employee_id": 2}]},
                "driver-swap",
                session=s,
                recheck=_recheck,
            ),
        )
    assert got.value.code == "PLAN_NOT_APPROVABLE"


def test_US_APR_01_AC6_negotiated_date_required(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE plan.fulfilment_plan SET target_date='2026-11-11' WHERE id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "date-without-agreement", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "DATE_AGREEMENT_REQUIRED"


def test_US_APR_01_AC7_invalid_role_forbidden(db: str) -> None:
    _hold(db)
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor("customer_service"), {}, "role-no", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "FORBIDDEN"


def test_US_APR_01_AC8_source_version_mismatch_denied(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE ops.customer_order SET source_version=3 WHERE id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "stale-source", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "RESOURCE_CONFLICT"


def test_US_APR_01_AC9_no_active_hold_denied(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE plan.vehicle_reservation SET status='released' WHERE run_id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "missing-hold", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "PLAN_NOT_APPROVABLE"
