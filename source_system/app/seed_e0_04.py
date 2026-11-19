"""Publish one fresh, complete synthetic WMS observation and fixed E0-04 Source order.

This is only for the disposable SE demo after an approved CFO scope exists. The
previous Source stock batch supplies the simulated inventory state; publication
creates a new immutable batch at the E0-04 demo clock through the normal Source
publisher. CFO still has to ingest that batch through its real adapter.
"""

import asyncio
import os
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import create_engine
from app.seed_demo import _orders
from app.stock_batches import StockInput, publish, read_snapshot

DEMO_NOW = "2026-12-01T10:05:00+01:00"
EXTERNAL_REF = "SE-2026-000249"


async def run() -> tuple[int, int]:
    settings = Settings.from_env()
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or os.environ.get("APP_NOW") != DEMO_NOW
        or settings.source_schema != "src_se"
    ):
        raise ValueError("Disposable E0-04 Source context required")
    now = datetime.fromisoformat(DEMO_NOW)
    engine = create_engine(settings)
    try:
        previous = await read_snapshot(engine)
        captured = StockInput(as_of=now - timedelta(minutes=5), items=previous.items)
        order = {
            "id": EXTERNAL_REF,
            "customer_id": "DEMO-C002",
            "address_id": "DEMO-C002-A1",
            "store_code": "ST-001",
            "sales_code": "DEMO-SALES",
            "date_mode": "exact",
            "date_from": "2026-12-02",
            "date_to": "2026-12-02",
            "window_start": "07:00",
            "window_end": "16:00",
            "status": "SUBMITTED_FOR_PLANNING",
            "lines": [{"line_no": 1, "sku": "SE-BRD-GYP-13", "qty": "10"}],
        }
        async with AsyncSession(engine) as session, session.begin():
            added = await _orders(session, {"orders": [order], "completed_orders": []}, now)
            batch_id = await publish(session, captured, source_instance=settings.source_schema, now=now)
        return added, batch_id
    finally:
        await engine.dispose()


def main() -> int:
    try:
        added, batch_id = asyncio.run(run())
    except Exception:
        print("BLOCKED: E0-04 Source order/batch publication failed; check disposable clock and Source data.")
        return 2
    print(f"PASS: Source {EXTERNAL_REF} added={added}; complete stock batch_id={batch_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
