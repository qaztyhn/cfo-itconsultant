"""GET /orders (06 section 16; SRC-Q1/Q3/Q6/Q7): real PostgreSQL, order snapshot and incremental paging."""

import os
from collections.abc import AsyncIterator
from datetime import date, datetime, time
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import ORDER_SNAPSHOT_COLUMNS, initialize
from app.main import create_app
from app.models import Address, Customer, Order, OrderLine, Product

KEY = "orders-test-key-not-a-secret"
H = {"X-API-Key": KEY}


@pytest.fixture
async def src() -> AsyncIterator[tuple[AsyncClient, AsyncEngine, str]]:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("SOURCE_TEST_DATABASE_URL is required for real PostgreSQL integration tests")
    schema = "src_test_" + uuid4().hex
    settings = Settings(url, schema, KEY)
    engine = create_engine(settings)
    await initialize(engine, schema)
    app = create_app(settings)
    app.state.settings, app.state.engine = settings, engine
    async with engine.begin() as c:
        await c.execute(insert(Customer), [{"id": "C-1", "name": "Cust", "type": "business"}])
        await c.execute(insert(Address), [{"id": "A-1", "customer_id": "C-1", "address": "Live St 1"}])
        await c.execute(
            insert(Product),
            [
                {
                    "sku": "SE-CEM-25", "name": "Cement", "sale_unit": "bag", "units_to_base": Decimal(1),
                    "unit_price": Decimal(95), "weight_kg": Decimal(25), "volume_m3": Decimal("0.018"),
                }
            ],
        )  # fmt: skip
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://source.test") as http:
            yield http, engine, schema
    finally:
        async with engine.begin() as c:
            await c.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()


def _line(line_no: int, qty: Decimal, price: Decimal) -> dict[str, object]:
    return {"order_id": "POS-1", "line_no": line_no, "sku": "SE-CEM-25", "qty": qty, "unit_price": price}


def _order(order_id: str, status: str = "SUBMITTED_FOR_PLANNING", **extra: object) -> dict[str, object]:
    return {
        "id": order_id, "version": 1, "customer_id": "C-1", "address_id": "A-1", "date_mode": "latest",
        "date_to": date(2026, 11, 18), "window_start": time(8), "window_end": time(12), "status": status,
        "sales_code": "S-090", "store_code": "ST-021", "address": "Snapshot St 9", "lat": Decimal("59.32938"),
        "lon": Decimal("18.06871"), "contact_name": "Erik Berg", "contact_phone": "+46700000000",
        "contact_email": "erik@example.test", "receiving_restrictions": "Gate code 4411",
        "special_requirements": None, **extra,
    }  # fmt: skip


async def test_US_SRC_02_order_representation_uses_snapshot_not_live_address(
    src: tuple[AsyncClient, AsyncEngine, str],
) -> None:
    http, engine, _ = src
    async with engine.begin() as c:
        await c.execute(insert(Order), [_order("POS-1")])
        await c.execute(
            insert(OrderLine),
            [
                _line(2, Decimal("2.5"), Decimal("95.00")),
                _line(1, Decimal(20), Decimal("950")),
            ],
        )  # fmt: skip
        await c.execute(text(f"UPDATE {_s(engine)}.src_address SET address='Moved Rd 5', lat=1, lon=2"))
    r = await http.get("/api/v1/orders", headers=H)
    assert r.status_code == 200 and r.headers["X-Total-Count"] == "1"
    body = r.json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 50, 1)
    [o] = body["items"]
    assert o["address"] == "Snapshot St 9" and o["lat"] == 59.32938  # the later address change is not copied
    assert o["contact"] == {"name": "Erik Berg", "phone": "+46700000000", "email": "erik@example.test"}
    assert (o["window_start"], o["window_end"], o["date_from"], o["date_to"]) == (
        "08:00",
        "12:00",
        None,
        "2026-11-18",
    )
    assert o["receiving_restrictions"] == "Gate code 4411" and o["special_requirements"] is None
    assert [(ln["line_no"], ln["qty"], ln["unit_price"]) for ln in o["lines"]] == [
        (1, 20, "950.00"),
        (2, 2.5, "95.00"),
    ]
    assert datetime.fromisoformat(o["updated_at"]).tzinfo is not None


def _s(engine: AsyncEngine) -> str:
    return str(engine.sync_engine.get_execution_options()["schema_translate_map"]["source"])


async def test_US_SRC_02_paging_is_stable_with_equal_updated_at_and_filters_status(
    src: tuple[AsyncClient, AsyncEngine, str],
) -> None:
    http, engine, _ = src
    async with engine.begin() as c:  # one transaction: all rows share the same updated_at
        await c.execute(
            insert(Order),
            [_order(i) for i in ("O-3", "O-1", "O-5", "O-2", "O-4")] + [_order("O-9", "CANCELLED")],
        )
    seen: list[str] = []
    for page in (1, 2, 3):
        r = await http.get("/api/v1/orders", headers=H, params={"page": page, "page_size": 2})
        assert r.headers["X-Total-Count"] == "5"
        seen += [i["id"] for i in r.json()["items"]]
    assert seen == ["O-1", "O-2", "O-3", "O-4", "O-5"]  # id breaks ties; nothing skipped or repeated
    assert (await http.get("/api/v1/orders", headers=H, params={"page": 4, "page_size": 2})).json()[
        "items"
    ] == []
    cancelled = await http.get("/api/v1/orders", headers=H, params={"status": "CANCELLED"})
    assert [i["id"] for i in cancelled.json()["items"]] == ["O-9"]


async def test_US_SRC_02_updated_since_is_inclusive(src: tuple[AsyncClient, AsyncEngine, str]) -> None:
    http, engine, _ = src
    async with engine.begin() as c:
        await c.execute(insert(Order), [_order("O-1")])
    async with engine.begin() as c:
        await c.execute(insert(Order), [_order("O-2")])
    first, second = (
        datetime.fromisoformat(i["updated_at"])
        for i in (await http.get("/api/v1/orders", headers=H)).json()["items"]
    )
    assert first < second
    at_first = await http.get("/api/v1/orders", headers=H, params={"updated_since": first.isoformat()})
    assert [i["id"] for i in at_first.json()["items"]] == ["O-1", "O-2"]  # >=, boundary row is re-delivered
    at_second = await http.get("/api/v1/orders", headers=H, params={"updated_since": second.isoformat()})
    assert [i["id"] for i in at_second.json()["items"]] == ["O-2"]


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 501},
        {"status": "SOMETHING"},
        {"updated_since": "2026-11-05T07:00:00"},  # no timezone
    ],
)
async def test_US_SRC_02_invalid_query_is_422_without_echoing_input(
    src: tuple[AsyncClient, AsyncEngine, str], params: dict[str, object]
) -> None:
    http, _, _ = src
    r = await http.get("/api/v1/orders", headers=H, params=params)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_ERROR" and error["details"]["errors"]
    assert all(set(e) == {"loc", "type", "msg"} for e in error["details"]["errors"])
    assert all(str(v) not in r.text for v in params.values() if str(v) not in ("0",))


async def test_US_SRC_02_missing_key_is_rejected_before_query_validation(
    src: tuple[AsyncClient, AsyncEngine, str],
) -> None:
    http, _, _ = src
    assert (await http.get("/api/v1/orders", params={"page": 0})).status_code == 400
    assert (
        await http.get("/api/v1/orders", headers={"X-API-Key": "wrong"}, params={"page": 0})
    ).status_code == 401


async def test_SRC_Q1_additive_upgrade_keeps_existing_orders(
    src: tuple[AsyncClient, AsyncEngine, str],
) -> None:
    http, engine, schema = src
    async with engine.begin() as c:
        await c.execute(insert(Order), [_order("OLD-1")])
        for column, _ in ORDER_SNAPSHOT_COLUMNS:  # simulate an instance created before SRC-Q1
            await c.execute(text(f'ALTER TABLE "{schema}".src_order DROP COLUMN {column}'))
    await initialize(engine, schema)
    await initialize(engine, schema)  # repeatable
    [o] = (await http.get("/api/v1/orders", headers=H)).json()["items"]
    assert o["id"] == "OLD-1" and o["address"] is None and o["contact"]["name"] is None
