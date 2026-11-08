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

from app.adapters.ingestion_feed import FeedRecord, StockFeedValue, read_feed
from app.adapters.registry import AdapterRegistry
from app.adapters.rest_adapter import RestMarketAdapter
from app.core import clock
from app.core.config import MarketConfig
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder
from app.domain.models.ref import Market
from app.domain.models.stg import SyncCheckpoint, SyncReject, SyncRun
from app.services import ingest_orders as order_writer
from app.services import ingest_references
from app.services import ingest_stock as stock_writer
from app.services.alert_service import raise_alert, resolve
from app.services.ingest_types import (
    BatchRejected,
    IngestResult,
    ReplanSource,
    RowOutcome,
    RowRejected,
    SourceRisk,
    aware,
)

type RowWriter = Callable[[AsyncSession, Market, FeedRecord, int, datetime], Awaitable[RowOutcome]]
ENTITIES = ("customers", "products", "orders", "inbound", "fleet")
SUPPORTED_ENTITIES = (*ENTITIES, "stock")  # Explicit stock diagnostics fail closed pending the scope handoff.
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
    finalize: Callable[[AsyncSession, Market], Awaitable[None]] | None = None,
) -> IngestResult:
    """Retry creates a new API run; explicit partial retry replays its original lower bound.

    Complete partial runs may checkpoint per 04 §5.2; invalid times and blocked downstream
    work pin the affected feed for retry. Transport failure never checkpoints.
    """
    if entity not in SUPPORTED_ENTITIES:
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
                        count_in += record.weight
                        code = record.reject_code
                        if record.updated_at is None or record.updated_at > started:
                            if entity == "stock":
                                raise BatchRejected("BAD_DATE")
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
                                if entity == "stock":
                                    raise BatchRejected(str(error)) from None
                                code = str(error)
                            except IntegrityError:
                                if entity == "stock":
                                    raise BatchRejected("STOCK_BATCH_REJECTED") from None
                                code = "INVALID_SOURCE_ROW"
                        if code:
                            count_rejected += record.weight
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
                                "CFO_ORDER_NOT_INITIALIZED",
                                "CANCEL_TRANSITION_REQUIRES_REVIEW",
                            }:
                                pinned.add(feed)
                        else:
                            count_ok += record.weight
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
                if finalize is not None:
                    await finalize(session, market)
        except (Exception, asyncio.CancelledError) as error:
            failure = "SOURCE_SYNC_FAILED"
            count_ok = count_rejected = 0
            if isinstance(error, BatchRejected):
                failure = str(error)
                count_rejected = count_in
                session.add(
                    SyncReject(
                        run_id=run_id,
                        external_key="stock_batch",
                        reason_code=failure,
                        reason=failure,
                        raw=None,
                    )
                )
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


async def sync_entity(
    market_code: str,
    entity: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
    adapter: RestMarketAdapter | None = None,
    now: datetime | None = None,
    retry_run_id: int | None = None,
    risk: SourceRisk | None = None,
    replan: ReplanSource | None = None,
) -> IngestResult:
    """Reference transport/persistence entry point; trusted dependency callbacks are server-only."""
    if entity not in SUPPORTED_ENTITIES:
        raise ValueError("Entity persistence is not integrated")
    changed_references = False

    async def affected_orders(session: AsyncSession, market: Market) -> list[int]:
        return list(
            (
                await session.scalars(
                    select(CustomerOrder.id).where(
                        CustomerOrder.market_id == market.id,
                        CustomerOrder.status.in_(
                            ("APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED")
                        ),
                    )
                )
            ).all()
        )

    async def write(
        session: AsyncSession, market: Market, record: FeedRecord, run_id: int, started: datetime
    ) -> RowOutcome:
        nonlocal changed_references
        from app.adapters.order_wire import SourceCancellation, SourceOrder
        from app.adapters.reference_wire import SourceCustomer, SourceFleet, SourceInbound, SourceProduct

        value = record.value
        if isinstance(value, (SourceOrder, SourceCancellation)):
            return await order_writer.apply(session, market, value, replan=replan)
        if isinstance(value, SourceCustomer):
            return await ingest_references.customer(session, market, value)
        if isinstance(value, SourceProduct):
            return await ingest_references.product(session, market, value, started)
        if isinstance(value, StockFeedValue):
            outcome = await stock_writer.apply(session, market, value, run_id, started)
        elif isinstance(value, SourceInbound):
            outcome = await ingest_references.inbound(session, market, value, run_id)
        elif isinstance(value, SourceFleet):
            outcome = await ingest_references.fleet(session, market, value)
        else:
            raise RowRejected("INVALID_SOURCE_ROW")
        if outcome.changed:
            affected = await affected_orders(session, market)
            if affected and risk is None:
                if entity == "stock":
                    raise BatchRejected("RISK_DEPENDENCY_UNAVAILABLE")
                raise RowRejected("RISK_DEPENDENCY_UNAVAILABLE")
            await session.flush()
            changed_references = True
        return outcome

    async def finish(session: AsyncSession, market: Market) -> None:
        if changed_references and risk is not None:
            for order_id in await affected_orders(session, market):
                await risk(session, order_id, "source_change")

    return await synchronize(
        market_code,
        entity,
        maker=maker or get_sessionmaker(),
        writer=write,
        adapter=adapter,
        now=now,
        retry_run_id=retry_run_id,
        finalize=finish,
    )


async def run_entity(market_code: str, entity: str) -> int:
    result = await sync_entity(market_code, entity)
    if result.status != "ok":
        raise RuntimeError("Source synchronization did not complete; inspect the recorded run")
    return result.rows_ok


async def ingest_customers(market_code: str) -> int:
    return await run_entity(market_code, "customers")


async def ingest_orders(market_code: str) -> int:
    return await run_entity(market_code, "orders")


async def ingest_products(market_code: str) -> int:
    return await run_entity(market_code, "products")


async def ingest_inbound(market_code: str) -> int:
    return await run_entity(market_code, "inbound")


async def ingest_fleet(market_code: str) -> int:
    return await run_entity(market_code, "fleet")


async def ingest_stock(market_code: str) -> int:
    return await run_entity(market_code, "stock")
