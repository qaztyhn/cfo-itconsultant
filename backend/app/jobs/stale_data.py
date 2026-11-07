"""US-INT-03 AC2: warn on stale stock without changing reservations or source data."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import MarketConfig
from app.core.db import get_sessionmaker
from app.core.logging import log_event
from app.domain.models.ops import StockSnapshot
from app.domain.models.ref import Location, Market
from app.services.alert_service import raise_alert, resolve


async def check_stale_stock(session: AsyncSession, *, now: datetime) -> int:
    """One open alert per warehouse, using the oldest retained SKU's source timestamp."""
    if now.tzinfo is None:
        raise ValueError("Staleness check time must have a timezone")
    records = await session.execute(
        select(Market, Location.id, func.min(StockSnapshot.as_of))
        .join(Location, Location.market_id == Market.id)
        .join(StockSnapshot, StockSnapshot.warehouse_id == Location.id)
        .where(Location.type == "warehouse")
        .group_by(Market.id, Location.id)
    )
    created = 0
    for market, warehouse_id, oldest in records:
        threshold = MarketConfig.model_validate(market.config).stale_stock_min
        if threshold <= 0:
            raise ValueError("Stock staleness threshold must be positive")
        key = f"STALE_DATA:stock:{warehouse_id}"
        if oldest < now - timedelta(minutes=threshold):
            alert_id = await raise_alert(
                session,
                market_id=market.id,
                type_="STALE_DATA",
                level="warning",
                message="Warehouse stock snapshot is stale.",
                dedupe_key=key,
                target_roles=["dispatcher"],
            )
            created += int(alert_id is not None)
        else:
            await resolve(session, key, now=now)
    return created


async def run() -> int:
    async with get_sessionmaker()() as session, session.begin():
        count = await check_stale_stock(session, now=clock.now())
    log_event("scheduler", "stale_data_check", rows_processed=count)
    return count
