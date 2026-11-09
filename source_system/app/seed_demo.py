"""Load approved synthetic source *inputs* without bypassing WMS stock publication.

Prerequisites: source-init and source reference seed. This module never writes
CFO ops.stock_snapshot or marks CFO orders approved/delivered. All changes are
additive and transactional; an existing conflicting demo identity fails closed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import create_engine
from app.models import (
    Address,
    Customer,
    Inbound,
    Order,
    OrderLine,
    Product,
    VehicleCalendar,
)
from app.seed_reference import (
    seed_catalog,
    seed_customers,
    seed_receiving_calendar,
    seed_sales_references,
)
from app.stock_batches import StockInput, publish

EXPECTED_SEED = 20261104


def check_manifest(data: dict[str, Any]) -> None:
    """Independent defensive check; source must never import running CFO app."""
    if (
        data.get("schema_version") != "cfo-demo-v1"
        or data.get("seed") != EXPECTED_SEED
        or data.get("gps_enabled") is not False
        or len(data.get("e2e_scenarios", [])) != 18
        or len(data.get("completed_orders", [])) != 48
        or len(data.get("orders", [])) != 18
    ):
        raise ValueError("Unsupported/incomplete demo manifest")
    history = data.get("driver_history", [])
    if len(history) != 560 or any(
        row.get("verified") is not False or row.get("reg_561_scope") != "unknown"
        for row in history
    ):
        raise ValueError("Synthetic driving history cannot be promoted to verified")
    edge_cases = data.get("driver_edge_cases", [])
    if len(edge_cases) != 9 or any(
        row.get("legally_verified") is not False for row in edge_cases
    ):
        raise ValueError("D7 edge cases must remain unverified")
    rows = data.get("stock_snapshot", {}).get("items", [])
    if (
        len(rows) != 300
        or len({(r.get("warehouse_code"), r.get("sku")) for r in rows}) != 300
    ):
        raise ValueError("Incomplete/duplicate published WMS snapshot")
    order_ids = [o["id"] for o in data["orders"] + data["completed_orders"]]
    if len(set(order_ids)) != len(order_ids):
        raise ValueError("Duplicate demo order identifiers")
    if not all(
        str(o["customer_id"]).startswith("DEMO-C")
        and str(o["address_id"]).startswith("DEMO-C")
        and str(o["id"]).startswith("SE-2026-")
        and o["status"] == "SUBMITTED_FOR_PLANNING"
        for o in data["orders"] + data["completed_orders"]
    ):
        raise ValueError(
            "Source order fixture must use synthetic, submitted identities"
        )


async def _orders(session: AsyncSession, data: dict[str, Any], now: datetime) -> int:
    inserted = 0
    for spec in data["orders"] + data["completed_orders"]:
        key = str(spec["id"])
        customer = await session.get(Customer, spec["customer_id"])
        address = await session.get(Address, spec["address_id"])
        if customer is None or address is None or address.customer_id != customer.id:
            raise ValueError("Unknown/mismatched demo customer and address")
        if spec["date_mode"] == "exact" and spec["date_from"] != spec["date_to"]:
            raise ValueError("Conflicting exact date in synthetic Source fixture")
        fields = {
            "customer_id": customer.id,
            "address_id": address.id,
            "date_mode": str(spec["date_mode"]),
            "date_from": date.fromisoformat(str(spec["date_from"])),
            # The scenario manifest specifies a requested *calendar day* twice
            # for downstream planning, but Source D1 exact-date schema requires
            # a NULL upper bound. Do not weaken the approved Source validator.
            "date_to": (
                None
                if spec["date_mode"] == "exact" and spec["date_from"] == spec["date_to"]
                else date.fromisoformat(str(spec["date_to"]))
            ),
            "window_start": time.fromisoformat(str(spec["window_start"])),
            "window_end": time.fromisoformat(str(spec["window_end"])),
            "sales_code": str(spec["sales_code"]),
            "store_code": str(spec["store_code"]),
        }
        existing = await session.get(Order, key)
        if existing is None:
            session.add(
                Order(
                    id=key,
                    version=1,
                    status="SUBMITTED_FOR_PLANNING",
                    address=address.address,
                    lat=address.lat,
                    lon=address.lon,
                    contact_name=customer.name,
                    contact_phone=None,
                    contact_email=customer.email,
                    receiving_restrictions=None,
                    special_requirements=None,
                    created_at=now,
                    updated_at=now,
                    **fields,
                )
            )
            await session.flush()
            inserted += 1
        elif any(getattr(existing, field) != value for field, value in fields.items()):
            raise ValueError(f"Conflicting source order identity: {key}")
        # Preserve operational status/version on rerun. The existing lines
        # must still match; never rewrite a POS-edited or executed order.
        actual = (
            await session.scalars(
                select(OrderLine)
                .where(OrderLine.order_id == key)
                .order_by(OrderLine.line_no)
            )
        ).all()
        expected = []
        for line in spec["lines"]:
            product = await session.get(Product, line["sku"])
            if product is None:
                raise ValueError(f"Missing SKU for demo order: {key}")
            expected.append(
                (
                    int(line["line_no"]),
                    product.sku,
                    Decimal(str(line["qty"])),
                    product.unit_price,
                )
            )
        if existing is not None:
            if [(v.line_no, v.sku, v.qty, v.unit_price) for v in actual] != expected:
                raise ValueError(f"Conflicting source order lines: {key}")
            continue
        for line_no, sku, qty, price in expected:
            session.add(
                OrderLine(
                    order_id=key,
                    line_no=line_no,
                    sku=sku,
                    qty=qty,
                    unit_price=price,
                    created_at=now,
                    updated_at=now,
                )
            )
    return inserted


async def _inbound_and_fleet(
    session: AsyncSession, data: dict[str, Any], now: datetime
) -> None:
    for spec in data["inbound"]:
        key = (spec["inbound_ref"], spec["warehouse_code"], spec["sku"])
        inbound_existing = await session.get(Inbound, key)
        values = {
            "qty": Decimal(str(spec["qty"])),
            "eta_date": date.fromisoformat(str(spec["eta_date"])),
            "confirmed": bool(spec["confirmed"]),
            "received": bool(spec["received"]),
        }
        if inbound_existing is not None:
            if any(getattr(inbound_existing, k) != v for k, v in values.items()):
                raise ValueError(
                    "Conflicting inbound shipment; refusing source overwrite"
                )
            continue
        session.add(
            Inbound(
                inbound_ref=key[0],
                warehouse_code=key[1],
                sku=key[2],
                created_at=now,
                updated_at=now,
                **values,
            )
        )
    for spec in data["vehicle_calendar"]:
        start = datetime.fromisoformat(str(spec["from_ts"]))
        end = datetime.fromisoformat(str(spec["to_ts"]))
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Invalid demo fleet time range")
        key = (spec["vehicle_code"], start, end)
        fleet_existing = await session.get(VehicleCalendar, key)
        if fleet_existing is not None:
            if fleet_existing.kind != spec["kind"]:
                raise ValueError("Conflicting fleet calendar; refusing overwrite")
            continue
        session.add(
            VehicleCalendar(
                vehicle_code=key[0],
                from_ts=start,
                to_ts=end,
                kind=spec["kind"],
                created_at=now,
                updated_at=now,
            )
        )


async def load(
    session: AsyncSession, data: dict[str, Any], *, source_instance: str
) -> int:
    """Caller owns one PostgreSQL transaction. No cleanup, UPDATE or privileged grants."""
    check_manifest(data)
    now = datetime.fromisoformat(data["app_now"])
    if now.tzinfo is None:
        raise ValueError("APP_NOW must be timezone-aware")
    await session.execute(text("SELECT pg_advisory_xact_lock(20261104)"))
    connection = await session.connection()
    await seed_customers(connection, now=now)
    await seed_catalog(connection, now=now)
    await seed_receiving_calendar(connection, now=now)
    await seed_sales_references(connection, now=now)
    orders_added = await _orders(session, data, now)
    await _inbound_and_fleet(session, data, now)
    # The *existing* source WMS publisher is the sole writer of stock batches.
    stock = StockInput.model_validate(data["stock_snapshot"])
    await publish(session, stock, source_instance=source_instance, now=now)
    return orders_added


async def run(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    settings = Settings.from_env()
    engine = create_engine(settings)
    try:
        async with AsyncSession(engine) as session, session.begin():
            return await load(session, data, source_instance=settings.source_schema)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        added = asyncio.run(run(args.manifest))
    except Exception:
        print("Source demo input seed failed (no operational records overwritten).")
        return 1
    print(
        f"Source demo inputs seeded: {added} new orders; CFO workflow/golden outcomes not asserted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
