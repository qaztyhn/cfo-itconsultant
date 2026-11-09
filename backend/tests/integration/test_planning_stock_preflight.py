"""Real PostgreSQL read-only planning stock diagnosis, no new CFO stock writes."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.planning_stock_preflight import diagnose
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_approval_service import NOW
from tests.integration.test_approval_service import db as db  # noqa: F401

pytestmark = pytest.mark.integration


def inspect(db: str):
    async def run():
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session:
                return await diagnose(
                    session, market_code="SE", order_external_ref="EXT-1", now=NOW
                )
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_stock_preflight_discloses_unapproved_scope_and_missing_ingestion(db: str) -> None:
    before = fetch(db, "SELECT count(*) FROM ops.stock_snapshot")[0][0]
    result = inspect(db)
    assert result.status == "BLOCKED"
    assert "STOCK_SCOPE_NOT_EFFECTIVE" in result.blockers
    assert "NO_ACCEPTED_STOCK_BATCH" in result.blockers
    assert result.scope_version is None
    assert result.accepted_batch_id is None
    assert fetch(db, "SELECT count(*) FROM ops.stock_snapshot")[0][0] == before


def test_stock_preflight_identifies_exact_missing_product_and_warehouse(db: str) -> None:
    execute(db, "DELETE FROM ops.stock_snapshot WHERE warehouse_id=1 AND global_product_id=1")
    result = inspect(db)
    assert result.status == "BLOCKED"
    assert "STOCK_SNAPSHOT_MISSING" in result.blockers
    assert (1, 1) in result.missing
    assert "STOCK_SNAPSHOT_STALE" not in result.blockers


def test_stock_preflight_identifies_stale_snapshot(db: str) -> None:
    execute(
        db,
        "UPDATE ops.stock_snapshot SET as_of='2026-11-04T07:00:00Z' "
        "WHERE warehouse_id=1 AND global_product_id=1",
    )
    result = inspect(db)
    assert "STOCK_SNAPSHOT_STALE" in result.blockers
    assert (1, 1) in result.stale
    assert "STOCK_SNAPSHOT_MISSING" not in result.blockers


def test_stock_preflight_missing_market_order_is_not_success(db: str) -> None:
    async def run():
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session:
                return await diagnose(
                    session, market_code="SE", order_external_ref="NOT-IN-CFO", now=NOW
                )
        finally:
            await engine.dispose()

    with pytest.raises(ValueError, match="not been synced"):
        asyncio.run(run())
