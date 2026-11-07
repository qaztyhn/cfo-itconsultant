"""alert_service: dedupe chỉ khi cảnh báo còn mở (US-RSK-03 AC2–AC3; 05 mục 6 ux_alert_open_dedupe)."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.errors import DomainError
from app.services import alert_service as al
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR, rows.order_sql(1))
    yield empty_db


def run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def raise_orange(dsn: str) -> int | None:
    return run(
        dsn,
        lambda s: al.raise_alert(
            s,
            market_id=1,
            type_="RISK_ORANGE",
            level="warning",
            message="Order at risk",
            dedupe_key="order:1:RISK_ORANGE",
            target_roles=("dispatcher",),
            order_id=1,
        ),
    )


def test_US_RSK_03_AC2_same_dedupe_key_not_duplicated_while_open(db: str) -> None:
    first = raise_orange(db)
    assert first is not None
    assert raise_orange(db) is None
    assert len(fetch(db, "SELECT 1 FROM ops.alert")) == 1


def test_US_RSK_03_AC2_ack_records_employee_and_time_once(db: str) -> None:
    alert_id = raise_orange(db)
    assert alert_id is not None
    run(db, lambda s: al.ack(s, alert_id, employee_id=1, now=NOW))
    later = datetime(2026, 11, 12, 11, 0, tzinfo=UTC)
    run(db, lambda s: al.ack(s, alert_id, employee_id=2, now=later))  # đã ack: giữ người/giờ đầu tiên
    (row,) = fetch(db, "SELECT acknowledged_by, acknowledged_at, resolved_at FROM ops.alert")
    assert (row["acknowledged_by"], row["acknowledged_at"], row["resolved_at"]) == (1, NOW, None)


def test_ack_unknown_alert_is_not_found(db: str) -> None:
    with pytest.raises(DomainError) as caught:
        run(db, lambda s: al.ack(s, 999, employee_id=1, now=NOW))
    assert caught.value.code == "NOT_FOUND"


def test_US_RSK_03_AC3_new_alert_after_previous_resolved(db: str) -> None:
    first = raise_orange(db)
    assert run(db, lambda s: al.resolve(s, "order:1:RISK_ORANGE", now=NOW)) == 1
    second = raise_orange(db)
    assert second is not None and second != first
    assert run(db, lambda s: al.resolve(s, "order:1:RISK_ORANGE", now=NOW)) == 1
    assert run(db, lambda s: al.resolve(s, "order:1:RISK_ORANGE", now=NOW)) == 0  # không còn alert mở
