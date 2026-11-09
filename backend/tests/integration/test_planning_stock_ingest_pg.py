"""Real Source HTTP adapter -> reviewed CFO stock writer -> PostgreSQL preflight.

No manually inserted CFO stock, governance bypass, or production WMS writes.
"""

import asyncio

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.rest_adapter import RestMarketAdapter
from app.services import stock_scope_service as scope_service
from app.services.ingest_service import sync_entity
from app.services.planning_stock_preflight import diagnose
from tests.integration import rows
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_ingest_references import product
from tests.integration.test_ingest_runner import page
from tests.integration.test_stock_scope_service import ADMIN_A, ADMIN_B, NOW, run
from tests.integration.test_stock_scope_service import db as db  # noqa: F401

pytestmark = pytest.mark.integration


def _prepare_governance(db: str) -> None:
    execute(
        db,
        rows.order_sql(1),
        "INSERT INTO ops.order_line (order_id,line_no,local_sku,global_product_id,"
        "qty_sale,qty_base,unit_price,line_total) VALUES (1,1,'A',1,1,2.5,1,1)",
    )

    warehouses = fetch(
        db,
        "SELECT id,code FROM ref.location WHERE market_id=1 AND type='warehouse' ORDER BY id",
    )
    assert {row["code"] for row in warehouses} == {"WH-1", "WH-2"}
    warehouse_ids = [row["id"] for row in warehouses]

    async def create(session) -> int:
        row = await scope_service.create_scope(
            session,
            ADMIN_A,
            skus=["A"],
            warehouse_ids=warehouse_ids,
            reason_text="Reviewed synthetic stock scope",
        )
        return row.id

    scope_id = run(db, create)
    run(db, lambda s: scope_service.approve_scope(s, ADMIN_B, scope_id))


def _source_ingest(db: str, as_of: str):
    async def go():
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        stock = {
            "batch_id": 101,
            "as_of": as_of,
            "item_count": 2,
            "items": [
                {"warehouse_code": wh, "sku": "A", "on_hand": "10", "reserved": "2"}
                for wh in ("WH-1", "WH-2")
            ],
        }

        def source(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/stock":
                return httpx.Response(200, json=stock)
            if request.url.path == "/products":
                return page([product(sku="A", units_to_base="2.5000")])
            return httpx.Response(404)

        try:
            result = await sync_entity(
                "SE",
                "stock",
                maker=async_sessionmaker(engine, expire_on_commit=False),
                adapter=RestMarketAdapter(
                    "SE", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
                ),
                now=NOW,
            )
            async with async_sessionmaker(engine)() as session:
                preflight = await diagnose(session, market_code="SE", order_external_ref="EXT-1", now=NOW)
            return result, preflight
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_real_source_stock_writer_unblocks_snapshot_after_approved_scope(db: str) -> None:
    _prepare_governance(db)
    result, preflight = _source_ingest(db, NOW.isoformat())
    assert result.status == "ok", fetch(
        db, "SELECT error FROM stg.sync_run WHERE entity='stock' ORDER BY id DESC LIMIT 1"
    )[0][0]
    assert preflight.status == "PASS"
    assert preflight.expected_pairs == 2
    assert preflight.missing == preflight.stale == ()
    assert preflight.accepted_batch_id == 101
    assert fetch(db, "SELECT count(*) FROM ops.stock_snapshot")[0][0] == 2
    assert fetch(db, "SELECT count(*) FROM ops.stock_write_run WHERE status='accepted'")[0][0] == 1


def test_nonretroactive_scope_rejects_source_batch_captured_before_approval(db: str) -> None:
    _prepare_governance(db)
    as_of = "2026-11-09T08:50:00+00:00"
    result, preflight = _source_ingest(db, as_of)
    assert result.status == "failed"
    assert preflight.status == "BLOCKED"
    assert "NO_ACCEPTED_STOCK_BATCH" in preflight.blockers
    assert "STOCK_SNAPSHOT_MISSING" in preflight.blockers
    assert fetch(db, "SELECT count(*) FROM ops.stock_snapshot")[0][0] == 0
    assert (
        fetch(db, "SELECT error FROM stg.sync_run WHERE entity='stock'")[0][0] == "STOCK_SCOPE_NOT_CONFIGURED"
    )
