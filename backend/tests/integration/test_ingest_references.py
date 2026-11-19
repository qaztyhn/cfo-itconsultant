import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.rest_adapter import RestMarketAdapter
from app.services.ingest_service import sync_entity
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_ingest_runner import NOW, item, page
from tests.integration.test_ingest_runner import db as db

pytestmark = pytest.mark.integration


def run_feed(db: str, entity: str, items: list[dict[str, object]], **options: object):
    async def scenario():
        engine = create_async_engine(async_url(db), poolclass=NullPool, hide_parameters=True)
        try:
            return await sync_entity(
                "SE",
                entity,
                maker=async_sessionmaker(engine, expire_on_commit=False),
                adapter=RestMarketAdapter(
                    "SE",
                    "https://source.test",
                    "synthetic-key",
                    transport=httpx.MockTransport(lambda request: page(items)),
                ),
                now=NOW,
                **options,
            )
        finally:
            await engine.dispose()

    return asyncio.run(scenario())


def product(**changes: object) -> dict[str, object]:
    return {
        "sku": "P1",
        "name": "Synthetic product",
        "category": "Test",
        "gtin": None,
        "sale_unit": "pcs",
        "units_to_base": "1.0000",
        "unit_price": "0.00",
        "weight_kg": "1.000",
        "volume_m3": "0.0100",
        "updated_at": NOW.isoformat(),
        **changes,
    }


def mapped(db: str) -> None:
    execute(
        db,
        "INSERT INTO ref.product_se(local_sku,name,category,sale_unit,units_to_base,unit_price,"
        "global_product_id,mapping_status,mapped_by) "
        "VALUES('P1','Synthetic','Test','pcs',1,0,1,'confirmed',1)",
    )


def inbound(key: str = "I1", **changes: object) -> dict[str, object]:
    return {
        "inbound_ref": key,
        "warehouse_code": "WH-1",
        "sku": "P1",
        "qty": "1.125",
        "eta_date": "2026-11-05",
        "confirmed": True,
        "received": False,
        "updated_at": NOW.isoformat(),
        **changes,
    }


def test_US_INT_01_customers_upsert_without_rehydrating_anonymised_contacts(db: str) -> None:
    first = run_feed(db, "customers", [item("C2")])
    second = run_feed(db, "customers", [item("C2", name="Updated synthetic")])
    assert first.status == second.status == "ok"
    customer = fetch(db, "SELECT name,email FROM ref.customer WHERE external_ref='C2'")[0]
    assert customer["name"] == "Updated synthetic" and customer["email"] == "private@example.test"
    execute(
        db, "UPDATE ref.customer SET is_anonymised=true,name='Anonymised',email=NULL WHERE external_ref='C2'"
    )
    assert run_feed(db, "customers", [item("C2")]).status == "partial"
    assert fetch(db, "SELECT name FROM ref.customer WHERE external_ref='C2'")[0][0] == "Anonymised"


def test_US_INT_03_products_pending_is_ok_stale_source_is_skipped_and_mapping_preserved(db: str) -> None:
    first = run_feed(db, "products", [product(updated_at=(NOW - timedelta(seconds=30)).isoformat())])
    assert first.status == "ok" and first.rows_rejected == 0
    assert fetch(db, "SELECT mapping_status FROM ref.product_se WHERE local_sku='P1'")[0][0] == "pending"
    assert fetch(db, "SELECT count(*) FROM ref.mapping_task WHERE local_sku='P1'")[0][0] == 1
    execute(
        db,
        "UPDATE ref.product_se SET mapping_status='confirmed',global_product_id=1,mapped_by=1 "
        "WHERE local_sku='P1'",
    )
    stale = run_feed(
        db, "products", [product(name="Older", updated_at=(NOW - timedelta(seconds=60)).isoformat())]
    )
    assert stale.status == "ok"
    assert fetch(db, "SELECT name FROM ref.product_se WHERE local_sku='P1'")[0][0] == "Synthetic product"
    assert run_feed(db, "products", [product(name="New synthetic")]).status == "ok"
    row = fetch(db, "SELECT name,mapping_status,global_product_id FROM ref.product_se WHERE local_sku='P1'")[
        0
    ]
    assert tuple(row) == ("New synthetic", "confirmed", 1)


def test_US_INT_03_source_unit_change_is_rejected_instead_of_reinterpreting_existing_inventory(
    db: str,
) -> None:
    mapped(db)
    result = run_feed(db, "products", [product(sale_unit="pallet", units_to_base="40.0000")])
    assert result.status == "partial"
    assert fetch(db, "SELECT reason_code FROM stg.sync_reject")[0][0] == "UNIT_CONVERSION_CHANGED"
    assert fetch(db, "SELECT sale_unit,units_to_base FROM ref.product_se WHERE local_sku='P1'")[0][0] == "pcs"


def test_US_INT_03_inbound_incremental_updates_preserve_transfers_and_reject_bad_rows(db: str) -> None:
    mapped(db)
    execute(
        db,
        "INSERT INTO ops.inbound_shipment(inbound_ref,warehouse_id,global_product_id,qty,eta_date,source) "
        "VALUES('T1',1,1,7,'2026-11-05','transfer')",
    )
    result = run_feed(
        db,
        "inbound",
        [inbound("I1"), inbound("I2", qty="-5"), inbound("I3", warehouse_code="OTHER"), inbound("T1")],
    )
    assert (result.status, result.rows_ok, result.rows_rejected) == ("partial", 1, 3)
    assert {row[0] for row in fetch(db, "SELECT reason_code FROM stg.sync_reject")} == {
        "BAD_QTY",
        "UNKNOWN_WAREHOUSE",
        "SOURCE_KEY_COLLISION",
    }
    assert run_feed(db, "inbound", [inbound("I1", received=True)]).status == "ok"
    assert fetch(db, "SELECT received FROM ops.inbound_shipment WHERE inbound_ref='I1'")[0][0]
    assert fetch(db, "SELECT qty,source FROM ops.inbound_shipment WHERE inbound_ref='T1'")[0][1] == "transfer"
    assert run_feed(db, "inbound", []).status == "ok"  # a delta is not evidence of upstream deletion.


def test_US_INT_03_fleet_is_idempotent_and_does_not_replace_manual_calendar_entries(db: str) -> None:
    execute(
        db,
        "INSERT INTO ref.vehicle_availability(vehicle_id,during,kind,source) VALUES "
        "(1,'[2026-11-05 10:00Z,2026-11-05 11:00Z)','unavailable','manual')",
    )
    calendar = {
        "vehicle_code": "V-1",
        "from": "2026-11-05T11:00:00Z",
        "to": "2026-11-05T12:00:00Z",
        "kind": "external_booking",
        "updated_at": NOW.isoformat(),
    }
    assert run_feed(db, "fleet", [calendar]).status == "ok"
    assert run_feed(db, "fleet", [calendar]).status == "ok"
    assert fetch(db, "SELECT count(*) FROM ref.vehicle_availability")[0][0] == 2
    assert fetch(db, "SELECT kind FROM ref.vehicle_availability WHERE source='manual'")[0][0] == "unavailable"


def test_US_INT_03_fleet_collision_is_partial_and_never_erases_manual_busy_time(db: str) -> None:
    execute(
        db,
        "INSERT INTO ref.vehicle_availability(vehicle_id,during,kind,source) VALUES "
        "(1,'[2026-11-05 10:00Z,2026-11-05 11:00Z)','maintenance','manual')",
    )
    result = run_feed(
        db,
        "fleet",
        [
            {
                "vehicle_code": "V-1",
                "from": "2026-11-05T10:30:00Z",
                "to": "2026-11-05T12:00:00Z",
                "kind": "external_booking",
                "updated_at": NOW.isoformat(),
            }
        ],
    )
    assert result.status == "partial" and result.rows_rejected == 1
    assert fetch(db, "SELECT count(*) FROM ref.vehicle_availability")[0][0] == 1


def test_US_INT_03_inbound_aliases_do_not_overwrite_the_same_global_row(db: str) -> None:
    mapped(db)
    execute(
        db,
        "INSERT INTO ref.product_se(local_sku,name,category,sale_unit,unit_price,global_product_id,"
        "mapping_status,mapped_by) VALUES('P2','Synthetic','Test','pcs',0,1,'confirmed',1)",
    )
    result = run_feed(db, "inbound", [inbound()])
    assert result.status == "partial"
    assert not fetch(db, "SELECT * FROM ops.inbound_shipment")
