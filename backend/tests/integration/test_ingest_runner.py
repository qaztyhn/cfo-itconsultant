import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters.ingestion_feed import FeedRecord
from app.adapters.reference_wire import SourceCustomer
from app.adapters.rest_adapter import RestMarketAdapter
from app.core.errors import DomainError
from app.domain.models.ref import Customer, Market
from app.services.ingest_service import synchronize
from app.services.ingest_types import RowOutcome
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


@pytest.fixture
def db(empty_db: str) -> str:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR)
    return empty_db


def item(key: str, **changes: object) -> dict[str, object]:
    return {
        "id": key,
        "type": "business",
        "name": "Synthetic private name",
        "email": "private@example.test",
        "phone": None,
        "updated_at": NOW.isoformat(),
        **changes,
    }


def page(items: list[dict[str, object]], number: int = 1, total: int | None = None) -> httpx.Response:
    size = len(items) if total is None else total
    return httpx.Response(
        200,
        headers={"X-Total-Count": str(size)},
        json={"items": items, "page": number, "page_size": 50, "total": size},
    )


async def write(session, market: Market, record: FeedRecord, run_id: int, now: datetime) -> RowOutcome:
    value = record.value
    assert isinstance(value, SourceCustomer)
    await session.execute(
        insert(Customer)
        .values(market_id=market.id, external_ref=value.id, type=value.type, name=value.name)
        .on_conflict_do_update(
            index_elements=[Customer.market_id, Customer.external_ref], set_={"name": value.name}
        )
    )
    return RowOutcome(changed=True)


def run(db: str, source: Callable[[httpx.Request], httpx.Response], *, retry_run_id: int | None = None):
    async def scenario():
        engine = create_async_engine(async_url(db), poolclass=NullPool, hide_parameters=True)
        try:
            return await synchronize(
                "ZZ",
                "customers",
                maker=async_sessionmaker(engine, expire_on_commit=False),
                writer=write,
                adapter=RestMarketAdapter(
                    "ZZ", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
                ),
                now=NOW,
                retry_run_id=retry_run_id,
            )
        finally:
            await engine.dispose()

    return asyncio.run(scenario())


def test_US_INT_01_AC2_duplicate_run_upserts_once_and_keeps_history(db: str) -> None:
    first = run(db, lambda request: page([item("C2")]))
    second = run(db, lambda request: page([item("C2")]))
    assert first.status == second.status == "ok" and first.rows_ok == second.rows_ok == 1
    assert first.run_id != second.run_id
    assert fetch(db, "SELECT count(*) FROM ref.customer WHERE external_ref='C2'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM stg.sync_run WHERE status='ok'")[0][0] == 2
    assert fetch(db, "SELECT last_updated_since FROM stg.sync_checkpoint")[0][0] == NOW


def test_US_INT_01_AC3_bad_row_does_not_prevent_good_row_and_rejects_do_not_echo_pii(db: str) -> None:
    result = run(db, lambda request: page([item("C2", updated_at="private-invalid-time"), item("C3")]))
    assert (result.status, result.rows_in, result.rows_ok, result.rows_rejected) == ("partial", 2, 1, 1)
    reject = fetch(db, "SELECT reason_code,reason,raw::text FROM stg.sync_reject")[0]
    assert reject["reason_code"] == "BAD_DATE" and reject["raw"] in (None, "null")
    assert "private" not in str(reject)
    assert fetch(db, "SELECT count(*) FROM ref.customer WHERE external_ref='C3'")[0][0] == 1
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")  # invalid source time cannot be skipped.


def test_US_INT_01_AC4_page_failure_rolls_back_data_and_checkpoint_then_retry_recovers(db: str) -> None:
    def source(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params["page"])
        if number == 2:
            return httpx.Response(500, text="private@example.test synthetic-key")
        return page([item(f"C{i:03d}") for i in range(50)], total=51)

    failed = run(db, source)
    assert failed.status == "failed" and failed.rows_ok == 0
    assert fetch(db, "SELECT count(*) FROM ref.customer")[0][0] == 1  # pre-existing fixture only.
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='SYNC_FAILED'")[0][0] == 1
    again = run(db, source)
    assert again.status == "failed" and fetch(db, "SELECT count(*) FROM ops.alert")[0][0] == 1
    recovered = run(db, lambda request: page([item("C2")]), retry_run_id=failed.run_id)
    assert recovered.status == "ok"
    assert fetch(db, "SELECT count(*) FROM stg.sync_run WHERE status='failed'")[0][0] == 2
    assert fetch(db, "SELECT resolved_at IS NOT NULL FROM ops.alert")[0][0]
    assert fetch(db, "SELECT error FROM stg.sync_run WHERE status='failed'")[0][0] == "SOURCE_SYNC_FAILED"


def test_US_INT_01_AC5_checkpoint_overlap_and_partial_retry_original_bound(db: str) -> None:
    run(db, lambda request: page([item("C2")]))
    bounds: list[datetime] = []

    def source(request: httpx.Request) -> httpx.Response:
        bounds.append(datetime.fromisoformat(request.url.params["updated_since"]))
        return page([item("C3", name=None)])

    partial = run(db, source)
    assert partial.status == "partial" and bounds == [NOW - timedelta(minutes=2)]
    run(
        db,
        lambda request: (
            bounds.append(datetime.fromisoformat(request.url.params["updated_since"])) or page([item("C3")])
        ),
        retry_run_id=partial.run_id,
    )
    assert bounds[-1] == NOW - timedelta(minutes=2)


def test_US_ADM_01_AC2_concurrent_worker_refused_and_running_run_is_visible(db: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        entered, release = asyncio.Event(), asyncio.Event()

        async def source(request: httpx.Request) -> httpx.Response:
            entered.set()
            await release.wait()
            return page([item("C2")])

        adapter = RestMarketAdapter(
            "ZZ", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
        )
        first = asyncio.create_task(
            synchronize("ZZ", "customers", maker=maker, writer=write, adapter=adapter, now=NOW)
        )
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            async with maker() as reader:
                from sqlalchemy import text

                assert (
                    await reader.scalar(text("SELECT count(*) FROM stg.sync_run WHERE status='running'")) == 1
                )
            with pytest.raises(DomainError) as error:
                await synchronize("ZZ", "customers", maker=maker, writer=write, adapter=adapter, now=NOW)
            assert error.value.code == "SYNC_IN_PROGRESS"
        finally:
            release.set()
            await first
            await engine.dispose()

    asyncio.run(scenario())
