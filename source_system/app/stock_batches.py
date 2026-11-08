"""D1-D full stock publication, including authoritative empty batches; no CFO writes."""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings
from app.core import clock
from app.db import create_engine
from app.models import Stock, StockBatch


class StockItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warehouse_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    physical_stock_pool_id: str = Field(min_length=1)
    on_hand: Decimal = Field(allow_inf_nan=False)
    reserved: Decimal = Field(allow_inf_nan=False)

    @field_serializer("on_hand", "reserved")
    def number(self, value: Decimal) -> int | float:
        return int(value) if value == value.to_integral_value() else float(value)


class StockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: AwareDatetime
    items: list[StockItem]


class StockSnapshot(BaseModel):
    batch_id: int | None = None
    as_of: datetime | None = None
    complete: bool = False
    row_count: int = 0
    items: list[StockItem] = Field(default_factory=list)


def fingerprint(items: list[StockItem]) -> str:
    canonical = [
        (
            r.warehouse_code,
            r.sku,
            r.physical_stock_pool_id,
            str(r.on_hand.normalize()),
            str(r.reserved.normalize()),
        )
        for r in sorted(items, key=lambda item: (item.warehouse_code, item.sku))
    ]
    return hashlib.sha256(json.dumps(canonical).encode()).hexdigest()


async def publish(session: AsyncSession, data: StockInput, *, source_instance: str, now: datetime) -> int:
    """Caller owns transaction. Explicit full replacement of source inventory; never infer a partial batch."""
    if now.tzinfo is None or data.as_of > now or not source_instance.strip():
        raise ValueError("Invalid publication timestamp/instance")
    ordered = sorted(data.items, key=lambda item: (item.warehouse_code, item.sku))
    if len({(item.warehouse_code, item.sku) for item in ordered}) != len(ordered):
        raise ValueError("Duplicate stock keys")
    digest = fingerprint(ordered)
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('source-stock-publish',0))"))
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
    await session.execute(delete(Stock))
    for item in ordered:
        session.add(
            Stock(
                warehouse_code=item.warehouse_code,
                sku=item.sku,
                physical_stock_pool_id=item.physical_stock_pool_id,
                on_hand=item.on_hand,
                reserved=item.reserved,
                as_of=data.as_of,
                batch_id=batch.id,
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()
    return batch.id


async def read_snapshot(engine: AsyncEngine) -> StockSnapshot:
    # One MVCC snapshot prevents a concurrent full publication appearing as a partial/empty old batch.
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="REPEATABLE READ")
        async with AsyncSession(bind=connection) as session, session.begin():
            batch = await session.scalar(select(StockBatch).order_by(StockBatch.id.desc()).limit(1))
            if batch is None or not batch.complete or batch.published_at is None:
                return StockSnapshot()
            rows = (await session.scalars(select(Stock).order_by(Stock.warehouse_code, Stock.sku))).all()
            if len(rows) != batch.row_count or any(
                row.as_of != batch.as_of or row.batch_id != batch.id for row in rows
            ):
                return StockSnapshot(batch_id=batch.id)
            try:
                items = [
                    StockItem(
                        warehouse_code=r.warehouse_code,
                        sku=r.sku,
                        physical_stock_pool_id=r.physical_stock_pool_id or "",
                        on_hand=r.on_hand,
                        reserved=r.reserved,
                    )
                    for r in rows
                ]
            except ValueError:
                return StockSnapshot(batch_id=batch.id)
            if fingerprint(items) != batch.content_hash:
                return StockSnapshot(batch_id=batch.id)
            return StockSnapshot(
                batch_id=batch.id, as_of=batch.as_of, complete=True, row_count=batch.row_count, items=items
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
    print(f"Published complete source stock snapshot: {len(data.items)} items.")


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
