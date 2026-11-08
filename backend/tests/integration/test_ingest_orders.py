import asyncio
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.rest_adapter import RestMarketAdapter
from app.domain.models.plan import PlanningRun
from app.services.ingest_service import sync_entity
from tests.integration import rows
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_ingest_references import inbound, mapped, run_feed
from tests.integration.test_ingest_runner import NOW, page
from tests.integration.test_ingest_runner import db as db

pytestmark = pytest.mark.integration


def routing(no: int, route: str = "cfo") -> str:
    reason = "all_confirmed" if route == "cfo" else "unmapped_sku"
    return (
        "INSERT INTO ops.order_routing(market_id,external_ref,route,reason_code,decided_at,"
        "decided_source_version,decided_by_user_id,decided_by_role) "
        f"VALUES(1,'EXT-{no}','{route}','{reason}','2026-11-04T09:00Z',1,1,'dispatcher')"
    )


def source(no: int = 1, **changes: object) -> dict[str, object]:
    return {
        "id": f"EXT-{no}",
        "version": 2,
        "updated_at": NOW.isoformat(),
        "status": "SUBMITTED_FOR_PLANNING",
        "customer_id": "C-1",
        "address_id": "A1",
        "address": "New synthetic site",
        "lat": 59,
        "lon": 18,
        "contact": {"name": "Synthetic", "email": "synthetic@example.test", "phone": None},
        "date_mode": "exact",
        "date_from": "2026-11-10",
        "date_to": None,
        "store_code": "ST-1",
        "lines": [{"line_no": 1, "sku": "P1", "qty": 1.125, "unit_price": "2.00"}],
        **changes,
    }


def prepare(db: str, *, approved: bool = False, dispatched: bool = False) -> None:
    mapped(db)
    execute(
        db,
        rows.order_sql(1),
        routing(1),
        "UPDATE ops.customer_order SET origin_store_id=2 WHERE id=1",
        "INSERT INTO ops.order_line(order_id,line_no,local_sku,global_product_id,qty_sale,qty_base,"
        "unit_price,line_total) "
        "VALUES(1,1,'P1',1,5,5,2,10)",
    )
    if approved or dispatched:
        execute(
            db,
            rows.run_sql(1, 1),
            rows.plan_sql(1, 1, 1, status="approved"),
            "UPDATE ops.customer_order SET status='PLANNED' WHERE id=1",
            "UPDATE ops.customer_order SET status='APPROVED',approved_plan_id=1 WHERE id=1",
            "INSERT INTO plan.stock_reservation(run_id,order_id,warehouse_id,global_product_id,qty,status) "
            "VALUES(1,1,1,1,5,'committed')",
        )
    if dispatched:
        execute(
            db,
            *[
                f"UPDATE ops.customer_order SET status='{status}' WHERE id=1"
                for status in ("PREPARING", "GOODS_READY", "LOADED", "DISPATCHED")
            ],
        )


def run_orders(
    db: str,
    submitted: list[dict[str, object]],
    cancelled: list[dict[str, object]] | None = None,
    **options: object,
):
    async def scenario():
        engine = create_async_engine(async_url(db), poolclass=NullPool, hide_parameters=True)
        try:

            def handler(request: httpx.Request) -> httpx.Response:
                assert request.method == "GET"
                return page((cancelled or []) if request.url.params["status"] == "CANCELLED" else submitted)

            return await sync_entity(
                "SE",
                "orders",
                maker=async_sessionmaker(engine, expire_on_commit=False),
                adapter=RestMarketAdapter(
                    "SE", "https://source.test", "synthetic-key", transport=httpx.MockTransport(handler)
                ),
                now=NOW,
                **options,
            )
        finally:
            await engine.dispose()

    return asyncio.run(scenario())


def test_US_INT_01_AC2_orders_replay_and_stale_version_do_not_duplicate_or_regress(db: str) -> None:
    prepare(db)
    assert run_orders(db, [source(version=3)]).status == "ok"
    assert run_orders(db, [source(version=3)]).status == "ok"
    assert run_orders(db, [source(version=2, address="Older synthetic site")]).status == "ok"
    record = fetch(db, "SELECT source_version,version,delivery_address,total_amount FROM ops.customer_order")[
        0
    ]
    assert tuple(record) == (3, 2, "New synthetic site", Decimal("2.25"))
    assert fetch(db, "SELECT count(*),max(qty_base) FROM ops.order_line")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 1


def test_US_INT_01_AC3_bad_quantity_is_partial_and_explicit_retry_imports_repaired_row(db: str) -> None:
    prepare(db)
    execute(db, rows.order_sql(2), routing(2), "UPDATE ops.customer_order SET origin_store_id=2 WHERE id=2")
    invalid = source(lines=[{"line_no": 1, "sku": "P1", "qty": -5, "unit_price": "2.00"}])
    result = run_orders(db, [invalid, source(2)])
    assert (result.status, result.rows_ok, result.rows_rejected) == ("partial", 1, 1)
    assert fetch(db, "SELECT reason_code,raw::text FROM stg.sync_reject")[0][0] == "BAD_QTY"
    assert fetch(db, "SELECT source_version FROM ops.customer_order ORDER BY id")[0][0] == 1
    assert run_orders(db, [source(), source(2)], retry_run_id=result.run_id).status == "ok"
    assert [row[0] for row in fetch(db, "SELECT source_version FROM ops.customer_order ORDER BY id")] == [
        2,
        2,
    ]


def test_DEC_ROUTING_002_polling_never_creates_undecided_or_legacy_cfo_orders(db: str) -> None:
    mapped(db)
    execute(db, routing(2, "legacy"))
    result = run_orders(db, [source(1), source(2)])
    assert result.status == "partial" and result.rows_ok == result.rows_rejected == 1
    assert not fetch(db, "SELECT * FROM ops.customer_order")
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 1
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")


def test_US_INT_02_AC1_approved_change_preserves_data_commitments_and_pins_missing_replan(db: str) -> None:
    prepare(db, approved=True)
    result = run_orders(db, [source()])
    assert result.status == "partial"
    assert run_orders(db, [source()]).status == "partial"
    assert tuple(
        fetch(db, "SELECT source_version,status,delivery_address,approved_plan_id FROM ops.customer_order")[0]
    ) == (1, "APPROVED", "Address", 1)
    assert tuple(fetch(db, "SELECT qty,status FROM plan.stock_reservation")[0]) == (Decimal(5), "committed")
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='ORDER_CHANGED_AFTER_APPROVAL'")[0][0] == 1
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint WHERE entity='orders'")


def test_US_INT_02_AC3_trusted_suggestion_handoff_receives_new_source_and_deduplicates(db: str) -> None:
    prepare(db, approved=True)
    calls: list[int] = []

    async def fake_planning_contract(session, order, fresh):
        # Tests only the handoff, not a real five-gate planning implementation.
        calls.append(fresh.version)
        assert order.delivery_address == "Address" and fresh.address == "New synthetic site"
        run = PlanningRun(
            order_id=order.id,
            order_version=order.version,
            run_no=2,
            kind="replan_suggestion",
            trigger="source_change",
            params={"source_version": fresh.version},
            input_snapshot={"synthetic_only": True},
            result="infeasible",
        )
        session.add(run)
        await session.flush()
        return run.id

    assert run_orders(db, [source()], replan=fake_planning_contract).status == "ok"
    assert run_orders(db, [source()], replan=fake_planning_contract).status == "ok"
    assert calls == [2]
    assert fetch(db, "SELECT count(*) FROM plan.planning_run WHERE kind='replan_suggestion'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM plan.stock_reservation")[0][0] == 1


@pytest.mark.parametrize("bad", ["hold", "overwrite"])
def test_US_APR_04_AC3_invalid_replan_handoff_rolls_back_without_losing_warning(db: str, bad: str) -> None:
    prepare(db, approved=True)

    async def bad_contract(session, order, fresh):
        if bad == "overwrite":
            order.delivery_address = fresh.address
        run = PlanningRun(
            order_id=order.id,
            order_version=order.version,
            run_no=2,
            kind="replan_suggestion",
            trigger="source_change",
            params={"source_version": fresh.version},
            input_snapshot={},
            result="infeasible",
            hold_expires_at=NOW + timedelta(minutes=15) if bad == "hold" else None,
        )
        session.add(run)
        await session.flush()
        return run.id

    assert run_orders(db, [source()], replan=bad_contract).status == "partial"
    assert fetch(db, "SELECT delivery_address FROM ops.customer_order")[0][0] == "Address"
    assert fetch(db, "SELECT count(*) FROM ops.alert")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM plan.planning_run")[0][0] == 1


def test_US_INT_02_AC2_post_dispatch_cancel_is_alert_only_with_independent_checkpoint(db: str) -> None:
    prepare(db, dispatched=True)
    cancellation = {
        "id": "EXT-1",
        "version": 2,
        "updated_at": NOW.isoformat(),
        "status": "CANCELLED",
        "cancel_reason": {"reason_code": "other", "reason_text": "Synthetic"},
        "cancelled_at": NOW.isoformat(),
    }
    assert run_orders(db, [], [cancellation]).status == "ok"
    assert fetch(db, "SELECT status FROM ops.customer_order")[0][0] == "DISPATCHED"
    assert fetch(db, "SELECT entity FROM stg.sync_checkpoint")[0][0] == "orders:cancelled"
    assert fetch(db, "SELECT count(*) FROM plan.planning_run")[0][0] == 1


def test_D1_cancel_before_approval_does_not_invent_a_system_transition(db: str) -> None:
    prepare(db)
    cancellation = {"id": "EXT-1", "version": 2, "updated_at": NOW.isoformat(), "status": "CANCELLED"}
    assert run_orders(db, [], [cancellation]).status == "partial"
    assert fetch(db, "SELECT status FROM ops.customer_order")[0][0] == "SUBMITTED"
    assert fetch(db, "SELECT reason_code FROM stg.sync_reject")[0][0] == "CANCEL_TRANSITION_REQUIRES_REVIEW"


def test_US_INT_03_risk_handoff_is_required_atomic_after_all_rows_and_not_repeated_for_replay(
    db: str,
) -> None:
    prepare(db, approved=True)
    data = [inbound("I1"), inbound("I2")]
    assert run_feed(db, "inbound", data).status == "partial"
    assert not fetch(db, "SELECT * FROM ops.inbound_shipment")
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")
    calls: list[int] = []

    async def fake_risk_contract(session, order_id, trigger):
        assert trigger == "source_change"
        assert await session.scalar(text("SELECT count(*) FROM ops.inbound_shipment")) == 2
        calls.append(order_id)

    assert run_feed(db, "inbound", data, risk=fake_risk_contract).status == "ok"
    assert run_feed(db, "inbound", data, risk=fake_risk_contract).status == "ok"
    assert calls == [1]
