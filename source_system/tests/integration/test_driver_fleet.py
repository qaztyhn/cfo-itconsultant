"""Source reads remain authenticated, ordered and inclusive at the checkpoint."""

from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import DriverAvailability, DriverEligibility
from tests.integration.test_order_writes import NOW, H


@pytest.mark.parametrize("feed", ["driver-availability", "driver-eligibility"])
async def test_DEC_R3_07_verified_fleet_feed_uses_source_pagination(
    order_source: tuple[AsyncClient, AsyncEngine], feed: str
) -> None:
    http, engine = order_source
    now = datetime.fromisoformat(NOW)
    model = DriverAvailability if feed == "driver-availability" else DriverEligibility
    fields = (
        dict(
            work_date=date(2026, 11, 4),
            available_from=now,
            available_to=now + timedelta(hours=1),
            max_driving_min=60,
            superseded=True,
        )
        if model is DriverAvailability
        else dict(vehicle_code=None, licence_class="C", verified_until=now.date(), revoked=True)
    )
    async with engine.begin() as conn:
        await conn.execute(
            insert(model),
            [
                dict(
                    fields,
                    source_ref=ref,
                    employee_no="E1",
                    verified_by="Fleet desk",
                    verified_at=now,
                    updated_at=now,
                )
                for ref in ("C", "A", "B")
            ],
        )
    path = f"/api/v1/fleet/{feed}"
    assert (await http.get(path)).status_code == 400
    assert (await http.get(path, headers={"X-API-Key": "incorrect"})).status_code == 401
    response = await http.get(path, headers=H, params={"page_size": 2, "page": 2, "updated_since": NOW})
    assert response.status_code == 200 and response.headers["X-Total-Count"] == "3"
    item = response.json()["items"][0]
    assert datetime.fromisoformat(item["updated_at"]) == now
    assert item["source_ref"] == "C"
    assert item["superseded" if model is DriverAvailability else "revoked"] is True
    later = await http.get(
        path, headers=H, params={"updated_since": (now + timedelta(seconds=1)).isoformat()}
    )
    assert later.json()["items"] == []
