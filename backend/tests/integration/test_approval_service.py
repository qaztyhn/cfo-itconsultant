"""T16: real-PostgreSQL approval transaction and concurrency regression tests."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.plan import StockReservation
from app.domain.models.ref import Market
from app.services import approval_service, reservation_service
from app.services.approval_service import RecheckProof
from app.services.notification_delivery import deliver_queued
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
GATES = (
    '{"stock":{"passed":true},"preparation":{"passed":true},"truck":{"passed":true},'
    '"site_date":{"passed":true},"safety":{"passed":true}}'
)


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
        "INSERT INTO hr.warehouse_staff (employee_id,role,counts_in_capacity) " "VALUES (1,'operator',true)",
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
        "UPDATE plan.fulfilment_plan SET workload = " """'{"prep_by_day":{"2026-11-10":"1.500"}}'::jsonb""",
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
        lambda s: approval_service.approve(1, _actor(), {}, "same-key", session=s, recheck=_recheck),
    )
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1,
                _actor(),
                {"note": "changed"},
                "same-key",
                session=s,
                recheck=_recheck,
            ),
        )
    assert got.value.code == "IDEMPOTENCY_CONFLICT"


def test_DEC_HOLD_001_reject_expired_even_before_sweeper(db: str) -> None:
    _hold(db)
    clock.set_now(NOW + timedelta(minutes=16))
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(1, _actor(), {}, "expired", session=s, recheck=_recheck),
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
                1,
                _actor("sales", (999,)),
                {},
                "wrong-store",
                session=s,
                recheck=_recheck,
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
            lambda s: approval_service.approve(1, _actor(), {}, "stock-too-low", session=s, recheck=_recheck),
        )
    assert got.value.code == "RESOURCE_CONFLICT"
    assert got.value.details["conflict"] == "stock"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "held"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0


def test_US_APR_01_AC5_exact_stock_after_own_wms_reserve(db: str) -> None:
    _hold(db)
    execute(
        db,
        "UPDATE ops.stock_snapshot SET on_hand=20, wms_reserved=20 WHERE warehouse_id=1",
    )

    async def check(session: AsyncSession) -> None:
        market = await session.get(Market, 1)
        held = (await session.scalars(select(StockReservation).where(StockReservation.run_id == 1))).all()
        assert market is not None and len(held) == 1
        await approval_service._stock_available(
            session,
            held,
            1,
            clock.now(),
            MarketConfig.model_validate(market.config),
            sales=False,
            wms_self_reserved=True,
        )
        with pytest.raises(DomainError) as got:
            await approval_service._stock_available(
                session,
                held,
                1,
                clock.now(),
                MarketConfig.model_validate(market.config),
                sales=False,
            )
        assert got.value.code == "RESOURCE_CONFLICT"

    _run(db, check)


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
                1,
                _actor("customer_service"),
                {},
                "role-no",
                session=s,
                recheck=_recheck,
            ),
        )
    assert got.value.code == "FORBIDDEN"


def test_US_APR_01_AC8_source_version_mismatch_denied(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE ops.customer_order SET source_version=3 WHERE id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(1, _actor(), {}, "stale-source", session=s, recheck=_recheck),
        )
    assert got.value.code == "RESOURCE_CONFLICT"


def test_US_APR_01_AC9_no_active_hold_denied(db: str) -> None:
    _hold(db)
    execute(db, "UPDATE plan.vehicle_reservation SET status='released' WHERE run_id=1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(1, _actor(), {}, "missing-hold", session=s, recheck=_recheck),
        )
    assert got.value.code == "PLAN_NOT_APPROVABLE"


def _second_order(db: str, *, stock: int = 30, hours: str = "1.500") -> None:
    """Two orders hold the same warehouse stock/labour with different trucks and drivers."""
    execute(
        db,
        rows.order_sql(2),
        "UPDATE ops.customer_order SET origin_store_id=2 WHERE id=2",
        "INSERT INTO ops.order_routing (market_id,external_ref,route,reason_code,decided_at,"
        "decided_source_version,decided_by_user_id,decided_by_role) "
        "VALUES (1,'EXT-2','cfo','all_confirmed','2026-11-04T09:00Z',1,1,'dispatcher')",
        "INSERT INTO ops.order_line (order_id,line_no,local_sku,global_product_id,qty_sale,qty_base,"
        "unit_price,line_total) VALUES (2,1,'SKU1',1,20,20,1,20)",
        "INSERT INTO hr.driver_staff (employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES (2,1,'C','2027-01-01')",
        rows.run_sql(2, 1),
        rows.plan_sql(2, 2, 1),
        rows.plan_vehicle_sql(2, 1, 2, 2),
        "UPDATE plan.fulfilment_plan SET workload="
        f"""'{{"prep_by_day":{{"2026-11-10":"{hours}"}}}}'::jsonb WHERE id=2""",
        f"UPDATE plan.fulfilment_plan SET checks='{GATES}'::jsonb WHERE id=2",
        "UPDATE plan.fulfilment_plan SET workload="
        f"""'{{"prep_by_day":{{"2026-11-10":"{hours}"}}}}'::jsonb WHERE id=1""",
        f"UPDATE ops.stock_snapshot SET on_hand={stock} WHERE warehouse_id=1 AND global_product_id=1",
    )
    _run(db, lambda s: reservation_service.hold(2, session=s))
    execute(db, "UPDATE ops.customer_order SET status='PLANNED' WHERE id=2")


def _parallel_approve(db: str) -> tuple[list[int], list[str]]:
    async def go() -> tuple[list[int], list[str]]:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        successes: list[int] = []
        failures: list[str] = []

        async def one(plan_id: int) -> None:
            async with async_sessionmaker(engine)() as session:
                try:
                    async with session.begin():
                        await approval_service.approve(
                            plan_id,
                            _actor(),
                            {},
                            f"race-{plan_id}",
                            session=session,
                            recheck=_recheck,
                        )
                    successes.append(plan_id)
                except DomainError as exc:
                    failures.append(exc.code)

        try:
            await asyncio.gather(one(1), one(2))
        finally:
            await engine.dispose()
        return successes, failures

    return asyncio.run(go())


def test_US_APR_01_AC10_concurrent_stock_approval_single_winner(db: str) -> None:
    _hold(db)
    _second_order(db, stock=30)
    winners, failures = _parallel_approve(db)
    assert len(winners) == 1
    assert failures == ["RESOURCE_CONFLICT"]
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.customer_order WHERE status='APPROVED'")[0][0] == 1


def test_US_APR_01_AC11_concurrent_labour_approval_single_winner(db: str) -> None:
    _hold(db)
    _second_order(db, stock=100, hours="4.000")
    execute(
        db,
        "UPDATE plan.prep_reservation SET hours=4.000 WHERE order_id IN (1,2)",
    )
    winners, failures = _parallel_approve(db)
    assert len(winners) == 1
    assert failures == ["RESOURCE_CONFLICT"]
    assert fetch(db, "SELECT count(*) FROM plan.prep_reservation WHERE status='committed'")[0][0] == 1


def test_T28_concurrent_identical_approval_keys_create_exactly_one_trip(
    db: str,
) -> None:
    """Two real transactions replay one committed result, never double-approve."""
    _hold(db)

    async def race() -> tuple[dict[str, object], dict[str, object]]:
        engine = create_async_engine(async_url(db), poolclass=NullPool)

        async def submit() -> dict[str, object]:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await approval_service.approve(
                    1, _actor(), {}, "t28-same-key", session=session, recheck=_recheck
                )

        try:
            first, second = await asyncio.wait_for(asyncio.gather(submit(), submit()), timeout=20)
            return first, second
        finally:
            await engine.dispose()

    first, second = asyncio.run(race())
    assert first == second
    assert first["order"]["status"] == "APPROVED"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.trip_stop")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 1


def test_T28_idempotent_approval_replay_does_not_bypass_revoked_role(db: str) -> None:
    """Even an already successful request cannot be replayed by a downgraded actor."""
    _hold(db)
    original = _run(
        db,
        lambda s: approval_service.approve(1, _actor(), {}, "t28-revoked-role", session=s, recheck=_recheck),
    )
    assert original["order"]["status"] == "APPROVED"
    with pytest.raises(DomainError) as denied:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor("viewer"), {}, "t28-revoked-role", session=s, recheck=_recheck
            ),
        )
    assert denied.value.code == "FORBIDDEN"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 1


def test_T28_failed_fresh_safety_gate_rolls_back_all_approval_writes(db: str) -> None:
    """A genuine failed gate is not replaced by the green stored planning checks."""
    _hold(db)

    async def rejected_safety(session: AsyncSession, plan_id: int) -> RecheckProof:
        proof = await _recheck(session, plan_id)
        return RecheckProof(
            plan_id=proof.plan_id,
            order_version=proof.order_version,
            source_version=proof.source_version,
            gates={**proof.gates, "safety": False},
            checked_at=proof.checked_at,
        )

    with pytest.raises(DomainError) as denied:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "t28-unsafe", session=s, recheck=rejected_safety
            ),
        )
    assert denied.value.code == "RESOURCE_CONFLICT"
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
    assert fetch(db, "SELECT status FROM plan.fulfilment_plan WHERE id=1")[0][0] == "proposed"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "held"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 0


def test_DEC_WMS_RESERVE_SYNC_disposable_demo_fails_closed_without_ack(db: str, monkeypatch) -> None:
    """No real demo APPROVED/trip/audit when only local gates and holds are proven."""
    _hold(db)
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    with pytest.raises(DomainError) as got:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "no-authoritative-ack", session=s, recheck=_recheck
            ),
        )
    assert got.value.code == "PLAN_NOT_APPROVABLE"
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 0
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "held"
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 0


def test_US_NOT_01_AC1_t21_approved_plan_enqueues_one_confirmed_email(db: str) -> None:
    """The approved order and frozen CONFIRMED outbox share one PG transaction."""
    execute(
        db,
        "UPDATE ref.customer SET email='confirmed@cfo.test' WHERE id=1",
        "UPDATE ref.market SET shadow_mode=false WHERE id=1",
    )
    _hold(db)

    async def approve(session: AsyncSession) -> dict[str, object]:
        return await approval_service.approve(
            1, _actor(), {}, "t21-confirmed-once", session=session, recheck=_recheck
        )

    first = _run(db, approve)
    again = _run(db, approve)
    assert again == first
    assert first["order"]["status"] == "APPROVED"
    assert len(first["notifications"]) == 1
    order = fetch(
        db,
        "SELECT id, approved_plan_id, order_no, promise_start, promise_end "
        "FROM ops.customer_order WHERE id=1",
    )[0]
    notification = fetch(
        db,
        "SELECT id, order_id, plan_id, status::text, recipient, skipped_reason, "
        "subject, body, dedupe_key, eta_window FROM ops.notification "
        "WHERE template='CONFIRMED'",
    )[0]
    assert notification["id"] > 0
    assert notification["order_id"] == order["id"] == first["order"]["id"]
    assert notification["plan_id"] == order["approved_plan_id"] == first["plan"]["id"]
    assert notification["status"] == "queued"
    assert first["notifications"] == [{"id": notification["id"], "template": "CONFIRMED", "status": "queued"}]
    assert notification["recipient"] == "confirmed@cfo.test"
    assert notification["skipped_reason"] is None
    assert notification["dedupe_key"] == f"{order['id']}:CONFIRMED:1:APPROVED"
    assert order["order_no"] in notification["subject"]
    assert order["order_no"] in notification["body"]
    market_timezone = fetch(db, "SELECT timezone FROM ref.market WHERE id=1")[0][0]
    zone = ZoneInfo(market_timezone)
    assert order["promise_start"].astimezone(zone).isoformat(timespec="minutes") in notification["body"]
    assert order["promise_end"].astimezone(zone).isoformat(timespec="minutes") in notification["body"]
    assert fetch(db, "SELECT count(*) FROM ops.notification WHERE template='CONFIRMED'")[0][0] == 1

    # E2 may have sent the email after the original commit. Approval retries
    # must return the frozen Idempotency-Key response, not its live outbox status.
    execute(
        db,
        f"UPDATE ops.notification SET status='sent', sent_at='2026-11-04T10:00:00Z' "
        f"WHERE id={notification['id']}",
    )
    replay_after_worker = _run(db, approve)
    assert replay_after_worker == first
    assert replay_after_worker["notifications"] == [
        {"id": notification["id"], "template": "CONFIRMED", "status": "queued"}
    ]
    assert fetch(db, "SELECT status::text FROM ops.notification WHERE id=1")[0][0] == "sent"
    assert fetch(db, "SELECT count(*) FROM ops.notification WHERE template='CONFIRMED'")[0][0] == 1
    print(
        "T21 CONFIRMED PG evidence (synthetic ids only): "
        f"order_id={order['id']} plan_id={notification['plan_id']} "
        f"notification_id={notification['id']} status={notification['status']}"
    )


def test_US_NOT_01_AC1_t21_missing_email_approves_but_suppresses(db: str) -> None:
    execute(db, "UPDATE ref.customer SET email=NULL WHERE id=1")
    _hold(db)
    result = _run(
        db,
        lambda s: approval_service.approve(1, _actor(), {}, "t21-no-email", session=s, recheck=_recheck),
    )
    assert result["order"]["status"] == "APPROVED"
    row = fetch(
        db,
        "SELECT id, order_id, plan_id, status::text, recipient, skipped_reason "
        "FROM ops.notification WHERE template='CONFIRMED'",
    )[0]
    assert row["id"] > 0 and (row["order_id"], row["plan_id"]) == (1, 1)
    assert result["notifications"] == [{"id": row["id"], "template": "CONFIRMED", "status": "suppressed"}]
    assert (row["status"], row["recipient"], row["skipped_reason"]) == (
        "suppressed",
        None,
        "SKIPPED_NO_CHANNEL",
    )
    email = AsyncMock()
    assert _run(db, lambda s: deliver_queued(s, now=NOW + timedelta(days=1), email=email)) == 0
    email.send.assert_not_called()
    assert fetch(db, "SELECT count(*) FROM ops.notification")[0][0] == 1


def test_US_NOT_01_AC1_t21_expired_hold_creates_no_confirmed(db: str) -> None:
    _hold(db)
    clock.set_now(NOW + timedelta(minutes=16))
    with pytest.raises(DomainError) as error:
        _run(
            db,
            lambda s: approval_service.approve(1, _actor(), {}, "t21-expired", session=s, recheck=_recheck),
        )
    assert error.value.code == "HOLD_EXPIRED"
    assert fetch(db, "SELECT count(*) FROM ops.notification")[0][0] == 0
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"


def test_US_NOT_01_AC1_t21_wms_gate_rejection_creates_no_confirmed(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold(db)
    # Exercise the existing fail-closed real-WMS branch, not a synthetic ACK.
    monkeypatch.setattr(approval_service, "get_settings", lambda: SimpleNamespace(app_env="production"))
    with pytest.raises(DomainError) as error:
        _run(
            db,
            lambda s: approval_service.approve(
                1, _actor(), {}, "t21-wms-unavailable", session=s, recheck=_recheck
            ),
        )
    assert error.value.code == "PLAN_NOT_APPROVABLE"
    assert fetch(db, "SELECT count(*) FROM ops.notification")[0][0] == 0
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"


def test_US_NOT_01_AC1_t21_post_enqueue_rollback_is_atomic(db: str) -> None:
    execute(db, "UPDATE ref.customer SET email='confirmed@cfo.test' WHERE id=1")
    _hold(db)

    async def aborted_approval(session: AsyncSession) -> None:
        response = await approval_service.approve(
            1,
            _actor(),
            {},
            "t21-abort-after-enqueue",
            session=session,
            recheck=_recheck,
        )
        assert response["order"]["status"] == "APPROVED"
        staged = await session.execute(
            text("SELECT id FROM ops.notification WHERE order_id=1 AND template='CONFIRMED'")
        )
        notification_id = staged.scalar_one()
        assert notification_id > 0
        assert response["notifications"] == [
            {"id": notification_id, "template": "CONFIRMED", "status": "queued"}
        ]
        raise RuntimeError("synthetic failure after enqueue before commit")

    with pytest.raises(RuntimeError, match="synthetic failure"):
        _run(db, aborted_approval)
    assert fetch(db, "SELECT status, approved_plan_id FROM ops.customer_order WHERE id=1")[0] == (
        "PLANNED",
        None,
    )
    assert fetch(db, "SELECT count(*) FROM ops.notification")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 0
