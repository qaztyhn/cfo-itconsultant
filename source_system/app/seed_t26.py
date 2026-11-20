"""Load only the T26 Source cases using the E0-04 reference publisher."""

import asyncio
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import create_engine
from app.seed_demo import _inbound_and_fleet, _orders, check_manifest
from app.seed_reference import (
    seed_catalog,
    seed_customers,
    seed_receiving_calendar,
    seed_sales_references,
)
from app.stock_batches import StockInput, publish

FIXTURE = Path(__file__).resolve().parents[1] / "seed/se/t26.json"


async def run(manifest: Path) -> int:
    settings = Settings.from_env()
    database = make_url(settings.database_url)
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or settings.app_now != "2026-11-04T10:05:00+01:00"
        or settings.source_schema != "src_se"
        or database.host not in ("postgres", "127.0.0.1")
        or database.database != "source_se"
    ):
        raise ValueError("Disposable T26 Source context required")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    base = json.loads(manifest.read_text(encoding="utf-8"))
    check_manifest(base)
    now = datetime.fromisoformat(settings.app_now)
    orders = []
    for order in base["orders"]:
        case = fixture["source_cases"].get(order["id"])
        if case is None:
            continue
        order["date_from"] = order["date_to"] = case["date"]
        if case["purpose"] == "two_vehicles":
            order["lines"] = [
                {"line_no": n, "sku": item["sku"], "qty": str(item["count"] * item["units_per_pallet"])}
                for n, item in enumerate(fixture["pallets"], 1)
            ]
        if case["purpose"] == "sales_rank_2":
            order["address_id"] = "DEMO-C001-A2"
        orders.append(order)
    if len(orders) != len(fixture["source_cases"]):
        raise ValueError("T26 Source cases missing from E0-04 manifest")
    stock = base["stock_snapshot"]
    stock["items"] = [item for item in stock["items"] if item["warehouse_code"] in fixture["warehouses"]]
    for item in stock["items"]:
        if item["sku"] == "SE-TIL-ADH-25" and item["warehouse_code"] == "STO":
            item["on_hand"] = "0"
    inbound = dict(base["inbound"][0], warehouse_code="STO", eta_date="2026-12-03")
    engine = create_engine(settings)
    try:
        async with AsyncSession(engine) as session, session.begin():
            connection = await session.connection()
            # The midpoint site can be served by both demo warehouses.
            await seed_customers(
                connection, now=now, sites={"DEMO-C001-A2": (Decimal("58.60"), Decimal("15.45"))}
            )
            await seed_catalog(
                connection,
                now=now,
                volumes={sku: Decimal(volume) for sku, volume in fixture["volume_m3_per_base"].items()},
            )
            await seed_receiving_calendar(connection, now=now)
            await seed_sales_references(connection, now=now, count=len(fixture["stores"]))
            added = await _orders(session, {"orders": orders, "completed_orders": []}, now)
            await _inbound_and_fleet(session, {"inbound": [inbound], "vehicle_calendar": []}, now)
            await publish(
                session, StockInput.model_validate(stock), source_instance=settings.source_schema, now=now
            )
            return added
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        result = asyncio.run(run(Path(sys.argv[1])))
    except Exception:
        raise SystemExit("BLOCKED: T26 Source seed failed; verify disposable context and manifest.") from None
    print(f"T26 Source scenario rows added={result}")
