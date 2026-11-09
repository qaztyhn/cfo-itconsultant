"""Real PostgreSQL regression: synthetic WMS ledger cannot forge final approval.

Use original T16 PG setup/locks/holds/recheck; keep production guard intact.
"""

from types import SimpleNamespace

import pytest

from app.adapters.wms_reservation import AckLine, ReservationAck
from app.core.errors import DomainError
from app.services import approval_service, wms_intent
from tests.integration.conftest import execute, fetch
from tests.integration.test_approval_service import _actor, _hold, _recheck, _run
from tests.integration.test_approval_service import db as db  # noqa: F401
from tests.integration.test_wms_intent import _request

pytestmark = pytest.mark.integration


def _scope(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setattr(
        wms_intent,
        "get_settings",
        lambda: SimpleNamespace(app_env="test", app_now="2026-11-04T10:05:00+01:00"),
    )


def _approve(db: str, key: str) -> None:
    _run(
        db,
        lambda s: approval_service.approve(
            1, _actor(), {}, key, session=s, recheck=_recheck
        ),
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
        lambda s: wms_intent.mark_refreshed(
            s, req.idempotency_key, batch_id=2, inclusion_proven=True
        ),
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
