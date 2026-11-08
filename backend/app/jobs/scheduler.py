"""T07 explicit ingest-only APScheduler worker. No unapproved D8/internal-tick schedule."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.rest_adapter import RestMarketAdapter
from app.core import clock
from app.core.config import MarketConfig, get_settings
from app.core.db import get_engine, get_sessionmaker
from app.core.logging import log_event
from app.domain.models.ref import Market
from app.jobs.ingest import IngestBatchError, run_market
from app.services.ingest_types import ReplanSource, SourceRisk, aware


async def create_scheduler(
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
    now: datetime | None = None,
    adapter_factory: Callable[[str], RestMarketAdapter] | None = None,
    replan: ReplanSource | None = None,
    risk: SourceRisk | None = None,
) -> AsyncIOScheduler:
    """Build, do not auto-start. One ingest job/market; cross-process safety lives in DB leases.

    Cadence is the existing 04/06 MarketConfig sync interval, not D8's proposed extra jobs.
    Config changes require rebuilding this worker; a second replica cannot bypass feed leases.
    """
    factory = maker or get_sessionmaker()
    timestamp = aware(now or clock.now())
    scheduler = AsyncIOScheduler(timezone=UTC)

    async def poll(code: str) -> None:
        batch = await run_market(
            code,
            maker=factory,
            adapter=adapter_factory(code) if adapter_factory is not None else None,
            replan=replan,
            risk=risk,
        )
        if not batch.ok:
            raise IngestBatchError("Scheduled ingestion incomplete; inspect persisted sync runs")

    async with factory() as session:
        markets = (await session.scalars(select(Market).order_by(Market.code))).all()
        for market in markets:
            cfg = MarketConfig.model_validate(market.config)
            if cfg.sync.interval_min <= 0:
                raise ValueError("Ingestion interval must be positive")
            zone = ZoneInfo(market.timezone)
            scheduler.add_job(
                poll,
                trigger=IntervalTrigger(
                    minutes=cfg.sync.interval_min,
                    timezone=zone,
                    start_date=timestamp + timedelta(minutes=cfg.sync.interval_min),
                ),
                id=f"ingest:{market.code}",
                kwargs={"code": market.code},
                coalesce=True,
                max_instances=1,
                replace_existing=False,
            )
    return scheduler


async def run() -> int:
    """One explicitly requested ingestion tick; no HTTP endpoint/extended D8 contract is added."""
    from app.jobs.ingest import run as ingest_once

    return await ingest_once()


async def serve() -> None:
    clock.init_from_settings(get_settings().app_now)
    scheduler = await create_scheduler()
    scheduler.start()
    log_event("scheduler", "ingestion_scheduler_started", jobs=len(scheduler.get_jobs()))
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await get_engine().dispose()


def main() -> int:
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        return 0
    except Exception:
        log_event("scheduler", "ingestion_scheduler_failed", level="error")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
