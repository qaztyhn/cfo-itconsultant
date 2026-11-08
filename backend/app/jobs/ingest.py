"""T07 read-only source polling. Stock persistence/freshness is a separate T07 delivery."""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.rest_adapter import RestMarketAdapter
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.core.errors import DomainError
from app.core.logging import log_event
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
    args = parser.parse_args()

    async def execute() -> int:
        clock.init_from_settings(get_settings().app_now)
        try:
            return await run(args.market)
        finally:
            await get_engine().dispose()

    try:
        count = asyncio.run(execute())
    except Exception:
        log_event("integration", "ingestion_cli_failed", level="error")
        return 1
    print(f"Ingestion completed: {count} accepted records. Stock is not integrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
