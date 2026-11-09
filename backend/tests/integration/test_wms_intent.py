"""PostgreSQL-backed WMS intent and recovery; no final APPROVED assertion."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters import synthetic_wms
from app.adapters.wms_reservation import ReservationMismatch, build_request
from app.adapters.wms_sku import (
    ConfirmedMapping,
    OrderLineRef,
    ReverseSkuError,
    WmsSkuRelation,
    resolve_reservation_lines,
)
from app.core.errors import DomainError
from app.services import wms_intent
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch
from tests.integration.test_approval_service import db as db  # noqa: F401

pytestmark = pytest.mark.integration


def _run(dsn: str, fn):
    async def go():
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _request():
    lines = resolve_reservation_lines(
        "ZZ",
        "WH-1",
        [OrderLineRef(1, "SKU1", 1, Decimal("20"), "map-v1")],
        {"SKU1": ConfirmedMapping("SKU1", 1, "pcs", Decimal(1), True, "map-v1")},
        [WmsSkuRelation("ZZ", "WH-1", "SKU1", "WMS-1", "pcs", Decimal(1), False, True)],
        {("WH-1", "WMS-1")},
    )
    return build_request("ZZ", 1, 1, lines)


def _prepare(db: str) -> None:
    # The existing approval fixture already migrated this isolated PostgreSQL database.
    execute(
        db,
        "UPDATE ops.customer_order SET status='PLANNED' WHERE id=1",
    )


def test_intent_unique_idempotent_and_exact_native_sku(db: str) -> None:
    _prepare(db)
    request = _request()
    first = _run(db, lambda s: wms_intent.begin_intent(s, request, synthetic=True))
    second = _run(db, lambda s: wms_intent.begin_intent(s, request, synthetic=True))
    assert first.id == second.id
    assert fetch(db, "SELECT count(*) FROM ops.wms_reservation_intent")[0][0] == 1
    assert first.request_payload["lines"][0]["wms_sku"] == "WMS-1"
    assert first.request_payload["lines"][0]["mapping_version"] == "map-v1"
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"


def test_changed_intent_is_rejected_without_second_reservation(db: str) -> None:
    _prepare(db)
    request = _request()
    _run(db, lambda s: wms_intent.begin_intent(s, request, synthetic=True))
    different = build_request("ZZ", 1, 1, (request.lines[0].__class__(
        1, "SKU1", "WMS-1", "WH-1", Decimal(21), "pcs", "map-v1"
    ),))
    with pytest.raises(DomainError) as err:
        _run(db, lambda s: wms_intent.begin_intent(s, different, synthetic=True))
    assert err.value.code == "RESOURCE_CONFLICT"
    assert fetch(db, "SELECT count(*) FROM ops.wms_reservation_intent")[0][0] == 1


def test_ack_commit_failure_recovers_from_same_synthetic_key(db: str, monkeypatch) -> None:
    _prepare(db)
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setattr(
        synthetic_wms,
        "get_settings",
        lambda: SimpleNamespace(app_env="test", app_now=synthetic_wms.DEMO_NOW),
    )
    request = _request()
    _run(db, lambda s: wms_intent.begin_intent(s, request, synthetic=True))
    port = synthetic_wms.SyntheticWmsPort({("WH-1", "WMS-1"): Decimal(50)})
    ack = asyncio.run(port.reserve(request))

    async def lost_commit(session):
        await wms_intent.record_ack(session, request.idempotency_key, ack)
        raise RuntimeError("synthetic CFO commit failure")

    with pytest.raises(RuntimeError):
        _run(db, lost_commit)
    assert fetch(db, "SELECT status FROM ops.wms_reservation_intent")[0][0] == "pending"
    recovered = asyncio.run(port.status("ZZ", request.idempotency_key))
    assert recovered == ack
    stored = _run(db, lambda s: wms_intent.record_ack(s, request.idempotency_key, recovered))
    assert stored.status == "acked"
    assert stored.is_synthetic is True
    assert port.reserve_count == 1
    assert asyncio.run(port.reserve(request)) == ack
    assert port.reserve_count == 1
    with pytest.raises(DomainError):
        _run(
            db,
            lambda s: wms_intent.mark_refreshed(
                s, request.idempotency_key, batch_id=ack.reflected_in_batch_id - 1,
                inclusion_proven=True,
            ),
        )
    refreshed = _run(
        db,
        lambda s: wms_intent.mark_refreshed(
            s, request.idempotency_key, batch_id=ack.reflected_in_batch_id,
            inclusion_proven=True,
        ),
    )
    assert refreshed.status == "refreshed"
    assert fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0


def test_wrong_ack_cannot_enter_ledger(db: str, monkeypatch) -> None:
    _prepare(db)
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setattr(
        synthetic_wms,
        "get_settings",
        lambda: SimpleNamespace(app_env="test", app_now=synthetic_wms.DEMO_NOW),
    )
    request = _request()
    _run(db, lambda s: wms_intent.begin_intent(s, request, synthetic=True))
    port = synthetic_wms.SyntheticWmsPort({("WH-1", "WMS-1"): Decimal(50)})
    ack = asyncio.run(port.reserve(request))
    from dataclasses import replace

    with pytest.raises(ReservationMismatch):
        _run(
            db,
            lambda s: wms_intent.record_ack(s, request.idempotency_key, replace(ack, idempotency_key="wrong")),
        )
    assert fetch(db, "SELECT status FROM ops.wms_reservation_intent")[0][0] == "pending"


def test_mapping_must_be_confirmed_and_exact() -> None:
    request = _request()
    assert request.lines[0].wms_sku == "WMS-1"
    with pytest.raises(ReverseSkuError):
        resolve_reservation_lines(
            "ZZ",
            "WH-1",
            [OrderLineRef(1, "SKU1", 1, Decimal(20), "map-v1")],
            {"SKU1": ConfirmedMapping("SKU1", 1, "pcs", Decimal(1), False, "map-v1")},
            [WmsSkuRelation("ZZ", "WH-1", "SKU1", "WMS-1", "pcs", Decimal(1), False, True)],
            {("WH-1", "WMS-1")},
        )
