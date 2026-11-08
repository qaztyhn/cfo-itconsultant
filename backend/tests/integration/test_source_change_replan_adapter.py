"""T14 adapter for the T07 `ReplanSource` callback: joins the caller transaction, never approves or holds."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.source_change_adapters import replan_source
from tests.integration.conftest import execute, fetch
from tests.integration.test_planning_service import _loader, _request, _run
from tests.integration.test_planning_service import db as db

pytestmark = pytest.mark.integration


def _approve(db: str, status: str = "APPROVED") -> None:
    path = ("PREPARING", "GOODS_READY", "LOADED", "DISPATCHED")  # the order trigger allows only legal steps
    steps = path[: path.index(status) + 1] if status in path else ()
    execute(
        db,
        "UPDATE plan.fulfilment_plan SET status='approved' WHERE id=1",
        "UPDATE plan.stock_reservation SET status='committed' WHERE run_id=1",
        "UPDATE plan.prep_reservation SET status='committed' WHERE run_id=1",
        "UPDATE plan.vehicle_reservation SET status='committed' WHERE run_id=1",
        "UPDATE ops.customer_order SET status='APPROVED',approved_plan_id=1 WHERE id=1",
        *(f"UPDATE ops.customer_order SET status='{step}' WHERE id=1" for step in steps),
    )


class _Order:
    id = 1


async def _suggest(session: AsyncSession) -> int | None:
    return await replan_source(inputs_loader=_loader)(session, _Order(), None)  # type: ignore[arg-type]


def test_source_change_creates_one_unheld_suggestion_and_keeps_the_approved_plan(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _request(db, monkeypatch)
    _approve(db)
    first = _run(db, _suggest)
    assert first == 2 and _run(db, _suggest) == 2  # one run per source version
    run = fetch(db, "SELECT kind,params->>'trigger' AS t,hold_expires_at FROM plan.planning_run WHERE id=2")[
        0
    ]
    assert (run["kind"], run["t"], run["hold_expires_at"]) == ("replan_suggestion", "source_change", None)
    assert (
        fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "APPROVED"
    )  # never auto-approved
    assert fetch(db, "SELECT status FROM plan.fulfilment_plan WHERE id=1")[0][0] == "approved"
    assert fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0] == "committed"
    assert fetch(db, "SELECT count(*) FROM plan.stock_reservation WHERE run_id=2")[0][0] == 0  # no new hold
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='REPLAN_SUGGESTED'")[0][0] == 1


def test_the_adapter_joins_the_callers_transaction(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _request(db, monkeypatch)
    _approve(db)

    async def then_fail(session: AsyncSession) -> None:
        assert await _suggest(session) == 2
        raise RuntimeError("caller aborts after the adapter")

    with pytest.raises(RuntimeError):
        _run(db, then_fail)
    assert fetch(db, "SELECT count(*) FROM plan.planning_run WHERE kind='replan_suggestion'")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='REPLAN_SUGGESTED'")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='REPLAN_SUGGESTED'")[0][0] == 0


def test_dispatched_order_gets_an_alert_but_no_replacement_run(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _request(db, monkeypatch)
    _approve(db, "DISPATCHED")
    assert _run(db, _suggest) is None
    assert fetch(db, "SELECT count(*) FROM plan.planning_run WHERE kind='replan_suggestion'")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.alert WHERE type='REPLAN_SUGGESTED'")[0][0] == 1


def test_an_order_that_is_not_yet_approved_is_not_replanned(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _request(db, monkeypatch)  # PLANNED with a live hold: the normal Plan Again path owns this case
    assert _run(db, _suggest) is None
    assert fetch(db, "SELECT count(*) FROM plan.planning_run")[0][0] == 1
