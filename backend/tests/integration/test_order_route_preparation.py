import secrets
from datetime import UTC, datetime

import httpx
import pytest

from alembic import command
from app.providers.routing_ors import OrsRoutingProvider, RoutingUnavailable
from app.services.routing_service import prepare_order_routes
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, tzinfo=UTC)


def prepare(dsn: str) -> None:
    command.upgrade(alembic_config(dsn), "0007")
    execute(
        dsn,
        *rows.REF_HR,
        rows.order_sql(1),
        "INSERT INTO ref.location(market_id,type,code,name,lat,lon,loading_cutoff_time) "
        "VALUES (1,'warehouse','WH-2','Second',59.5,18.5,'15:00')",
        "INSERT INTO ref.location(market_id,type,code,name,lat,lon,is_active,loading_cutoff_time) "
        "VALUES (1,'warehouse','WH-OFF','Inactive',59.5,18.5,false,'15:00')",
        "INSERT INTO ref.market(code,name,timezone,currency) VALUES ('YY','Other','UTC','EUR')",
        "INSERT INTO ref.location(market_id,type,code,name,lat,lon,loading_cutoff_time) "
        "VALUES (2,'warehouse','OTHER','Other',59.5,18.5,'15:00')",
    )


def test_US_INT_05_AC1_prepare_only_active_same_market_warehouses_and_reuse_cache(empty_db: str) -> None:
    prepare(empty_db)
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"distances": [[12]], "durations": [[660]]})

    provider = OrsRoutingProvider(secrets.token_urlsafe(12), transport=httpx.MockTransport(respond))
    for _ in range(2):
        routes = transact(empty_db, lambda s: prepare_order_routes(s, 1, provider, now=NOW))
        assert len(routes) == 2
        assert all(route.provider == "ors" and route.duration_min == 11 for route in routes.values())
    assert len(calls) == 2
    assert [
        row[0] for row in fetch(empty_db, "SELECT warehouse_id FROM plan.route_matrix ORDER BY warehouse_id")
    ] == [1, 3]
    assert fetch(empty_db, "SELECT status,approved_plan_id FROM ops.customer_order")[0] == ("SUBMITTED", None)
    assert fetch(empty_db, "SELECT count(*) FROM plan.stock_reservation")[0][0] == 0
    assert fetch(empty_db, "SELECT count(*) FROM plan.fulfilment_plan")[0][0] == 0


def test_US_INT_05_AC1_failure_rolls_back_preparation_and_leaves_order_unchanged(empty_db: str) -> None:
    prepare(empty_db)
    execute(empty_db, 'UPDATE ref.market SET config=\'{"routing":{"allow_fallback":false}}\'')
    count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return (
            httpx.Response(200, json={"distances": [[12]], "durations": [[660]]})
            if count == 1
            else httpx.Response(503)
        )

    provider = OrsRoutingProvider(secrets.token_urlsafe(12), transport=httpx.MockTransport(respond))
    with pytest.raises(RoutingUnavailable):
        transact(empty_db, lambda s: prepare_order_routes(s, 1, provider, now=NOW))
    assert count == 2
    assert fetch(empty_db, "SELECT count(*) FROM plan.route_matrix")[0][0] == 0
    assert fetch(empty_db, "SELECT status FROM ops.customer_order")[0][0] == "SUBMITTED"


def test_US_INT_05_AC2_offline_fallback_and_missing_order_do_not_call_network(empty_db: str) -> None:
    prepare(empty_db)
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("Offline must not call ORS")

    provider = OrsRoutingProvider("", transport=httpx.MockTransport(respond))
    routes = transact(empty_db, lambda s: prepare_order_routes(s, 1, provider, now=NOW))
    assert len(routes) == 2 and all(route.provider == "fallback" for route in routes.values())
    execute(empty_db, 'UPDATE ref.market SET config=\'{"routing":{"allow_fallback":false}}\'')
    with pytest.raises(RoutingUnavailable):
        transact(empty_db, lambda s: prepare_order_routes(s, 1, provider, now=NOW))
    with pytest.raises(ValueError, match="Order unavailable"):
        transact(empty_db, lambda s: prepare_order_routes(s, 999, provider, now=NOW))
    assert not calls
