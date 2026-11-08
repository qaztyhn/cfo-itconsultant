"""T07 incremental source ingestion (04 §5.2, DEC-SRC-D1-001, DEC-ROUTING-002).

One database lease per market/entity, a durable running record, transactional row savepoints,
whole-run rollback on page failure and independent submitted/cancelled checkpoints.
No source writes, automatic routing/holds/approval or unreviewed stock persistence.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.ingestion_feed import FeedRecord, read_feed
from app.adapters.registry import AdapterRegistry
from app.adapters.rest_adapter import RestMarketAdapter
from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.domain.models.ref import Market
from app.domain.models.stg import SyncCheckpoint, SyncReject, SyncRun
from app.services.alert_service import raise_alert, resolve
from app.services.ingest_types import IngestResult, RowOutcome, RowRejected, aware

type RowWriter = Callable[[AsyncSession, Market, FeedRecord, int, datetime], Awaitable[RowOutcome]]
ENTITIES = ("customers", "products", "orders", "inbound", "fleet")
INITIAL_CHECKPOINT = datetime.min.replace(tzinfo=UTC)


async def synchronize(
    market_code: str,
    entity: str,
    *,
    maker: async_sessionmaker[AsyncSession],
    writer: RowWriter,
    adapter: RestMarketAdapter | None = None,
    now: datetime | None = None,
    retry_run_id: int | None = None,
) -> IngestResult:
    """Retry creates a new API run; explicit partial retry replays its original lower bound.

    Complete partial runs may checkpoint per 04 §5.2; invalid times and blocked downstream
    work pin the affected feed for retry. Transport failure never checkpoints.
    """
    if entity not in ENTITIES:
        raise ValueError("Unsupported or unintegrated ingestion entity")
    started = aware(now or clock.now())
    cancelled: asyncio.CancelledError | None = None
    async with maker() as session, session.begin():
        market = await session.scalar(select(Market).where(Market.code == market_code))
        if market is None:
            raise DomainError("NOT_FOUND", "Source market not found.")
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"ingest:{market.id}:{entity}"},
        )
        if not locked:
            raise DomainError("SYNC_IN_PROGRESS", "A synchronization is already running.")
        cfg = MarketConfig.model_validate(market.config)
        if cfg.sync.overlap_min != 2:
            raise ValueError("T07 requires the approved two-minute source overlap")
        feeds = ("orders", "orders:cancelled") if entity == "orders" else (entity,)
        checkpoints = {feed: await session.get(SyncCheckpoint, (market.id, feed)) for feed in feeds}
        bounds: dict[str, datetime | None] = {
            feed: (
                max(INITIAL_CHECKPOINT, point.last_updated_since - timedelta(minutes=2)) if point else None
            )
            for feed, point in checkpoints.items()
        }
        if retry_run_id is not None:
            prior = await session.get(SyncRun, retry_run_id)
            if prior is None or (prior.market_id, prior.entity, prior.kind) != (market.id, entity, "api"):
                raise ValueError("Retry run does not match this API feed")
            if prior.status not in {"failed", "partial"}:
                raise ValueError("Only a failed or partial API run may be retried")
            bounds = {feed: prior.checkpoint_from for feed in feeds}
        # The lease proves old running rows have no live worker in this implementation.
        await session.execute(
            update(SyncRun)
            .where(
                SyncRun.market_id == market.id,
                SyncRun.entity == entity,
                SyncRun.kind == "api",
                SyncRun.status == "running",
            )
            .values(status="failed", finished_at=started, error="INTERRUPTED_RUN")
        )
        async with maker() as journal, journal.begin():
            run = SyncRun(
                market_id=market.id,
                entity=entity,
                kind="api",
                status="running",
                started_at=started,
                checkpoint_from=(
                    min(value for value in bounds.values() if value is not None)
                    if all(value is not None for value in bounds.values())
                    else None
                ),
            )
            journal.add(run)
            await journal.flush()
            run_id = run.id
        count_in = count_ok = count_rejected = 0
        greatest: dict[str, datetime] = {}
        pinned: set[str] = set()
        failure: str | None = None
        try:
            async with session.begin_nested():
                if adapter is None:
                    registry = AdapterRegistry()
                    registry.configure(
                        market.code,
                        market.source_base_url,
                        market.source_api_key_ref,
                        market_timezone=market.timezone,
                    )
                    reader = registry.get(market.code)
                else:
                    if adapter.market_code != market.code:
                        raise ValueError("Adapter market does not match synchronization scope")
                    reader = adapter
                for feed in feeds:
                    async for record in read_feed(reader, feed, bounds[feed]):
                        count_in += 1
                        code = record.reject_code
                        if record.updated_at is None or record.updated_at > started:
                            code = code or "BAD_DATE"
                            pinned.add(feed)
                        else:
                            greatest[feed] = max(greatest.get(feed, INITIAL_CHECKPOINT), record.updated_at)
                        if not code:
                            try:
                                async with session.begin_nested():
                                    outcome = await writer(session, market, record, run_id, started)
                                    await session.flush()
                                    code = outcome.reject_code
                            except RowRejected as error:
                                code = str(error)
                            except IntegrityError:
                                code = "INVALID_SOURCE_ROW"
                        if code:
                            count_rejected += 1
                            session.add(
                                SyncReject(
                                    run_id=run_id,
                                    external_key=record.external_key,
                                    reason_code=code,
                                    reason=code,
                                    raw=None,
                                )
                            )
                            if code in {
                                "REPLAN_DEPENDENCY_UNAVAILABLE",
                                "RISK_DEPENDENCY_UNAVAILABLE",
                                "ORDER_STATE_LOCKED",
                                "ROUTING_UNRESOLVED",
                            }:
                                pinned.add(feed)
                        else:
                            count_ok += 1
                    if feed in greatest and feed not in pinned:
                        old = checkpoints[feed]
                        target = max(greatest[feed], old.last_updated_since if old else INITIAL_CHECKPOINT)
                        await session.execute(
                            insert(SyncCheckpoint)
                            .values(market_id=market.id, entity=feed, last_updated_since=target)
                            .on_conflict_do_update(
                                index_elements=[SyncCheckpoint.market_id, SyncCheckpoint.entity],
                                set_={"last_updated_since": target},
                            )
                        )
        except (Exception, asyncio.CancelledError) as error:
            failure = "SOURCE_SYNC_FAILED"
            count_ok = count_rejected = 0
            if isinstance(error, asyncio.CancelledError):
                cancelled = error
        status = "failed" if failure else "partial" if count_rejected else "ok"
        saved = await session.get(SyncRun, run_id)
        assert saved is not None
        saved.status, saved.rows_in, saved.rows_ok, saved.rows_rejected = (
            status,
            count_in,
            count_ok,
            count_rejected,
        )
        saved.finished_at = aware(now or clock.now())
        saved.checkpoint_to = max(greatest.values()) if not failure and greatest else None
        saved.data_as_of, saved.error = saved.checkpoint_to, failure
        key = f"SYNC_FAILED:{market.id}:{entity}"
        if failure:
            await raise_alert(
                session,
                market_id=market.id,
                type_="SYNC_FAILED",
                level="warning",
                message="Source synchronization failed; retry after checking the source connection.",
                dedupe_key=key,
                target_roles=("admin",),
            )
        elif status == "ok":
            await resolve(session, key, now=started)
    if cancelled is not None:
        raise cancelled
    return IngestResult(run_id, status, count_in, count_ok, count_rejected)
