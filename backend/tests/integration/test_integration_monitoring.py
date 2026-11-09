"""Real PostgreSQL monitoring tests with database-backed users and scope."""

import asyncio

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.deps import CurrentUser
from app.services import integration_monitor_service as monitor
from tests.integration import rows
from tests.integration.api_harness import Api, assert_error
from tests.integration.api_harness import api as api_fixture
from tests.integration.conftest import async_url, execute

pytestmark = pytest.mark.integration
api = api_fixture


@pytest.fixture
def monitoring(api: Api) -> Api:
    execute(
        api.dsn,
        *rows.REF_HR,
        "INSERT INTO ref.app_user (email,password_hash,roles) "
        "VALUES ('admin.integration@test.invalid','synthetic-not-usable','{admin}')",
        "INSERT INTO hr.employee (market_id,employee_no,first_name,last_name,position_code,hire_date) "
        "VALUES (1,'E3','Synthetic','Three','TEST_POS','2026-01-01')",
        "INSERT INTO ref.app_user (employee_id,email,password_hash,roles) "
        "VALUES (3,'scoped.integration@test.invalid','synthetic-not-usable','{admin}')",
        "INSERT INTO ref.market (code,name,timezone,currency) "
        "VALUES ('YY','Second synthetic market','UTC','EUR')",
        "INSERT INTO ref.market (code,name,timezone,currency) "
        "VALUES ('SE','Synthetic Sweden','Europe/Stockholm','SEK')",
        "INSERT INTO ref.app_user (employee_id,email,password_hash,roles) "
        "VALUES (2,'other.integration@test.invalid','synthetic-not-usable','{sales}')",
        "INSERT INTO stg.sync_run "
        "(market_id,entity,status,rows_in,rows_ok,rows_rejected,"
        "started_at,finished_at,data_as_of,error) VALUES "
        "(1,'orders','ok',3,3,0,'2026-11-08T10:00Z','2026-11-08T10:01Z',"
        "'2026-11-08T09:59Z',NULL),"
        "(1,'orders','partial',4,3,1,'2026-11-08T11:00Z',"
        "'2026-11-08T11:01Z','2026-11-08T10:59Z',NULL),"
        "(1,'orders','failed',0,0,0,'2026-11-08T12:00Z',"
        "'2026-11-08T12:01Z',NULL,'private@example.test synthetic'),"
        "(2,'orders','ok',2,2,0,'2026-11-08T13:00Z',"
        "'2026-11-08T13:01Z','2026-11-08T12:59Z',NULL)",
        "INSERT INTO stg.sync_reject (run_id,external_key,reason_code,reason,raw) "
        "VALUES (2,'private@example.test','BAD_DATE',"
        "'Sensitive address email token',"
        '\'{"customer":"private@example.test","secret":"token"}\'::jsonb),'
        "(2,'private@example.test','UNEXPECTED private@example.test',"
        "'PII','{}'::jsonb)",
        "INSERT INTO stg.sync_checkpoint(market_id,entity,last_updated_since) VALUES "
        "(1,'orders','2026-11-08T09:59Z'),"
        "(2,'orders','2026-11-08T12:59Z')",
        "INSERT INTO ref.product_se(local_sku,name,category,sale_unit,unit_price) "
        "VALUES ('SKU-A','Synthetic pending','synthetic','pcs',1)",
    )
    return api


def test_US_ADM_01_AC1_pagination_status_filter_latest_success(monitoring: Api) -> None:
    result = monitoring.get("/sync-runs", 2, market="ZZ", entity="orders", page_size=2)
    assert result.status_code == 200, result.text
    body = result.json()
    assert (body["total"], body["page"], body["page_size"]) == (3, 1, 2)
    assert [row["status"] for row in body["items"]] == ["failed", "partial"]
    assert body["items"][1]["complete_success"] is False
    assert body["items"][0]["error_code"] is None
    assert "private" not in result.text.lower()
    second = monitoring.get("/sync-runs", 2, market="ZZ", page=2, page_size=2)
    assert [row["status"] for row in second.json()["items"]] == ["ok"]
    partial = monitoring.get("/sync-runs", 2, market="ZZ", status="partial")
    assert partial.json()["total"] == 1
    assert partial.json()["items"][0]["rows_rejected"] == 1
    overview = monitoring.get("/integration/overview", 2, market="ZZ")
    assert overview.status_code == 200, overview.text
    feed = next(item for item in overview.json()["sources"] if item["entity"] == "orders")
    assert feed["status"] == "failed"
    assert feed["last_successful_run_id"] == 1
    assert feed["checkpoint"] == "2026-11-08T09:59:00+00:00"


def test_US_ADM_01_AC1_rejects_are_redacted_and_paginated(monitoring: Api) -> None:
    first = monitoring.get("/sync-runs/2/rejects", 2, market="ZZ", page_size=1)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["total"] == 2
    assert result["items"] == [{"id": 1, "reason_code": "BAD_DATE"}]
    assert "private" not in first.text.lower()
    second = monitoring.get("/sync-runs/2/rejects", 2, market="ZZ", page=2, page_size=1)
    assert second.json()["items"] == [{"id": 2, "reason_code": "UNVERIFIED"}]
    assert "token" not in second.text.lower()


def test_US_ADM_01_AC1_stock_scheduler_and_mapping_status(monitoring: Api) -> None:
    result = monitoring.get("/integration/overview", 2, market="ZZ")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["scheduler"]["runtime_health"] == "unverified"
    assert data["scheduler"]["last_tick_at"] is None
    assert data["scheduler"]["last_tick_status"] == "unknown"
    assert data["scheduler"]["jobs"] == []
    assert "stock" not in data["scheduler"]["supported_feed_types"]
    assert data["route_matrix"]["pairs"] == 0
    stock = next(item for item in data["sources"] if item["entity"] == "stock")
    assert (
        stock["availability"],
        stock["status"],
        stock["stock_scope"],
    ) == ("unconfigured", "unconfigured", "unconfigured")
    products = next(item for item in data["sources"] if item["entity"] == "products")
    assert products["unmapped"] == 0  # ZZ has no local product catalog.
    sweden = monitoring.get("/integration/overview", 2, market="SE")
    se_products = next(
        item for item in sweden.json()["sources"] if item["entity"] == "products"
    )
    assert se_products["unmapped"] == 1
    assert products["rejected"] is None
    assert products["status"] == "never_run"


def test_US_ADM_01_AC1_market_scope_cannot_be_bypassed(monitoring: Api) -> None:
    assert_error(monitoring.get("/integration/overview", 3, market="YY"), 404, "NOT_FOUND")
    assert_error(monitoring.get("/sync-runs", 3, market="YY"), 404, "NOT_FOUND")
    assert_error(monitoring.get("/sync-runs/4/rejects", 3), 404, "NOT_FOUND")
    result = monitoring.get("/sync-runs", 3)
    assert result.status_code == 200
    assert result.json()["total"] == 3
    assert all(row["market_id"] == 1 for row in result.json()["items"])
    assert_error(
        monitoring.get("/sync-runs/4/rejects", 2, market="ZZ"),
        404,
        "NOT_FOUND",
    )


def test_US_ADM_01_AC1_role_gate_and_query_validation(monitoring: Api) -> None:
    for path in (
        "/sync-runs",
        "/sync-runs/2/rejects",
        "/integration/overview",
    ):
        assert_error(monitoring.get(path, 1), 403, "FORBIDDEN")
        assert_error(monitoring.get(path, 4), 403, "FORBIDDEN")
        assert_error(monitoring.get(path, None), 401, "AUTH_INVALID")
    for params in (
        {"page": 0},
        {"page_size": 201},
        {"entity": "unsupported"},
        {"status": "healthy"},
    ):
        assert_error(monitoring.get("/sync-runs", 2, **params), 422, "VALIDATION_ERROR")
    assert_error(monitoring.get("/sync-runs/999/rejects", 2), 404, "NOT_FOUND")


def test_US_INT_01_AC4_empty_and_failed_only_runs(monitoring: Api) -> None:
    empty = monitoring.get("/sync-runs", 2, market="YY", status="failed")
    assert empty.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 50,
    }
    failed = monitoring.get("/sync-runs", 2, market="ZZ", status="failed")
    assert failed.json()["items"][0]["complete_success"] is False
    overview = monitoring.get("/integration/overview", 2, market="YY")
    empty_feed = next(item for item in overview.json()["sources"] if item["entity"] == "customers")
    assert empty_feed["last_successful_run_id"] is None
    assert empty_feed["status"] == "never_run"


def test_US_ADM_01_AC1_concurrent_read_and_persisted_insert(
    monitoring: Api,
) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_url(monitoring.dsn), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        user = CurrentUser(id=3, employee_id=3, roles=("admin",), market="ZZ")

        async def reader() -> list[int]:
            totals: list[int] = []
            for _ in range(3):
                async with maker() as session:
                    result = await monitor.list_runs(
                        session,
                        user,
                        market="ZZ",
                        entity="orders",
                        status=None,
                        page=1,
                        page_size=50,
                    )
                    totals.append(result["total"])
            return totals

        async def writer() -> None:
            conn = await asyncpg.connect(monitoring.dsn)
            try:
                await conn.execute(
                    "INSERT INTO stg.sync_run(market_id,entity,status) " "VALUES (1,'orders','running')"
                )
            finally:
                await conn.close()

        try:
            counts, _ = await asyncio.gather(reader(), writer())
            assert all(3 <= count <= 4 for count in counts)
            async with maker() as session:
                result = await monitor.list_runs(
                    session,
                    user,
                    market="ZZ",
                    entity="orders",
                    status=None,
                    page=1,
                    page_size=50,
                )
                assert result["total"] == 4
        finally:
            await engine.dispose()

    asyncio.run(scenario())
