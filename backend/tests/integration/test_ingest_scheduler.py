import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.rest_adapter import RestMarketAdapter
from app.core.errors import DomainError
from app.jobs.ingest import IngestBatchError, run_market
from app.jobs.scheduler import create_scheduler
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_ingest_references import product
from tests.integration.test_ingest_runner import NOW, page
from tests.integration.test_ingest_runner import db as db

pytestmark = pytest.mark.integration


def empty_stock() -> httpx.Response:
    return httpx.Response(200, json={"batch_id": 1, "as_of": NOW.isoformat(), "item_count": 0, "items": []})


def test_T07_one_failed_feed_does_not_suppress_other_sync_runs_including_stock(db: str) -> None:
    calls: list[str] = []

    def source(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.method == "GET"
        if request.url.path == "/customers":
            return httpx.Response(500, text="private-credential")
        if request.url.path == "/stock":
            return empty_stock()
        return page([product()] if request.url.path == "/products" else [])

    async def scenario():
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        try:
            return await run_market(
                "SE",
                maker=async_sessionmaker(engine, expire_on_commit=False),
                now=NOW,
                adapter=RestMarketAdapter(
                    "SE", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
                ),
            )
        finally:
            await engine.dispose()

    batch = asyncio.run(scenario())
    assert not batch.ok and len(batch.runs) == 6 and not batch.errors
    assert [run.status for run in batch.runs] == ["failed", "ok", "ok", "ok", "ok", "ok"]
    assert calls == [
        "/customers",
        "/products",
        "/orders",
        "/orders",
        "/inbound",
        "/fleet/calendar",
        "/stock",
        "/products",
        "/stock",
    ]
    assert fetch(db, "SELECT count(*) FROM stg.sync_run")[0][0] == 6
    assert fetch(db, "SELECT target_roles FROM ops.alert WHERE type='SYNC_FAILED'")[0][0] == ["admin"]


def test_T07_scheduler_build_is_market_scoped_configured_and_has_no_implicit_start(db: str) -> None:
    execute(
        db,
        "UPDATE ref.market SET config='{"
        + '"sync":{"interval_min":10,"overlap_min":2}'
        + "}'::jsonb WHERE code='ZZ'",
    )
    calls: list[str] = []

    def adapter(code: str) -> RestMarketAdapter:
        def source(request: httpx.Request) -> httpx.Response:
            calls.append(code)
            return empty_stock() if request.url.path == "/stock" else page([])

        return RestMarketAdapter(
            code, "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
        )

    async def scenario() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        try:
            scheduler = await create_scheduler(
                maker=async_sessionmaker(engine, expire_on_commit=False), now=NOW, adapter_factory=adapter
            )
            assert not scheduler.running
            jobs = {job.id: job for job in scheduler.get_jobs()}
            assert set(jobs) == {"ingest:SE", "ingest:ZZ"}
            assert jobs["ingest:SE"].trigger.interval == timedelta(minutes=5)
            assert jobs["ingest:ZZ"].trigger.interval == timedelta(minutes=10)
            assert str(jobs["ingest:SE"].trigger.timezone) == "Europe/Stockholm"
            assert jobs["ingest:SE"].max_instances == 1 and jobs["ingest:SE"].coalesce
            assert jobs["ingest:SE"].trigger.get_next_fire_time(None, NOW) == NOW + timedelta(minutes=5)
            await jobs["ingest:SE"].func(**jobs["ingest:SE"].kwargs)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
    assert set(calls) == {"SE"} and len(calls) == 9
    assert fetch(db, "SELECT count(*) FROM stg.sync_run WHERE market_id=1 AND status='ok'")[0][0] == 6


def test_T07_scheduler_does_not_report_an_incomplete_batch_as_success(db: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        try:
            scheduler = await create_scheduler(
                maker=async_sessionmaker(engine, expire_on_commit=False),
                now=NOW,
                adapter_factory=lambda code: RestMarketAdapter(
                    code,
                    "https://source.test",
                    "synthetic-key",
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(503, text="private-source-error")
                    ),
                ),
            )
            job = next(job for job in scheduler.get_jobs() if job.id == "ingest:SE")
            with pytest.raises(IngestBatchError) as error:
                await job.func(**job.kwargs)
            assert "private" not in str(error.value)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
    assert fetch(db, "SELECT count(*) FROM stg.sync_run WHERE status='failed'")[0][0] == 6


def test_T07_invalid_scheduler_interval_is_rejected_without_activating_jobs(db: str) -> None:
    execute(db, "UPDATE ref.market SET config='{" + '"sync":{"interval_min":0}' + "}'::jsonb WHERE code='SE'")

    async def scenario() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        try:
            with pytest.raises(ValueError, match="positive"):
                await create_scheduler(maker=async_sessionmaker(engine, expire_on_commit=False), now=NOW)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
    assert not fetch(db, "SELECT * FROM stg.sync_run")


def test_T07_explicitly_started_apscheduler_executes_an_ingestion_job(db: str, monkeypatch) -> None:
    import apscheduler.executors.base
    import apscheduler.schedulers.base
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

    class FrozenSchedulerDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    # The library's timer uses its own wall clock, separate from CFO's injected business clock.
    monkeypatch.setattr(apscheduler.schedulers.base, "datetime", FrozenSchedulerDatetime)
    monkeypatch.setattr(apscheduler.executors.base, "datetime", FrozenSchedulerDatetime)

    async def scenario() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        scheduler = None
        try:
            scheduler = await create_scheduler(
                maker=async_sessionmaker(engine, expire_on_commit=False),
                now=NOW,
                adapter_factory=lambda code: RestMarketAdapter(
                    code,
                    "https://source.test",
                    "synthetic-key",
                    transport=httpx.MockTransport(
                        lambda request: empty_stock() if request.url.path == "/stock" else page([])
                    ),
                ),
            )
            scheduler.remove_job("ingest:ZZ")
            completed = asyncio.Event()
            errors: list[object] = []

            def listener(event) -> None:
                if event.exception is not None:
                    errors.append(type(event.exception).__name__)
                completed.set()

            scheduler.add_listener(listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
            scheduler.start(paused=True)
            scheduler.modify_job("ingest:SE", next_run_time=NOW)
            scheduler.resume()
            await asyncio.wait_for(completed.wait(), timeout=10)
            assert not errors
        finally:
            if scheduler is not None and scheduler.running:
                scheduler.shutdown(wait=False)
                await asyncio.sleep(0)
            await engine.dispose()

    asyncio.run(scenario())
    assert fetch(db, "SELECT count(*) FROM stg.sync_run WHERE status='ok'")[0][0] == 6


def test_T07_periodic_timer_uses_library_time_independent_of_frozen_business_clock(
    db: str, monkeypatch
) -> None:
    import apscheduler.triggers.interval

    technical_now = NOW + timedelta(days=10)

    class FrozenTimer(datetime):
        @classmethod
        def now(cls, tz=None):
            return technical_now.astimezone(tz) if tz else technical_now.replace(tzinfo=None)

    monkeypatch.setattr(apscheduler.triggers.interval, "datetime", FrozenTimer)

    async def scenario() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        try:
            scheduler = await create_scheduler(maker=async_sessionmaker(engine, expire_on_commit=False))
            job = next(job for job in scheduler.get_jobs() if job.id == "ingest:SE")
            assert job.trigger.start_date == technical_now + timedelta(minutes=5)
            assert not scheduler.running
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_T07_two_market_workers_cannot_interleave_dependent_feeds(db: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        entered, release = asyncio.Event(), asyncio.Event()

        async def source(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/customers":
                entered.set()
                await release.wait()
            return empty_stock() if request.url.path == "/stock" else page([])

        adapter = RestMarketAdapter(
            "SE", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
        )
        first = asyncio.create_task(run_market("SE", maker=maker, adapter=adapter, now=NOW))
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            with pytest.raises(DomainError) as error:
                await run_market("SE", maker=maker, adapter=adapter, now=NOW)
            assert error.value.code == "SYNC_IN_PROGRESS"
        finally:
            release.set()
            assert (await first).ok
            await engine.dispose()

    asyncio.run(scenario())
    assert fetch(db, "SELECT count(*) FROM stg.sync_run")[0][0] == 6
