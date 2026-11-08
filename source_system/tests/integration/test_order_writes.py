import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import initialize
from app.main import create_app
from app.models import Address, CreateRequest, Customer, Order, Product, Sales, Store

H = {"X-API-Key": "synthetic-orders-key"}
NOW = "2026-11-04T09:05:00+00:00"


@pytest.fixture
async def source() -> AsyncIterator[tuple[AsyncClient, AsyncEngine]]:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("SOURCE_TEST_DATABASE_URL required")
    schema = "src_test_" + uuid4().hex
    settings = Settings(url, schema, H["X-API-Key"], NOW)
    engine = create_engine(settings)
    await initialize(engine, schema)
    async with engine.begin() as c:
        await c.execute(insert(Customer).values(id="C1", name="Synthetic", type="business"))
        await c.execute(insert(Customer).values(id="C2", name="Synthetic", type="business"))
        await c.execute(
            insert(Address).values(
                id="A1", customer_id="C1", address="Original synthetic site", lat=59, lon=18
            )
        )
        await c.execute(insert(Store).values(code="ST1"))
        await c.execute(insert(Sales).values(code="S1", store_code="ST1"))
        await c.execute(
            insert(Product).values(
                sku="P1",
                name="Synthetic pending SKU",
                sale_unit="pcs",
                units_to_base=1,
                unit_price=0,
                weight_kg=1,
                volume_m3=1,
            )
        )
    app = create_app(settings)
    app.state.settings, app.state.engine = settings, engine
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://source.test") as http:
            yield http, engine
    finally:
        async with engine.begin() as c:
            await c.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


def draft(**extra: object) -> dict[str, object]:
    return {"customer_id": "C1", "address_id": "A1", "store_code": "ST1", "date_mode": "exact", **extra}


async def test_US_ORD_01_AC1_source_draft_snapshots_address_and_allows_incomplete_details(
    source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = source
    response = await http.post("/api/v1/orders", headers=H, json=draft())
    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "DRAFT" and order["version"] == 1
    assert datetime.fromisoformat(order["updated_at"]) == datetime.fromisoformat(NOW)
    assert order["address"] == "Original synthetic site" and order["lat"] == 59
    assert order["lines"] == [] and order["date_from"] is None
    async with engine.begin() as c:
        await c.execute(update(Address).values(address="Changed synthetic site", lat=60))
    read = await http.get("/api/v1/orders", headers=H, params={"status": "DRAFT"})
    assert read.json()["items"][0]["address"] == "Original synthetic site"


async def test_US_ORD_01_AC1_source_create_idempotency_is_concurrent_and_payload_bound(
    source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = source
    headers = {**H, "Idempotency-Key": str(uuid4())}
    one, two = await asyncio.gather(
        *[http.post("/api/v1/orders", headers=headers, json=draft()) for _ in range(2)]
    )
    assert one.status_code == two.status_code == 201 and one.json()["id"] == two.json()["id"]
    conflict = await http.post("/api/v1/orders", headers=headers, json=draft(special_requirements="changed"))
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    async with engine.connect() as c:
        assert await c.scalar(select(func.count()).select_from(Order)) == 1
        assert await c.scalar(select(func.count()).select_from(CreateRequest)) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"lat": 1},
        {"status": "SUBMITTED_FOR_PLANNING"},
        {"customer_id": "C2"},
        {"lines": [{"line_no": 1, "sku": "UNKNOWN", "qty": 1, "unit_price": "0.00"}]},
        {"lines": [{"line_no": 1, "sku": "P1", "qty": 1, "unit_price": "-1.00"}]},
    ],
)
async def test_US_SRC_03_AC1_source_create_rejects_untrusted_or_inconsistent_fields_atomically(
    source: tuple[AsyncClient, AsyncEngine], extra: dict[str, object]
) -> None:
    http, engine = source
    response = await http.post("/api/v1/orders", headers=H, json=draft(**extra))
    assert response.status_code == 422
    async with engine.connect() as c:
        assert await c.scalar(select(func.count()).select_from(Order)) == 0


async def test_US_SRC_03_AC1_draft_lines_allow_zero_price_without_cfo_mapping(
    source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, _ = source
    response = await http.post(
        "/api/v1/orders",
        headers=H,
        json=draft(
            sales_code="S1",
            contact={"name": "Synthetic", "email": "synthetic@example.test"},
            lines=[{"line_no": 1, "sku": "P1", "qty": 1.125, "unit_price": "0.00"}],
        ),
    )
    assert response.status_code == 201
    assert response.json()["lines"][0] == {"line_no": 1, "sku": "P1", "qty": 1.125, "unit_price": "0.00"}
