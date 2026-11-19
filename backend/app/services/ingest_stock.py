"""T07 stock writer gated by the approved, versioned scope/evidence (DEC-OWNER-20261109 S1-S5; #148).

A complete Source batch is written ONLY when all of the following hold, otherwise the WHOLE batch is rejected
(nothing is written, the checkpoint is not advanced, previous stock is preserved):
1. an approved scope version is effective at the trusted batch `as_of` (never sync time or mappings);
2. every expected warehouse x in-scope SKU row is present (absent = unknown, never zero; explicit 0 is valid);
3. `normalize_stock` accepts it: confirmed mappings, declared unit/factor, exact NUMERIC(12,3),
   several SKUs of one global product only inside verified, unexpired, still-matching independence evidence;
4. out-of-scope rows are ignored and can never block.
Accepted writes record the scope/evidence binding (`ops.stock_write_run`); replaying an already accepted
batch id is a no-op. The scheduler still does not run `stock`: the writer is reachable only through the
explicit stock CLI until Dev 2 and Dev 1 verify the integration end to end.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ingestion_feed import StockFeedValue
from app.adapters.stock_batches import (
    StockMapping,
    StockNormalizationError,
    normalize_stock,
)
from app.core.config import MarketConfig
from app.domain.models.ops import StockSnapshot, StockWriteRun
from app.domain.models.ref import Location, Market, ProductSE
from app.services import stock_scope_service as scope_service
from app.services.ingest_types import BatchRejected, RowOutcome


async def _context(session: AsyncSession, market_id: int, as_of: datetime) -> scope_service.StockContext:
    try:
        return await scope_service.resolve_stock_context(session, market_id, as_of)
    except scope_service.StockScopeError:
        raise BatchRejected("STOCK_SCOPE_NOT_CONFIGURED") from None


async def usable(session: AsyncSession, market_id: int, *, now: datetime) -> bool:
    """Fresh = latest ACCEPTED write within `stale_stock_min` and its scope version still effective."""
    market = await session.get(Market, market_id)
    if market is None:
        return False
    try:
        stale = MarketConfig.model_validate(market.config or {}).stale_stock_min
    except ValueError:
        return False
    run = await session.scalar(
        select(StockWriteRun)
        .where(StockWriteRun.market_id == market_id, StockWriteRun.status == "accepted")
        .order_by(StockWriteRun.as_of.desc(), StockWriteRun.id.desc())
        .limit(1)
    )
    if run is None or run.as_of < now - timedelta(minutes=stale):
        return False
    current = await scope_service.scope_effective_at(session, market_id, now)
    return current is not None and current.id == run.scope_version_id


async def apply(
    session: AsyncSession,
    market: Market,
    value: StockFeedValue,
    run_id: int,
    now: datetime,
    *,
    source_kind: str = "source",
) -> RowOutcome:
    snapshot = value.snapshot
    ctx = await _context(session, market.id, snapshot.as_of)
    replay = await session.scalar(
        select(StockWriteRun.id).where(
            StockWriteRun.market_id == market.id,
            StockWriteRun.source_batch_id == int(snapshot.batch_id or 0),
            StockWriteRun.source_kind == source_kind,
            StockWriteRun.status == "accepted",
        )
    )
    if replay is not None:
        return RowOutcome()  # the same published batch was already applied: nothing to rewrite
    codes = {
        row.id: row.code
        for row in (
            await session.scalars(
                select(Location).where(Location.id.in_(ctx.warehouse_ids), Location.market_id == market.id)
            )
        ).all()
    }
    if len(codes) != len(ctx.warehouse_ids):
        raise BatchRejected("STOCK_SCOPE_WAREHOUSE_UNKNOWN")
    try:
        expected = scope_service.expected_rows(ctx, codes)
        scope_service.require_expected_coverage(expected, {(i.warehouse_code, i.sku) for i in snapshot.items})
    except scope_service.StockScopeError:
        raise BatchRejected("STOCK_ROWS_MISSING") from None
    products = (await session.scalars(select(ProductSE).where(ProductSE.local_sku.in_(ctx.skus)))).all()
    mappings = {
        p.local_sku: StockMapping(
            p.global_product_id,
            p.sale_unit,
            p.units_to_base,
            p.mapping_status == "confirmed",
        )
        for p in products
        if p.global_product_id is not None
    }
    try:
        rows = normalize_stock(
            snapshot,
            mappings,
            value.declared,
            scope=ctx.skus,
            verified_independent=ctx.verified_independent,
        )
    except StockNormalizationError:
        raise BatchRejected("STOCK_NORMALIZATION_REJECTED") from None
    warehouse_ids = {code: wid for wid, code in codes.items()}
    for row in rows:
        statement = insert(StockSnapshot).values(
            warehouse_id=warehouse_ids[row.warehouse_code],
            global_product_id=row.global_product_id,
            on_hand=row.on_hand,
            wms_reserved=row.reserved,
            as_of=row.as_of,
            run_id=run_id,
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    StockSnapshot.warehouse_id,
                    StockSnapshot.global_product_id,
                ],
                set_={
                    "on_hand": statement.excluded.on_hand,
                    "wms_reserved": statement.excluded.wms_reserved,
                    "as_of": statement.excluded.as_of,
                    "run_id": statement.excluded.run_id,
                },
            )
        )
    await scope_service.record_write_run(
        session,
        market_id=market.id,
        source_batch_id=int(snapshot.batch_id or 0),
        source_kind=source_kind,
        ingest_run_id=run_id,
        as_of=snapshot.as_of,
        context=ctx,
        expected=len(expected),
        recorded=len(expected),
    )
    return RowOutcome(changed=True)
