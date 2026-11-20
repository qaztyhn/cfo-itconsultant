"""T15 PostgreSQL integration: rotation ordering, rollback, concurrency and handover.

These tests require TEST_DATABASE_URL and a disposable PostgreSQL 16 database.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.errors import DomainError
from app.domain.models.ops import DeliveryTrip
from app.services.dispatcher_assignment import choose_dispatcher, handover_trip
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration


@pytest.fixture
def dispatcher_db(empty_db: str) -> str:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,
        "INSERT INTO hr.dispatcher_staff (employee_id, in_rotation) VALUES (1, true), (2, true)",
    )
    return empty_db


def _run(dsn: str, fn):
    async def go():
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as db, db.begin():
                return await fn(db)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _actor(*, role: str = "dispatcher", market: str = "ZZ"):
    return SimpleNamespace(id=1, employee_id=1, roles=(role,), market=market)


def _trip(db: str, employee_id: int, vehicle: int = 1) -> None:
    execute(
        db,
        "INSERT INTO ops.delivery_trip "
        "(warehouse_id, vehicle_id, driver_employee_id, depart_planned_at, assigned_dispatcher_employee_id) "
        f"VALUES (1, {vehicle}, 1, '2026-11-10T07:00Z', {employee_id})",
    )


def test_T15_rotation_unassigned_first_then_oldest_then_id(dispatcher_db: str) -> None:
    db = dispatcher_db
    assert _run(db, lambda s: choose_dispatcher(s, 1)) == 1
    _trip(db, 1)
    assert _run(db, lambda s: choose_dispatcher(s, 1)) == 2
    _trip(db, 2, vehicle=2)
    # Same transaction-stamped assignment times may tie: smallest employee ID wins.
    # If stamps differ, the earliest assignment wins (also employee 1).
    assert _run(db, lambda s: choose_dispatcher(s, 1)) == 1
    execute(db, "UPDATE hr.dispatcher_staff SET in_rotation=false WHERE employee_id=1")
    assert _run(db, lambda s: choose_dispatcher(s, 1)) == 2
    execute(db, "UPDATE hr.employee SET status='terminated' WHERE id=2")
    assert _run(db, lambda s: choose_dispatcher(s, 1)) is None


def test_T15_rollback_does_not_consume_turn(dispatcher_db: str) -> None:
    async def failed(session):
        selected = await choose_dispatcher(session, 1)
        session.add(
            DeliveryTrip(
                warehouse_id=1,
                vehicle_id=1,
                driver_employee_id=1,
                depart_planned_at=datetime.fromisoformat("2026-11-10T07:00:00+00:00"),
                assigned_dispatcher_employee_id=selected,
            )
        )
        await session.flush()
        raise RuntimeError("force rollback")

    with pytest.raises(RuntimeError):
        _run(dispatcher_db, failed)
    assert fetch(dispatcher_db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0
    assert _run(dispatcher_db, lambda s: choose_dispatcher(s, 1)) == 1


def test_T15_market_lock_serializes_simultaneous_assignments(dispatcher_db: str) -> None:
    async def go():
        engine = create_async_engine(async_url(dispatcher_db), poolclass=NullPool)

        async def choose_and_insert(vehicle_id):
            async with async_sessionmaker(engine)() as db, db.begin():
                chosen = await choose_dispatcher(db, 1)
                await db.execute(
                    text(
                        "INSERT INTO ops.delivery_trip (warehouse_id, vehicle_id, driver_employee_id, "
                        "depart_planned_at, assigned_dispatcher_employee_id) "
                        "VALUES (1, :vehicle, 1, '2026-11-10T07:00Z', :assigned)"
                    ),
                    {"vehicle": vehicle_id, "assigned": chosen},
                )
                return chosen

        try:
            return await asyncio.gather(choose_and_insert(1), choose_and_insert(2))
        finally:
            await engine.dispose()

    assert set(asyncio.run(go())) == {1, 2}


def test_T15_handover_scoped_audited_and_rejected_without_changes(dispatcher_db: str) -> None:
    _trip(dispatcher_db, 1)
    result = _run(
        dispatcher_db,
        lambda s: handover_trip(s, 1, _actor(), to_employee_id=2, reason_text="Shift coverage reassignment"),
    )
    assert result["assigned_dispatcher_employee_id"] == 2
    assert (
        fetch(
            dispatcher_db,
            "SELECT assigned_dispatcher_employee_id " "FROM ops.delivery_trip WHERE id=1",
        )[
            0
        ][0]
        == 2
    )
    assert (
        fetch(
            dispatcher_db,
            "SELECT count(*) FROM audit.decision_log "
            "WHERE action='TRIP_DISPATCHER_HANDOVER'",
        )[0][0]
        == 1
    )
    for actor, target, reason in [
        (_actor(role="sales"), 1, "no role"),
        (_actor(market="XX"), 1, "wrong market"),
        (_actor(), 1, "  "),
    ]:
        with pytest.raises(DomainError):
            _run(
                dispatcher_db,
                lambda s, a=actor, t=target, r=reason: handover_trip(
                    s, 1, a, to_employee_id=t, reason_text=r
                ),
            )
    execute(dispatcher_db, "UPDATE hr.dispatcher_staff SET in_rotation=false WHERE employee_id=1")
    with pytest.raises(DomainError):
        _run(
            dispatcher_db,
            lambda s: handover_trip(s, 1, _actor(), to_employee_id=1, reason_text="Ineligible recipient"),
        )
    assert (
        fetch(
            dispatcher_db,
            "SELECT assigned_dispatcher_employee_id " "FROM ops.delivery_trip WHERE id=1",
        )[
            0
        ][0]
        == 2
    )
    assert (
        fetch(
            dispatcher_db,
            "SELECT count(*) FROM audit.decision_log "
            "WHERE action='TRIP_DISPATCHER_HANDOVER'",
        )[0][0]
        == 1
    )
