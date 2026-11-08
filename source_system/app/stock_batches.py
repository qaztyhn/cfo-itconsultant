"""Full stock publication as complete batches (SRC-Q9), one row per (batch, warehouse, SKU) (SRC-Q10).

DEC-SRC-Q10-SKU-001: every SKU has one declared stock unit and quantities are always in that unit; there is
no pool or alias concept, and a duplicate key is a malformed batch (never summed, never last-row-wins).
DEC-SRC-Q9-ERROR-001: `GET /stock` serves the latest completely published batch; if there is none (or it
fails the integrity check) the endpoint answers 503 STOCK_UNAVAILABLE. A complete published zero-row batch
is a valid 200. Publication is a source-internal action: one transaction, invisible until it commits,
and nothing is written to CFO.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings
from app.core import clock
from app.db import create_engine
from app.errors import StockUnavailable
from app.models import Product, Stock, StockBatch


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


class StockItem(BaseModel):
    """One inventory row in the SKU's declared stock unit; unknown fields (e.g. a pool id) are refused."""

    model_config = ConfigDict(extra="forbid")
    warehouse_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    on_hand: Decimal = Field(allow_inf_nan=False, ge=0)
    reserved: Decimal = Field(allow_inf_nan=False, ge=0)

    @field_serializer("on_hand", "reserved")
    def number(self, value: Decimal) -> int | float:
        return _number(value)


class StockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: AwareDatetime
    items: list[StockItem]


class StockSnapshot(BaseModel):
    """`GET /stock` 200 body: the latest complete published batch."""

    as_of: AwareDatetime
    batch_id: int
    item_count: int
    items: list[StockItem]


def fingerprint(items: list[StockItem]) -> str:
    canonical = [
        (r.warehouse_code, r.sku, str(r.on_hand.normalize()), str(r.reserved.normalize()))
        for r in sorted(items, key=lambda item: (item.warehouse_code, item.sku))
    ]
    return hashlib.sha256(json.dumps(canonical).encode()).hexdigest()


async def publish(session: AsyncSession, data: StockInput, *, source_instance: str, now: datetime) -> int:
    """Caller owns the transaction. Publishes a full batch; an identical retry returns the same id."""
    if now.tzinfo is None or data.as_of > now or not source_instance.strip():
        raise ValueError("Invalid publication timestamp/instance")
    ordered = sorted(data.items, key=lambda item: (item.warehouse_code, item.sku))
    if len({(item.warehouse_code, item.sku) for item in ordered}) != len(ordered):
        raise ValueError("Duplicate stock keys")
    digest = fingerprint(ordered)
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('source-stock-publish',0))"))
    units = {
        sku: factor
        for sku, factor in (
            await session.execute(
                select(Product.sku, Product.units_to_base).where(Product.sku.in_({i.sku for i in ordered}))
            )
        ).all()
    }
    for item in ordered:
        factor = units.get(item.sku)
        if factor is None or not factor.is_finite() or factor <= 0:  # unknown SKU or unusable unit conversion
            raise ValueError("Stock SKU is unknown or has no valid unit conversion")
    previous = await session.scalar(select(StockBatch).order_by(StockBatch.id.desc()).limit(1))
    if previous is not None:
        if previous.source_instance != source_instance or data.as_of < previous.as_of:
            raise ValueError("Stock instance/capture regression")
        if data.as_of == previous.as_of:
            if previous.complete and previous.content_hash == digest:
                return previous.id
            raise ValueError("Capture timestamp reused with different inventory")
    batch = StockBatch(
        source_instance=source_instance,
        as_of=data.as_of,
        published_at=now,
        complete=True,
        row_count=len(ordered),
        content_hash=digest,
        created_at=now,
        updated_at=now,
    )
    session.add(batch)
    await session.flush()
    for item in ordered:  # earlier batches are history and stay untouched
        session.add(
            Stock(
                batch_id=batch.id,
                warehouse_code=item.warehouse_code,
                sku=item.sku,
                on_hand=item.on_hand,
                reserved=item.reserved,
                as_of=data.as_of,
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()
    return batch.id


async def read_snapshot(engine: AsyncEngine) -> StockSnapshot:
    """Latest complete published batch in one MVCC snapshot; raises StockUnavailable if none is usable."""
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="REPEATABLE READ")
        async with AsyncSession(bind=connection) as session, session.begin():
            batch = await session.scalar(
                select(StockBatch)
                .where(StockBatch.complete.is_(True), StockBatch.published_at.is_not(None))
                .order_by(StockBatch.as_of.desc(), StockBatch.id.desc())
                .limit(1)
            )
            if batch is None:
                raise StockUnavailable
            rows = (
                await session.scalars(
                    select(Stock).where(Stock.batch_id == batch.id).order_by(Stock.warehouse_code, Stock.sku)
                )
            ).all()
            if len(rows) != batch.row_count or any(row.as_of != batch.as_of for row in rows):
                raise StockUnavailable  # a published batch that fails its integrity check is never served
            try:
                items = [
                    StockItem(
                        warehouse_code=r.warehouse_code, sku=r.sku, on_hand=r.on_hand, reserved=r.reserved
                    )
                    for r in rows
                ]
            except ValueError:
                raise StockUnavailable from None
            if fingerprint(items) != batch.content_hash:
                raise StockUnavailable
            return StockSnapshot(
                as_of=batch.as_of, batch_id=batch.id, item_count=batch.row_count, items=items
            )


async def run(path: Path) -> None:
    data = StockInput.model_validate_json(path.read_text(encoding="utf-8-sig"))
    settings = Settings.from_env()
    engine = create_engine(settings)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await publish(
                session, data, source_instance=settings.source_schema, now=clock.now(settings.app_now)
            )
    finally:
        await engine.dispose()
    print(f"Published complete source stock batch: {len(data.items)} items.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--complete-snapshot", action="store_true", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.snapshot))
    except Exception:
        print(
            "Stock publication failed; check schema, full snapshot, product keys, instance and capture time."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
