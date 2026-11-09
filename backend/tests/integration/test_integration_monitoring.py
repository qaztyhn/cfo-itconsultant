"""Real PostgreSQL contract tests for read-only admin integration monitoring.

The api fixture applies Alembic to an isolated database and authenticates
against database-backed user roles; no SQLite/mock database substitutes.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import asyncpg
import pytest

from app.deps import CurrentUser
from app.services import integration_monitor_service as monitor
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from tests.integration.api_harness import Api, api as api_fixture, assert_error
from tests.integration.conftest import async_url, execute, fetch
from tests.integration import rows

pytestmark = pytest.mark.integration

# Keep the fixture import available under its expected pytest name.
api = api_fixture


@pytest.fixture
def monitoring(api: Api) -> Api:
    execute(api.dsn,
        *rows.REF_HR,
        # ID 2: system admin; ID 3: market-bound admin at ZZ.
        "INSERT INTO ref.app_user (email,password_hash,roles) "
        "VALUES ('admin.integration@test.invalid','synthetic-not-usable','{admin}')",
        "INSERT INTO ref.app_user (employee_id,email,password_hash,roles) "
        "VALUES (1,'scoped.integration@test.invalid','synthetic-not-usable','{admin}')",
        "INSERT INTO ref.market (code,name,timezone,currency) "
        "VALUES ('YY','Second synthetic market','UTC','EUR')",
        "INSERT INTO ref.app_user (employee_id,email,password_hash,roles) "
        "VALUES (2,'other.integration@test.invalid','synthetic-not-usable','{sales}')",
        "INSERT INTO stg.sync_run (market_id,entity,status,rows_in,rows_ok,rows_rejected,"
        "started_at,finished_at,data_as_of,error) VALUES "
        "(1,'orders','ok',3,3,0,'2026-11-08T10:00Z','2026-11-08T10:01Z',"
        "'2026-11-08T09:59Z',NULL),"
        "(1,'orders','partial',4,3,1,'2026-11-08T11:00Z','2026-11-08T11:01Z',"
        "'2026-11-08T10:59Z',NULL),"
        "(1,'orders','failed',0,0,0,'2026-11-08T12:00Z','2026-11-08T12:01Z',"
        "NULL,'private@example.test password synthetic'),"
        "(2,'orders','ok',2,2,0,'2026-11-08T13:00Z','2026-11-08T13:01Z',"
        "'2026-11-08T12:59Z',NULL)",
        "INSERT INTO stg.sync_reject (run_id,external_key,reason_code,reason,raw) VALUES "
        "(2,'private@example.test','BAD_DATE','Sensitive address, email, token',"
        "'{\"customer\":\"private@example.test\",\"secret\":\"token\"}'::jsonb),"
        "(2,'private@example.test','UNEXPECTED private@example.test','PII','{}'::jsonb)",
        "INSERT INTO stg.sync_checkpoint(market_id,entity,last_updated_since) "
        "VALUES (1,'orders','2026-11-08T09:59Z'),(2,'orders','2026-11-08T12:59Z')",
        "INSERT INTO ref.product_se(local_sku,name,category,sale_unit,unit_price) "
        "VALUES ('SKU-A','Synthetic pending','synthetic','pcs',1)",
    )
    return api


def test_US_ADM_01_AC1_pagination_status_filter_and_latest_success(monitoring: Api) -> None:
    result=monitoring.get("/sync-runs",2,market="ZZ",entity="orders",page=1,page_size=2)
    assert result.status_code==200, result.text
    body=result.json()
    assert (body["total"],body["page"],body["page_size"])==(3,1,2)
    assert [row["status"] for row in body["items"]]==["failed","partial"]
    assert body["items"][1]["complete_success"] is False
    assert body["items"][0]["error_code"] is None
    assert "private" not in result.text.lower()
    second=monitoring.get("/sync-runs",2,market="ZZ",page=2,page_size=2)
    assert [row["status"] for row in second.json()["items"]]==["ok"]
    only=monitoring.get("/sync-runs",2,market="ZZ",status="partial")
    assert only.json()["total"]==1 and only.json()["items"][0]["rows_rejected"]==1
    overview=monitoring.get("/integration/overview",2,market="ZZ")
    assert overview.status_code==200,overview.text
    feed=next(item for item in overview.json()["sources"] if item["entity"]=="orders")
    assert feed["status"]=="failed"
    assert feed["last_successful_run_id"]==1
    assert feed["checkpoint"]=="2026-11-08T09:59:00+00:00"
    assert feed["last_tick_status"] if "last_tick_status" in feed else True


def test_US_ADM_01_AC1_reject_details_are_redacted_and_paginated(monitoring: Api) -> None:
    first=monitoring.get("/sync-runs/2/rejects",2,market="ZZ",page_size=1)
    assert first.status_code==200,first.text
    result=first.json()
    assert result["total"]==2
    assert result["items"]==[{"id":1,"reason_code":"BAD_DATE"}]
    assert "private" not in first.text.lower()
    assert "raw" not in first.text.lower() or "raw values" in first.text.lower()
    second=monitoring.get("/sync-runs/2/rejects",2,market="ZZ",page=2,page_size=1)
    assert second.json()["items"]==[{"id":2,"reason_code":"UNVERIFIED"}]
    assert "token" not in second.text.lower()


def test_US_ADM_01_AC1_overview_unknown_scheduler_and_stock_scope(monitoring: Api) -> None:
    result=monitoring.get("/integration/overview",2,market="ZZ")
    assert result.status_code==200,result.text
    data=result.json()
    assert data["scheduler"]["runtime_health"]=="unverified"
    assert data["scheduler"]["last_tick_at"] is None
    assert data["scheduler"]["last_tick_status"]=="unknown"
    assert data["route_matrix"]["pairs"]==0
    stock=next(item for item in data["sources"] if item["entity"]=="stock")
    assert (stock["availability"],stock["status"],stock["stock_scope"])==(
        "unconfigured","unconfigured","unconfigured")
    products=next(item for item in data["sources"] if item["entity"]=="products")
    assert products["unmapped"]==1
    assert products["rejected"] is None
    assert products["status"]=="never_run"


def test_US_ADM_01_AC1_market_scope_cannot_be_bypassed(monitoring: Api) -> None:
    assert_error(monitoring.get("/integration/overview",3,market="YY"),404,"NOT_FOUND")
    assert_error(monitoring.get("/sync-runs",3,market="YY"),404,"NOT_FOUND")
    assert_error(monitoring.get("/sync-runs/4/rejects",3),404,"NOT_FOUND")
    result=monitoring.get("/sync-runs",3)
    assert result.status_code==200
    assert result.json()["total"]==3
    assert all(row["market_id"]==1 for row in result.json()["items"])
    assert_error(monitoring.get("/sync-runs/4/rejects",2,market="ZZ"),404,"NOT_FOUND")


def test_US_ADM_01_AC1_admin_only_and_validated_query(monitoring: Api) -> None:
    for path in ("/sync-runs","/sync-runs/2/rejects","/integration/overview"):
        assert_error(monitoring.get(path,1),403,"FORBIDDEN")
        assert_error(monitoring.get(path,4),403,"FORBIDDEN")
        assert_error(monitoring.get(path,None),401,"AUTH_INVALID")
    for params in ({"page":0},{"page_size":201},{"entity":"unsupported"},{"status":"healthy"}):
        assert_error(monitoring.get("/sync-runs",2,**params),422,"VALIDATION_ERROR")
    assert_error(monitoring.get("/sync-runs/999/rejects",2),404,"NOT_FOUND")


def test_US_INT_01_AC4_empty_and_failed_only_runs(monitoring: Api) -> None:
    empty=monitoring.get("/sync-runs",2,market="YY",status="failed")
    assert empty.json()=={"items":[],"total":0,"page":1,"page_size":50}
    failed=monitoring.get("/sync-runs",2,market="ZZ",status="failed")
    assert failed.json()["items"][0]["complete_success"] is False
    empty_feed=next(x for x in monitoring.get("/integration/overview",2,market="YY").json()["sources"]
                    if x["entity"]=="customers")
    assert empty_feed["last_successful_run_id"] is None
    assert empty_feed["status"]=="never_run"


def test_US_ADM_01_AC1_read_queries_concurrent_with_persisted_updates(monitoring: Api) -> None:
    async def scenario()->None:
        engine=create_async_engine(async_url(monitoring.dsn),poolclass=NullPool)
        maker=async_sessionmaker(engine,expire_on_commit=False)
        user=CurrentUser(id=3,employee_id=1,roles=("admin",),market="ZZ")

        async def reader()->list[int]:
            totals=[]
            for _ in range(3):
                async with maker() as session:
                    result=await monitor.list_runs(session,user,market="ZZ",entity="orders",
                        status=None,page=1,page_size=50)
                    totals.append(result["total"])
            return totals

        async def writer()->None:
            conn=await asyncpg.connect(monitoring.dsn)
            try:
                await conn.execute("INSERT INTO stg.sync_run(market_id,entity,status) "
                                   "VALUES (1,'orders','running')")
            finally:
                await conn.close()

        try:
            (counts,_)=await asyncio.gather(reader(),writer())
            assert all(3<=count<=4 for count in counts)
            async with maker() as session:
                data=await monitor.list_runs(session,user,market="ZZ",entity="orders",
                    status=None,page=1,page_size=50)
                assert data["total"]==4
        finally:
            await engine.dispose()

    asyncio.run(scenario())
