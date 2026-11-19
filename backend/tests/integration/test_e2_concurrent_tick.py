"""Scheduler and HTTP tick contend for one real PostgreSQL outbox row."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
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


def test_US_NOT_03_AC4_scheduler_and_tick_do_not_send_same_row_twice(empty_db: str, monkeypatch) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        "UPDATE ops.customer_order SET promise_start='2026-11-10T08:00Z',"
        "promise_end='2026-11-10T10:00Z' WHERE id=1",
        "INSERT INTO ops.notification(order_id,template,recipient,body,scheduled_for,dedupe_key) "
        "VALUES (1,'CONFIRMED','synthetic@cfo.test','',"
        "'2026-11-04T00:00Z','e2:concurrent:1')",
    )
    engine = create_async_engine(async_url(empty_db), poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        internal, "get_settings", lambda: SimpleNamespace(internal_tick_key="e2-key", app_env="test")
    )
    monkeypatch.setattr(internal, "get_sessionmaker", lambda: maker)
    monkeypatch.setattr(notification_delivery, "get_sessionmaker", lambda: maker)
    clock.set_now(NOW)
    entered, release = asyncio.Event(), asyncio.Event()
    sends: list[int] = []

    class PausedTransport:
        async def send(self, *, recipient: str, subject: str, text: str) -> None:
            sends.append(1)
            entered.set()
            await release.wait()

    monkeypatch.setattr(notification_delivery, "SmtpEmailProvider", lambda *args, **kwargs: PausedTransport())

    async def race() -> tuple[int, int]:
        scheduler = await create_scheduler(maker=maker)
        job = next(job for job in scheduler.get_jobs() if job.id == "notify_outbox:SE")
        scheduled = asyncio.create_task(job.func(**job.kwargs))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/internal/tick?job=notify_outbox&market=SE",
                    headers={"X-Internal-Key": "e2-key"},
                )
            assert response.status_code == 200
            tick_count = response.json()["processed"]
        finally:
            release.set()
        return await scheduled, tick_count

    try:
        assert asyncio.run(race()) == (1, 0)
        assert len(sends) == 1
        assert fetch(empty_db, "SELECT status,attempts FROM ops.notification")[0] == ("sent", 1)
        assert (
            fetch(empty_db, "SELECT count(*) FROM audit.decision_log WHERE action='NOTIFICATION_SENT'")[0][0]
            == 1
        )
    finally:
        asyncio.run(engine.dispose())
