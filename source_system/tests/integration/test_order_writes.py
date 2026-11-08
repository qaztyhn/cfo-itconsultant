import asyncio
import os
from collections.abc import AsyncIterator
from datetime import date, datetime
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
from app.models import Address, CreateRequest, Customer, Order, Product, ReceivingCalendar, Sales, Store

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
            insert(ReceivingCalendar).values(
                id="instance",
                timezone="UTC",
                valid_from=date(2026, 1, 1),
                valid_to=date(2027, 12, 31),
                working_days=[1, 2, 3, 4, 5],
                holidays=[],
            )
        )
        await c.execute(
            update(Address).values(receiving_hours={str(day): [["07:00", "16:00"]] for day in range(1, 6)})
        )
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


def complete(**extra: object) -> dict[str, object]:
    return draft(
        sales_code="S1",
        contact={"name": "Synthetic", "email": "synthetic@example.test"},
        date_from="2026-11-05",
        date_to=None,
        window_start="09:00",
        window_end="11:00",
        lines=[{"line_no": 1, "sku": "P1", "qty": 1.125, "unit_price": "0.00"}],
        **extra,
    )


async def test_US_SRC_03_AC1_validate_submit_is_locked_idempotent_and_returns_same_dto(
    source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, _ = source
    created = (await http.post("/api/v1/orders", headers=H, json=complete())).json()
    path = f"/api/v1/orders/{created['id']}"
    premature = await http.post(path + "/submit", headers=H)
    assert premature.status_code == 409 and premature.json()["error"]["code"] == "ILLEGAL_TRANSITION"
    validated = await http.post(path + "/validate", headers=H)
    assert validated.status_code == 200 and validated.json()["status"] == "VALIDATED"
    assert validated.json()["version"] == 2
    assert (await http.post(path + "/validate", headers=H)).json()["version"] == 2
    first, second = await asyncio.gather(*[http.post(path + "/submit", headers=H) for _ in range(2)])
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "SUBMITTED_FOR_PLANNING"
    assert first.json()["version"] == second.json()["version"] == 3
    assert datetime.fromisoformat(first.json()["updated_at"]) == datetime.fromisoformat(NOW)


@pytest.mark.parametrize(
    "field,value,kind",
    [
        ("contact", None, "contact_required"),
        ("lines", [], "lines_required"),
        ("date_from", None, "invalid_date_range"),
        ("window_start", "06:00", "outside_receiving_hours"),
        ("window_end", None, "invalid_receiving_window"),
        ("date_from", "2028-01-01", "receiving_calendar_missing"),
    ],
)
async def test_US_SRC_03_AC1_invalid_draft_validation_preserves_status_and_version(
    source: tuple[AsyncClient, AsyncEngine], field: str, value: object, kind: str
) -> None:
    http, _ = source
    payload = complete()
    payload[field] = value
    created = (await http.post("/api/v1/orders", headers=H, json=payload)).json()
    response = await http.post(f"/api/v1/orders/{created['id']}/validate", headers=H)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["errors"][0]["type"] == kind
    assert "synthetic@example.test" not in response.text
    read = (await http.get("/api/v1/orders", headers=H, params={"status": "DRAFT"})).json()["items"][0]
    assert read["version"] == 1


async def test_US_SRC_03_AC1_submit_revalidates_customer_and_calendar_after_validation(
    source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = source
    created = (await http.post("/api/v1/orders", headers=H, json=complete())).json()
    path = f"/api/v1/orders/{created['id']}"
    assert (await http.post(path + "/validate", headers=H)).status_code == 200
    async with engine.begin() as c:
        await c.execute(update(Customer).where(Customer.id == "C1").values(is_active=False))
    assert (await http.post(path + "/submit", headers=H)).status_code == 422
    async with engine.connect() as c:
        assert (await c.execute(select(Order.status, Order.version))).one() == ("VALIDATED", 2)


@pytest.mark.parametrize(
    "mode,first,last",
    [
        ("range", "2026-11-07", "2026-11-09"),
        ("latest", None, "2026-11-07"),
    ],
)
async def test_US_SRC_03_AC1_range_latest_need_a_real_receiving_day(
    source: tuple[AsyncClient, AsyncEngine], mode: str, first: str | None, last: str
) -> None:
    http, _ = source
    payload = complete()
    payload.update(date_mode=mode, date_from=first, date_to=last)
    created = (await http.post("/api/v1/orders", headers=H, json=payload)).json()
    response = await http.post(f"/api/v1/orders/{created['id']}/validate", headers=H)
    assert response.status_code == 200
