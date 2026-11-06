"""record_decision() (09 bất biến 13–14, US-LOG-01 AC1/AC4) và GET /health (06 mục 15) trên PostgreSQL.

Test là hàm sync (giống test migration); phần async chạy bằng asyncio.run vì helper fetch/execute tự mở loop.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import timedelta
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core import logging as cfo_logging
from app.core.correlation import correlation_id_var
from app.core.db import session_scope, to_async_url
from app.core.errors import DomainError
from app.deps import get_db
from app.main import create_app
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch

pytestmark = pytest.mark.integration

Maker = async_sessionmaker[AsyncSession]


@pytest.fixture
def head_db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    yield empty_db


@pytest.fixture
def maker(head_db: str) -> Maker:
    return async_sessionmaker(create_async_engine(to_async_url(head_db), poolclass=NullPool))


@pytest.fixture
def correlation() -> Iterator[str]:
    cid = str(uuid.uuid4())
    token = correlation_id_var.set(cid)
    yield cid
    correlation_id_var.reset(token)


def _record(maker: Maker, action: Action, *, rollback: bool = False, **kwargs: object) -> int:
    """Gọi record_decision trong một transaction; rollback=True mô phỏng nghiệp vụ thất bại."""

    async def scenario() -> int:
        async with maker() as session:
            new_id = await record_decision(session, action, **kwargs)  # type: ignore[arg-type]
            await (session.rollback() if rollback else session.commit())
            return new_id

    return asyncio.run(scenario())


# --- record_decision ---------------------------------------------------------------------------------


def test_US_LOG_01_AC1_record_decision_inserts_one_row_with_correlation_id(
    head_db: str, maker: Maker, correlation: str
) -> None:
    new_id = _record(
        maker,
        Action.ALT_SELECTED,
        entity="plan",
        entity_id="77",
        order_id=4021,
        plan_id=77,
        reason_code="customer_request",
        before={"rank": 1},
        after={"rank": 2},
        snapshot={"score": "0.25"},
        actor_role="dispatcher",
    )
    (row,) = fetch(head_db, "SELECT * FROM audit.decision_log")
    assert row["id"] == new_id and str(row["correlation_id"]) == correlation
    assert (row["action"], row["entity"], row["entity_id"], row["order_id"], row["plan_id"]) == (
        "ALT_SELECTED",
        "plan",
        "77",
        4021,
        77,
    )
    assert json.loads(row["before"]) == {"rank": 1} and json.loads(row["after"]) == {"rank": 2}
    assert row["actor_role"] == "dispatcher"
    assert row["ts"] == clock.now()  # thời điểm quyết định theo đồng hồ hệ thống (APP_NOW)
    assert row["created_at"] != row["ts"]  # created_at = lúc ghi bản ghi (ASM-001)


def test_record_decision_rolls_back_with_business_transaction(
    head_db: str, maker: Maker, correlation: str
) -> None:
    _record(maker, Action.PLAN_PROPOSED, entity="order", entity_id="1", order_id=1, rollback=True)
    assert fetch(head_db, "SELECT 1 FROM audit.decision_log") == []


@pytest.mark.parametrize("reason_text", [None, "", "   "])
def test_reason_required_actions_reject_missing_reason(
    head_db: str, maker: Maker, reason_text: str | None
) -> None:
    with pytest.raises(DomainError) as caught:
        _record(maker, Action.ORDER_CANCELLED, entity="order", entity_id="1", reason_text=reason_text)
    assert caught.value.code == "REASON_REQUIRED" and caught.value.http_status == 422
    assert fetch(head_db, "SELECT 1 FROM audit.decision_log") == []


def test_US_LOG_01_AC4_decision_log_and_technical_log_share_correlation_id(
    head_db: str, maker: Maker, correlation: str
) -> None:
    record = cfo_logging.build_record("api", "plan.approved", order_id=1)
    _record(maker, Action.PLAN_APPROVED, entity="plan", entity_id="1", order_id=1)
    (row,) = fetch(head_db, "SELECT correlation_id FROM audit.decision_log")
    assert str(row["correlation_id"]) == record["correlation_id"] == correlation


def test_record_decision_outside_request_generates_correlation_id(head_db: str, maker: Maker) -> None:
    _record(maker, Action.HOLD_EXPIRED, entity="planning_run", entity_id="5")
    (row,) = fetch(head_db, "SELECT correlation_id FROM audit.decision_log")
    assert uuid.UUID(str(row["correlation_id"]))


# --- GET /health -------------------------------------------------------------------------------------


def _client(dsn: str) -> Callable[[], TestClient]:
    maker = async_sessionmaker(create_async_engine(to_async_url(dsn), poolclass=NullPool))

    async def test_db() -> AsyncIterator[AsyncSession]:
        async for session in session_scope(maker):
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = test_db
    return lambda: TestClient(app)


def test_health_ok_without_auth(head_db: str) -> None:
    with _client(head_db)() as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "last_sync_age_min": None, "notify_queue": 0}


def test_health_reports_age_of_last_successful_sync(head_db: str) -> None:
    finished = (clock.now() - timedelta(minutes=30)).isoformat()
    execute(
        head_db,
        "INSERT INTO stg.sync_run (market_id, entity, status, finished_at) "
        f"VALUES (1, 'orders', 'ok', '{finished}')",
        "INSERT INTO stg.sync_run (market_id, entity, status, finished_at) "
        f"VALUES (1, 'stock', 'failed', '{clock.now().isoformat()}')",
    )
    with _client(head_db)() as client:
        assert client.get("/api/v1/health").json()["last_sync_age_min"] == 30


def test_health_counts_only_queued_notifications(head_db: str) -> None:
    sql = (
        "INSERT INTO ops.notification (order_id, template, channel, recipient, body, status, dedupe_key) "
        "VALUES (1, 'CONFIRMED', 'email', 'r@cfo.test', 'Body', '{status}', '{key}')"
    )
    execute(
        head_db,
        *rows.REF_HR,
        rows.order_sql(1),
        *(
            sql.format(status=status, key=status + str(i))
            for i, status in enumerate(("queued", "queued", "sent"))
        ),
        sql.format(status="draft", key="draft"),
    )
    with _client(head_db)() as client:
        assert client.get("/api/v1/health").json()["notify_queue"] == 2


def test_health_503_when_database_unavailable() -> None:
    with _client("postgresql://cfo@127.0.0.1:1/none")() as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["status"] == "error" and response.json()["db"] == "unavailable"
    assert "127.0.0.1" not in response.text


def test_invalid_correlation_header_does_not_break_decision_log(head_db: str) -> None:
    """Header 'request-123' không được làm INSERT decision_log lỗi và rollback nghiệp vụ."""
    maker = async_sessionmaker(create_async_engine(to_async_url(head_db), poolclass=NullPool))

    async def test_db() -> AsyncIterator[AsyncSession]:
        async for session in session_scope(maker):
            yield session

    probe = APIRouter()

    @probe.post("/_probe/decide")
    async def decide(db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, int]:
        return {"id": await record_decision(db, Action.PLAN_PROPOSED, "order", "1", order_id=1)}

    app = create_app()
    app.include_router(probe, prefix="/api/v1")
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        response = client.post("/api/v1/_probe/decide", headers={"X-Correlation-ID": "request-123"})
    assert response.status_code == 200, response.text
    (row,) = fetch(head_db, "SELECT correlation_id FROM audit.decision_log")
    assert str(row["correlation_id"]) == response.headers["X-Correlation-ID"]
