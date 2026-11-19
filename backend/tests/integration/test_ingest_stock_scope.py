"""#121 x #148: the stock writer is gated by the approved versioned scope (S3/S4) on real PostgreSQL."""

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.integration.conftest import execute, fetch
from tests.integration.test_ingest_references import product
from tests.integration.test_ingest_runner import NOW
from tests.integration.test_ingest_runner import db as db  # noqa: F401
from tests.integration.test_ingest_stock import prepare, run_stock, snapshot

pytestmark = pytest.mark.integration

APPROVE = (
    "INSERT INTO ref.app_user (employee_id, email, password_hash, roles) "
    "VALUES (2,'a2@cfo.test','x','{admin}')",
    "INSERT INTO ops.stock_scope_version (market_id,version,status,skus,warehouse_ids,reason_text,created_by,"
    "approved_by,approved_at,effective_from) VALUES (1,1,'approved','{P1}','{1}','Pilot scope',1,2,"
    "'2026-11-01T00:00Z','2026-11-01T00:00Z')",
)


def stock_rows(db: str) -> list[tuple[int, int, Decimal, Decimal]]:
    return [
        tuple(r)
        for r in fetch(
            db,
            "SELECT warehouse_id,global_product_id,on_hand,wms_reserved FROM ops.stock_snapshot ORDER BY 1,2",
        )
    ]


def test_S3_approved_scope_effective_at_batch_as_of_writes_the_complete_batch_and_binds_versions(
    db: str,
) -> None:
    prepare(db)
    execute(db, *APPROVE)
    result, ready = run_stock(db, snapshot())
    assert result.status == "ok", result
    assert stock_rows(db) == [(1, 1, Decimal("10.000"), Decimal("2.000"))]
    run = fetch(
        db,
        "SELECT source_batch_id,status,scope_version_id,expected_rows,recorded_rows FROM ops.stock_write_run",
    )
    assert [tuple(r) for r in run] == [(1, "accepted", 1, 1, 1)]
    assert ready is True  # fresh write bound to the still effective scope


def test_S3_scope_approved_after_the_batch_as_of_is_never_retroactive(db: str) -> None:
    prepare(db)
    execute(
        db,
        APPROVE[0],
        "INSERT INTO ops.stock_scope_version (market_id,version,status,skus,warehouse_ids,reason_text,"
        "created_by,approved_by,approved_at,effective_from) VALUES (1,1,'approved','{P1}','{1}','Late',1,2,"
        "'2026-11-05T00:00Z','2026-11-05T00:00Z')",
    )
    result, ready = run_stock(db, snapshot())  # batch as_of 2026-11-04 precedes the approval
    assert result.status == "failed" and not ready
    assert (
        fetch(db, "SELECT error FROM stg.sync_run WHERE id=$1", result.run_id)[0][0]
        == "STOCK_SCOPE_NOT_CONFIGURED"
    )
    assert stock_rows(db) == [(1, 1, Decimal("99.000"), Decimal("3.000"))]  # previous stock untouched
    assert not fetch(db, "SELECT * FROM ops.stock_write_run")
    assert not fetch(db, "SELECT * FROM stg.sync_checkpoint")


def test_S4_missing_required_row_rejects_everything_and_explicit_zero_is_valid(
    db: str,
) -> None:
    prepare(db)
    execute(db, *APPROVE)
    other = snapshot(items=[{"warehouse_code": "WH-1", "sku": "OTHER", "on_hand": "5", "reserved": "0"}])
    result, _ = run_stock(db, other, catalogue=[product()])
    assert result.status == "failed"
    assert (
        fetch(db, "SELECT error FROM stg.sync_run WHERE id=$1", result.run_id)[0][0] == "STOCK_ROWS_MISSING"
    )
    assert stock_rows(db) == [(1, 1, Decimal("99.000"), Decimal("3.000"))]  # missing is unknown, not zero
    zero = snapshot(
        batch_id=2,
        items=[{"warehouse_code": "WH-1", "sku": "P1", "on_hand": "0", "reserved": "0"}],
    )
    result, _ = run_stock(db, zero)
    assert result.status == "ok"
    assert stock_rows(db) == [(1, 1, Decimal("0.000"), Decimal("0.000"))]  # an explicit zero is zero


def test_S4_out_of_scope_rows_are_ignored_and_never_block(db: str) -> None:
    prepare(db)
    execute(db, *APPROVE)
    body = snapshot(
        item_count=2,
        items=[
            {"warehouse_code": "WH-1", "sku": "P1", "on_hand": "10", "reserved": "2"},
            {
                "warehouse_code": "WH-9",
                "sku": "NOT-IN-SCOPE",
                "on_hand": "7",
                "reserved": "0",
            },
        ],
    )
    result, _ = run_stock(db, body)
    assert result.status == "ok"
    assert stock_rows(db) == [(1, 1, Decimal("10.000"), Decimal("2.000"))]


def test_unit_drift_in_scope_rejects_the_whole_batch(db: str) -> None:
    prepare(db)
    execute(db, *APPROVE)
    result, _ = run_stock(db, snapshot(), catalogue=[product(sale_unit="box")])
    assert result.status == "failed"
    assert (
        fetch(db, "SELECT error FROM stg.sync_run WHERE id=$1", result.run_id)[0][0]
        == "STOCK_NORMALIZATION_REJECTED"
    )
    assert stock_rows(db) == [(1, 1, Decimal("99.000"), Decimal("3.000"))]


def test_replaying_the_same_published_batch_is_a_noop_and_a_new_batch_replaces(
    db: str,
) -> None:
    prepare(db)
    execute(db, *APPROVE)
    assert run_stock(db, snapshot())[0].status == "ok"
    assert run_stock(db, snapshot())[0].status == "ok"  # poll sees the same batch id again
    assert fetch(db, "SELECT count(*) FROM ops.stock_write_run")[0][0] == 1
    assert (
        run_stock(
            db,
            snapshot(
                batch_id=2,
                items=[
                    {
                        "warehouse_code": "WH-1",
                        "sku": "P1",
                        "on_hand": "8",
                        "reserved": "1",
                    }
                ],
            ),
        )[0].status
        == "ok"
    )
    assert stock_rows(db) == [(1, 1, Decimal("8.000"), Decimal("1.000"))]


def test_US_APR_01_AC1_wms_batch_two_is_distinct_from_source_batch_two(db: str) -> None:
    prepare(db)
    execute(db, *APPROVE)
    source = snapshot(
        batch_id=2,
        items=[{"warehouse_code": "WH-1", "sku": "P1", "on_hand": "10", "reserved": "0"}],
    )
    assert run_stock(db, source)[0].status == "ok"
    wms = snapshot(
        batch_id=2,
        items=[{"warehouse_code": "WH-1", "sku": "P1", "on_hand": "10", "reserved": "4"}],
    )
    result, _ = run_stock(db, wms, stock_origin="wms_synthetic")
    assert result.status == "ok"
    assert stock_rows(db) == [(1, 1, Decimal("10.000"), Decimal("4.000"))]
    runs = fetch(
        db,
        "SELECT source_kind,source_batch_id,ingest_run_id FROM ops.stock_write_run ORDER BY id",
    )
    assert [tuple(row) for row in runs] == [
        ("source", 2, 1),
        ("wms_synthetic", 2, result.run_id),
    ]


def test_freshness_and_scope_supersession_make_stock_unusable(db: str) -> None:
    prepare(db)
    execute(db, *APPROVE)
    run_stock(db, snapshot())
    _, fresh = run_stock(db, snapshot(), now=NOW + timedelta(minutes=5))
    assert fresh is True
    _, stale = run_stock(db, snapshot(), now=NOW + timedelta(minutes=30))  # default stale_stock_min is 15
    assert stale is False
    execute(
        db,
        "UPDATE ops.stock_scope_version SET status='superseded', superseded_at='2026-11-04T09:10Z'",
        "INSERT INTO ops.stock_scope_version (market_id,version,status,skus,warehouse_ids,reason_text,"
        "created_by,approved_by,approved_at,effective_from) VALUES (1,2,'approved','{P1}','{1}','v2',1,2,"
        "'2026-11-04T09:10Z','2026-11-04T09:10Z')",
    )
    _, after_change = run_stock(db, snapshot(batch_id=3), now=NOW + timedelta(minutes=5))
    # a write bound to the superseded version is not usable under the new one: a new batch is required
    assert after_change is False
    newer = snapshot(batch_id=4, as_of=(NOW + timedelta(minutes=6)).isoformat())
    _, renewed = run_stock(db, newer, now=NOW + timedelta(minutes=7))
    assert renewed is True
