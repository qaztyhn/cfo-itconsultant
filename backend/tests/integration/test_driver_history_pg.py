# ruff: noqa: F811
"""D7: one verified-history proof drives planning context AND execution authorization (real PostgreSQL)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.ops import DeliveryTrip
from app.domain.models.ref import Market
from app.engine.types import DriverCtx, VehicleCtx
from app.services import driver_history, execution_service, planning_inputs
from tests.d7_evidence import evidence, interval
from tests.integration.conftest import execute
from tests.integration.dev2_helpers import transact
from tests.integration.test_execution_api import api, execution_api  # noqa: F401

pytestmark = pytest.mark.integration

DAY = date(2026, 11, 10)
EVENT = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)  # 09:00 Stockholm, inside the 07:00-17:00 official shift
DRIVER = CurrentUser(id=5, employee_id=5, roles=("driver",), market="SE")
SHIFT = (
    "INSERT INTO hr.employee_shift_schedule (employee_id,warehouse_id,work_date,start_time,end_time,"
    "assigned_by,assigned_at) VALUES (5,1,'2026-11-10','07:00','17:00',3,'2026-11-08T09:00Z')",
    "INSERT INTO hr.attendance (employee_id, work_date, status) VALUES (5, '2026-11-10', 'present')",
)


class Reader:
    def __init__(self, ev):
        self.ev = ev

    async def read(self, session, employee_id, market_code, target_date):
        return self.ev


@pytest.fixture(autouse=True)
def _no_reader():
    driver_history.configure_reader(None)
    yield
    driver_history.configure_reader(None)


async def gate(session):
    trip = await session.get(DeliveryTrip, 1)
    market = await session.get(Market, 1)
    return await execution_service._driver_gate(session, DRIVER, trip, market, EVENT)


def run_gate(dsn: str) -> str:
    try:
        transact(dsn, gate)
    except DomainError as exc:
        return f"{exc.code}: {exc.message}"
    return "ALLOWED"


def with_evidence(dsn: str, ev) -> str:
    execute(dsn, *SHIFT)
    driver_history.configure_reader(Reader(ev))
    return run_gate(dsn)


def test_accepted_complete_verified_history_allows_the_driver(execution_api) -> None:
    assert with_evidence(execution_api.dsn, evidence(5, DAY)) == "ALLOWED"


def test_without_an_approved_evidence_source_execution_stays_fail_closed(execution_api) -> None:
    execute(execution_api.dsn, *SHIFT)
    assert "EVIDENCE_MISSING" in run_gate(execution_api.dsn)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"expires_at": EVENT - timedelta(minutes=1)}, "EVIDENCE_EXPIRED"),
        ({"revoked": True}, "EVIDENCE_REVOKED"),
        ({"verified_by": None}, "EVIDENCE_UNVERIFIED"),
        ({"mutate": lambda d: d[:-1]}, "DAY_MISSING"),
        ({"mutate": lambda d: [replace(d[0], status="unknown"), *d[1:]]}, "DAY_UNKNOWN"),
    ],
)
def test_expired_revoked_unverified_or_incomplete_evidence_blocks(execution_api, kwargs, reason) -> None:
    outcome = with_evidence(execution_api.dsn, evidence(5, DAY, **kwargs))
    assert outcome.startswith("PLAN_NOT_APPROVABLE") and reason in outcome


def test_conflicting_evidence_blocks(execution_api) -> None:
    def contradict(days):
        off = next(i for i, x in enumerate(days) if x.status == "off_duty")
        return [
            *days[:off],
            replace(days[off], duty=interval(days[off].local_date, "08:00", "16:00")),
            *days[off + 1 :],
        ]

    outcome = with_evidence(execution_api.dsn, evidence(5, DAY, mutate=contradict))
    assert "INCONSISTENT" in outcome


def test_synthetic_evidence_is_refused_in_production(execution_api, monkeypatch) -> None:
    class Prod:
        app_env = "production"

    monkeypatch.setattr(driver_history, "get_settings", lambda: Prod())
    assert "SYNTHETIC_NOT_ALLOWED" in with_evidence(execution_api.dsn, evidence(5, DAY))
    driver_history.configure_reader(Reader(evidence(5, DAY, source_kind="verified_import")))
    assert run_gate(execution_api.dsn) == "ALLOWED"


def _last_duty_ending(hour_utc: int, minute: int = 0):
    """Replace the newest day with a duty ending the previous evening at the given UTC time."""

    def mutate(days):
        end = datetime(2026, 11, 9, hour_utc, minute, tzinfo=UTC)
        day = days[-1].local_date
        return [
            *days[:-1],
            replace(
                days[-1],
                status="duty",
                duty=(end - timedelta(hours=8), end),
                driving=(),
                rest=None,
                local_date=day,
            ),
        ]

    return mutate


def test_eleven_hours_of_rest_are_required_to_the_minute(execution_api) -> None:
    short = with_evidence(
        execution_api.dsn, evidence(5, DAY, mutate=_last_duty_ending(21, 1))
    )  # 10h59 before 08:00Z
    assert "rest" in short and short.startswith("PLAN_NOT_APPROVABLE")
    assert run_gate(execution_api.dsn).startswith("PLAN_NOT_APPROVABLE")
    driver_history.configure_reader(Reader(evidence(5, DAY, mutate=_last_duty_ending(21, 0))))  # exactly 11 h
    assert run_gate(execution_api.dsn) == "ALLOWED"


def test_driving_limit_uses_todays_recorded_driving_on_top_of_the_proof(execution_api) -> None:
    execute(
        execution_api.dsn,
        "INSERT INTO hr.driver_duty_log (employee_id,duty_start,duty_end,driving_min,source) "
        "VALUES (5,'2026-11-10T06:00Z','2026-11-10T07:30Z',600,'shift')",
    )
    outcome = with_evidence(execution_api.dsn, evidence(5, DAY))
    assert outcome.startswith("PLAN_NOT_APPROVABLE") and "driving" in outcome  # 600 min > 540 min/day


def test_missing_official_shift_blocks_even_with_complete_history(execution_api) -> None:
    driver_history.configure_reader(Reader(evidence(5, DAY)))
    assert "official driver shift" in run_gate(execution_api.dsn)


def test_planning_context_uses_the_same_proof(execution_api) -> None:
    execute(execution_api.dsn, *SHIFT)
    zone = ZoneInfo("Europe/Stockholm")

    async def context(session):
        vehicle = VehicleCtx(1, "V-EX-1", Decimal(9000), Decimal(30), frozenset(), "C", frozenset(), ())
        driver = DriverCtx(5, "CE", date(2027, 1, 31), frozenset({DAY}), {}, ())
        _, drivers = await planning_inputs.official_driver_context(
            session, 1, (vehicle,), (driver,), days=[DAY], now=EVENT, zone=zone, market_code="SE"
        )
        return drivers[0]

    blocked = transact(execution_api.dsn, context)
    assert blocked.history_complete is False and blocked.shifts  # no source: fail closed
    driver_history.configure_reader(Reader(evidence(5, DAY)))
    ok = transact(execution_api.dsn, context)
    assert ok.history_complete is True and len(ok.duty_history) == 18
    assert ok.driving_min_by_day and ok.driving_min_week == 480
    driver_history.configure_reader(Reader(evidence(5, DAY, mutate=lambda d: d[:-1])))
    assert transact(execution_api.dsn, context).history_complete is False
