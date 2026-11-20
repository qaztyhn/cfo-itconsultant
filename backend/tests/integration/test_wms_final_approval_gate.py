"""Real PostgreSQL regression: synthetic WMS ledger cannot forge final approval.

Use original T16 PG setup/locks/holds/recheck; keep production guard intact.
"""

import asyncio
import json
import secrets
from collections.abc import Iterator
from datetime import timedelta
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.disposable_wms_client import DisposableWmsPort
from app.adapters.disposable_wms_service import FROZEN, create_app
from app.adapters.wms_reservation import AckLine, ReservationAck
from app.core import clock
from app.core.config import get_settings
from app.core.errors import DomainError
from app.services import approval_service, ingest_service, wms_intent, wms_mode, wms_reserve_phase
from tests.integration import rows
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.test_approval_service import _actor, _hold, _recheck, _run
from tests.integration.test_approval_service import db as db  # noqa: F401
from tests.integration.test_wms_intent import _request
from tests.integration.test_wms_request import _fixture, _product

pytestmark = pytest.mark.integration


def _scope(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setattr(
        wms_intent,
        "get_settings",
        lambda: SimpleNamespace(app_env="test", app_now="2026-11-04T10:05:00+01:00"),
    )
    monkeypatch.setattr(
        wms_mode,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="test",
            app_now="2026-11-04T10:05:00+01:00",
            wms_reservation_mode="simulated",
        ),
    )


def _approve(db: str, key: str) -> None:
    _run(
        db,
        lambda s: approval_service.approve(1, _actor(), {}, key, session=s, recheck=_recheck),
    )


def _assert_not_approved(db: str) -> None:
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
    assert fetch(db, "SELECT status FROM plan.fulfilment_plan WHERE id=1")[0][0] == "proposed"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 0


def test_missing_wms_intent_does_not_approve(db: str, monkeypatch) -> None:
    _scope(monkeypatch)
    _hold(db)
    with pytest.raises(DomainError) as caught:
        _approve(db, "wms-missing")
    assert caught.value.code == "PLAN_NOT_APPROVABLE"
    _assert_not_approved(db)


def test_unknown_wms_ack_stays_blocked_after_retry(db: str, monkeypatch) -> None:
    _scope(monkeypatch)
    _hold(db)
    request = _request()
    _run(db, lambda s: wms_intent.begin_intent(s, request, synthetic=True))
    _run(db, lambda s: wms_intent.record_unknown(s, request.idempotency_key))
    with pytest.raises(DomainError) as caught:
        _approve(db, "wms-unknown")
    assert caught.value.code == "PLAN_NOT_APPROVABLE"
    _assert_not_approved(db)


def test_ack_and_refreshed_marker_cannot_forge_approval(db: str, monkeypatch) -> None:
    """A boolean included flag on the ledger cannot prove Source/WMS batch lineage."""
    _scope(monkeypatch)
    _hold(db)
    req = _request()
    _run(db, lambda s: wms_intent.begin_intent(s, req, synthetic=True))
    ack = ReservationAck(
        reservation_id="SYNTHETIC-1",
        status="accepted",
        revision="synthetic-2",
        idempotency_key=req.idempotency_key,
        reflected_in_batch_id=2,
        lines=(AckLine("WMS-1", "WH-1", req.lines[0].quantity),),
    )
    _run(db, lambda s: wms_intent.record_ack(s, req.idempotency_key, ack))
    _run(
        db,
        lambda s: wms_intent.mark_refreshed(s, req.idempotency_key, batch_id=2, inclusion_proven=True),
    )
    with pytest.raises(DomainError) as caught:
        _approve(db, "wms-apparent-refresh")
    assert caught.value.code == "PLAN_NOT_APPROVABLE"
    assert "WMS_CFO_STOCK_BATCH_LINK_UNVERIFIED" in caught.value.message
    _assert_not_approved(db)


def test_changed_source_after_ack_still_fails_closed(db: str, monkeypatch) -> None:
    _scope(monkeypatch)
    _hold(db)
    req = _request()
    _run(db, lambda s: wms_intent.begin_intent(s, req, synthetic=True))
    execute(db, "UPDATE ops.customer_order SET source_version=2 WHERE id=1")
    with pytest.raises(DomainError) as caught:
        _approve(db, "wms-changed-source")
    assert caught.value.code in ("RESOURCE_CONFLICT", "PLAN_NOT_APPROVABLE")
    _assert_not_approved(db)


@pytest.fixture
def disposable_wms(
    db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[httpx.ASGITransport, str]]:
    _hold(db)
    _fixture(tmp_path, monkeypatch)
    _product(db)
    execute(
        db,
        "INSERT INTO hr.employee_assignment (employee_id,location_id,start_date)"
        " VALUES (1,1,'2026-01-01')",
        "INSERT INTO hr.driver_availability (driver_employee_id,work_date,available_from,available_to,"
        "max_driving_min,verified_by,verified_at,source,source_ref) VALUES"
        " (1,'2026-11-10','2026-11-10T07:00Z','2026-11-10T17:00Z',240,"
        "'Fleet desk','2026-11-04T08:00Z','fleet_api','WMS-AV')",
        "INSERT INTO hr.driver_vehicle_eligibility (driver_employee_id,vehicle_id,verified_until,"
        "verified_by,verified_at,source,source_ref) VALUES"
        " (1,1,'2026-11-10','Fleet desk','2026-11-04T08:00Z','fleet_api','WMS-QUAL')",
        "INSERT INTO ref.app_user (employee_id,email,password_hash,roles)"
        " VALUES (2,'stock-review@cfo.test','x','{admin}')",
        "INSERT INTO ops.stock_scope_version (market_id,version,status,skus,warehouse_ids,"
        "reason_text,created_by,approved_by,approved_at,effective_from)"
        " VALUES (1,1,'approved','{SKU1}','{1}','Synthetic scope',1,2,"
        "'2026-11-01T00:00Z','2026-11-01T00:00Z')",
    )
    fixture_path = tmp_path / "wms.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["source_orders"] = [
        {
            "order_id": 1,
            "plan_id": 1,
            "source_version": 1,
            "source_ref": "EXT-1",
            "lines": [
                {"order_line_id": 1, "pos_sku": "SKU1", "warehouse_code": "WH-1", "quantity": "20.000"}
            ],
        }
    ]
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    secret = secrets.token_urlsafe(32)
    url = "http://127.0.0.1:8199"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_NOW", FROZEN)
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setenv("WMS_RESERVATION_MODE", "simulated")
    monkeypatch.setenv("SYNTHETIC_WMS_URL", url)
    monkeypatch.setenv("SYNTHETIC_WMS_API_KEY", secret)
    monkeypatch.setenv("SYNTHETIC_WMS_SHARED_KEY", secret)
    monkeypatch.delenv("WMS_PRODUCTION_ENABLED", raising=False)
    get_settings.cache_clear()
    engine = create_async_engine(async_url(db), poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for module in (approval_service, ingest_service, wms_reserve_phase):
        monkeypatch.setattr(module, "get_sessionmaker", lambda: maker)
    transport = httpx.ASGITransport(app=create_app(tmp_path / "wms.sqlite", secret, fixture))
    monkeypatch.setattr(
        wms_reserve_phase, "DisposableWmsPort", partial(DisposableWmsPort, transport=transport)
    )
    try:
        yield transport, secret
    finally:
        asyncio.run(engine.dispose())
        get_settings.cache_clear()


@pytest.mark.parametrize("report_fixture", [True, False], ids=["t26-report", "missing-trip"])
def test_US_APR_01_AC1_refresh_acked_wms_stock_hands_off_risk_in_same_transaction(
    db: str, disposable_wms: tuple[httpx.ASGITransport, str], report_fixture: bool
) -> None:
    execute(
        db,
        rows.order_sql(2),
        rows.run_sql(2, 1),
        rows.plan_sql(2, 2, 1, "approved"),
        rows.plan_vehicle_sql(2, 1, 2),
        rows.trip_sql(2),
        "UPDATE ops.delivery_trip SET plan_vehicle_id=2,status='on_road',"
        "depart_actual_at='2026-11-04T08:30Z' WHERE id=1",
        rows.stop_sql(1, 2),
        rows.order_sql(3),
        rows.run_sql(3, 1),
        rows.plan_sql(3, 3, 1, "approved"),
        "UPDATE ops.customer_order SET approved_plan_id=id,"
        "promise_start='2026-11-10T09:00Z',promise_end='2026-11-10T11:00Z' WHERE id IN (2,3)",
        *(
            f"UPDATE ops.customer_order SET status='{status}' WHERE id IN (2,3)"
            for status in ("PLANNED", "APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED")
        ),
    )
    if report_fixture:
        execute(db, """UPDATE plan.planning_run SET input_snapshot='{"fixture":"t26-r3-v1"}' WHERE id=3""")

    async def refresh_after_ack() -> None:
        assert await wms_reserve_phase.reserve_simulated(1, 1) == "acked"
        if report_fixture:
            await wms_reserve_phase.refresh_simulated(1, 1)
            await wms_reserve_phase.refresh_simulated(1, 1)
        else:
            with pytest.raises(DomainError, match="WMS stock batch was not accepted"):
                await wms_reserve_phase.refresh_simulated(1, 1)

    asyncio.run(refresh_after_ack())
    forecasts = fetch(db, "SELECT order_id,trigger FROM ops.eta_forecast ORDER BY order_id")
    writes = fetch(db, "SELECT source_batch_id FROM ops.stock_write_run WHERE source_kind='wms_synthetic'")
    intent = fetch(db, "SELECT status FROM ops.wms_reservation_intent")[0][0]
    if report_fixture:
        assert [tuple(row) for row in forecasts] == [(2, "source_change")]
        assert [row[0] for row in writes] == [2]
        assert intent == "refreshed"
    else:
        assert not forecasts and not writes
        assert intent == "acked"


def test_US_APR_01_concurrent_distinct_keys_do_not_release_committed_wms_hold(
    db: str, disposable_wms: tuple[httpx.ASGITransport, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    transport, secret = disposable_wms
    reserve = approval_service._reserve_before_approval

    async def race() -> None:
        after_preflight = asyncio.Barrier(2)
        approved = asyncio.Event()

        async def reserve_after_preflight(plan_id: int, actor: object) -> None:
            await after_preflight.wait()
            task = asyncio.current_task()
            assert task is not None
            if task.get_name() == "loser":
                await approved.wait()
            await reserve(plan_id, actor)

        monkeypatch.setattr(approval_service, "_reserve_before_approval", reserve_after_preflight)

        async def winner() -> None:
            result = await approval_service.approve(1, _actor(), {}, "winner", recheck=_recheck)
            assert result["order"]["status"] == "APPROVED"
            approved.set()
            assert await approval_service.approve(1, _actor(), {}, "winner", recheck=_recheck) == result

        async def loser() -> None:
            with pytest.raises(DomainError, match="currently proposed plan") as caught:
                await approval_service.approve(1, _actor(), {}, "loser", recheck=_recheck)
            assert caught.value.code == "PLAN_NOT_APPROVABLE"

        async with asyncio.timeout(20), asyncio.TaskGroup() as group:
            group.create_task(winner(), name="winner")
            group.create_task(loser(), name="loser")
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8199") as client:
            batch = (await client.get("/v1/stock", headers={"X-Demo-WMS-Key": secret})).json()
        assert batch["items"][0]["reserved"] == "20.000"
        assert len(batch["included_reservation_ids"]) == 1

    asyncio.run(race())
    assert fetch(db, "SELECT status FROM ops.wms_reservation_intent")[0][0] == "refreshed"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.notification WHERE template='CONFIRMED'")[0][0] == 1


def test_US_APR_01_driver_revoked_after_wms_refresh_blocks_final_approval(
    db: str, disposable_wms: tuple[httpx.ASGITransport, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    refresh = wms_reserve_phase.refresh_simulated

    async def refresh_then_revoke(order_id: int, plan_id: int) -> None:
        await refresh(order_id, plan_id)
        await asyncio.to_thread(
            execute, db, "UPDATE hr.driver_vehicle_eligibility SET revoked_at='2026-11-04T09:05Z'"
        )

    monkeypatch.setattr(wms_reserve_phase, "refresh_simulated", refresh_then_revoke)
    with pytest.raises(DomainError) as caught:
        asyncio.run(approval_service.approve(1, _actor(), {}, "revoke-after-wms", recheck=_recheck))
    assert caught.value.code == "RESOURCE_CONFLICT"
    _assert_not_approved(db)


def test_release_compensates_only_an_expired_unapproved_hold(
    db: str, disposable_wms: tuple[httpx.ASGITransport, str]
) -> None:
    transport, secret = disposable_wms

    async def expiry() -> None:
        await wms_reserve_phase.reserve_simulated(1, 1)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8199") as client:
            await wms_reserve_phase.release_invalid_plan(1)
            headers = {"X-Demo-WMS-Key": secret}
            reserved = (await client.get("/v1/stock", headers=headers)).json()
            assert reserved["items"][0]["reserved"] == "20.000"
            clock.set_now(clock.now() + timedelta(hours=1))
            await wms_reserve_phase.release_invalid_plan(1)
            await wms_reserve_phase.release_invalid_plan(1)
            released = (await client.get("/v1/stock", headers=headers)).json()
            assert released["items"][0]["reserved"] == "0.000"
            assert released["items"][0]["on_hand"] == "100.000"
            assert released["batch_id"] == reserved["batch_id"] + 1

    asyncio.run(expiry())
    assert fetch(db, "SELECT status FROM ops.wms_reservation_intent")[0][0] == "released"
    _assert_not_approved(db)
