"""BE-23: Owner-approved explicit market selection and period boundaries (Q6).

Real PostgreSQL tests, not a market-combined synthetic fixture.
"""

import pytest

from app.core.security import issue_token
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute
from tests.integration.hr_fixture import ADMIN, CS, DISPATCHER, SYSTEM_ADMIN
from tests.integration.test_m8_kpi_api import SEED

pytestmark = pytest.mark.integration
WINDOW = {"from": "2026-11-10", "to": "2026-11-11"}


@pytest.fixture
def markets(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SEED)
    return api


def test_be23_system_admin_must_choose_market_and_never_mix_currencies(markets: Api) -> None:
    assert_error(markets.get("/kpi/summary", SYSTEM_ADMIN, **WINDOW), 403, "FORBIDDEN")
    selected = markets.get("/kpi/summary", SYSTEM_ADMIN, market="SE", **WINDOW)
    expected = markets.get("/kpi/summary", DISPATCHER, **WINDOW)
    assert selected.status_code == 200 and selected.json() == expected.json()
    zero_market = markets.get("/kpi/summary", SYSTEM_ADMIN, market="ZZ", **WINDOW)
    assert zero_market.status_code == 200
    assert zero_market.json()["metrics"]["on_time_rate"]["value"] is None
    assert zero_market.json()["metrics"]["planning_time_min"]["value"] is None
    assert_error(markets.get("/kpi/summary", SYSTEM_ADMIN, market="XY", **WINDOW), 404, "NOT_FOUND")
    assert_error(markets.get("/kpi/summary", CS, market="SE", **WINDOW), 403, "FORBIDDEN")


def test_be23_employee_market_cannot_be_overridden(markets: Api) -> None:
    for uid in (ADMIN, DISPATCHER):
        assert_error(markets.get("/kpi/summary", uid, market="ZZ", **WINDOW), 404, "NOT_FOUND")
    own = markets.get("/kpi/summary", DISPATCHER, market="SE", **WINDOW)
    assert own.status_code == 200


def test_be23_daily_and_null_diagnostics_require_explicit_scope(markets: Api) -> None:
    assert_error(
        markets.get("/kpi/daily", SYSTEM_ADMIN, metric="on_time_rate", **WINDOW),
        403,
        "FORBIDDEN",
    )
    daily = markets.get("/kpi/daily", SYSTEM_ADMIN, metric="on_time_rate", market="SE", **WINDOW)
    assert daily.status_code == 200
    assert len(daily.json()["points"]) == 2
    assert_error(markets.get("/kpi/diagnostics", SYSTEM_ADMIN), 403, "FORBIDDEN")
    diag = markets.get("/kpi/diagnostics", SYSTEM_ADMIN, market="SE")
    assert diag.status_code == 200
    assert diag.json() == {
        "hard_constraint_violations": None,
        "event_to_alert_latency_s_median": None,
    }


def test_be23_baseline_write_is_bound_to_explicit_market(markets: Api) -> None:
    headers = {"Authorization": f"Bearer {issue_token(SYSTEM_ADMIN, {})}"}
    without = markets.client.put(
        "/api/v1/kpi/baseline/on_time_rate",
        headers=headers,
        json={"value": "0.70"},
    )
    assert_error(without, 403, "FORBIDDEN")
    accepted = markets.client.put(
        "/api/v1/kpi/baseline/on_time_rate",
        headers=headers,
        params={"market": "ZZ"},
        json={"value": "0.70"},
    )
    assert accepted.status_code == 200, accepted.text
    se = markets.get("/kpi/summary", DISPATCHER, **WINDOW).json()
    zz = markets.get("/kpi/summary", SYSTEM_ADMIN, market="ZZ", **WINDOW).json()
    assert se["metrics"]["on_time_rate"].get("baseline") is None
    assert zz["metrics"]["on_time_rate"]["baseline"] == pytest.approx(0.7)


def test_be23_inclusive_30_day_default_and_366_day_max(markets: Api) -> None:
    last = markets.get("/kpi/summary", DISPATCHER, to="2026-11-11")
    assert last.status_code == 200
    assert last.json()["period"] == {"from": "2026-10-13", "to": "2026-11-11"}
    max_window = markets.get(
        "/kpi/daily", DISPATCHER, metric="manual_plan_count", **{"from": "2025-11-11", "to": "2026-11-11"}
    )
    assert max_window.status_code == 200
    assert len(max_window.json()["points"]) == 366
    over = markets.get(
        "/kpi/daily", DISPATCHER, metric="manual_plan_count", **{"from": "2025-11-10", "to": "2026-11-11"}
    )
    assert_error(over, 422, "VALIDATION_ERROR")
