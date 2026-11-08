"""T07 all-or-nothing fixed-SKU stock replacement after merged #105/#111, no source writes."""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ingestion_feed import StockFeedValue
from app.adapters.stock_batches import StockMapping, StockNormalizationError, normalize_stock
from app.core.config import MarketConfig
from app.domain.models.ops import StockSnapshot
from app.domain.models.ref import Location, Market
from app.domain.models.stg import SyncRun
from app.services.alert_service import raise_alert, resolve
from app.services.ingest_types import BatchRejected, RowOutcome


async def usable(session: AsyncSession, market_id: int, *, now: datetime) -> bool:
    """Availability/freshness handoff for T14/T16: retained old rows alone are NOT proof of availability.

    Call in addition to per-item availability and the live source/approval recheck. Not wired into
    forbidden planning/approval files here. A failed latest run invalidates even a recently cached batch.
    A complete empty successful batch is fresh zero, distinct from never having a published batch.
    """
    market = await session.get(Market, market_id)
    if market is None or now.tzinfo is None:
        return False
    run = await session.scalar(
        select(SyncRun)
        .where(SyncRun.market_id == market_id, SyncRun.entity == "stock")
        .order_by(SyncRun.id.desc())
        .limit(1)
    )
    threshold = MarketConfig.model_validate(market.config).stale_stock_min
    return bool(
        run
        and run.status == "ok"
        and run.data_as_of is not None
        and threshold > 0
        and run.data_as_of <= now <= run.data_as_of + timedelta(minutes=threshold)
    )


async def apply(
    session: AsyncSession, market: Market, value: StockFeedValue, run_id: int, now: datetime
) -> RowOutcome:
    snapshot = value.snapshot
    if value.latest_catalog_time is not None and value.latest_catalog_time > now:
        raise BatchRejected("BAD_DATE")
    products = (
        await session.execute(
            text("""
        SELECT p.local_sku,p.global_product_id,p.sale_unit,p.units_to_base,p.mapping_status
        FROM ref.v_product_local p JOIN ref.market m ON m.code=p.market_code WHERE m.id=:market
    """),
            {"market": market.id},
        )
    ).all()
    mappings = {
        row.local_sku: StockMapping(
            row.global_product_id, row.sale_unit, row.units_to_base, row.mapping_status == "confirmed"
        )
        for row in products
    }
    try:
        normalized = normalize_stock(snapshot, mappings, value.declared)
    except StockNormalizationError:
        raise BatchRejected("STOCK_BATCH_REJECTED") from None
    warehouses = (
        await session.execute(
            select(Location.id, Location.code, Location.is_active).where(
                Location.market_id == market.id, Location.type == "warehouse"
            )
        )
    ).all()
    by_code = {row.code: row for row in warehouses}
    if any(
        row.warehouse_code not in by_code or not by_code[row.warehouse_code].is_active for row in normalized
    ):
        raise BatchRejected("UNKNOWN_WAREHOUSE")
    ids = [row.id for row in warehouses]
    previous = await session.scalar(
        select(func.max(SyncRun.data_as_of)).where(
            SyncRun.market_id == market.id, SyncRun.entity == "stock", SyncRun.status == "ok"
        )
    )
    stored = (await session.scalars(select(StockSnapshot).where(StockSnapshot.warehouse_id.in_(ids)))).all()
    newest = max([row.as_of for row in stored] + ([previous] if previous else []), default=None)
    if newest is not None and snapshot.as_of < newest:
        raise BatchRejected("STALE_SOURCE_BATCH")
    expected = {
        (by_code[row.warehouse_code].id, row.global_product_id): (row.on_hand, row.reserved, row.as_of)
        for row in normalized
    }
    current = {
        (row.warehouse_id, row.global_product_id): (row.on_hand, row.wms_reserved, row.as_of)
        for row in stored
    }
    changed = expected != current
    if previous == snapshot.as_of and changed:
        raise BatchRejected("STOCK_CAPTURE_CONFLICT")
    if changed:
        # Full market-source replacement, including explicit complete empty batches. Never lock snapshot rows
        # FOR UPDATE, alter CFO reservations or publish a filtered/partial normalization as complete.
        await session.execute(delete(StockSnapshot).where(StockSnapshot.warehouse_id.in_(ids)))
        session.add_all(
            [
                StockSnapshot(
                    warehouse_id=warehouse,
                    global_product_id=product,
                    on_hand=state[0],
                    wms_reserved=state[1],
                    as_of=state[2],
                    run_id=run_id,
                )
                for (warehouse, product), state in expected.items()
            ]
        )
    cfg = MarketConfig.model_validate(market.config)
    if cfg.stale_stock_min <= 0:
        raise BatchRejected("INVALID_FRESHNESS_CONFIGURATION")
    for warehouse in warehouses:
        key = f"STALE_DATA:stock:{warehouse.id}"
        if snapshot.as_of < now - timedelta(minutes=cfg.stale_stock_min):
            await raise_alert(
                session,
                market_id=market.id,
                type_="STALE_DATA",
                level="warning",
                message="Warehouse stock snapshot is stale.",
                dedupe_key=key,
                target_roles=("dispatcher",),
            )
        else:
            await resolve(session, key, now=now)
    return RowOutcome(changed=changed)
