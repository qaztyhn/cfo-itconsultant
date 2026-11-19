"""Optional real PostgreSQL and Mailpit E2 smoke; set E2_MAILPIT_URL explicitly."""

import asyncio
import json
import os
import urllib.request
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.api.v1 import internal
from app.core import clock
from app.jobs.scheduler import create_scheduler
from app.main import app
from app.services import notification_delivery
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 11, tzinfo=UTC)


def _mailpit_messages(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/api/v1/messages", timeout=5) as response:
        return json.load(response)


def test_US_NOT_01_AC3_tick_sends_confirmed_once_to_mailpit(empty_db: str, monkeypatch) -> None:
    mailpit = os.environ.get("E2_MAILPIT_URL")
    if not mailpit:
        pytest.skip("E2_MAILPIT_URL absent: real SMTP/Mailpit NOT VERIFIED")
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        "UPDATE ops.customer_order SET committed_date='2026-11-10',promise_start='2026-11-10T08:00Z',"
        "promise_end='2026-11-10T10:00Z' WHERE id=1",
        "INSERT INTO ops.notification(order_id,template,recipient,body,scheduled_for,dedupe_key) "
        "VALUES (1,'CONFIRMED','e2-synthetic@cfo.test','',"
        "'2026-11-04T00:00Z','e2:confirmed:1')",
    )
    engine = create_async_engine(async_url(empty_db), poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        internal, "get_settings", lambda: SimpleNamespace(internal_tick_key="e2-key", app_env="test")
    )
    monkeypatch.setattr(internal, "get_sessionmaker", lambda: maker)
    monkeypatch.setattr(notification_delivery, "get_sessionmaker", lambda: maker)
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1025")
    clock.set_now(NOW)
    client = TestClient(app)
    before = _mailpit_messages(mailpit)["total"]
    headers = {"X-Internal-Key": "e2-key"}
    try:
        first = client.post("/api/v1/internal/tick?job=notify_outbox&market=SE", headers=headers)
        assert first.status_code == 200 and first.json()["processed"] == 1
        assert fetch(empty_db, "SELECT status,sent_at IS NOT NULL FROM ops.notification")[0] == (
            "sent",
            True,
        )
        assert fetch(empty_db, "SELECT action FROM audit.decision_log")[0][0] == "NOTIFICATION_SENT"
        after = _mailpit_messages(mailpit)
        assert after["total"] == before + 1
        message_id = after["messages"][0]["ID"]
        with urllib.request.urlopen(f"{mailpit}/api/v1/message/{message_id}", timeout=5) as response:
            detail = json.load(response)
        assert "ZZ-000001" in detail["Text"]
        assert "Delivery window:" in detail["Text"]
        again = client.post("/api/v1/internal/tick?job=notify_outbox&market=SE", headers=headers)
        assert again.status_code == 200 and again.json()["processed"] == 0
        assert _mailpit_messages(mailpit)["total"] == before + 1

        execute(
            empty_db,
            "INSERT INTO ops.notification(order_id,template,recipient,body,scheduled_for,dedupe_key) "
            "VALUES (1,'CONFIRMED','e2-synthetic@cfo.test','',"
            "'2026-11-04T00:00Z','e2:confirmed:2')",
        )

        async def scheduled_once() -> None:
            scheduler = await create_scheduler(maker=maker)
            result = asyncio.Event()
            errors: list[object] = []

            def completed(event) -> None:
                if event.job_id == "notify_outbox:SE":
                    if event.exception is not None:
                        errors.append(event.exception)
                    result.set()

            scheduler.add_listener(completed, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            try:
                scheduler.start(paused=True)
                scheduler.modify_job("notify_outbox:SE", next_run_time=datetime.now(UTC))
                scheduler.resume()
                await asyncio.wait_for(result.wait(), timeout=10)
                assert not errors
            finally:
                scheduler.shutdown(wait=False)

        asyncio.run(scheduled_once())
        assert fetch(empty_db, "SELECT count(*) FROM ops.notification WHERE status='sent'")[0][0] == 2
        assert _mailpit_messages(mailpit)["total"] == before + 2
    finally:
        asyncio.run(engine.dispose())
