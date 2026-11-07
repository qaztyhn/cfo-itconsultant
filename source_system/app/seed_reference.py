"""Additive synthetic catalogue/customers/addresses from 08 sections 5.2/5.5.

Owner: Dev 2 (M1). Requires explicit source-init first; never resets source data.
Receiving calendars and order snapshots remain pending SRC-Q1/SRC-Q8.
"""

import asyncio
import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from random import Random

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.db import create_engine
from app.models import Address, Customer, Product
from seed.se.catalog import catalog_products

BUSINESSES = (
    "Nordbygg Entreprenad AB",
    "Uppsala Takservice AB",
    "Mälardalens Golv AB",
    "Öresund Fastighetsservice AB",
    "Skånska Kakel & Klinker AB",
    "Hallands Snickeri AB",
    "Göta Renovering AB",
    "Nordic Ställning AB",
    "Bygg & Montage Väst AB",
)
CENTRES = (("57.7089", "11.9746"), ("59.3293", "18.0686"), ("55.6050", "13.0038"))


async def seed_customers(connection: AsyncConnection, *, now: datetime) -> None:
    """Caller owns transaction; conflict leaves existing identities/contact/addresses unchanged."""
    if now.tzinfo is None:
        raise ValueError("Seed timestamp must be timezone-aware")
    await connection.execute(text("SELECT pg_advisory_xact_lock(20261104)"))
    rng = Random(20261104)
    for index in range(1, 41):
        key = f"DEMO-C{index:03d}"
        name = BUSINESSES[index - 1] if index <= len(BUSINESSES) else f"Demo customer {index:03d}"
        await connection.execute(
            insert(Customer)
            .values(
                id=key,
                name=name,
                type="business" if index <= 30 else "consumer",
                email=f"demo-c{index:03d}@cfo.test",
                phone=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=[Customer.id])
        )
        for address_no in (1, 2):
            centre_lat, centre_lon = CENTRES[(index - 1) % len(CENTRES)]
            lat = Decimal(centre_lat) + Decimal(rng.randint(-10000, 10000)) / 100000
            lon = Decimal(centre_lon) + Decimal(rng.randint(-10000, 10000)) / 100000
            await connection.execute(
                insert(Address)
                .values(
                    id=f"{key}-A{address_no}",
                    customer_id=key,
                    address=f"Synthetic site {index:03d}-{address_no}",
                    lat=lat,
                    lon=lon,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=[Address.id])
            )


async def seed_catalog(connection: AsyncConnection, *, now: datetime) -> None:
    """Add missing SKUs only, preserving prices, metadata and timestamps of existing rows."""
    if now.tzinfo is None:
        raise ValueError("Seed timestamp must be timezone-aware")
    await connection.execute(text("SELECT pg_advisory_xact_lock(20261104)"))
    values = [asdict(product) | {"created_at": now, "updated_at": now} for product in catalog_products()]
    await connection.execute(
        insert(Product).values(values).on_conflict_do_nothing(index_elements=[Product.sku])
    )


async def run() -> None:
    settings = Settings.from_env()
    now = datetime.fromisoformat(os.environ.get("APP_NOW") or "2026-11-04T10:05:00+01:00")
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await seed_customers(connection, now=now)
            await seed_catalog(connection, now=now)
    finally:
        await engine.dispose()


def main() -> int:
    try:
        asyncio.run(run())
    except Exception:
        print("Source reference seed failed; check source-init, database configuration and APP_NOW.")
        return 1
    print("Source catalogue/customers/addresses seeded; full orders/scenario seed remains pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
