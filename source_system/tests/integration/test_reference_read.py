"""D1-A / US-SRC-02 AC1 subset: same reference contract on two isolated source instances."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
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
from app.models import Address, Customer, Inbound, Product, VehicleCalendar

NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
H = {"X-API-Key": "reference-tests-synthetic-key"}
PATHS = ("/customers", "/products", "/addresses", "/inbound", "/fleet/calendar")


@pytest.fixture(params=("se", "shadow"))
async def source(request: pytest.FixtureRequest) -> AsyncIterator[AsyncClient]:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("SOURCE_TEST_DATABASE_URL required; PostgreSQL tests cannot be skipped")
    schema = f"src_test_{request.param}_{uuid4().hex}"
    settings = Settings(url, schema, H["X-API-Key"])
    engine: AsyncEngine = create_engine(settings)
    await initialize(engine, schema)
    async with engine.begin() as c:
        for number in (2, 1):  # Intentionally reversed insertion order, equal timestamps.
            await c.execute(
                insert(Customer).values(
                    id=f"C{number}", name=f"Synthetic {number}", type="business", updated_at=NOW
                )
            )
            await c.execute(
                insert(Address).values(
                    id=f"A{number}",
                    customer_id=f"C{number}",
                    address=f"Synthetic {number}% Road",
                    lat=Decimal("59.3"),
                    lon=18,
                    updated_at=NOW,
                )
            )
            await c.execute(
                insert(Product).values(
                    sku=f"P{number}",
                    name="Synthetic product",
                    sale_unit="bag",
                    units_to_base=1,
                    unit_price=Decimal("10.50"),
                    weight_kg=Decimal("1.25"),
                    volume_m3=Decimal("0.025"),
                    updated_at=NOW,
                )
            )
            await c.execute(
                insert(Inbound).values(
                    inbound_ref="IN",
                    warehouse_code="WH",
                    sku=f"P{number}",
                    qty=Decimal("2.125"),
                    eta_date=date(2026, 11, 5),
                    confirmed=True,
                    received=False,
                    updated_at=NOW,
                )
            )
            await c.execute(
                insert(VehicleCalendar).values(
                    vehicle_code="V",
                    from_ts=NOW,
                    to_ts=NOW + timedelta(hours=number),
                    kind="busy",
                    updated_at=NOW,
                )
            )
    app = create_app(settings)
    app.state.settings, app.state.engine = settings, engine
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://source.test") as http:
            yield http
    finally:
        async with engine.begin() as c:
            await c.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


def params(**extra: object) -> dict[str, object]:
    return {"from": NOW.isoformat(), "to": (NOW + timedelta(hours=3)).isoformat(), **extra}


@pytest.mark.parametrize("path,key", zip(PATHS, ("id", "sku", "id", "sku", "to_ts"), strict=True))
async def test_US_SRC_02_AC1_reference_paging_and_inclusive_checkpoint(
    source: AsyncClient, path: str, key: str
) -> None:
    first = await source.get(
        "/api/v1" + path, headers=H, params=params(page_size=1, updated_since=NOW.isoformat())
    )
    second = await source.get(
        "/api/v1" + path, headers=H, params=params(page=2, page_size=1, updated_since=NOW.isoformat())
    )
    assert first.status_code == second.status_code == 200
    assert first.headers["X-Total-Count"] == "2"
    assert first.json()["total"] == second.json()["total"] == 2
    assert first.json()["items"][0][key] < second.json()["items"][0][key]
    empty = await source.get(
        "/api/v1" + path, headers=H, params=params(updated_since=(NOW + timedelta(seconds=1)).isoformat())
    )
    assert empty.json() == {"items": [], "page": 1, "page_size": 50, "total": 0}


async def test_US_SRC_02_AC1_reference_filters_and_numeric_wire_types(source: AsyncClient) -> None:
    addresses = await source.get("/api/v1/addresses", headers=H, params={"q": "%", "customer_id": "C1"})
    assert [r["id"] for r in addresses.json()["items"]] == ["A1"]
    assert addresses.json()["items"][0]["lat"] == 59.3
    assert (await source.get("/api/v1/addresses", headers=H, params={"q": "_"})).json()["total"] == 0
    product = (await source.get("/api/v1/products", headers=H)).json()["items"][0]
    assert product["unit_price"] == "10.50"
    assert product["weight_kg"] == 1.25 and product["units_to_base"] == 1
    inbound = (await source.get("/api/v1/inbound", headers=H)).json()["items"][0]
    assert inbound["qty"] == 2.125 and inbound["eta_date"] == "2026-11-05"
    fleet = await source.get(
        "/api/v1/fleet/calendar",
        headers=H,
        params={"from": (NOW + timedelta(hours=1)).isoformat(), "to": (NOW + timedelta(hours=2)).isoformat()},
    )
    assert fleet.json()["total"] == 1  # [NOW,NOW+1h) does not overlap the requested interval.


@pytest.mark.parametrize("path", PATHS)
async def test_US_SRC_02_AC1_reference_auth_and_private_query_errors(source: AsyncClient, path: str) -> None:
    missing = await source.get("/api/v1" + path, params={"page_size": 999})
    assert missing.status_code == 400
    wrong = await source.get("/api/v1" + path, headers={"X-API-Key": "wrong"}, params=params())
    assert wrong.status_code == 401
    for bad in ({"page_size": 501}, {"page": 0}, {"updated_since": "PII-sensitive-invalid-date"}):
        response = await source.get("/api/v1" + path, headers=H, params=params(**bad))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "PII-sensitive" not in response.text


async def test_US_SRC_02_AC1_fleet_requires_aware_ordered_time_range(source: AsyncClient) -> None:
    for query in (
        {"from": NOW.isoformat(), "to": NOW.isoformat()},
        {"from": "2026-11-04T09:00:00", "to": NOW.isoformat()},
        {},
    ):
        response = await source.get("/api/v1/fleet/calendar", headers=H, params=query)
        assert response.status_code == 422
