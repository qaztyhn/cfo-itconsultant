"""D1-A list endpoints (06 section 16.1): real PostgreSQL; envelope, inclusive incremental paging, filters."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
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

KEY = "lists-test-key-not-a-secret"
H = {"X-API-Key": KEY}


@pytest.fixture
async def src() -> AsyncIterator[tuple[AsyncClient, AsyncEngine]]:
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
        async with engine.begin() as c:
            await c.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()


def _product(sku: str) -> dict[str, Any]:
    return {
        "sku": sku, "name": f"Name {sku}", "sale_unit": "bag", "units_to_base": Decimal("1.5"),
        "unit_price": Decimal("95"), "weight_kg": Decimal(25), "volume_m3": Decimal("0.018"),
    }  # fmt: skip


def _address(
    address_id: str, customer_id: str, text: str, lat: Decimal | None = None, lon: Decimal | None = None
) -> dict[str, Any]:
    return {"id": address_id, "customer_id": customer_id, "address": text, "lat": lat, "lon": lon}


async def _seed_refs(engine: AsyncEngine) -> None:
    async with engine.begin() as c:
        await c.execute(
            insert(Customer),
            [{"id": f"C-{i}", "name": f"Cust {i}", "type": "business"} for i in (3, 1, 2)],
        )
        await c.execute(
            insert(Address),
            [
                _address("A-2", "C-2", "Storgatan 50% Rabatt_1", Decimal("59.1"), Decimal("18.1")),
                _address("A-1", "C-1", "Storgatan 1"),
                _address("A-3", "C-1", "Lillgatan 3"),
            ],
        )
        await c.execute(insert(Product), [_product(s) for s in ("P-2", "P-3", "P-1")])


@pytest.mark.parametrize(
    ("path", "key"),
    [("/customers", "id"), ("/products", "sku"), ("/addresses", "id")],
)
async def test_D1_A_equal_updated_at_pages_by_natural_key_and_reports_total(
    src: tuple[AsyncClient, AsyncEngine], path: str, key: str
) -> None:
    http, engine = src
    await _seed_refs(engine)  # one transaction per table -> equal updated_at inside each table
    seen: list[str] = []
    for page in (1, 2):
        r = await http.get("/api/v1" + path, headers=H, params={"page": page, "page_size": 2})
        assert r.status_code == 200 and r.headers["X-Total-Count"] == "3"
        body = r.json()
        assert (body["page"], body["page_size"], body["total"]) == (page, 2, 3)
        seen += [i[key] for i in body["items"]]
    assert seen == sorted(seen) and len(set(seen)) == 3
    default = (await http.get("/api/v1" + path, headers=H)).json()
    assert default["page_size"] == 50 and len(default["items"]) == 3


async def test_D1_A_updated_since_is_inclusive_for_products(src: tuple[AsyncClient, AsyncEngine]) -> None:
    http, engine = src
    async with engine.begin() as c:
        await c.execute(insert(Product), [_product("P-1")])
    async with engine.begin() as c:
        await c.execute(insert(Product), [_product("P-2")])
    items = (await http.get("/api/v1/products", headers=H)).json()["items"]
    first, second = (datetime.fromisoformat(i["updated_at"]) for i in items)
    assert first < second
    got = await http.get("/api/v1/products", headers=H, params={"updated_since": first.isoformat()})
    assert [i["sku"] for i in got.json()["items"]] == ["P-1", "P-2"]
    got = await http.get("/api/v1/products", headers=H, params={"updated_since": second.isoformat()})
    assert [i["sku"] for i in got.json()["items"]] == ["P-2"]
    item = items[0]
    assert item["unit_price"] == "95.00" and item["units_to_base"] == 1.5 and item["weight_kg"] == 25


async def test_D1_A_addresses_filter_by_customer_and_text_without_wildcards(
    src: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = src
    await _seed_refs(engine)
    by_customer = await http.get("/api/v1/addresses", headers=H, params={"customer_id": "C-1"})
    assert [i["id"] for i in by_customer.json()["items"]] == ["A-1", "A-3"]
    text = await http.get("/api/v1/addresses", headers=H, params={"q": "storgatan"})
    assert [i["id"] for i in text.json()["items"]] == ["A-1", "A-2"]
    literal = await http.get("/api/v1/addresses", headers=H, params={"q": "%"})
    assert [i["id"] for i in literal.json()["items"]] == ["A-2"]  # % and _ are literals, not wildcards
    underscore = await http.get("/api/v1/addresses", headers=H, params={"q": "_1"})
    assert [i["id"] for i in underscore.json()["items"]] == ["A-2"]
    a2 = (await http.get("/api/v1/addresses", headers=H, params={"customer_id": "C-2"})).json()["items"][0]
    assert (a2["lat"], a2["lon"]) == (59.1, 18.1)


async def test_D1_A_inbound_and_natural_key_order(src: tuple[AsyncClient, AsyncEngine]) -> None:
    http, engine = src
    async with engine.begin() as c:
        await c.execute(insert(Product), [_product("P-1"), _product("P-2")])
        await c.execute(
            insert(Inbound),
            [
                {"inbound_ref": "IN-2", "warehouse_code": "GBG", "sku": "P-1", "qty": Decimal(10),
                 "eta_date": date(2026, 11, 20), "confirmed": True, "received": False},
                {"inbound_ref": "IN-1", "warehouse_code": "STO", "sku": "P-2", "qty": Decimal("2.5"),
                 "eta_date": date(2026, 11, 21), "confirmed": False, "received": False},
                {"inbound_ref": "IN-1", "warehouse_code": "GBG", "sku": "P-2", "qty": Decimal(1),
                 "eta_date": date(2026, 11, 22), "confirmed": True, "received": True},
            ],
        )  # fmt: skip
    body = (await http.get("/api/v1/inbound", headers=H)).json()
    assert [(i["inbound_ref"], i["warehouse_code"], i["sku"]) for i in body["items"]] == [
        ("IN-1", "GBG", "P-2"), ("IN-1", "STO", "P-2"), ("IN-2", "GBG", "P-1"),
    ]  # fmt: skip
    assert body["items"][1]["qty"] == 2.5 and body["items"][0]["eta_date"] == "2026-11-22"
    assert body["items"][0]["received"] is True and body["total"] == 3


def _block(code: str, start: str, end: str) -> dict[str, Any]:
    return {
        "vehicle_code": code, "from_ts": datetime.fromisoformat(start), "to_ts": datetime.fromisoformat(end),
        "kind": "maintenance",
    }  # fmt: skip


async def test_D1_A_fleet_calendar_uses_half_open_overlap(src: tuple[AsyncClient, AsyncEngine]) -> None:
    http, engine = src
    async with engine.begin() as c:
        await c.execute(
            insert(VehicleCalendar),
            [
                _block("V-1", "2026-11-05T08:00:00+00:00", "2026-11-05T10:00:00+00:00"),
                _block("V-2", "2026-11-05T10:00:00+00:00", "2026-11-05T12:00:00+00:00"),
                _block("V-3", "2026-11-05T09:00:00+00:00", "2026-11-05T09:30:00+00:00"),
            ],
        )
    window = {"from": "2026-11-05T10:00:00Z", "to": "2026-11-05T11:00:00Z"}
    # Same instants written with other UTC offsets must select the same rows (aware instants, not local text).
    offset = {"from": "2026-11-05T11:00:00+01:00", "to": "2026-11-05T05:00:00-06:00"}
    assert (await http.get("/api/v1/fleet/calendar", headers=H, params=offset)).json()["items"][0][
        "vehicle_code"
    ] == "V-2"
    r = await http.get("/api/v1/fleet/calendar", headers=H, params=window)
    assert r.status_code == 200
    assert [i["vehicle_code"] for i in r.json()["items"]] == ["V-2"]  # V-1 ends exactly at `from`: excluded
    item = r.json()["items"][0]
    assert set(item) == {"vehicle_code", "from", "to", "kind", "updated_at"}
    assert datetime.fromisoformat(item["from"]) == datetime(2026, 11, 5, 10, tzinfo=UTC)
    before_end = await http.get(
        "/api/v1/fleet/calendar",
        headers=H,
        params={"from": "2026-11-05T07:00:00Z", "to": "2026-11-05T08:00:00Z"},
    )
    assert before_end.json()["items"] == []  # V-1 starts exactly at `to`: excluded
    everything = await http.get("/api/v1/fleet/calendar", headers=H)
    assert everything.json()["total"] == 3


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/customers", {"page": 0}),
        ("/products", {"page_size": 501}),
        ("/inbound", {"updated_since": "2026-11-05T07:00:00"}),
        ("/addresses", {"page_size": 0}),
        ("/fleet/calendar", {"from": "2026-11-05T10:00:00"}),
        ("/fleet/calendar", {"from": "2026-11-05T10:00:00Z", "to": "2026-11-05T10:00:00Z"}),
    ],
)
async def test_D1_A_invalid_parameters_are_422_without_echo(
    src: tuple[AsyncClient, AsyncEngine], path: str, params: dict[str, object]
) -> None:
    http, _ = src
    r = await http.get("/api/v1" + path, headers=H, params=params)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert all(set(e) == {"loc", "type", "msg"} for e in error["details"]["errors"])
    assert all(str(v) not in r.text for v in params.values() if len(str(v)) > 3)


async def test_D1_A_key_is_checked_before_validation(src: tuple[AsyncClient, AsyncEngine]) -> None:
    http, _ = src
    for path in ("/customers", "/products", "/inbound", "/addresses", "/fleet/calendar"):
        assert (await http.get("/api/v1" + path, params={"page": 0})).status_code == 400
        assert (
            await http.get("/api/v1" + path, headers={"X-API-Key": "x"}, params={"page": 0})
        ).status_code == 401
