"""PostgreSQL coverage for verified fleet imports and checkpoint replays."""

import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.rest_adapter import RestMarketAdapter
from app.core.config import get_settings
from app.services.ingest_service import sync_entity
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_ingest_runner import NOW, page
from tests.integration.test_ingest_runner import db as db

pytestmark = pytest.mark.integration


def sync(db: str, entity: str, *items: dict):
    ordered = sorted(items, key=lambda item: (item["updated_at"], item["source_ref"]))

    def source(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/fleet/{entity}"
        assert request.headers["X-API-Key"] == "test-key"
        bound = request.url.params.get("updated_since")
        return page([item for item in ordered if not bound or item["updated_at"] >= bound])

    async def run():
        engine = create_async_engine(async_url(db), hide_parameters=True)
        try:
            return await sync_entity(
                "SE",
                entity,
                maker=async_sessionmaker(engine, expire_on_commit=False),
                now=NOW,
                adapter=RestMarketAdapter(
                    "SE", "https://fleet.test", "test-key", transport=httpx.MockTransport(source)
                ),
            )
        finally:
            await engine.dispose()

    return asyncio.run(run())


def common(source_ref: str, **overrides: object) -> dict:
    return {
        "source_ref": source_ref,
        "employee_no": "E1",
        "verified_by": "Fleet desk",
        "updated_at": NOW.isoformat(),
        "verified_at": (NOW - timedelta(minutes=2)).isoformat(),
        **overrides,
    }


def availability(source_ref: str, **overrides: object) -> dict:
    return {
        **common(source_ref),
        "work_date": "2026-11-10",
        "available_from": "2026-11-10T07:00:00Z",
        "available_to": "2026-11-10T17:00:00Z",
        "max_driving_min": 540,
        "superseded": False,
        **overrides,
    }


def qualification(source_ref: str, **overrides: object) -> dict:
    return {
        **common(source_ref),
        "vehicle_code": "V-1",
        "licence_class": None,
        "verified_until": "2026-11-10",
        "revoked": False,
        **overrides,
    }


def test_US_PLN_03_AC2_fleet_ingest_replays_replacements_and_revocations(db: str) -> None:
    execute(
        db,
        "INSERT INTO hr.driver_staff (employee_id,home_warehouse_id,licence_class,licence_expires_on)"
        " VALUES (1,1,'C','2027-01-01')",
    )
    original = availability("AV-A")
    newer = availability("AV-B", verified_at=NOW.isoformat(), max_driving_min=300)
    revoked = qualification("EL-A", revoked=True)
    assert sync(db, "driver-availability", original).rows_ok == 1
    assert sync(db, "driver-availability", original, newer).rows_ok == 2
    assert sync(db, "driver-availability", original, newer).rows_ok == 2
    assert (
        [
            (r[0], r[1], r[2])
            for r in fetch(
                db,
                """
        SELECT source_ref,max_driving_min,superseded_at IS NULL
        FROM hr.driver_availability ORDER BY source_ref
    """,
            )
        ]
        == [("AV-A", 540, False), ("AV-B", 300, True)]
    )

    assert sync(db, "driver-availability", {**newer, "superseded": True}).rows_ok == 1
    assert sync(db, "driver-availability", availability("AV-OLD")).rows_ok == 1
    assert not fetch(db, "SELECT id FROM hr.driver_availability WHERE superseded_at IS NULL")

    assert sync(db, "driver-eligibility", qualification("EL-A")).rows_ok == 1
    assert sync(db, "driver-eligibility", revoked).rows_ok == 1
    assert sync(db, "driver-eligibility", qualification("EL-A")).rows_ok == 1
    assert fetch(db, "SELECT count(*), count(revoked_at) FROM hr.driver_vehicle_eligibility")[0][:] == (1, 1)


def test_US_PLN_03_AC2_fleet_ingest_journals_rejects(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    execute(
        db,
        "INSERT INTO hr.driver_staff (employee_id,home_warehouse_id,licence_class,licence_expires_on)"
        " VALUES (1,1,'C','2027-01-01')",
    )
    availability_run = sync(
        db,
        "driver-availability",
        availability("ok"),
        availability("verification", verified_by=" "),
        availability("driver", employee_no="E2"),
        availability("market", market="ZZ"),
        availability("time", available_from="2026-11-10T18:00:00Z"),
    )
    assert (availability_run.status, availability_run.rows_ok, availability_run.rows_rejected) == (
        "partial",
        1,
        4,
    )
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        qualification_run = sync(
            db,
            "driver-eligibility",
            qualification("vehicle", vehicle_code="UNKNOWN"),
            qualification("synthetic", source="synthetic_demo"),
            qualification("both", licence_class="CE"),
        )
    finally:
        get_settings.cache_clear()
    assert (qualification_run.status, qualification_run.rows_rejected) == ("partial", 3)
    assert [
        (r[0], r[1]) for r in fetch(db, "SELECT external_key,reason_code FROM stg.sync_reject ORDER BY 1")
    ] == [
        ("both", "INVALID_SOURCE_ROW"),
        ("driver", "UNKNOWN_DRIVER"),
        ("market", "WRONG_MARKET"),
        ("synthetic", "DRIVER_NOT_VERIFIED"),
        ("time", "BAD_DATE"),
        ("vehicle", "UNKNOWN_VEHICLE"),
        ("verification", "DRIVER_NOT_VERIFIED"),
    ]
    assert not fetch(db, "SELECT id FROM hr.driver_vehicle_eligibility")
