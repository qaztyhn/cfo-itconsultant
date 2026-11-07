"""API ánh xạ SKU (06 v1.4 mục 12.1–12.2).

US-PRD-01 AC1–AC4, US-PRD-02, US-PRD-03, US-PRD-04 AC2/AC4, US-PRD-05.

Người dùng và địa điểm ở hr_fixture (market 1 = SE; market 2 = ZZ). Danh mục global: G-1 (GTIN trùng SKU
SE-NEW-77), G-2 (tên gần giống, cùng category), G-3 (tên giống nhưng khác category). Quy tắc 'Cement%' → N3.
Hai đơn SE chứa SE-NEW-77 bị chặn qua prepare_for_planning thật.
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.order_service import prepare_for_planning
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401  (fixture)
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.hr_fixture import (
    ADMIN,
    CS,
    DISPATCHER,
    DRIVER,
    SALES,
    SETUP,
    SYSTEM_ADMIN,
    VIEWER,
    WAREHOUSE,
    ZZ_WAREHOUSE,
)
from tests.integration.order_rows import order_sql

pytestmark = pytest.mark.integration
GTIN = "7312345678901"


def _global(code: str, name: str, category: str, gtin: str | None = None) -> str:
    g = f"'{gtin}'" if gtin else "NULL"
    return (
        "INSERT INTO ref.product_global (code, name, category, gtin, base_unit, weight_kg, volume_m3, "
        f"handling_group_id) VALUES ('{code}', '{name}', '{category}', {g}, 'bag', 25, 0.018, 3)"
    )


def _local(sku: str, name: str, status: str = "pending", gtin: str | None = None) -> str:
    g = f"'{gtin}'" if gtin else "NULL"
    return (
        "INSERT INTO ref.product_se (local_sku, name, category, gtin, sale_unit, units_to_base, unit_price, "
        f"weight_kg, mapping_status) VALUES ('{sku}', '{name}', 'Cement', {g}, 'bag', 1, 95, 25, '{status}')"
    )


async def _prepare(dsn: str, *order_ids: int) -> None:
    engine = create_async_engine(async_url(dsn), poolclass=NullPool)
    try:
        for order_id in order_ids:
            async with async_sessionmaker(engine)() as session, session.begin():
                await prepare_for_planning(session, order_id)
    finally:
        await engine.dispose()


@pytest.fixture
def mp(api: Api) -> Api:  # noqa: F811
    execute(
        api.dsn,
        *SETUP,
        "INSERT INTO ref.customer (market_id, external_ref, type, name) "
        "VALUES (1, 'C-1', 'business', 'Cust')",
        _global("G-1", "Portland cement", "Cement", GTIN),
        _global("G-2", "Cement 25 kg bag", "Cement"),
        _global("G-3", "Cement 25 kg bag", "Tools"),
        "INSERT INTO ref.handling_group_rule (priority, category_like, handling_group_id) "
        "VALUES (10, 'Cement%', 3)",
        _local("SE-NEW-77", "Cement 25kg bag", gtin=GTIN),
        _local("SE-P-2", "Mortar bag"),
        _local("SE-P-3", "Tile adhesive"),
        _local("SE-OK", "Mapped cement", "rejected"),
        *order_sql(1, "SUBMITTED", ("SE-NEW-77",)),
        *order_sql(2, "SUBMITTED", ("SE-NEW-77",)),
    )
    asyncio.run(_prepare(api.dsn, 1, 2))
    return api


def test_US_PRD_01_AC3_AC4_task_lists_gtin_and_name_candidates(mp: Api) -> None:
    r = mp.get("/mapping/tasks", DISPATCHER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1 and body["page"] == 1
    [task] = body["items"]
    assert (task["local_sku"], task["blocked_order_count"], task["status"], task["market"]) == (
        "SE-NEW-77",
        2,
        "open",
        "SE",
    )
    assert task["mapping_status"] == "pending" and task["resolved_by"] is None
    reasons = [(c["code"], c["reason"]) for c in task["candidates"]]
    assert reasons[0] == ("G-1", "gtin") and task["candidates"][0]["score"] == 1.0
    assert ("G-2", "name_sim") in reasons and 0.45 <= task["candidates"][1]["score"] < 1
    assert "G-3" not in [code for code, _ in reasons]  # khác category
    assert "blocked_orders" not in task and "suggested_handling_group" not in task


def test_US_PRD_04_AC2_detail_has_suggested_group_and_blocked_orders(mp: Api) -> None:
    r = mp.get("/mapping/tasks/1", ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["suggested_handling_group"] == "N3"
    assert body["blocked_orders"] == [{"id": 1, "order_no": "SE-000001"}, {"id": 2, "order_no": "SE-000002"}]
    # warehouse: đơn chưa có kế hoạch từ kho mình → không liệt kê, tổng vẫn giữ
    w = mp.get("/mapping/tasks/1", WAREHOUSE).json()
    assert w["blocked_orders"] == [] and w["blocked_order_count"] == 2


@pytest.mark.parametrize("user_id", [ADMIN, SYSTEM_ADMIN, DISPATCHER, WAREHOUSE])
def test_read_allowed_roles(mp: Api, user_id: int) -> None:
    assert mp.get("/mapping/tasks", user_id).json()["total"] == 1
    assert mp.get("/products/local", user_id).status_code == 200


@pytest.mark.parametrize("user_id", [SALES, DRIVER, CS, VIEWER])
def test_read_forbidden_roles(mp: Api, user_id: int) -> None:
    assert_error(mp.get("/mapping/tasks", user_id), 403, "FORBIDDEN")
    assert_error(mp.get("/mapping/tasks/1", user_id), 403, "FORBIDDEN")
    assert_error(mp.get("/products/local", user_id), 403, "FORBIDDEN")


def test_other_market_cannot_see_task(mp: Api) -> None:
    assert mp.get("/mapping/tasks", ZZ_WAREHOUSE).json()["total"] == 0
    assert_error(mp.get("/mapping/tasks/1", ZZ_WAREHOUSE), 404, "NOT_FOUND")
    assert mp.get("/products/local", ZZ_WAREHOUSE).json()["total"] == 0


def test_US_PRD_02_AC1_confirm_unblocks_orders(mp: Api) -> None:
    r = mp.send("POST", "/mapping/tasks/1/confirm", ADMIN, {"global_product_id": 1, "units_to_base": 1})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "task_id": 1,
        "local_sku": "SE-NEW-77",
        "global_product_id": 1,
        "mapping_status": "confirmed",
        "ready_order_ids": [1, 2],
        "still_blocked_order_ids": [],
    }
    statuses = [
        row["status"] for row in fetch(mp.dsn, "SELECT status::text AS status FROM ops.customer_order")
    ]
    assert statuses == ["SUBMITTED", "SUBMITTED"]
    assert fetch(mp.dsn, "SELECT action FROM audit.decision_log")[0]["action"] == "MAPPING_CONFIRMED"


@pytest.mark.parametrize("user_id", [DISPATCHER, WAREHOUSE, SALES, DRIVER, CS, VIEWER, SYSTEM_ADMIN])
def test_US_PRD_02_AC2_only_it_with_employee_record_writes(mp: Api, user_id: int) -> None:
    body = {"global_product_id": 1, "units_to_base": 1}
    assert_error(mp.send("POST", "/mapping/tasks/1/confirm", user_id, body), 403, "FORBIDDEN")
    assert_error(mp.send("POST", "/mapping/tasks/1/reject", user_id, {"reason_text": "x"}), 403, "FORBIDDEN")
    assert fetch(
        mp.dsn, "SELECT mapping_status::text AS s FROM ref.product_se WHERE local_sku = 'SE-NEW-77'"
    )[0]["s"] == ("pending")


def test_US_PRD_04_AC4_create_global_n6_fragile_rejected(mp: Api) -> None:
    body = {
        "units_to_base": 1,
        "create_global": {
            "code": "G-9",
            "name": "Glass door",
            "category": "Doors",
            "base_unit": "pcs",
            "weight_kg": 30,
            "volume_m3": 0.5,
            "handling_group_code": "N6",
            "base_units_per_prep_unit": 1,
            "flags": ["FRAGILE"],
        },
    }
    r = mp.send("POST", "/mapping/tasks/1/confirm", ADMIN, body)
    assert_error(r, 422, "VALIDATION_ERROR")
    assert r.json()["error"]["details"]["field"] == "create_global.flags"


def test_confirm_body_is_strict(mp: Api) -> None:
    r = mp.send(
        "POST", "/mapping/tasks/1/confirm", ADMIN, {"global_product_id": 1, "units_to_base": 1, "x": 1}
    )
    assert_error(r, 422, "VALIDATION_ERROR")
    missing = mp.send(
        "POST", "/mapping/tasks/999/confirm", ADMIN, {"global_product_id": 1, "units_to_base": 1}
    )
    assert_error(missing, 404, "NOT_FOUND")


def test_US_PRD_03_reject_requires_reason_then_keeps_orders_blocked(mp: Api) -> None:
    assert_error(mp.send("POST", "/mapping/tasks/1/reject", ADMIN, {}), 422, "REASON_REQUIRED")
    assert_error(
        mp.send("POST", "/mapping/tasks/1/reject", ADMIN, {"reason_text": "  "}), 422, "REASON_REQUIRED"
    )
    r = mp.send("POST", "/mapping/tasks/1/reject", ADMIN, {"reason_text": "Discontinued"})
    assert r.status_code == 200, r.text
    assert r.json() == {"task_id": 1, "local_sku": "SE-NEW-77", "mapping_status": "rejected"}
    assert (
        mp.get("/mapping/tasks", DISPATCHER, status="done").json()["items"][0]["mapping_status"] == "rejected"
    )
    rows = fetch(mp.dsn, "SELECT status::text AS s, block_reason FROM ops.customer_order ORDER BY id")
    assert all(r["s"] == "BLOCKED_UNMAPPED_SKU" and "Discontinued" in r["block_reason"] for r in rows)


def test_US_PRD_05_AC1_local_products_filter_and_paginate(mp: Api) -> None:
    r = mp.get("/products/local", ADMIN, market="SE", mapping_status="pending", page_size=2)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3 and [i["local_sku"] for i in body["items"]] == ["SE-NEW-77", "SE-P-2"]
    item = body["items"][0]
    assert item["market"] == "SE" and item["mapping_status"] == "pending" and item["gtin"] == GTIN
    page2 = mp.get("/products/local", ADMIN, mapping_status="pending", page_size=2, page=2).json()
    assert [i["local_sku"] for i in page2["items"]] == ["SE-P-3"]
    assert mp.get("/products/local", DISPATCHER, q="mortar").json()["total"] == 1


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/mapping/tasks", {"status": "closed"}),
        ("/mapping/tasks", {"sort": "name"}),
        ("/products/local", {"mapping_status": "unknown"}),
        ("/products/local", {"sort": "-price"}),
        ("/products/local", {"page_size": 201}),
    ],
)
def test_invalid_query_parameters(mp: Api, path: str, params: dict[str, object]) -> None:
    assert_error(mp.get(path, ADMIN, **params), 422, "VALIDATION_ERROR")
