"""GET /stock (06 section 16.4; DEC-SRC-Q9-ERROR-001, DEC-SRC-Q10-SKU-001): real PostgreSQL, two instances."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import insert, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import initialize
from app.main import create_app
from app.models import Product, Stock, StockBatch
from app.stock_batches import StockInput, publish

KEY = "stock-test-key-not-a-secret"
H = {"X-API-Key": KEY}
T0 = datetime(2026, 11, 5, 7, tzinfo=UTC)

Instance = tuple[AsyncClient, AsyncEngine, str]


async def _instance(url: str) -> tuple[Instance, str]:
    schema = "src_test_" + uuid4().hex
    settings = Settings(url, schema, KEY)
    engine = create_engine(settings)
    await initialize(engine, schema)
    app = create_app(settings)
    app.state.settings, app.state.engine = settings, engine
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://source.test")
    return (client, engine, schema), schema


async def _drop(instance: Instance) -> None:
    client, engine, schema = instance
    await client.aclose()
    async with engine.begin() as connection:
        await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
    await engine.dispose()


def _url() -> str:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("SOURCE_TEST_DATABASE_URL is required for real PostgreSQL integration tests")
    return url


@pytest.fixture
async def src() -> AsyncIterator[Instance]:
    instance, _ = await _instance(_url())
    try:
        yield instance
    finally:
        await _drop(instance)


def _product(sku: str, factor: str = "1") -> dict[str, Any]:
    return {
        "sku": sku, "name": sku, "sale_unit": "bag", "units_to_base": Decimal(factor),
        "unit_price": Decimal(10), "weight_kg": Decimal(1), "volume_m3": Decimal("0.01"),
    }  # fmt: skip


async def _products(engine: AsyncEngine, *skus: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(insert(Product), [_product(s) for s in skus])


def _data(as_of: datetime, *rows: tuple[str, str, int | str, int | str]) -> StockInput:
    return StockInput.model_validate(
        {
            "as_of": as_of,
            "items": [{"warehouse_code": w, "sku": s, "on_hand": o, "reserved": r} for w, s, o, r in rows],
        }
    )


async def _publish(engine: AsyncEngine, data: StockInput, *, now: datetime | None = None) -> int:
    async with AsyncSession(engine) as session, session.begin():
        return await publish(session, data, source_instance="synthetic", now=now or data.as_of)


def _assert_unavailable(response: Any) -> None:
    assert response.status_code == 503
    error = response.json()["error"]
    assert (error["code"], error["message"], error["details"]) == (
        "STOCK_UNAVAILABLE", "Stock snapshot is unavailable.", {},
    )  # fmt: skip
    assert str(UUID(error["correlation_id"])) == response.headers["X-Correlation-ID"]
    assert set(response.json()) == {"error"}  # never a 200-style stock body


async def test_published_batch_shape_order_numbers_and_no_pool_field(src: Instance) -> None:
    http, engine, _ = src
    await _products(engine, "B-2", "A-1")
    batch = await _publish(
        engine,
        _data(T0, ("STO", "A-1", "12.5", 2), ("GBG", "B-2", 800, 20), ("GBG", "A-1", 0, 0)),
        now=T0 + timedelta(hours=1),
    )
    response = await http.get("/api/v1/stock", headers=H)
    assert response.status_code == 200 and "X-Total-Count" not in response.headers  # not paginated
    body = response.json()
    assert set(body) == {"as_of", "batch_id", "item_count", "items"}
    assert datetime.fromisoformat(body["as_of"]) == T0  # the batch capture, never a row-derived min/max
    assert (body["batch_id"], body["item_count"]) == (batch, 3)
    assert [(i["warehouse_code"], i["sku"]) for i in body["items"]] == [
        ("GBG", "A-1"), ("GBG", "B-2"), ("STO", "A-1"),
    ]  # fmt: skip
    assert all(set(i) == {"warehouse_code", "sku", "on_hand", "reserved"} for i in body["items"])
    assert body["items"][1]["on_hand"] == 800 and isinstance(body["items"][1]["on_hand"], int)
    assert body["items"][2]["on_hand"] == 12.5


async def test_no_batch_is_503_stock_unavailable_never_zero(src: Instance) -> None:
    http, _, _ = src
    _assert_unavailable(await http.get("/api/v1/stock", headers=H))
    echoed = await http.get(
        "/api/v1/stock", headers={**H, "X-Correlation-ID": "3f2504e0-4f89-41d3-9a0c-0305e82c3301"}
    )
    assert echoed.headers["X-Correlation-ID"] == "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


async def test_key_is_checked_before_availability(src: Instance) -> None:
    http, _, _ = src
    assert (await http.get("/api/v1/stock")).status_code == 400
    assert (await http.get("/api/v1/stock", headers={"X-API-Key": "wrong"})).status_code == 401


async def test_complete_published_empty_batch_is_200_zero_stock(src: Instance) -> None:
    http, engine, _ = src
    first = await _publish(engine, StockInput(as_of=T0, items=[]))
    assert await _publish(engine, StockInput(as_of=T0, items=[])) == first  # identical retry is idempotent
    result = (await http.get("/api/v1/stock", headers=H)).json()
    assert (result["batch_id"], result["item_count"], result["items"]) == (first, 0, [])
    assert datetime.fromisoformat(result["as_of"]) == T0


async def test_legacy_rows_and_unpublished_batches_are_unavailable(src: Instance) -> None:
    http, engine, _ = src
    await _products(engine, "P1")
    async with engine.begin() as c:  # legacy row: no batch, no completeness proof
        await c.execute(
            insert(Stock), [{"warehouse_code": "WH", "sku": "P1", "on_hand": 5, "reserved": 0, "as_of": T0}]
        )
    _assert_unavailable(await http.get("/api/v1/stock", headers=H))
    unpublished = _header(T0, published_at=None, complete=False, rows=1, digest="x")
    flagged = _header(T0 + timedelta(hours=1), published_at=T0, complete=False, rows=0, digest="y")
    async with engine.begin() as c:  # a batch never published (loading) and one flagged incomplete (failed)
        await c.execute(insert(StockBatch), [unpublished, flagged])
    _assert_unavailable(await http.get("/api/v1/stock", headers=H))


async def test_failed_newer_load_keeps_serving_the_published_batch_with_its_original_as_of(
    src: Instance,
) -> None:
    http, engine, _ = src
    await _products(engine, "P1")
    first = await _publish(engine, _data(T0, ("WH", "P1", 5, 0)))
    later = T0 + timedelta(hours=1)
    with pytest.raises(ValueError):  # unknown SKU: the whole new batch is refused and rolled back
        await _publish(engine, _data(later, ("WH", "P1", 6, 0), ("WH", "MISSING", 1, 0)))
    result = (await http.get("/api/v1/stock", headers=H)).json()
    assert result["batch_id"] == first and datetime.fromisoformat(result["as_of"]) == T0
    assert result["items"][0]["on_hand"] == 5  # the failed load never became an empty or partial replacement
    async with AsyncSession(engine) as session, session.begin():  # uncommitted publication stays invisible
        await publish(session, _data(later, ("WH", "P1", 9, 0)), source_instance="synthetic", now=later)
        assert (await http.get("/api/v1/stock", headers=H)).json()["batch_id"] == first


async def test_each_batch_keeps_its_rows_and_only_the_latest_is_served(src: Instance) -> None:
    http, engine, _ = src
    await _products(engine, "P1")
    first = await _publish(engine, _data(T0, ("WH", "P1", 5, 0)))
    second = await _publish(engine, _data(T0 + timedelta(hours=1), ("WH", "P1", 7, 1)))
    assert second > first
    result = (await http.get("/api/v1/stock", headers=H)).json()
    assert (result["batch_id"], result["items"][0]["on_hand"]) == (second, 7)
    async with engine.connect() as c:
        rows = (await c.execute(select_batches())).all()
    assert sorted((r[0], r[1]) for r in rows) == [(first, 5), (second, 7)]  # history is kept, never rewritten


def _header(
    as_of: datetime, *, published_at: datetime | None, complete: bool, rows: int, digest: str
) -> dict[str, Any]:
    return {
        "source_instance": "synthetic", "as_of": as_of, "published_at": published_at,
        "complete": complete, "row_count": rows, "content_hash": digest,
    }  # fmt: skip


def select_batches() -> Any:
    from sqlalchemy import select

    return select(Stock.batch_id, Stock.on_hand)


async def test_one_row_per_batch_warehouse_sku_is_enforced_before_and_inside_the_database(
    src: Instance,
) -> None:
    _, engine, _ = src
    await _products(engine, "P1")
    row = ("WH", "P1", 1, 0)
    with pytest.raises(ValueError, match="Duplicate"):  # a duplicate is a malformed batch, never summed
        await _publish(engine, _data(T0, row, row))
    batch = await _publish(engine, _data(T0, row))
    with pytest.raises(IntegrityError):  # the database refuses it too
        async with engine.begin() as c:
            await c.execute(
                insert(Stock),
                [
                    {
                        "batch_id": batch,
                        "warehouse_code": "WH",
                        "sku": "P1",
                        "on_hand": 9,
                        "reserved": 0,
                        "as_of": T0,
                    }
                ],
            )
    with pytest.raises(ValueError):  # same capture, different content
        await _publish(engine, _data(T0, ("WH", "P1", 2, 0)))


async def test_publication_refuses_unknown_sku_bad_conversion_pool_field_and_negative_quantity(
    src: Instance,
) -> None:
    _, engine, _ = src
    await _products(engine, "P1")
    async with engine.begin() as c:
        await c.execute(insert(Product), [_product("ZERO", "0")])
    with pytest.raises(ValueError, match="unknown or has no valid"):
        await _publish(engine, _data(T0, ("WH", "NOPE", 1, 0)))
    with pytest.raises(ValueError, match="unknown or has no valid"):  # factor 0: no usable unit conversion
        await _publish(engine, _data(T0, ("WH", "ZERO", 1, 0)))
    good = {"warehouse_code": "WH", "sku": "P1", "on_hand": 1, "reserved": 0}
    for bad in (
        {**good, "physical_stock_pool_id": "pool-a"},
        {**good, "on_hand": -1},
        {**good, "reserved": "NaN"},
    ):
        with pytest.raises(ValidationError):
            StockInput.model_validate({"as_of": T0, "items": [bad]})
    with pytest.raises(ValidationError):
        StockInput.model_validate({"as_of": "2026-11-05T07:00:00", "items": []})  # no timezone


async def test_a_published_batch_that_fails_its_integrity_check_is_unavailable(src: Instance) -> None:
    http, engine, _ = src
    await _products(engine, "P1", "P2")
    await _publish(engine, _data(T0, ("WH", "P1", 1, 0), ("WH", "P2", 1, 0)))
    async with engine.begin() as c:
        await c.execute(update(Stock).where(Stock.sku == "P1").values(on_hand=2))
    _assert_unavailable(await http.get("/api/v1/stock", headers=H))  # content hash no longer matches
    async with engine.begin() as c:
        await c.execute(update(Stock).where(Stock.sku == "P1").values(on_hand=1))
        await c.execute(text(f"DELETE FROM \"{src[2]}\".src_stock WHERE sku = 'P2'"))
    _assert_unavailable(await http.get("/api/v1/stock", headers=H))  # row count no longer matches


async def test_two_instances_are_isolated() -> None:
    first, _ = await _instance(_url())
    second, _ = await _instance(_url())
    try:
        await _products(first[1], "P1")
        await _publish(first[1], _data(T0, ("WH", "P1", 3, 0)))
        assert (await first[0].get("/api/v1/stock", headers=H)).status_code == 200
        _assert_unavailable(
            await second[0].get("/api/v1/stock", headers=H)
        )  # no batch there: unknown, not zero
        await _publish(second[1], StockInput(as_of=T0, items=[]))
        assert (await second[0].get("/api/v1/stock", headers=H)).json()["items"] == []
        assert (await first[0].get("/api/v1/stock", headers=H)).json()["items"][0]["on_hand"] == 3
    finally:
        await _drop(first)
        await _drop(second)


async def test_upgrade_from_the_pool_era_table_keeps_legacy_rows_unserved_and_is_repeatable(
    src: Instance,
) -> None:
    http, engine, schema = src
    await _products(engine, "P1")
    async with engine.begin() as c:  # recreate the pre-batch shape (composite key + the rejected pool column)
        await c.execute(text(f'DROP TABLE "{schema}".src_stock'))
        await c.execute(
            text(
                f'CREATE TABLE "{schema}".src_stock (warehouse_code text, '
                f'sku text REFERENCES "{schema}".src_product(sku), '
                "on_hand numeric NOT NULL, reserved numeric NOT NULL, as_of timestamptz NOT NULL, "
                "created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now(), "
                "batch_id bigint, physical_stock_pool_id text, PRIMARY KEY (warehouse_code, sku))"
            )
        )
        await c.execute(
            text(
                f'INSERT INTO "{schema}".src_stock (warehouse_code, sku, on_hand, reserved, as_of, '
                "physical_stock_pool_id) VALUES ('WH','P1',5,0,'2026-11-05T07:00Z','pool-a')"
            )
        )
    await initialize(engine, schema)
    await initialize(engine, schema)
    async with engine.connect() as c:
        columns = {
            r[0]
            for r in await c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = 'src_stock'"
                ),
                {"s": schema},
            )
        }
        legacy = (
            await c.execute(text(f'SELECT warehouse_code, sku, on_hand, batch_id FROM "{schema}".src_stock'))
        ).all()
    assert "physical_stock_pool_id" not in columns and "id" in columns
    assert [tuple(r) for r in legacy] == [("WH", "P1", Decimal(5), None)]  # kept, with no batch
    _assert_unavailable(await http.get("/api/v1/stock", headers=H))  # legacy rows are never served
    first = await _publish(engine, _data(T0, ("WH", "P1", 6, 0)))
    second = await _publish(
        engine, _data(T0 + timedelta(hours=1), ("WH", "P1", 7, 0))
    )  # several batches now fit
    assert (await http.get("/api/v1/stock", headers=H)).json()["batch_id"] == second > first
