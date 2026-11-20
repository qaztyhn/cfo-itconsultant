# ruff: noqa: F811
"""The legacy D7 reader remains usable without authorizing R3 execution."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services import driver_history
from tests.d7_evidence import evidence, interval
from tests.integration.dev2_helpers import transact
from tests.integration.test_execution_api import api, execution_api  # noqa: F401

pytestmark = pytest.mark.integration
DAY = date(2026, 11, 10)
EVENT = datetime(2026, 11, 10, 8, tzinfo=UTC)


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


def proof(dsn):
    return transact(dsn, lambda s: driver_history.load_proof(s, 5, "SE", ZoneInfo("Europe/Stockholm"), EVENT))


def test_legacy_reader_requires_an_evidence_source(execution_api) -> None:
    assert "EVIDENCE_MISSING" in proof(execution_api.dsn).reasons
    driver_history.configure_reader(Reader(evidence(5, DAY)))
    verified = proof(execution_api.dsn)
    assert verified.complete and len(verified.duty_history) == 18


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
def test_legacy_reader_rejects_expired_revoked_unverified_or_incomplete_evidence(
    execution_api, kwargs, reason
) -> None:
    driver_history.configure_reader(Reader(evidence(5, DAY, **kwargs)))
    rejected = proof(execution_api.dsn)
    assert not rejected.complete and reason in rejected.reasons


def test_legacy_reader_rejects_conflicting_evidence(execution_api) -> None:
    def contradict(days):
        off = next(i for i, item in enumerate(days) if item.status == "off_duty")
        return [
            *days[:off],
            replace(days[off], duty=interval(days[off].local_date, "08:00", "16:00")),
            *days[off + 1 :],
        ]

    driver_history.configure_reader(Reader(evidence(5, DAY, mutate=contradict)))
    assert "INCONSISTENT" in proof(execution_api.dsn).reasons


def test_legacy_reader_rejects_synthetic_evidence_in_production(execution_api, monkeypatch) -> None:
    class Prod:
        app_env = "production"

    monkeypatch.setattr(driver_history, "get_settings", lambda: Prod())
    driver_history.configure_reader(Reader(evidence(5, DAY)))
    assert "SYNTHETIC_NOT_ALLOWED" in proof(execution_api.dsn).reasons
    driver_history.configure_reader(Reader(evidence(5, DAY, source_kind="verified_import")))
    assert proof(execution_api.dsn).complete
