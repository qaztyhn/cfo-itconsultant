from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from alembic import command
from app.providers.route_cache import ensure_route
from app.providers.routing_ors import OrsRoutingProvider, RoutingUnavailable
from app.seed.infrastructure import seed_infrastructure
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 7, tzinfo=UTC)


def test_US_INT_05_AC1_cache_reuses_route_and_honours_disabled_fallback(
    empty_db: str,
) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    transact(empty_db, lambda s: seed_infrastructure(s, year=2026))
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503)

    provider = OrsRoutingProvider("", transport=httpx.MockTransport(response))
    wh = fetch(empty_db, "SELECT id FROM ref.location WHERE code='GBG'")[0][0]
    for _ in range(2):
        route = transact(
            empty_db,
            lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), provider, now=NOW),
        )
        assert route.provider == "fallback"
    assert fetch(empty_db, "SELECT count(*) FROM plan.route_matrix")[0][0] == 1
    execute(
        empty_db,
        'UPDATE ref.market SET config=\'{"routing":{"allow_fallback":false}}\'',
    )
    with pytest.raises(RoutingUnavailable):
        transact(
            empty_db,
            lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), provider, now=NOW),
        )


def test_US_INT_05_AC1_ors_replaces_disallowed_fallback(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    transact(empty_db, lambda s: seed_infrastructure(s, year=2026))
    wh = fetch(empty_db, "SELECT id FROM ref.location WHERE code='GBG'")[0][0]
    transact(
        empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), OrsRoutingProvider(""), now=NOW)
    )
    execute(empty_db, 'UPDATE ref.market SET config=\'{"routing":{"allow_fallback":false}}\'')
    provider = OrsRoutingProvider(
        "test-only",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"distances": [[22]], "durations": [[1200]]})
        ),
    )
    upgraded = transact(empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), provider, now=NOW))
    assert upgraded.provider == "ors"
    assert upgraded.distance_km == Decimal(22)
    assert upgraded.duration_min == 20
    assert fetch(empty_db, "SELECT provider FROM plan.route_matrix")[0][0] == "ors"
