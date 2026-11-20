"""US-APR-05: real PostgreSQL coverage for Sales/Dispatcher pre-approval parity (DEC-R3-10)."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.errors import DomainError
from app.services import approval_service, planning_service
from tests.integration import rows
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_approval_service import (
    GATES,
    _actor,
    _hold,
    _recheck,
    _run,
    _second_order,
)
from tests.integration.test_approval_service import db as db

pytestmark = pytest.mark.integration


def _three_ranked_options(db: str) -> None:
    """All three options on one run; rank 2 uses two distinct trucks and drivers."""
    execute(
        db,
        "INSERT INTO hr.driver_staff (employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES (2,1,'C','2027-01-01')",
        rows.plan_sql(1, 1, 2),
        rows.plan_sql(1, 1, 3),
        rows.plan_vehicle_sql(2, 1, 1, 1),
        rows.plan_vehicle_sql(2, 2, 2, 2),
        rows.plan_vehicle_sql(3, 1, 2, 2),
        "UPDATE plan.fulfilment_plan SET vehicle_count=2 WHERE id=2",
        'UPDATE plan.fulfilment_plan SET workload=\'{"prep_by_day":{"2026-11-10":"1.500"}}\'::jsonb '
        "WHERE id IN (2,3)",
        f"UPDATE plan.fulfilment_plan SET checks='{GATES}'::jsonb WHERE id IN (2,3)",
    )
    _hold(db)


def test_US_APR_05_AC1_sales_reads_three_sanitized_options_and_approves_multi_vehicle(db: str) -> None:
    _three_ranked_options(db)
    preview = _run(db, lambda s: planning_service.get_run(1, _actor("sales"), session=s))
    assert [plan["rank"] for plan in preview["plans"]] == [1, 2, 3]
    assert [plan["warehouse"]["id"] for plan in preview["plans"]] == [1, 1, 1]
    assert preview["sales_approvable"] is True
    assert all(p["approvable"] and p["checks"]["safety"]["passed"] for p in preview["plans"])
    assert all("driver_employee_id" not in str(p) for p in preview["plans"])
    assert all("detail" not in p["checks"]["stock"] for p in preview["plans"])
    rank3 = _run(db, lambda s: planning_service.get_plan(3, _actor("sales"), session=s))
    assert rank3["rank"] == 3 and "driver_employee_id" not in str(rank3)
    result = _run(
        db,
        lambda s: approval_service.approve(
            2,
            _actor("sales"),
            {"reason_code": "closest_to_customer"},
            "t19-rank2-multi",
            session=s,
            recheck=_recheck,
        ),
    )
    assert result["plan"]["id"] == 2 and result["order"]["status"] == "APPROVED"
    assert len(result["trip_ids"]) == 2
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 2
    assert fetch(db, "SELECT count(*) FROM ops.trip_stop")[0][0] == 2
    # All trips must retain the same T15 Dispatcher assignment, including unassigned fail-closed case.
    assignments = fetch(db, "SELECT assigned_dispatcher_employee_id FROM ops.delivery_trip")
    assert len({row[0] for row in assignments}) == 1
    approval = fetch(
        db,
        "SELECT actor_role,reason_code,snapshot->>'rank' FROM audit.decision_log "
        "WHERE action='PLAN_APPROVED'",
    )[0]
    assert tuple(approval) == ("sales", "closest_to_customer", "2")
    alt = fetch(db, "SELECT actor_role,reason_code FROM audit.decision_log " "WHERE action='ALT_SELECTED'")[0]
    assert tuple(alt) == ("sales", "closest_to_customer")
    assert fetch(db, "SELECT count(*) FROM ops.notification WHERE template='CONFIRMED'")[0][0] == 1
    assert fetch(db, "SELECT approved_plan_id FROM ops.customer_order WHERE id=1")[0][0] == 2
    assert fetch(db, "SELECT status FROM plan.fulfilment_plan WHERE id=1")[0][0] == "superseded"
    # The original key/body replays without new trips or notifications.
    replay = _run(
        db,
        lambda s: approval_service.approve(
            2,
            _actor("sales"),
            {"reason_code": "closest_to_customer"},
            "t19-rank2-multi",
            session=s,
            recheck=_recheck,
        ),
    )
    assert replay == result
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 2


def test_US_APR_05_AC1_sales_can_approve_rank3_and_tight(db: str) -> None:
    _three_ranked_options(db)
    execute(db, "UPDATE plan.planning_run SET reserve_class='tight' WHERE id=1")
    result = _run(
        db,
        lambda s: approval_service.approve(
            3,
            _actor("sales"),
            {"reason_code": "customer_prefers_earlier_slot"},
            "t19-rank3-tight",
            session=s,
            recheck=_recheck,
        ),
    )
    assert result["plan"]["rank"] == 3
    assert len(result["trip_ids"]) == 1
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 1


@pytest.mark.parametrize("role", ["sales", "dispatcher"])
def test_US_APR_05_AC2_rank2_note_without_reason_code_rejected(db: str, role: str) -> None:
    _three_ranked_options(db)
    with pytest.raises(DomainError) as rejected:
        _run(
            db,
            lambda s: approval_service.approve(
                2,
                _actor(role),
                {"reason_text": "Customer asked for it"},
                f"t19-note-{role}",
                session=s,
                recheck=_recheck,
            ),
        )
    assert rejected.value.code == "REASON_REQUIRED"
    assert rejected.value.http_status == 422
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0


def test_US_APR_05_AC4_sales_negotiates_date_without_changing_commitment(db: str) -> None:
    _three_ranked_options(db)
    execute(db, "UPDATE plan.fulfilment_plan SET target_date='2026-11-11' WHERE id=2")
    body = {"reason_code": "closest_to_customer"}
    with pytest.raises(DomainError) as no_agreement:
        _run(
            db,
            lambda s: approval_service.approve(
                2,
                _actor("sales"),
                body,
                "t19-no-agreement",
                session=s,
                recheck=_recheck,
            ),
        )
    assert no_agreement.value.code == "DATE_AGREEMENT_REQUIRED"
    agreement_id = _run(
        db,
        lambda session: approval_service.record_date_negotiation(
            1,
            _actor("sales"),
            {
                "proposed_date": "2026-11-11",
                "outcome": "agreed",
                "channel": "in_person",
                "contacted_at": "2026-11-04T09:00:00+00:00",
            },
            session=session,
        ),
    )
    history = _run(db, lambda s: planning_service.list_date_negotiations(1, _actor("sales"), session=s))
    assert any(item["id"] == agreement_id and item["outcome"] == "agreed" for item in history["items"])
    assert fetch(db, "SELECT committed_date FROM ops.customer_order WHERE id=1")[0][0] is None
    audit = fetch(
        db, "SELECT actor_role FROM audit.decision_log " "WHERE action='DATE_NEGOTIATION_RECORDED'"
    )[0]
    assert audit[0] == "sales"
    approved = _run(
        db,
        lambda s: approval_service.approve(
            2,
            _actor("sales"),
            {**body, "date_negotiation_id": agreement_id},
            "t19-date-agreed",
            session=s,
            recheck=_recheck,
        ),
    )
    assert approved["order"]["committed"]["date"] == "2026-11-11"


def test_US_APR_05_AC5_scope_and_manual_denials(db: str) -> None:
    _three_ranked_options(db)
    outsider = _actor("sales", (999,))
    for operation in (
        lambda s: planning_service.get_run(1, outsider, session=s),
        lambda s: planning_service.get_plan(2, outsider, session=s),
        lambda s: planning_service.list_date_negotiations(1, outsider, session=s),
    ):
        with pytest.raises(DomainError) as denied:
            _run(db, operation)
        assert denied.value.code == "NOT_FOUND"
    with pytest.raises(DomainError) as denied:
        _run(db, lambda s: approval_service.manual_plan(1, _actor("sales"), {}, "t19-manual"))
    assert denied.value.code == "FORBIDDEN"


def test_US_APR_05_AC7_concurrent_sales_and_dispatcher_share_stock_single_winner(db: str) -> None:
    _hold(db)
    _second_order(db, stock=30)

    async def race() -> tuple[list[int], list[str]]:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        succeeded: list[int] = []
        failed: list[str] = []

        async def one(plan_id: int, role: str) -> None:
            async with async_sessionmaker(engine)() as session:
                try:
                    async with session.begin():
                        await approval_service.approve(
                            plan_id,
                            _actor(role),
                            {},
                            f"t19-race-{plan_id}",
                            session=session,
                            recheck=_recheck,
                        )
                    succeeded.append(plan_id)
                except DomainError as error:
                    failed.append(error.code)

        try:
            await asyncio.gather(one(1, "sales"), one(2, "dispatcher"))
        finally:
            await engine.dispose()
        return succeeded, failed

    success, failure = asyncio.run(race())
    assert len(success) == 1 and failure == ["RESOURCE_CONFLICT"]
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.notification WHERE template='CONFIRMED'")[0][0] == 1
