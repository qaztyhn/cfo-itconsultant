import asyncio
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.rest_adapter import RestMarketAdapter
from app.services.ingest_service import sync_entity
from app.services.ingest_stock import usable
from tests.integration import rows
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_ingest_references import mapped, product
from tests.integration.test_ingest_runner import NOW, page
from tests.integration.test_ingest_runner import db as db

pytestmark = pytest.mark.integration


def snapshot(**changes: object) -> dict[str, object]:
    return {
        "batch_id": 1,
        "as_of": NOW.isoformat(),
        "item_count": 1,
        "items": [{"warehouse_code": "WH-1", "sku": "P1", "on_hand": "10.000", "reserved": "2.000"}],
        **changes,
    }


def prepare(db: str) -> None:
    mapped(db)
    execute(
        db,
        "INSERT INTO ops.stock_snapshot(warehouse_id,global_product_id,on_hand,wms_reserved,as_of) "
        "VALUES(1,1,99,3,'2026-11-04T08:35Z')",
    )


def run_stock(
    db: str,
    body: dict[str, object],
    *,
    catalogue: list[dict[str, object]] | None = None,
    unavailable: bool = False,
    changed_during_read: bool = False,
    now=NOW,
    **options: object,
):
    async def scenario():
        calls = 0

        def source(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            assert request.method == "GET"
            if request.url.path == "/products":
                assert "updated_since" not in request.url.params
                return page(catalogue if catalogue is not None else [product()])
            assert request.url.path == "/stock"
            calls += 1
            if unavailable:
                return httpx.Response(503, json={"error": {"code": "STOCK_UNAVAILABLE"}})
            return httpx.Response(
                200, json={**body, **({"batch_id": 2} if changed_during_read and calls > 1 else {})}
            )

        engine = create_async_engine(async_url(db), poolclass=NullPool, hide_parameters=True)
        try:
            result = await sync_entity(
                "SE",
                "stock",
                maker=async_sessionmaker(engine, expire_on_commit=False),
                adapter=RestMarketAdapter(
                    "SE", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
                ),
                now=now,
                **options,
            )
            async with async_sessionmaker(engine)() as session:
                available = await usable(session, 1, now=now)
            return result, available
        finally:
            await engine.dispose()

    return asyncio.run(scenario())


@pytest.mark.parametrize("empty", [False, True])
def test_US_INT_03_AC1_unconfigured_scope_never_publishes_or_clears_stock(db: str, empty: bool) -> None:
    prepare(db)
    execute(
        db,
        rows.order_sql(1),
        rows.run_sql(1, 1),
        "INSERT INTO plan.stock_reservation(run_id,order_id,warehouse_id,global_product_id,qty,status) "
        "VALUES(1,1,1,1,5,'held')",
        "INSERT INTO ref.location(market_id,type,code,name,lat,lon,loading_cutoff_time) "
        "VALUES(2,'warehouse','ZZ-WH','Synthetic',59,18,'15:00')",
        "INSERT INTO ops.stock_snapshot(warehouse_id,global_product_id,on_hand,as_of) "
        "VALUES(3,1,50,'2026-11-04T08:35Z')",
    )
    result, ready = run_stock(db, snapshot(item_count=0, items=[]) if empty else snapshot())
    assert result.status == "failed" and result.rows_ok == 0 and not ready
    assert (
        fetch(db, "SELECT error FROM stg.sync_run WHERE id=$1", result.run_id)[0][0]
        == "STOCK_SCOPE_NOT_CONFIGURED"
    )
    assert [
        (r[0], r[1])
        for r in fetch(db, "SELECT warehouse_id,on_hand FROM ops.stock_snapshot ORDER BY warehouse_id")
    ] == [(1, Decimal(99)), (3, Decimal(50))]
    assert tuple(fetch(db, "SELECT qty,status FROM plan.stock_reservation")[0]) == (Decimal(5), "held")
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")
    assert fetch(db, "SELECT reason_code FROM stg.sync_reject")[0][0] == "STOCK_SCOPE_NOT_CONFIGURED"


@pytest.mark.parametrize(
    "failure",
    [
        "unmapped",
        "alias",
        "unit_drift",
        "unknown_warehouse",
        "older",
        "unavailable",
        "racing",
        "future",
        "fractional",
        "negative",
    ],
)
def test_Q9_stock_diagnostic_retains_previous_data_on_every_failure(db: str, failure: str) -> None:
    prepare(db)
    body, catalogue = snapshot(), [product()]
    if failure in {"unmapped", "alias"}:
        catalogue.append(product(sku="P2"))
        body = snapshot(
            item_count=2,
            items=[
                {"warehouse_code": "WH-1", "sku": "P1", "on_hand": "10", "reserved": "2"},
                {"warehouse_code": "WH-1", "sku": "P2", "on_hand": "5", "reserved": "0"},
            ],
        )
        if failure == "alias":
            execute(
                db,
                "INSERT INTO ref.product_se(local_sku,name,category,sale_unit,unit_price,global_product_id,"
                "mapping_status,mapped_by) VALUES('P2','Synthetic','Test','pcs',0,1,'confirmed',1)",
            )
    elif failure == "unit_drift":
        catalogue = [product(units_to_base="2.0000")]
    elif failure == "unknown_warehouse":
        body = snapshot(items=[{"warehouse_code": "OTHER", "sku": "P1", "on_hand": "5", "reserved": "0"}])
    elif failure in {"older", "future"}:
        body = snapshot(
            as_of=(NOW + (timedelta(minutes=1) if failure == "future" else -timedelta(hours=1))).isoformat()
        )
    elif failure in {"fractional", "negative"}:
        body = snapshot(
            items=[
                {
                    "warehouse_code": "WH-1",
                    "sku": "P1",
                    "on_hand": "1.0001" if failure == "fractional" else "-1",
                    "reserved": "0",
                }
            ]
        )
    result, ready = run_stock(
        db,
        body,
        catalogue=catalogue,
        unavailable=failure == "unavailable",
        changed_during_read=failure == "racing",
    )
    assert result.status == "failed" and result.rows_ok == 0 and not ready
    assert tuple(fetch(db, "SELECT on_hand,wms_reserved FROM ops.stock_snapshot")[0]) == (
        Decimal(99),
        Decimal(3),
    )
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='SYNC_FAILED'")[0][0] == 1
    if failure in {"unmapped", "alias", "unit_drift", "unknown_warehouse", "older", "fractional"}:
        # No implicit scope from confirmed mappings, and no guessed independence evidence.
        assert fetch(db, "SELECT error FROM stg.sync_run")[0][0] == "STOCK_SCOPE_NOT_CONFIGURED"


def test_Q9_explicit_retry_is_new_failed_history_until_scope_handoff(db: str) -> None:
    prepare(db)
    first, _ = run_stock(db, snapshot())
    second, ready = run_stock(db, snapshot(), retry_run_id=first.run_id)
    assert first.run_id != second.run_id and second.status == "failed" and not ready
    assert fetch(db, "SELECT count(*) FROM stg.sync_run WHERE status='failed'")[0][0] == 2
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='SYNC_FAILED'")[0][0] == 1
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")
    assert fetch(db, "SELECT on_hand FROM ops.stock_snapshot")[0][0] == Decimal(99)


def test_Q9_missing_scope_prevents_risk_callback_and_preserves_approved_commitments(db: str) -> None:
    from tests.integration.test_ingest_orders import prepare as prepare_order

    prepare_order(db, approved=True)
    execute(
        db,
        "INSERT INTO ops.stock_snapshot(warehouse_id,global_product_id,on_hand,wms_reserved,as_of) "
        "VALUES(1,1,99,3,'2026-11-04T08:35Z')",
    )
    calls: list[int] = []

    async def risk(session, order_id, trigger):
        calls.append(order_id)

    result, ready = run_stock(db, snapshot(), risk=risk)
    assert result.status == "failed" and not ready and not calls
    assert fetch(db, "SELECT on_hand FROM ops.stock_snapshot")[0][0] == Decimal(99)
    assert tuple(fetch(db, "SELECT qty,status FROM plan.stock_reservation")[0]) == (Decimal(5), "committed")
    assert fetch(db, "SELECT status FROM ops.customer_order")[0][0] == "APPROVED"
