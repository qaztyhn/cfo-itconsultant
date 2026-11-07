"""M0 tests against real PostgreSQL; missing DATABASE URL is a failure, never a skip.

Only a uniquely named schema created by this test is removed during cleanup.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, insert, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import initialize
from app.main import create_app
from app.models import Address, Customer, Order, Product
from app.seed_reference import seed_catalog, seed_customers


@pytest.fixture
async def database() -> AsyncIterator[tuple[AsyncEngine, str]]:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("SOURCE_TEST_DATABASE_URL is required for real PostgreSQL integration tests")
    schema = "src_test_" + uuid4().hex
    engine = create_engine(Settings(url, schema))
    try:
        await initialize(engine, schema)
        yield engine, schema
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()


async def test_all_source_tables_and_timestamps_exist(
    database: tuple[AsyncEngine, str],
) -> None:
    engine, schema = database
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names(schema=schema))
        assert set(tables) == {
            "src_customer",
            "src_address",
            "src_product",
            "src_stock",
            "src_inbound",
            "src_vehicle_calendar",
            "src_order",
            "src_order_line",
        }
        for table in tables:
            columns = await connection.run_sync(
                lambda sync, name=table: inspect(sync).get_columns(name, schema=schema)
            )
            assert {"created_at", "updated_at"} <= {column["name"] for column in columns}


async def test_US_SRC_01_AC1_customer_reference_seed_preserves_existing_data(
    database: tuple[AsyncEngine, str],
) -> None:
    engine, _ = database
    now = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
    async with engine.begin() as connection:
        await seed_customers(connection, now=now)
        customers = (await connection.execute(select(Customer.id, Customer.type))).all()
        assert len(customers) == 40
        assert sum(row.type == "business" for row in customers) == 30
        before = (
            await connection.execute(select(Address.id, Address.lat, Address.lon).order_by(Address.id))
        ).all()
        assert len(before) == 80
        assert all(row.lat is not None and row.lon is not None for row in before)
        await connection.execute(update(Customer).where(Customer.id == "DEMO-C001").values(name="Edited"))
        await seed_customers(connection, now=now)
        assert await connection.scalar(select(Customer.name).where(Customer.id == "DEMO-C001")) == "Edited"
        assert (
            before
            == (
                await connection.execute(select(Address.id, Address.lat, Address.lon).order_by(Address.id))
            ).all()
        )


async def test_US_SRC_01_AC1_product_seed_preserves_edits_timestamps_and_unrelated_rows(
    database: tuple[AsyncEngine, str],
) -> None:
    engine, _ = database
    now = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
    async with engine.begin() as connection:
        await seed_catalog(connection, now=now)
        assert await connection.scalar(select(func.count()).select_from(Product)) == 100
        assert await connection.scalar(select(Product.created_at).where(Product.sku == "88412")) == now
        await connection.execute(
            update(Product)
            .where(Product.sku == "88412")
            .values(name="Operator edit", unit_price=Decimal("12.34"))
        )
        await connection.execute(
            insert(Product).values(
                sku="EXTERNAL",
                name="Unrelated",
                sale_unit="piece",
                units_to_base=1,
                unit_price=Decimal("9.99"),
                weight_kg=1,
                volume_m3=Decimal("0.01"),
            )
        )
        fields = (Product.sku, Product.name, Product.unit_price, Product.created_at, Product.updated_at)
        before = (await connection.execute(select(*fields).order_by(Product.sku))).all()
        await seed_catalog(connection, now=now)
        assert (await connection.execute(select(*fields).order_by(Product.sku))).all() == before
        assert len(before) == 101
        assert await connection.scalar(select(func.count()).select_from(Order)) == 0


async def test_bootstrap_preserves_data_and_database_updates_timestamp(
    database: tuple[AsyncEngine, str],
) -> None:
    engine, schema = database
    async with engine.begin() as connection:
        before = await connection.scalar(
            insert(Customer)
            .values(id="C-test", name="Synthetic", type="business")
            .returning(Customer.updated_at)
        )
    await initialize(engine, schema)
    async with engine.begin() as connection:
        after = await connection.scalar(
            update(Customer)
            .where(Customer.id == "C-test")
            .values(type="individual")
            .returning(Customer.updated_at)
        )
        assert before is not None and after is not None and after > before
        assert await connection.scalar(select(Customer.name)) == "Synthetic"


async def test_postgresql_enforces_source_foreign_keys_and_status(
    database: tuple[AsyncEngine, str],
) -> None:
    engine, _ = database
    async with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(
                    insert(Address).values(id="A-test", customer_id="missing", address="Test")
                )
        await connection.execute(insert(Customer).values(id="C-test", name="Synthetic", type="business"))
        await connection.execute(insert(Address).values(id="A-test", customer_id="C-test", address="Test"))
        with pytest.raises(IntegrityError, match="ck_src_order_status"):
            async with connection.begin_nested():
                await connection.execute(
                    insert(Order).values(
                        id="O-test",
                        version=1,
                        customer_id="C-test",
                        address_id="A-test",
                        date_mode="latest",
                        status="UNKNOWN",
                    )
                )


async def test_source_amounts_preserve_decimal_precision(
    database: tuple[AsyncEngine, str],
) -> None:
    engine, _ = database
    async with engine.begin() as connection:
        await connection.execute(
            insert(Product).values(
                sku="TEST",
                name="Synthetic",
                sale_unit="unit",
                units_to_base=Decimal("1"),
                unit_price=Decimal("123.4567"),
                weight_kg=Decimal("0.125"),
                volume_m3=Decimal("0.000125"),
            )
        )
        assert await connection.scalar(select(Product.unit_price)) == Decimal("123.4567")


async def test_health_checks_real_database(database: tuple[AsyncEngine, str]) -> None:
    engine, _ = database
    app = create_app()
    app.state.engine = engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://source.test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT 1")) == 1
