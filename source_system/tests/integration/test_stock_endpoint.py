"""GET /stock (06 section 16, US-SRC-02): real PostgreSQL; shape consumed by the CFO REST adapter."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import initialize
from app.main import create_app
from app.models import Product, Stock

KEY = "stock-test-key-not-a-secret"


@pytest.fixture
async def client() -> AsyncIterator[tuple[AsyncClient, AsyncEngine]]:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("SOURCE_TEST_DATABASE_URL is required for real PostgreSQL integration tests")
    schema = "src_test_" + uuid4().hex
    settings = Settings(url, schema, KEY)
    engine = create_engine(settings)
    await initialize(engine, schema)
    app = create_app(settings)
    app.state.settings, app.state.engine = settings, engine
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://source.test") as http:
            yield http, engine
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()


def _product(sku: str) -> dict[str, object]:
    return {
        "sku": sku, "name": sku, "sale_unit": "bag", "units_to_base": Decimal(1),
        "unit_price": Decimal(10), "weight_kg": Decimal(1), "volume_m3": Decimal("0.01"),
    }  # fmt: skip


def _stock(warehouse: str, sku: str, on_hand: Decimal, reserved: int, as_of: datetime) -> dict[str, object]:
    return {
        "warehouse_code": warehouse, "sku": sku, "on_hand": on_hand,
        "reserved": Decimal(reserved), "as_of": as_of,
    }  # fmt: skip


async def test_US_SRC_02_stock_snapshot_shape_order_and_numbers(
    client: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = client
    newer, older = datetime(2026, 11, 5, 8, tzinfo=UTC), datetime(2026, 11, 5, 7, tzinfo=UTC)
    async with engine.begin() as connection:
        await connection.execute(insert(Product), [_product("B-2"), _product("A-1")])
        await connection.execute(
            insert(Stock),
            [
                _stock("STO", "A-1", Decimal("12.5"), 2, newer),
                _stock("GBG", "B-2", Decimal(800), 20, older),
                _stock("GBG", "A-1", Decimal(0), 0, newer),
            ],
        )
    response = await http.get("/api/v1/stock", headers={"X-API-Key": KEY})
    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["as_of"]) == older  # oldest row: never claims fresher data
    assert [(i["warehouse_code"], i["sku"]) for i in body["items"]] == [
        ("GBG", "A-1"), ("GBG", "B-2"), ("STO", "A-1"),
    ]  # fmt: skip
    assert set(body["items"][0]) == {"warehouse_code", "sku", "on_hand", "reserved"}
    assert body["items"][1]["on_hand"] == 800 and isinstance(body["items"][1]["on_hand"], int)
    assert body["items"][2]["on_hand"] == 12.5


async def test_US_SRC_02_empty_stock_does_not_invent_as_of(client: tuple[AsyncClient, AsyncEngine]) -> None:
    http, _ = client
    response = await http.get("/api/v1/stock", headers={"X-API-Key": KEY})
    assert response.status_code == 200
    assert response.json() == {
        "as_of": None,
        "items": [],
    }  # SRC-Q9 open: adapter rejects instead of zero stock


async def test_US_SRC_02_stock_requires_key(client: tuple[AsyncClient, AsyncEngine]) -> None:
    http, _ = client
    assert (await http.get("/api/v1/stock")).status_code == 400
    assert (await http.get("/api/v1/stock", headers={"X-API-Key": "wrong"})).status_code == 401
