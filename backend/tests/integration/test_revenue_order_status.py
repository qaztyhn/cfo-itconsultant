"""US-REV-02 AC1–AC7 over HTTP and real PostgreSQL."""

from datetime import datetime

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.domain.models.ops import CustomerOrder
from app.domain.transitions import S, transition
from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.test_revenue_api import PERIOD, SEED
from tests.integration.test_revenue_service import _order, run

pytestmark = pytest.mark.integration

STATUS = "/revenue/order-status"
ORDERS = "/revenue/orders"
GROUPS = {
    "approved": ["APPROVED", "PREPARING", "GOODS_READY", "LOADED"],
    "in_transit": ["DISPATCHED"],
    "completed": ["DELIVERED"],
    "failed": ["FAILED"],
    "cancelled": ["CANCELLED"],
}


@pytest.fixture
def report(api: Api, monkeypatch: pytest.MonkeyPatch) -> Api:  # noqa: F811
    fixtures = [
        # status, amount, origin store, plan warehouse, commitment, actual delivery
        ("APPROVED", "10.10", 2, 4, "2026-11-01", None),
        ("PREPARING", "20.20", 2, 4, "2026-11-15", None),
        ("GOODS_READY", "30.30", 2, 1, "2026-11-15", None),
        ("LOADED", "40.40", 2, 4, "2026-11-30", None),
        ("DISPATCHED", "50.50", 2, 4, "2026-11-15", None),
        ("DELIVERED", "60.60", 2, 4, "2026-11-30", "2026-12-01T11:00Z"),
        ("FAILED", "70.70", 2, 4, "2026-11-15", None),
        ("PLANNED", "80.80", 2, 4, None, None),  # proposed, never approved
        ("APPROVED", "90.90", 2, 4, "2026-12-05", None),
        ("PLANNED", "100.10", 2, None, None, None),
        ("DELIVERED", "110.11", 2, 4, "2026-12-01", "2026-11-30T11:00Z"),
        ("APPROVED", "120.12", 2, 4, "2026-10-31", None),
        ("APPROVED", "130.13", 2, 4, "2026-12-05", None),
        ("SUBMITTED", "140.14", 2, None, None, None),
        ("PLANNED", "150.15", 2, 4, None, None),
        ("NO_FEASIBLE_DATE", "160.16", 2, None, None, None),
        ("BLOCKED_UNMAPPED_SKU", "170.17", 2, None, None, None),
        ("APPROVED", "180.18", 3, 1, "2026-11-15", None),
        ("CANCELLED", "190.19", 2, None, None, None),  # legacy row without cancellation time
    ]
    statements = list(SEED)
    plan_id = 0
    for no, (status, amount, store, warehouse, committed, delivered) in enumerate(fixtures, 1):
        statements.append(_order(no, status, amount, store, committed=committed, delivered=delivered))
        if warehouse is not None:
            plan_id += 1
            approved = status != "PLANNED"
            statements.extend(
                (
                    rows.run_sql(no, 1),
                    rows.plan_sql(plan_id, no, 1, "approved" if approved else "proposed"),
                    f"UPDATE plan.fulfilment_plan SET warehouse_id = {warehouse} WHERE id = {plan_id}",
                )
            )
            if approved:
                statements.append(
                    f"UPDATE ops.customer_order SET approved_plan_id = {plan_id} WHERE id = {no}"
                )
    execute(api.dsn, *statements)

    async def cancel_orders(session: AsyncSession) -> None:
        reason = "Synthetic customer cancellation"
        async with session.begin():
            for order_id, ts in (
                (8, "2026-11-29T23:01Z"),  # 00:01 Stockholm, Nov 30
                (9, "2026-11-30T22:59Z"),  # 23:59 Stockholm, Nov 30
                (10, "2026-11-30T23:00Z"),  # 00:00 Stockholm, Dec 1
            ):
                with monkeypatch.context() as mp:
                    cancel_at = datetime.fromisoformat(ts)
                    mp.setattr(clock, "now", lambda cancel_at=cancel_at: cancel_at)
                    result = await transition(session, order_id, S.CANCELLED, "dispatcher", reason)
                    assert result.closed is not None
                    await record_decision(
                        session,
                        Action.ORDER_CANCELLED,
                        entity="order",
                        entity_id=str(order_id),
                        order_id=order_id,
                        actor_user_id=4,
                        actor_employee_id=4,
                        actor_role="dispatcher",
                        reason_text=reason,
                        before=result.closed.before | {"status": result.from_status.value},
                        after={"status": "CANCELLED"},
                    )

    run(api.dsn, cancel_orders)
    return api


def test_US_REV_02_AC1_AC2_groups_amounts_and_empty_period(report: Api) -> None:
    response = report.get(STATUS, 1, view="store", location_id=2, **PERIOD)
    assert response.status_code == 200, response.text
    groups = [
        {
            "key": key,
            "statuses": statuses,
            "date_basis": "cancelled_at" if key == "cancelled" else "committed_date",
            "orders": count,
            "amount": amount,
        }
        for (key, statuses), (count, amount) in zip(
            GROUPS.items(),
            [(4, "101.00"), (1, "50.50"), (1, "60.60"), (1, "70.70"), (2, "171.70")],
            strict=True,
        )
    ]
    assert response.json() == {
        "period": PERIOD,
        "view": "store",
        "location_id": 2,
        "currency": "SEK",
        "total": {"orders": 9, "amount": "454.50"},
        "groups": groups,
    }
    empty = report.get(STATUS, 2, view="store", **{"from": "2027-02-01", "to": "2027-02-01"})
    assert empty.status_code == 200, empty.text
    assert empty.json()["total"] == {"orders": 0, "amount": "0.00"}
    assert empty.json()["groups"] == [group | {"orders": 0, "amount": "0.00"} for group in groups]


def test_US_REV_02_AC3_delivery_moves_the_order_to_completed(report: Api) -> None:
    params = dict(view="store", location_id=2, **PERIOD)
    before = report.get(STATUS, 2, **params).json()
    assert report.get(ORDERS, 2, status_group="in_transit", **params).json()["total"] == 1

    async def deliver(session: AsyncSession) -> None:
        async with session.begin():
            await transition(session, 5, S.DELIVERED, "driver")
            await session.execute(
                update(CustomerOrder)
                .where(CustomerOrder.id == 5)
                .values(delivered_at=datetime.fromisoformat("2026-11-15T11:00Z"))
            )

    run(report.dsn, deliver)
    after = report.get(STATUS, 2, **params).json()
    assert before["total"] == after["total"]
    assert after["groups"][1] == before["groups"][1] | {"orders": 0, "amount": "0.00"}
    assert after["groups"][2] == before["groups"][2] | {"orders": 2, "amount": "111.10"}
    assert report.get(ORDERS, 2, status_group="in_transit", **params).json()["total"] == 0
    assert report.get(ORDERS, 2, status_group="completed", **params).json()["total"] == 2


def test_US_REV_02_AC4_scope_period_errors_and_market_isolation(report: Api) -> None:
    execute(
        report.dsn,
        "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
        "VALUES (1, 'E5', 'Test', 'Admin', 'TEST_POS', '2026-01-01')",
        "UPDATE ref.app_user SET employee_id=5 WHERE id=5",
        "INSERT INTO ref.customer (market_id, external_ref, type, name) "
        "VALUES (2, 'EUR-1', 'business', 'Other')",
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "delivery_address, delivery_lat, delivery_lon, date_mode, date_to, order_date, currency, "
        "submitted_at, status, total_amount, committed_date) "
        "SELECT 'ZZ-000001', 2, 'R-ZZ', 2, contact_name, delivery_address, delivery_lat, delivery_lon, "
        "date_mode, date_to, order_date, 'EUR', submitted_at, status, 9999.00, committed_date "
        "FROM ops.customer_order WHERE id=1",
    )
    for user, view, count in ((1, "store", 9), (2, "store", 10), (3, "warehouse", 7), (5, "store", 10)):
        response = report.get(STATUS, user, view=view, **PERIOD)
        assert response.status_code == 200, response.text
        assert response.json()["location_id"] is None
        assert response.json()["total"]["orders"] == count
        assert response.json()["currency"] == "SEK"
        assert "customer" not in response.text

    for route, extra in ((STATUS, {}), (ORDERS, {"status_group": "cancelled"})):
        assert_error(report.get(route, 4, view="store", location_id=2, **extra, **PERIOD), 403, "FORBIDDEN")
        assert_error(report.get(route, 1, view="store", location_id=3, **extra, **PERIOD), 404, "NOT_FOUND")
        assert_error(
            report.get(route, 3, view="store", location_id=4, **extra, **PERIOD),
            422,
            "VALIDATION_ERROR",
        )
    assert_error(report.get(STATUS, 3, view="store", **PERIOD), 403, "FORBIDDEN")
    assert_error(report.get(STATUS, None, view="store", **PERIOD), 401, "AUTH_INVALID")
    for role in ("customer_service", "sales", "driver", "viewer"):
        execute(report.dsn, f"UPDATE ref.app_user SET roles='{{{role}}}' WHERE id=4")
        assert_error(report.get(STATUS, 4, view="store", **PERIOD), 403, "FORBIDDEN")
    for period in (
        {"from": "2026-11-02", "to": "2026-11-01"},
        {"from": "2025-01-01", "to": "2026-11-30"},
    ):
        assert_error(report.get(STATUS, 2, view="store", **period), 422, "VALIDATION_ERROR")


def test_US_REV_02_AC5_AC6_group_drill_down_and_legacy_revenue(report: Api) -> None:
    for view, location in (("store", 2), ("warehouse", 4)):
        params = dict(view=view, location_id=location, **PERIOD)
        status = report.get(STATUS, 2, **params).json()
        for group in status["groups"]:
            paged = report.get(ORDERS, 2, status_group=group["key"], page_size=1, **params)
            assert paged.status_code == 200, paged.text
            assert paged.json()["total"] == group["orders"]
            assert paged.json()["items"][0]["status"] in group["statuses"]
            assert "customer_name" not in paged.json()["items"][0]

    params = dict(view="store", location_id=2, **PERIOD)
    for page, order_no in ((1, "SE-000008"), (2, "SE-000009"), (3, None)):
        paged = report.get(ORDERS, 2, status_group="cancelled", page_size=1, page=page, **params).json()
        assert paged["total"] == 2
        assert [row["order_no"] for row in paged["items"]] == ([order_no] if order_no else [])
    assert_error(report.get(ORDERS, 2, status_group="unknown", **params), 422, "VALIDATION_ERROR")
    assert_error(
        report.get(ORDERS, 2, view="store", status_group="cancelled", **PERIOD), 422, "VALIDATION_ERROR"
    )
    completed = report.get(ORDERS, 2, status_group="completed", **params).json()
    assert [row["order_no"] for row in completed["items"]] == ["SE-000006"]
    legacy = report.get(ORDERS, 2, **params).json()
    assert legacy["total"] == 6
    assert [row["order_no"] for row in legacy["items"] if row["status"] == "DELIVERED"] == ["SE-000011"]
    assert report.get("/revenue/summary", 2, **params).json()["recognised"] == "110.11"


def test_US_REV_02_AC7_cancellation_audit_day_and_approved_warehouse(report: Api) -> None:
    audit = fetch(
        report.dsn,
        "SELECT l.before->>'approved_plan_id' AS previous_plan, o.approved_plan_id, o.committed_date "
        "FROM audit.decision_log l JOIN ops.customer_order o ON o.id = l.order_id "
        "WHERE l.action = 'ORDER_CANCELLED' ORDER BY o.id",
    )
    assert [tuple(row) for row in audit] == [(None, None, None), ("9", None, None), (None, None, None)]
    day = {"from": "2026-11-30", "to": "2026-11-30"}
    store = report.get(ORDERS, 1, view="store", location_id=2, status_group="cancelled", **day)
    assert store.status_code == 200, store.text
    assert [row["order_no"] for row in store.json()["items"]] == ["SE-000008", "SE-000009"]
    assert store.json()["items"][0]["customer_name"] == "Test customer"
    wh = report.get(ORDERS, 3, view="warehouse", location_id=4, status_group="cancelled", **day)
    assert wh.status_code == 200, wh.text
    assert [row["order_no"] for row in wh.json()["items"]] == ["SE-000009"]
    all_wh = report.get(STATUS, 2, view="warehouse", **day)
    assert all_wh.json()["groups"][-1]["orders"] == 2
    other_wh = report.get(STATUS, 2, view="warehouse", location_id=1, **day)
    assert other_wh.json()["groups"][-1]["orders"] == 0
    next_day = {"from": "2026-12-01", "to": "2026-12-01"}
    tomorrow = report.get(ORDERS, 2, view="store", location_id=2, status_group="cancelled", **next_day)
    assert [row["order_no"] for row in tomorrow.json()["items"]] == ["SE-000010"]
