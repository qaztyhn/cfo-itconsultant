"""GET /stock (06 section 16, US-SRC-02): real PostgreSQL; shape consumed by the CFO REST adapter."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import initialize
from app.main import create_app
from app.models import Product, Stock
from app.stock_batches import StockInput, publish

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
    data = StockInput.model_validate(
        {
            "as_of": older,
            "items": [
                {
                    "warehouse_code": "STO",
                    "sku": "A-1",
                    "physical_stock_pool_id": "pool-a",
                    "on_hand": Decimal("12.5"),
                    "reserved": 2,
                },
                {
                    "warehouse_code": "GBG",
                    "sku": "B-2",
                    "physical_stock_pool_id": "pool-b",
                    "on_hand": Decimal(800),
                    "reserved": 20,
                },
                {
                    "warehouse_code": "GBG",
                    "sku": "A-1",
                    "physical_stock_pool_id": "pool-a",
                    "on_hand": Decimal(0),
                    "reserved": 0,
                },
            ],
        }
    )
    async with AsyncSession(engine) as session, session.begin():
        await publish(session, data, source_instance="synthetic", now=newer)
    response = await http.get("/api/v1/stock", headers={"X-API-Key": KEY})
    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["as_of"]) == older  # one authoritative complete batch capture
    assert [(i["warehouse_code"], i["sku"]) for i in body["items"]] == [
        ("GBG", "A-1"), ("GBG", "B-2"), ("STO", "A-1"),
    ]  # fmt: skip
    assert set(body["items"][0]) == {"warehouse_code", "sku", "physical_stock_pool_id", "on_hand", "reserved"}
    assert body["items"][1]["on_hand"] == 800 and isinstance(body["items"][1]["on_hand"], int)
    assert body["items"][2]["on_hand"] == 12.5


async def test_US_SRC_02_empty_stock_does_not_invent_as_of(client: tuple[AsyncClient, AsyncEngine]) -> None:
    http, _ = client
    response = await http.get("/api/v1/stock", headers={"X-API-Key": KEY})
    assert response.status_code == 200
    assert response.json() == {
        "as_of": None,
        "batch_id": None,
        "complete": False,
        "row_count": 0,
        "items": [],
    }  # No published batch is unavailable, not zero inventory.


async def test_US_SRC_02_stock_requires_key(client: tuple[AsyncClient, AsyncEngine]) -> None:
    http, _ = client
    assert (await http.get("/api/v1/stock")).status_code == 400
    assert (await http.get("/api/v1/stock", headers={"X-API-Key": "wrong"})).status_code == 401


async def test_D1_published_empty_batch_is_authoritative_and_retry_is_idempotent(
    client: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = client
    capture = datetime(2026, 11, 5, 7, tzinfo=UTC)
    data = StockInput(as_of=capture, items=[])
    async with AsyncSession(engine) as session, session.begin():
        first = await publish(session, data, source_instance="synthetic", now=capture)
    async with AsyncSession(engine) as session, session.begin():
        assert await publish(session, data, source_instance="synthetic", now=capture) == first
    result = (await http.get("/api/v1/stock", headers={"X-API-Key": KEY})).json()
    assert result["complete"] is True and result["batch_id"] == first and result["row_count"] == 0
    assert result["items"] == [] and datetime.fromisoformat(result["as_of"]) == capture


async def test_D1_legacy_rows_without_a_published_marker_never_look_complete(
    client: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = client
    async with engine.begin() as c:
        await c.execute(insert(Product), [_product("P1")])
        await c.execute(insert(Stock), [_stock("WH", "P1", Decimal(5), 0, datetime(2026, 11, 5, tzinfo=UTC))])
    result = (await http.get("/api/v1/stock", headers={"X-API-Key": KEY})).json()
    assert result["as_of"] is None and result["complete"] is False and result["items"] == []


async def test_D1_failed_publication_rolls_back_and_source_read_never_sees_uncommitted_batch(
    client: tuple[AsyncClient, AsyncEngine],
) -> None:
    from sqlalchemy.exc import IntegrityError

    http, engine = client
    before = datetime(2026, 11, 5, 7, tzinfo=UTC)
    later = datetime(2026, 11, 5, 8, tzinfo=UTC)
    async with AsyncSession(engine) as session, session.begin():
        first = await publish(
            session, StockInput(as_of=before, items=[]), source_instance="synthetic", now=before
        )
    bad = StockInput.model_validate(
        {
            "as_of": later,
            "items": [
                {
                    "warehouse_code": "WH",
                    "sku": "MISSING",
                    "physical_stock_pool_id": "pool",
                    "on_hand": 1,
                    "reserved": 0,
                }
            ],
        }
    )
    with pytest.raises(IntegrityError):
        async with AsyncSession(engine) as session, session.begin():
            await publish(session, bad, source_instance="synthetic", now=later)
    async with AsyncSession(engine) as session, session.begin():
        await publish(session, StockInput(as_of=later, items=[]), source_instance="synthetic", now=later)
        result = (await http.get("/api/v1/stock", headers={"X-API-Key": KEY})).json()
        assert result["batch_id"] == first  # uncommitted publish cannot escape as an empty replacement
    result = (await http.get("/api/v1/stock", headers={"X-API-Key": KEY})).json()
    assert result["batch_id"] > first


async def test_D1_stock_publication_rejects_duplicate_and_changed_capture_intent(
    client: tuple[AsyncClient, AsyncEngine],
) -> None:
    _, engine = client
    capture = datetime(2026, 11, 5, tzinfo=UTC)
    item = {
        "warehouse_code": "WH",
        "sku": "P1",
        "physical_stock_pool_id": "pool",
        "on_hand": 1,
        "reserved": 0,
    }
    async with engine.begin() as c:
        await c.execute(insert(Product), [_product("P1")])
    async with AsyncSession(engine) as session, session.begin():
        await publish(
            session,
            StockInput.model_validate({"as_of": capture, "items": [item]}),
            source_instance="synthetic",
            now=capture,
        )
    for rows in ([item, item], [{**item, "on_hand": 2}]):
        with pytest.raises(ValueError):
            async with AsyncSession(engine) as session, session.begin():
                await publish(
                    session,
                    StockInput.model_validate({"as_of": capture, "items": rows}),
                    source_instance="synthetic",
                    now=capture,
                )


async def test_D1_corrupted_published_rows_are_unknown_not_a_partial_snapshot(
    client: tuple[AsyncClient, AsyncEngine],
) -> None:
    from sqlalchemy import update

    http, engine = client
    capture = datetime(2026, 11, 5, tzinfo=UTC)
    async with engine.begin() as c:
        await c.execute(insert(Product), [_product("P1")])
    async with AsyncSession(engine) as session, session.begin():
        data = StockInput.model_validate(
            {
                "as_of": capture,
                "items": [
                    {
                        "warehouse_code": "WH",
                        "sku": "P1",
                        "physical_stock_pool_id": "pool",
                        "on_hand": 1,
                        "reserved": 0,
                    }
                ],
            }
        )
        await publish(session, data, source_instance="synthetic", now=capture)
    async with engine.begin() as c:
        await c.execute(update(Stock).values(on_hand=2))
    result = (await http.get("/api/v1/stock", headers={"X-API-Key": KEY})).json()
    assert result["complete"] is False and result["as_of"] is None and result["items"] == []
