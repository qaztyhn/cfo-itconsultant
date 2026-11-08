"""T07 read-only source polling with complete fixed-SKU stock batches after #105/#111."""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.rest_adapter import RestMarketAdapter
from app.core import clock
from app.core.config import get_settings
from app.core.correlation import correlation_id_var, normalize_correlation_id
from app.core.db import get_engine, get_sessionmaker
from app.core.errors import DomainError
from app.core.logging import configure_logging, log_event
from app.domain.models.ref import Market
from app.services.ingest_service import ENTITIES, sync_entity
from app.services.ingest_types import IngestResult, ReplanSource, SourceRisk


@dataclass(frozen=True)
class BatchResult:
    market_code: str
    runs: tuple[IngestResult, ...]
    errors: tuple[tuple[str, str], ...]

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and len(self.runs) == len(ENTITIES)
            and all(run.status == "ok" for run in self.runs)
        )


class IngestBatchError(RuntimeError):
    """Counts/identifiers remain in sync_run; never copy source exception content into job logs."""


async def run_market(
    market_code: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None = None,
    adapter: RestMarketAdapter | None = None,
    now: datetime | None = None,
    replan: ReplanSource | None = None,
    risk: SourceRisk | None = None,
) -> BatchResult:
    token = correlation_id_var.set(normalize_correlation_id(None))
    try:
        factory = maker or get_sessionmaker()
        async with factory() as lease, lease.begin():
            market_id = await lease.scalar(select(Market.id).where(Market.code == market_code))
            if market_id is None:
                raise DomainError("NOT_FOUND", "Source market not found.")
            acquired = await lease.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"ingest-batch:{market_id}"},
            )
            if not acquired:
                raise DomainError("SYNC_IN_PROGRESS", "Market synchronization is already running.")
            return await _run_market(
                market_code, maker=factory, adapter=adapter, now=now, replan=replan, risk=risk
            )
    finally:
        correlation_id_var.reset(token)


async def _run_market(
    market_code: str,
    *,
    maker: async_sessionmaker[AsyncSession] | None,
    adapter: RestMarketAdapter | None,
    now: datetime | None,
    replan: ReplanSource | None,
    risk: SourceRisk | None,
) -> BatchResult:
    factory = maker or get_sessionmaker()
    results: list[IngestResult] = []
    errors: list[tuple[str, str]] = []
    for entity in ENTITIES:  # customers/products before orders and mapped inbound.
        try:
            results.append(
                await sync_entity(
                    market_code, entity, maker=factory, adapter=adapter, now=now, replan=replan, risk=risk
                )
            )
        except DomainError as error:
            errors.append((entity, error.code))
        except Exception:
            errors.append((entity, "INGESTION_UNAVAILABLE"))
    batch = BatchResult(market_code, tuple(results), tuple(errors))
    log_event(
        "integration",
        "ingestion_batch_finished",
        market=market_code,
        status="ok" if batch.ok else "incomplete",
        runs=len(results),
        failures=len(errors),
        rows_processed=sum(run.rows_ok for run in results),
    )
    return batch


async def run(market_code: str | None = None) -> int:
    factory = get_sessionmaker()
    async with factory() as session:
        codes = (
            [market_code]
            if market_code is not None
            else list((await session.scalars(select(Market.code).order_by(Market.code))).all())
        )
    total = 0
    incomplete = False
    for code in codes:
        batch = await run_market(code, maker=factory)
        total += sum(item.rows_ok for item in batch.runs)
        incomplete |= not batch.ok
    if incomplete:
        raise IngestBatchError("Ingestion incomplete; inspect sync runs/rejects and dependency handoffs")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market")
    parser.add_argument("--entity", choices=ENTITIES)
    parser.add_argument("--retry-run-id", type=int)
    args = parser.parse_args()
    if args.entity and not args.market:
        parser.error("--entity requires --market")
    if args.retry_run_id is not None and (not args.entity or args.retry_run_id <= 0):
        parser.error("--retry-run-id requires --market, --entity and a positive run ID")

    async def execute() -> int:
        settings = get_settings()
        clock.init_from_settings(settings.app_now)
        configure_logging(Path("logs") if settings.app_env == "local" else None)
        try:
            if args.entity:
                result = await sync_entity(args.market, args.entity, retry_run_id=args.retry_run_id)
                if result.status != "ok":
                    raise IngestBatchError(
                        "Source retry incomplete; inspect the persisted synchronization run"
                    )
                return result.rows_ok
            return await run(args.market)
        finally:
            await get_engine().dispose()

    try:
        count = asyncio.run(execute())
    except Exception:
        log_event("integration", "ingestion_cli_failed", level="error")
        return 1
    print(f"Ingestion completed: {count} accepted records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
