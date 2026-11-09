"""PostgreSQL source demo seed: complete WMS snapshot, rerun and collision rollback."""

from __future__ import annotations

import os
import runpy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import initialize
from app.models import Inbound, Order, StockBatch
from app.seed_demo import load
from app.stock_batches import read_snapshot

pytestmark = pytest.mark.integration


def _fixture() -> dict:
    path = Path(__file__).resolve().parents[3] / "backend" / "app" / "seed" / "scenarios.py"
    return runpy.run_path(str(path))["generate"]()


@pytest.mark.asyncio
async def test_US_SRC_01_AC1_source_demo_postgres_rerun_and_collision_rollback() -> None:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SOURCE_TEST_DATABASE_URL not set: PostgreSQL NOT VERIFIED")
    schema = "src_demo_" + uuid4().hex
    settings = Settings(url, schema)
    engine = create_engine(settings)
    try:
        await initialize(engine, schema)
        fixture = _fixture()
        async with AsyncSession(engine) as session, session.begin():
            assert await load(session, fixture, source_instance=schema) == 66
        async with AsyncSession(engine) as session, session.begin():
            assert await load(session, fixture, source_instance=schema) == 0
            assert (await session.scalars(select(Order))).all().__len__() == 66
            assert (await session.scalars(select(Inbound))).all().__len__() == 1
            assert (await session.scalars(select(StockBatch))).all().__len__() == 1
        snapshot = await read_snapshot(engine)
        assert snapshot.item_count == 300
        assert snapshot.batch_id >= 1
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                update(Order).where(Order.id == "SE-2026-000123").values(date_to="2026-11-11")
            )
        with pytest.raises(ValueError, match="Conflicting source order identity"):
            async with AsyncSession(engine) as session, session.begin():
                await load(session, fixture, source_instance=schema)
        async with AsyncSession(engine) as session, session.begin():
            order = await session.get(Order, "SE-2026-000123")
            assert order is not None and order.date_to.isoformat() == "2026-11-11"
            assert (await session.scalars(select(StockBatch))).all().__len__() == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()
