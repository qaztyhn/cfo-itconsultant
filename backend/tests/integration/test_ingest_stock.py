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


def test_US_INT_03_AC1_stock_converts_once_preserves_holds_and_replay_keeps_original_capture(db: str) -> None:
    prepare(db)
    execute(
        db,
        "UPDATE ref.product_se SET units_to_base=2 WHERE local_sku='P1'",
        rows.order_sql(1),
        rows.run_sql(1, 1),
        "INSERT INTO plan.stock_reservation(run_id,order_id,warehouse_id,global_product_id,qty,status) "
        "VALUES(1,1,1,1,5,'held')",
    )
    args = {"catalogue": [product(units_to_base="2.0000")]}
    first, ready = run_stock(db, snapshot(), **args)
    assert first.status == "ok" and first.rows_ok == 1 and ready
    row = fetch(db, "SELECT on_hand,wms_reserved,as_of,run_id FROM ops.stock_snapshot")[0]
    assert tuple(row) == (Decimal(20), Decimal(4), NOW, first.run_id)
    second, ready = run_stock(db, snapshot(), **args)
    assert second.status == "ok" and ready
    assert fetch(db, "SELECT run_id FROM ops.stock_snapshot")[0][0] == first.run_id
    assert tuple(fetch(db, "SELECT qty,status FROM plan.stock_reservation")[0]) == (Decimal(5), "held")


@pytest.mark.parametrize(
    "failure", ["unmapped", "alias", "unit_drift", "unknown_warehouse", "older", "unavailable", "racing"]
)
def test_Q9_stock_failure_never_commits_partial_or_zero_and_retains_previous_batch(
    db: str, failure: str
) -> None:
    prepare(db)
    body, catalogue = snapshot(), [product()]
    if failure in {"unmapped", "alias"}:
        catalogue.append(product(sku="P2"))
        body = snapshot(
            item_count=2,
            items=[
                {"warehouse_code": "WH-1", "sku": "P1", "on_hand": "10.000", "reserved": "2.000"},
                {"warehouse_code": "WH-1", "sku": "P2", "on_hand": "5.000", "reserved": "0.000"},
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
    elif failure == "older":
        body = snapshot(as_of=(NOW - timedelta(hours=1)).isoformat())
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


def test_Q9_complete_empty_batch_is_scoped_zero_and_distinct_from_unavailable(db: str) -> None:
    prepare(db)
    execute(
        db,
        "INSERT INTO ref.location(market_id,type,code,name,lat,lon,loading_cutoff_time) "
        "VALUES(2,'warehouse','ZZ-WH','Synthetic',59,18,'15:00')",
        "INSERT INTO ops.stock_snapshot(warehouse_id,global_product_id,on_hand,as_of) "
        "VALUES(3,1,50,'2026-11-04T08:35Z')",
    )
    result, ready = run_stock(db, snapshot(item_count=0, items=[]))
    assert result.status == "ok" and result.rows_in == result.rows_ok == 0 and ready
    assert [(row[0], row[1]) for row in fetch(db, "SELECT warehouse_id,on_hand FROM ops.stock_snapshot")] == [
        (3, Decimal(50))
    ]
    unavailable, ready = run_stock(db, snapshot(), unavailable=True)
    assert unavailable.status == "failed" and not ready
    assert fetch(db, "SELECT data_as_of FROM stg.sync_run WHERE status='ok'")[0][0] == NOW


def test_Q9_same_capture_conflict_fails_and_explicit_retry_recovers_without_refreshing_time(db: str) -> None:
    prepare(db)
    first, _ = run_stock(db, snapshot())
    bad = snapshot(items=[{"warehouse_code": "WH-1", "sku": "P1", "on_hand": "11", "reserved": "2"}])
    failed, ready = run_stock(db, bad)
    assert failed.status == "failed" and not ready
    assert fetch(db, "SELECT on_hand FROM ops.stock_snapshot")[0][0] == Decimal(10)
    recovered, ready = run_stock(db, snapshot(), retry_run_id=failed.run_id)
    assert recovered.status == "ok" and ready
    assert fetch(db, "SELECT as_of,run_id FROM ops.stock_snapshot")[0][1] == first.run_id
    assert fetch(db, "SELECT count(*) FROM stg.sync_run")[0][0] == 3


def test_US_INT_03_AC2_stale_capture_is_not_renewed_and_freshness_warning_is_deduplicated(db: str) -> None:
    prepare(db)
    old = NOW - timedelta(minutes=20)
    result, ready = run_stock(db, snapshot(as_of=old.isoformat()))
    assert result.status == "ok" and not ready
    assert fetch(db, "SELECT as_of FROM ops.stock_snapshot")[0][0] == old
    assert run_stock(db, snapshot(as_of=old.isoformat()))[0].status == "ok"
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='STALE_DATA'")[0][0] == 1


def test_Q9_stock_change_requires_risk_handoff_and_keeps_approved_commitments(db: str) -> None:
    from tests.integration.test_ingest_orders import prepare as prepare_order

    prepare_order(db, approved=True)
    execute(
        db,
        "INSERT INTO ops.stock_snapshot(warehouse_id,global_product_id,on_hand,wms_reserved,as_of) "
        "VALUES(1,1,99,3,'2026-11-04T08:35Z')",
    )
    failed, ready = run_stock(db, snapshot())
    assert failed.status == "failed" and not ready
    assert fetch(db, "SELECT on_hand FROM ops.stock_snapshot")[0][0] == Decimal(99)
    calls: list[int] = []

    async def fake_risk_contract(session, order_id, trigger):
        calls.append(order_id)
        assert trigger == "source_change"

    result, ready = run_stock(db, snapshot(), risk=fake_risk_contract)
    assert result.status == "ok" and ready and calls == [1]
    assert tuple(fetch(db, "SELECT qty,status FROM plan.stock_reservation")[0]) == (Decimal(5), "committed")
    assert fetch(db, "SELECT status,source_version FROM ops.customer_order")[0][0] == "APPROVED"
    assert run_stock(db, snapshot())[0].status == "ok"  # identical batch is not a new risk event.


@pytest.mark.parametrize("failure", ["future", "fractional", "negative"])
def test_Q9_invalid_capture_or_quantity_cannot_replace_retained_stock(db: str, failure: str) -> None:
    prepare(db)
    body = (
        snapshot(as_of=(NOW + timedelta(minutes=1)).isoformat())
        if failure == "future"
        else snapshot(
            items=[
                {
                    "warehouse_code": "WH-1",
                    "sku": "P1",
                    "on_hand": "1.0001" if failure == "fractional" else "-1",
                    "reserved": "0",
                }
            ]
        )
    )
    result, ready = run_stock(db, body)
    assert result.status == "failed" and not ready
    assert fetch(db, "SELECT on_hand FROM ops.stock_snapshot")[0][0] == Decimal(99)
