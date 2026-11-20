"""T21: the execution transaction emits at most one DISPATCHED per order."""

import asyncio
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1 import internal
from app.core.config import get_settings
from app.services import driver_history, notification_delivery, planning_service, risk_service
from tests.integration import rows
from tests.integration.api_harness import Api
from tests.integration.api_harness import api as api
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.hr_fixture import DRIVER, WAREHOUSE
from tests.integration.test_e2_mailpit import _mailpit_messages
from tests.integration.test_execution_api import execution_api as execution_api
from tests.integration.test_execution_api import send, verified_risk

pytestmark = pytest.mark.integration
DEPARTED_AT = "2026-11-10T08:10:00Z"


@pytest.fixture
def loaded_order(execution_api: Api, monkeypatch: pytest.MonkeyPatch) -> Api:
    execute(
        execution_api.dsn,
        "INSERT INTO hr.employee_shift_schedule "
        "(employee_id,warehouse_id,work_date,start_time,end_time,assigned_by,assigned_at) "
        "VALUES (5,1,'2026-11-10','07:00','17:00',3,'2026-11-08T09:00Z'), "
        "(11,1,'2026-11-10','07:00','17:00',3,'2026-11-08T09:00Z')",
        "UPDATE ref.customer SET email='t21-synthetic@cfo.test' WHERE id=1",
        "UPDATE ops.customer_order SET committed_date='2026-11-10',"
        "promise_start='2026-11-10T10:00Z',promise_end='2026-11-10T11:00Z' WHERE id=1",
    )

    async def synthetic_history(*args: object) -> driver_history.HistoryProof:
        return driver_history.HistoryProof(complete=True, reasons=())

    monkeypatch.setattr(driver_history, "load_proof", synthetic_history)
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    for kind, at, payload in (
        ("START_PREP", "07:00", {"crew_size": 3}),
        ("GOODS_READY", "07:30", {}),
        ("LOADED", "08:00", {"trip_id": 1}),
        ("LOADED", "08:05", {"trip_id": 2}),
    ):
        response = send(execution_api, WAREHOUSE, kind, f"2026-11-10T{at}:00Z", payload)
        assert response.status_code == 200, response.text
    return execution_api


def dispatched_notifications(api: Api):
    return fetch(
        api.dsn,
        "SELECT id, status, skipped_reason, dedupe_key FROM ops.notification "
        "WHERE order_id=1 AND template='DISPATCHED'",
    )


def depart(api: Api, actor: int, trip: int, key: str):
    response = send(api, actor, "DISPATCHED", DEPARTED_AT, {"trip_id": trip}, key)
    assert response.status_code == 200, response.text
    assert response.json()["order_status"] == "DISPATCHED"
    return response.json()


def assert_both_departed(api: Api) -> None:
    assert fetch(api.dsn, "SELECT status FROM ops.delivery_trip ORDER BY id") == [("on_road",)] * 2
    assert fetch(api.dsn, "SELECT status FROM ops.customer_order WHERE id=1") == [("DISPATCHED",)]
    assert fetch(
        api.dsn,
        "SELECT trip_id FROM ops.milestone_event "
        "WHERE order_id=1 AND event_type='DISPATCHED' ORDER BY trip_id",
    ) == [(1,), (2,)]


def assert_mailpit(api: Api, url: str, expected: int, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(async_url(api.dsn), poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(internal, "get_sessionmaker", lambda: maker)
    monkeypatch.setattr(notification_delivery, "get_sessionmaker", lambda: maker)
    monkeypatch.setenv("INTERNAL_TICK_KEY", "t21-test-key")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1025")
    get_settings.cache_clear()
    before = {message["ID"] for message in _mailpit_messages(url)["messages"]}
    try:
        for processed in (expected, 0):
            response = api.client.post(
                "/api/v1/internal/tick?job=notify_outbox&market=SE",
                headers={"X-Internal-Key": "t21-test-key"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["processed"] == processed
        after = _mailpit_messages(url)["messages"]
        new = [message for message in after if message["ID"] not in before]
        assert len(new) == expected
        notification = dispatched_notifications(api)[0]
        assert notification["status"] == ("sent" if expected else "suppressed")
        if expected:
            with urllib.request.urlopen(f"{url}/api/v1/message/{new[0]['ID']}", timeout=5) as response:
                message = json.load(response)
            assert message["Subject"] == "Your order is on its way"
            assert "Order SE-M6: Delivery dispatched." in message["Text"]
    finally:
        asyncio.run(engine.dispose())


@pytest.mark.parametrize("enabled", [True, False])
def test_US_NOT_01_AC3_two_trips_first_dispatch_only(
    loaded_order: Api, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setenv("NOTIFY_DISPATCHED_ENABLED", str(enabled))
    get_settings.cache_clear()
    key = str(uuid4())
    first = depart(loaded_order, DRIVER, 1, key)
    expected = ("queued", None) if enabled else ("suppressed", "SKIPPED_FLAG_DISABLED")
    notifications = dispatched_notifications(loaded_order)
    assert len(notifications) == 1
    assert tuple(notifications[0][1:]) == (*expected, "1:DISPATCHED")

    depart(loaded_order, 14, 2, str(uuid4()))
    assert depart(loaded_order, DRIVER, 1, key) == first
    assert_both_departed(loaded_order)
    assert dispatched_notifications(loaded_order) == notifications

    mailpit = os.getenv("E2_MAILPIT_URL")
    if mailpit:
        assert_mailpit(loaded_order, mailpit, int(enabled), monkeypatch)

    if not enabled:

        async def suggest_replan(*args: object, **kwargs: object) -> dict[str, int]:
            return {"id": 1}

        monkeypatch.setattr(planning_service, "suggest_replan", suggest_replan)
        deliver = send(
            loaded_order,
            DRIVER,
            "DELIVERED",
            "2026-11-10T09:30:00Z",
            {"trip_id": 1, "recipient_name": "Synthetic recipient"},
        )
        assert deliver.status_code == 200, deliver.text
        fail = send(
            loaded_order,
            14,
            "FAILED",
            "2026-11-10T09:35:00Z",
            {"trip_id": 2, "failure_reason": "customer_absent"},
        )
        assert fail.status_code == 200, fail.text
        assert fail.json()["order_status"] == "FAILED"
        assert fetch(loaded_order.dsn, "SELECT status FROM ops.notification WHERE template='FAILED'") == [
            ("queued",)
        ]


def test_US_NOT_01_AC3_distinct_keys_concurrently_dispatch_both_trips(
    loaded_order: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NOTIFY_DISPATCHED_ENABLED", raising=False)
    get_settings.cache_clear()
    assert get_settings().notify_dispatched_enabled
    ready = Barrier(2, timeout=10)

    def run(actor: int, trip: int) -> None:
        ready.wait()
        depart(loaded_order, actor, trip, str(uuid4()))

    with ThreadPoolExecutor(max_workers=2) as threads:
        first = threads.submit(run, DRIVER, 1)
        second = threads.submit(run, 14, 2)
        first.result()
        second.result()

    assert_both_departed(loaded_order)
    assert [row["status"] for row in dispatched_notifications(loaded_order)] == ["queued"]


def test_US_NOT_01_AC3_dispatched_legacy_key_from_previous_plan_is_preserved(loaded_order: Api) -> None:
    execute(
        loaded_order.dsn,
        rows.run_sql(1, 2),
        rows.plan_sql(2, 1, 1, "superseded"),
        "INSERT INTO ops.notification(order_id,plan_id,template,status,recipient,body,dedupe_key) "
        "VALUES (1,2,'DISPATCHED','sent','t21-synthetic@cfo.test','','1:DISPATCHED:2:DISPATCHED')",
    )
    notifications = dispatched_notifications(loaded_order)
    depart(loaded_order, DRIVER, 1, str(uuid4()))
    depart(loaded_order, 14, 2, str(uuid4()))
    assert_both_departed(loaded_order)
    assert len(notifications) == 1
    assert dispatched_notifications(loaded_order) == notifications
