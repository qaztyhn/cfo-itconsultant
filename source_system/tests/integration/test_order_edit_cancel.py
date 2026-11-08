import asyncio
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Address, Customer, Order
from tests.integration.test_order_writes import NOW, H, complete


async def create(http: AsyncClient) -> str:
    return (await http.post("/api/v1/orders", headers=H, json=complete())).json()["id"]


async def submitted(http: AsyncClient, order_id: str) -> None:
    path = f"/api/v1/orders/{order_id}"
    assert (await http.post(path + "/validate", headers=H)).status_code == 200
    assert (await http.post(path + "/submit", headers=H)).status_code == 200


async def test_US_ORD_01_AC1_full_replace_noop_version_conflict_and_snapshot_refresh(
    order_source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = order_source
    order_id = await create(http)
    path = f"/api/v1/orders/{order_id}"
    payload = {**complete(), "expected_version": 1}
    assert (await http.put(path, headers=H, json=payload)).json()["version"] == 1
    async with engine.begin() as c:
        await c.execute(update(Address).values(address="Changed synthetic address", lat=60))
    edited = await http.put(path, headers=H, json={**payload, "special_requirements": "Synthetic update"})
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert edited.json()["address"] == "Original synthetic site"
    stale = await http.put(path, headers=H, json=payload)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    refreshed = await http.put(
        path, headers=H, json={**payload, "expected_version": 2, "refresh_address": True}
    )
    assert refreshed.status_code == 200 and refreshed.json()["address"] == "Changed synthetic address"


async def test_US_SRC_03_AC1_edit_invalidates_validation_but_submitted_edit_stays_in_feed(
    order_source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, _ = order_source
    order_id = await create(http)
    path = f"/api/v1/orders/{order_id}"
    await http.post(path + "/validate", headers=H)
    payload = {**complete(), "expected_version": 2, "lines": []}
    edited = await http.put(path, headers=H, json=payload)
    assert edited.json()["status"] == "DRAFT" and edited.json()["version"] == 3
    await http.put(path, headers=H, json={**complete(), "expected_version": 3})
    await submitted(http, order_id)
    # version 6: create/validate/edit/edit/validate/submit.
    invalid = await http.put(path, headers=H, json={**complete(), "expected_version": 6, "lines": []})
    assert invalid.status_code == 422
    valid = await http.put(
        path,
        headers=H,
        json={**complete(), "expected_version": 6, "special_requirements": "Synthetic handling note"},
    )
    assert valid.status_code == 200 and valid.json()["status"] == "SUBMITTED_FOR_PLANNING"
    assert valid.json()["version"] == 7
    feed = await http.get("/api/v1/orders", headers=H)
    assert feed.json()["items"][0]["version"] == 7


async def test_US_ORD_01_cancel_provenance_is_terminal_idempotent_and_visible_to_cancel_feed(
    order_source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = order_source
    order_id = await create(http)
    path = f"/api/v1/orders/{order_id}"
    payload = {"expected_version": 1, "reason_code": "other", "reason_text": "Synthetic cancellation"}
    invalid = await http.post(path + "/cancel", headers=H, json={**payload, "reason_text": ""})
    assert invalid.status_code == 422
    one, two = await asyncio.gather(*[http.post(path + "/cancel", headers=H, json=payload) for _ in range(2)])
    assert one.status_code == two.status_code == 200 and one.json() == two.json()
    assert one.json()["version"] == 2 and one.json()["status"] == "CANCELLED"
    assert datetime.fromisoformat(one.json()["cancelled_at"]) == datetime.fromisoformat(NOW)
    assert (await http.post(path + "/submit", headers=H)).status_code == 409
    assert (await http.put(path, headers=H, json={**complete(), "expected_version": 2})).status_code == 409
    assert (
        await http.post(path + "/cancel", headers=H, json={**payload, "reason_code": "changed"})
    ).status_code == 409
    feed = await http.get("/api/v1/orders", headers=H, params={"status": "CANCELLED", "updated_since": NOW})
    assert feed.json()["items"][0]["cancel_reason"]["reason_code"] == "other"
    with pytest.raises(IntegrityError):
        async with engine.begin() as c:
            await c.execute(
                update(Order).where(Order.id == order_id).values(cancel_reason={"reason_code": "changed"})
            )


async def test_US_ORD_01_cancel_vs_edit_one_version_wins_without_partial_replacement(
    order_source: tuple[AsyncClient, AsyncEngine],
) -> None:
    http, engine = order_source
    order_id = await create(http)
    path = f"/api/v1/orders/{order_id}"
    cancel, edit = await asyncio.gather(
        http.post(path + "/cancel", headers=H, json={"expected_version": 1, "reason_code": "duplicate"}),
        http.put(path, headers=H, json={**complete(), "expected_version": 1, "lines": []}),
    )
    assert sorted([cancel.status_code, edit.status_code]) == [200, 409]
    async with engine.connect() as c:
        assert await c.scalar(select(Order.version)) == 2


async def test_US_SRC_02_AC1_database_exception_repr_hides_contact_parameters(
    order_source: tuple[AsyncClient, AsyncEngine],
) -> None:
    from sqlalchemy import insert

    _, engine = order_source
    with pytest.raises(IntegrityError) as error:
        async with engine.begin() as c:
            await c.execute(
                insert(Customer).values(id="C1", name="private-synthetic-contact-value", type="business")
            )
    assert "private-synthetic-contact-value" not in str(error.value)
