"""Read-only planning stock preflight for an approved disposable CFO demo.

Never writes Source or CFO stock, changes scope, creates orders, or approves a plan.
Only the reviewed Source publisher and the governed CFO stock writer may do so.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MarketConfig
from app.domain.models.ops import CustomerOrder, OrderLine, StockScopeVersion, StockSnapshot, StockWriteRun
from app.domain.models.ref import Location, Market
from app.domain.models.stg import SyncRun


@dataclass(frozen=True)
class StockPreflight:
    status: str
    blockers: tuple[str, ...]
    missing: tuple[tuple[int, int], ...]
    stale: tuple[tuple[int, int], ...]
    expected_pairs: int
    accepted_batch_id: int | None
    accepted_as_of: datetime | None
    scope_version: int | None
    latest_sync_status: str | None
    latest_sync_error: str | None


async def diagnose(
    session: AsyncSession,
    *,
    market_code: str,
    order_external_ref: str,
    now: datetime,
) -> StockPreflight:
    """Inspect exact eligible market warehouse x order product scope, without writes.

    Source scope approval is NON-retroactive: a Source batch captured before the
    approved scope became effective cannot be accepted, regardless of sync time.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Stock diagnosis requires timezone-aware demo time")
    market = await session.scalar(select(Market).where(Market.code == market_code))
    if market is None:
        raise ValueError("Unknown market")
    order = await session.scalar(
        select(CustomerOrder).where(
            CustomerOrder.market_id == market.id,
            CustomerOrder.external_ref == order_external_ref,
        )
    )
    if order is None:
        raise ValueError("CFO order has not been synced for this market")
    product_ids = set(
        (
            await session.scalars(
                select(OrderLine.global_product_id).where(OrderLine.order_id == order.id)
            )
        ).all()
    )
    warehouses = (
        await session.scalars(
            select(Location).where(
                Location.market_id == market.id,
                Location.type == "warehouse",
                Location.is_active.is_(True),
            )
        )
    ).all()
    eligible = {wh.id for wh in warehouses}
    expected = {(wh_id, product_id) for wh_id in eligible for product_id in product_ids}
    snapshots = (
        await session.scalars(
            select(StockSnapshot).where(
                StockSnapshot.warehouse_id.in_(eligible),
                StockSnapshot.global_product_id.in_(product_ids),
            )
        )
    ).all() if eligible and product_ids else []
    found = {(row.warehouse_id, row.global_product_id): row for row in snapshots}
    freshness = MarketConfig.model_validate(market.config).stale_stock_min
    missing = tuple(sorted(expected - set(found)))
    stale = tuple(
        sorted(
            key for key, row in found.items()
            if row.as_of < now - timedelta(minutes=freshness)
            or row.as_of > now + timedelta(minutes=freshness)
        )
    )
    approved = await session.scalar(
        select(StockScopeVersion)
        .where(
            StockScopeVersion.market_id == market.id,
            StockScopeVersion.status == "approved",
        )
        .order_by(StockScopeVersion.version.desc())
        .limit(1)
    )
    accepted = await session.scalar(
        select(StockWriteRun)
        .where(StockWriteRun.market_id == market.id, StockWriteRun.status == "accepted")
        .order_by(StockWriteRun.as_of.desc(), StockWriteRun.id.desc())
        .limit(1)
    )
    latest_sync = await session.scalar(
        select(SyncRun)
        .where(SyncRun.market_id == market.id, SyncRun.entity == "stock")
        .order_by(SyncRun.id.desc())
        .limit(1)
    )
    blockers: list[str] = []
    if not eligible or not product_ids:
        blockers.append("NO_ELIGIBLE_WAREHOUSE_OR_ORDER_LINES")
    if approved is None or approved.effective_from is None or approved.effective_from > now:
        blockers.append("STOCK_SCOPE_NOT_EFFECTIVE")
    if accepted is None:
        blockers.append("NO_ACCEPTED_STOCK_BATCH")
    elif approved is None or accepted.scope_version_id != approved.id:
        blockers.append("STOCK_BATCH_WRONG_SCOPE")
    elif approved.effective_from is not None and accepted.as_of < approved.effective_from:
        blockers.append("STOCK_BATCH_PREDATES_SCOPE")
    if missing:
        blockers.append("STOCK_SNAPSHOT_MISSING")
    if stale:
        blockers.append("STOCK_SNAPSHOT_STALE")
    return StockPreflight(
        status="BLOCKED" if blockers else "PASS",
        blockers=tuple(blockers),
        missing=missing,
        stale=stale,
        expected_pairs=len(expected),
        accepted_batch_id=accepted.source_batch_id if accepted else None,
        accepted_as_of=accepted.as_of if accepted else None,
        scope_version=approved.version if approved else None,
        latest_sync_status=latest_sync.status if latest_sync else None,
        latest_sync_error=latest_sync.error if latest_sync else None,
    )
