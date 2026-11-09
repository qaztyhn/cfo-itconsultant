"""M7 risk service: real PostgreSQL versions, event freshness and alert lifecycle."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.errors import DomainError
from app.services import risk_service
from tests.integration import rows
from tests.integration.api_harness import Api, api  # noqa: F401
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.hr_fixture import SETUP

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 10, 8, 45, tzinfo=UTC)


def run[T](dsn: str, action: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await action(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


SETUP_RISK = (
    *SETUP,
    "INSERT INTO ref.customer (market_id, external_ref, type, name) "
    "VALUES (1, 'RISK-C', 'business', 'Synthetic customer')",
    "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, "
    "required_licence) VALUES (1,'RSK-1','RSK-PL-1','Risk vehicle 1',8000,30,'C'),"
    "(1,'RSK-2','RSK-PL-2','Risk vehicle 2',8000,30,'C')",
    "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, "
    "contact_name, delivery_address, delivery_lat, delivery_lon, date_mode, date_to, "
    "order_date, currency, submitted_at, status, approved_at, promise_start, promise_end) "
    "VALUES ('SE-RISK-1',1,'RISK-1',1,'Synthetic','Synthetic',59,18,'latest','2026-11-10',"
    "'2026-11-04T09:00Z','SEK','2026-11-04T09:00Z','DISPATCHED',"
    "'2026-11-10T06:00Z','2026-11-10T08:00Z','2026-11-10T10:00Z')",
    rows.run_sql(1, 1),
    rows.plan_sql(1, 1, 1, "approved"),
    "UPDATE ops.customer_order SET approved_plan_id=1 WHERE id=1",
    rows.plan_vehicle_sql(1, 1, 1),
    rows.plan_vehicle_sql(1, 2, 2),
    "UPDATE plan.fulfilment_plan SET vehicle_count=2 WHERE id=1",
    rows.trip_sql(1),
    rows.trip_sql(2),
    "UPDATE ops.delivery_trip SET plan_vehicle_id=1 WHERE id=1",
    "UPDATE ops.delivery_trip SET plan_vehicle_id=2 WHERE id=2",
    rows.stop_sql(1, 1),
    rows.stop_sql(2, 1),
    "UPDATE ops.delivery_trip SET status='on_road',depart_actual_at='2026-11-10T08:30Z'",
)


@pytest.fixture
def risk_db(api: Api, monkeypatch: pytest.MonkeyPatch) -> tuple[str, dict[str, datetime]]:  # noqa: F811
    execute(api.dsn, *SETUP_RISK)
    state = {"now": NOW}
    monkeypatch.setattr(risk_service.clock, "now", lambda: state["now"])
    return api.dsn, state


def _recalc(dsn: str, *, at: datetime, trigger: str = "source_change") -> dict[str, object] | None:
    return run(
        dsn,
        lambda session: risk_service.recalculate(1, trigger, session=session, signal_at=at),
    )


def test_US_RSK_01_AC1_no_unverified_trigger_no_extra_version(
    risk_db: tuple[str, dict[str, datetime]],
) -> None:
    dsn, state = risk_db
    first = _recalc(dsn, at=NOW - timedelta(minutes=1))
    assert first is not None
    assert first["version"] == 1
    assert len(first["vehicles"]) == 2
    assert first["forecast_eta"] == "2026-11-10T10:30:00+00:00"
    same = _recalc(dsn, at=NOW - timedelta(minutes=1))
    assert same is None
    assert fetch(dsn, "SELECT count(*) AS n FROM ops.eta_forecast")[0]["n"] == 1
    with pytest.raises(DomainError) as missing:
        run(dsn, lambda s: risk_service.recalculate(1, "source_change", session=s))
    assert missing.value.code == "PLAN_NOT_APPROVABLE"
    state["now"] = NOW + timedelta(minutes=2)
    assert fetch(dsn, "SELECT count(*) AS n FROM ops.eta_forecast")[0]["n"] == 1


def test_US_RSK_02_AC4_AC5_negative_slack_twice_min_gap_and_dedupe(
    risk_db: tuple[str, dict[str, datetime]],
) -> None:
    dsn, state = risk_db
    orange = _recalc(dsn, at=NOW - timedelta(minutes=1))
    assert orange is not None
    assert (orange["risk_status"], orange["risk_color"], orange["consecutive_negative"]) == (
        "AT_RISK",
        "orange",
        1,
    )
    state["now"] += timedelta(minutes=2)
    short_gap = _recalc(dsn, at=state["now"] - timedelta(minutes=1))
    assert short_gap is not None
    assert short_gap["risk_status"] == "AT_RISK"
    state["now"] += timedelta(minutes=6)
    red = _recalc(dsn, at=state["now"] - timedelta(minutes=1))
    assert red is not None
    assert red["risk_status"] == "PREDICTED_LATE"
    assert red["consecutive_negative"] == 2
    assert red["delay_draft"] == "blocked_missing_approved_window"
    assert fetch(dsn, "SELECT count(*) FROM ops.notification")[0][0] == 0  # No auto-DELAY send.
    assert fetch(dsn, "SELECT count(*) AS n FROM ops.eta_forecast")[0]["n"] == 3
    active = fetch(dsn, "SELECT type,level,resolved_at FROM ops.alert ORDER BY id")
    assert [(a["type"], a["level"]) for a in active] == [
        ("RISK_ORANGE", "warning"),
        ("PREDICTED_LATE", "critical"),
    ]
    assert active[0]["resolved_at"] is not None  # replaced by critical
    assert active[1]["resolved_at"] is None


def test_US_RSK_02_AC3_recovery_resolves_alert_and_new_violation_reopens(
    risk_db: tuple[str, dict[str, datetime]],
) -> None:
    dsn, state = risk_db
    _recalc(dsn, at=NOW - timedelta(minutes=1))
    execute(dsn, "UPDATE ops.delivery_trip SET depart_actual_at='2026-11-10T07:00Z'")
    state["now"] += timedelta(minutes=6)
    good = _recalc(dsn, at=state["now"] - timedelta(minutes=1))
    assert good is not None and good["risk_status"] == "ON_TRACK"
    assert fetch(dsn, "SELECT count(*) AS n FROM ops.alert WHERE resolved_at IS NULL")[0]["n"] == 0
    execute(dsn, "UPDATE ops.delivery_trip SET depart_actual_at='2026-11-10T08:30Z'")
    state["now"] += timedelta(minutes=6)
    _recalc(dsn, at=state["now"] - timedelta(minutes=1))
    assert fetch(dsn, "SELECT count(*) AS n FROM ops.alert WHERE type='RISK_ORANGE'")[0]["n"] == 2


def test_US_RSK_01_AC2_event_signal_must_exist_and_cannot_replay(
    risk_db: tuple[str, dict[str, datetime]],
) -> None:
    dsn, state = risk_db
    assert (
        run(
            dsn,
            lambda s: risk_service.recalculate(
                1,
                "event:GOODS_READY",
                session=s,
            ),
        )
        is None
    )
    execute(
        dsn,
        "INSERT INTO ops.milestone_event (order_id, plan_id, event_type, occurred_at, "
        "actor_user_id, idempotency_key) "
        "VALUES (1,1,'GOODS_READY','2026-11-10T06:00Z',3,'m7-ready-1')",
    )
    result = run(
        dsn,
        lambda s: risk_service.recalculate(
            1,
            "event:GOODS_READY",
            session=s,
        ),
    )
    assert result is not None and result["version"] == 1
    assert (
        run(
            dsn,
            lambda s: risk_service.recalculate(
                1,
                "event:GOODS_READY",
                session=s,
            ),
        )
        is None
    )
    state["now"] += timedelta(minutes=1)


def test_US_RSK_02_AC6_overdue_without_delivered_order(risk_db: tuple[str, dict[str, datetime]]) -> None:
    dsn, state = risk_db
    state["now"] = datetime(2026, 11, 10, 10, 1, tzinfo=UTC)
    outcome = _recalc(dsn, at=state["now"] - timedelta(minutes=1))
    assert outcome is not None and outcome["risk_status"] == "OVERDUE"
    assert fetch(dsn, "SELECT type,level FROM ops.alert")[0]["type"] == "OVERDUE"


def test_US_RSK_01_AC1_recalculate_without_request_transaction_is_fail_closed() -> None:
    with pytest.raises(DomainError) as caught:
        asyncio.run(risk_service.recalculate(1, "approval"))
    assert caught.value.code == "PLAN_NOT_APPROVABLE"

@pytest.mark.parametrize("has_dispatcher", [False, True])
def test_US_NOT_02_AC1_risk_requires_reviewed_actor_and_caller_transaction(
    risk_db: tuple[str, dict[str, datetime]], monkeypatch: pytest.MonkeyPatch, has_dispatcher: bool
) -> None:
    dsn, state = risk_db
    calls: list[int] = []
    reviewer = SimpleNamespace(id=2, employee_id=2, roles=("dispatcher",), market="SE")

    async def draft(order_id: int, payload: dict[str, object], *, session: AsyncSession, actor: object) -> int:
        assert order_id == 1
        assert payload["version"] == 1
        assert session.in_transaction()
        assert actor is reviewer
        calls.append(order_id)
        return 42

    monkeypatch.setattr(risk_service.notify_service, "create_delay_draft", draft)
    _recalc(dsn, at=state["now"] - timedelta(minutes=1))
    state["now"] += timedelta(minutes=2)
    _recalc(dsn, at=state["now"] - timedelta(minutes=1))
    state["now"] += timedelta(minutes=6)
    reviewed_window: dict[str, object] = {
        "start": "2026-11-10T09:00:00Z",
        "end": "2026-11-10T11:00:00Z",
        "version": 1,
    }
    result = run(
        dsn,
        lambda session: risk_service.recalculate(
            1,
            "source_change",
            session=session,
            signal_at=state["now"] - timedelta(minutes=1),
            delay_window=reviewed_window,
            delay_actor=reviewer if has_dispatcher else None,
        ),
    )
    assert result is not None and result["risk_status"] == "PREDICTED_LATE"
    assert result["delay_draft"] == ("draft_requested" if has_dispatcher else "blocked_dispatcher_review")
    assert calls == ([1] if has_dispatcher else [])

