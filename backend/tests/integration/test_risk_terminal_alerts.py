"""M7: open risk alerts are closed when an order is DELIVERED (alerts stay possible while it is active)."""

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.errors import DomainError
from app.services import risk_service
from tests.integration.api_harness import Api, api  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.test_risk_service_m7 import NOW, _recalc, run
from tests.integration.test_risk_service_m7 import risk_db as risk_db

pytestmark = pytest.mark.integration

RISK = ("RISK_ORANGE", "PREDICTED_LATE", "OVERDUE")


def _alert(db: str, kind: str, *, order: int | None = 1, market: int = 1, key: str | None = None) -> None:
    order_sql = "NULL" if order is None else str(order)
    execute(
        db,
        "INSERT INTO ops.alert (market_id, order_id, level, type, message, target_roles, dedupe_key) "
        f"VALUES ({market}, {order_sql}, 'critical', '{kind}', 'Synthetic', '{{dispatcher}}', "
        f"'{key or f'k:{kind}:{order}:{market}'}')",
    )


def _deliver(db: str) -> None:
    execute(db, "UPDATE ops.customer_order SET status='DELIVERED' WHERE id=1")


def _open(db: str, kind: str, order: int | None = 1) -> int:
    where = "order_id IS NULL" if order is None else f"order_id={order}"
    return fetch(
        db, f"SELECT count(*) AS n FROM ops.alert WHERE type='{kind}' AND {where} AND resolved_at IS NULL"
    )[0]["n"]


def test_delivery_closes_the_orders_open_risk_alerts_and_keeps_history(risk_db) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dsn, _ = risk_db
    assert _recalc(dsn, at=NOW - timedelta(minutes=1)) is not None  # real flow raises RISK_ORANGE
    assert _open(dsn, "RISK_ORANGE") == 1
    for kind in ("PREDICTED_LATE", "OVERDUE"):
        _alert(dsn, kind)
    before = fetch(dsn, "SELECT id,type,message,level,dedupe_key,created_at FROM ops.alert ORDER BY id")
    _deliver(dsn)
    assert run(dsn, lambda s: risk_service.recalculate(1, "delivered", session=s)) is None
    assert sum(_open(dsn, kind) for kind in RISK) == 0
    after = fetch(
        dsn, "SELECT id,type,message,level,dedupe_key,created_at,resolved_at FROM ops.alert ORDER BY id"
    )
    assert [tuple(r)[:6] for r in after] == [tuple(r) for r in before]  # nothing deleted or rewritten
    assert all(r["resolved_at"] is not None for r in after if r["type"] in RISK)
    assert (
        fetch(dsn, "SELECT count(*) AS n FROM ops.eta_forecast")[0]["n"] == 1
    )  # no forecast for a delivered order


def test_duplicate_completion_is_idempotent_and_keeps_the_original_resolution_time(risk_db) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dsn, state = risk_db
    _alert(dsn, "PREDICTED_LATE")
    _deliver(dsn)
    run(dsn, lambda s: risk_service.recalculate(1, "delivered", session=s))
    first = fetch(dsn, "SELECT resolved_at FROM ops.alert")[0]["resolved_at"]
    assert first is not None  # the first completion really closed it
    state["now"] = NOW + timedelta(hours=1)
    assert run(dsn, lambda s: risk_service.recalculate(1, "delivered", session=s)) is None
    assert fetch(dsn, "SELECT resolved_at FROM ops.alert")[0]["resolved_at"] == first
    assert fetch(dsn, "SELECT count(*) AS n FROM ops.alert")[0]["n"] == 1


def test_a_later_recalculation_never_reopens_or_recreates_a_risk_alert_for_a_completed_order(risk_db) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dsn, state = risk_db
    assert _recalc(dsn, at=NOW - timedelta(minutes=1)) is not None
    _deliver(dsn)
    run(dsn, lambda s: risk_service.recalculate(1, "delivered", session=s))
    state["now"] = NOW + timedelta(hours=3)  # far past promise_end: it would be OVERDUE if still active
    for trigger in ("source_change", "overdue_milestone", "gps_update"):
        assert _recalc(dsn, at=state["now"] - timedelta(minutes=1), trigger=trigger) is None
    assert (
        fetch(
            dsn,
            "SELECT count(*) AS n FROM ops.alert WHERE type IN ('RISK_ORANGE','PREDICTED_LATE','OVERDUE')",
        )[0]["n"]
        == 1
    )
    assert sum(_open(dsn, kind) for kind in RISK) == 0
    assert fetch(dsn, "SELECT count(*) AS n FROM ops.eta_forecast")[0]["n"] == 1


def test_unrelated_alerts_other_orders_and_other_markets_are_untouched(risk_db) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dsn, _ = risk_db
    execute(
        dsn,
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "delivery_address, delivery_lat, delivery_lon, date_mode, date_to, order_date, currency, "
        "submitted_at, status) VALUES ('SE-RISK-2',1,'RISK-2',1,'Synthetic','Synthetic',59,18,'latest',"
        "'2026-11-10','2026-11-04T09:00Z','SEK','2026-11-04T09:00Z','SUBMITTED')",
    )
    _alert(dsn, "PREDICTED_LATE")  # the delivered order's risk alert: must close
    for kind in ("STALE_DATA", "EXCEPTION", "REPLAN_SUGGESTED", "ORDER_CHANGED_AFTER_APPROVAL"):
        _alert(dsn, kind)  # same order, other operational types: must stay open
    _alert(dsn, "GPS_LOST", order=None)  # no order
    _alert(dsn, "PREDICTED_LATE", order=2, key="k:other-order")  # another order
    _alert(dsn, "OVERDUE", order=1, market=2, key="k:other-market")  # same order id but another market
    _deliver(dsn)
    run(dsn, lambda s: risk_service.recalculate(1, "delivered", session=s))
    assert _open(dsn, "PREDICTED_LATE") == 0  # the delivered order's alert closed
    assert _open(dsn, "PREDICTED_LATE", order=2) == 1  # another order's alert untouched
    assert _open(dsn, "OVERDUE") == 1  # market-scoped: the other market's row is not closed
    for kind in ("STALE_DATA", "EXCEPTION", "REPLAN_SUGGESTED", "ORDER_CHANGED_AFTER_APPROVAL"):
        assert _open(dsn, kind) == 1
    assert _open(dsn, "GPS_LOST", order=None) == 1


def test_closing_alerts_joins_the_callers_transaction(risk_db) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dsn, _ = risk_db
    _alert(dsn, "OVERDUE")
    _deliver(dsn)

    async def then_fail(session) -> None:  # type: ignore[no-untyped-def]
        assert await risk_service.recalculate(1, "delivered", session=session) is None
        closed = await session.scalar(text("SELECT count(*) FROM ops.alert WHERE resolved_at IS NOT NULL"))
        assert closed == 1  # closed inside the transaction ...
        raise RuntimeError("the delivery transaction aborts")

    with pytest.raises(RuntimeError):
        run(dsn, then_fail)
    assert _open(dsn, "OVERDUE") == 1  # ... and open again: the closing rolled back with the caller


def test_a_failed_delivery_keeps_its_alerts_because_no_policy_closes_them(risk_db) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dsn, _ = risk_db
    _alert(dsn, "PREDICTED_LATE")
    execute(dsn, "UPDATE ops.customer_order SET status='FAILED' WHERE id=1")
    assert run(dsn, lambda s: risk_service.recalculate(1, "delivery_failed", session=s)) is None
    assert _open(dsn, "PREDICTED_LATE") == 1


def test_unknown_order_still_fails_with_not_found(risk_db) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    dsn, _ = risk_db
    with pytest.raises(DomainError) as missing:
        run(dsn, lambda s: risk_service.recalculate(99, "delivered", session=s))
    assert missing.value.code == "NOT_FOUND"
