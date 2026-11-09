"""Safe, read-only CFO stock scope/ingestion diagnostics for disposable Swedish demo.

Never bootstraps scope, grants, stock, reservations or approval. The absence of
a governed accepted write is BLOCKED, not zero stock and not a planned order.
"""

from __future__ import annotations

import asyncio
import json
import os

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.domain.models.ops import StockScopeVersion, StockSnapshot, StockWriteRun
from app.domain.models.ref import Location, Market

FROZEN = "2026-11-04T10:05:00+01:00"


async def report() -> dict[str, object]:
    settings = get_settings()
    if settings.app_env != "test" or settings.app_now != FROZEN or os.environ.get("DEMO_DISPOSABLE") != "1":
        raise ValueError("Disposable-only stock diagnostics")
    try:
        async with get_sessionmaker()() as session:
            market = await session.scalar(select(Market).where(Market.code == "SE"))
            if market is None:
                raise ValueError("Swedish market missing")
            warehouses = select(Location.id).where(
                Location.market_id == market.id, Location.type == "warehouse"
            )
            rows = await session.scalar(
                select(func.count()).select_from(StockSnapshot).where(
                    StockSnapshot.warehouse_id.in_(warehouses)
                )
            )
            accepted = await session.scalar(
                select(func.count()).select_from(StockWriteRun).where(
                    StockWriteRun.market_id == market.id,
                    StockWriteRun.status == "accepted",
                )
            )
            approved = await session.scalar(
                select(func.count()).select_from(StockScopeVersion).where(
                    StockScopeVersion.market_id == market.id,
                    StockScopeVersion.status == "approved",
                )
            )
            return {
                "market": "SE",
                "stock_rows": int(rows or 0),
                "accepted_write_runs": int(accepted or 0),
                "approved_scope_versions": int(approved or 0),
                "status": (
                    "PRESENT_NOT_APPROVAL_PROOF"
                    if rows and accepted and approved
                    else "BLOCKED_STOCK_NOT_GOVERNED"
                ),
            }
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(report()), sort_keys=True))
    except Exception:
        print('{"status":"BLOCKED_STOCK_DIAG_UNAVAILABLE"}')
        raise SystemExit(2) from None
