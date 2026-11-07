from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from alembic import command
from app.core.config import MarketConfig
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


def _counting(calls: list[httpx.Request], ok: bool) -> OrsRoutingProvider:
    def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if ok:
            return httpx.Response(200, json={"distances": [[22]], "durations": [[1200]]})
        return httpx.Response(503)

    return OrsRoutingProvider("test-only", transport=httpx.MockTransport(response))


def test_US_INT_05_AC1_fallback_reused_only_until_retry_ttl_then_ors_replaces_it(empty_db: str) -> None:
    """Review PR #65: fallback không được dùng vô thời hạn khi ORS đã khả dụng (TTL mặc định 60 phút)."""
    command.upgrade(alembic_config(empty_db), "head")
    transact(empty_db, lambda s: seed_infrastructure(s, year=2026))
    wh = fetch(empty_db, "SELECT id FROM ref.location WHERE code='GBG'")[0][0]
    down: list[httpx.Request] = []
    first = transact(
        empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), _counting(down, False), now=NOW)
    )
    assert first.provider == "fallback" and len(down) >= 1

    up: list[httpx.Request] = []
    fresh = NOW + timedelta(minutes=59)
    reused = transact(
        empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), _counting(up, True), now=fresh)
    )
    assert reused.provider == "fallback" and up == []  # còn trong TTL: không gọi ORS

    stale = NOW + timedelta(minutes=61)
    upgraded = transact(
        empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), _counting(up, True), now=stale)
    )
    assert upgraded.provider == "ors" and len(up) == 1
    row = fetch(empty_db, "SELECT provider, computed_at FROM plan.route_matrix")[0]
    assert row[0] == "ors" and row[1] == stale
    later = NOW + timedelta(days=30)
    assert (
        transact(
            empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), _counting(up, True), now=later)
        ).provider
        == "ors"
    )
    assert len(up) == 1  # route ORS được dùng lại, không gọi thêm


def test_US_INT_05_AC1_stale_fallback_refreshed_when_ors_still_down(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    transact(empty_db, lambda s: seed_infrastructure(s, year=2026))
    wh = fetch(empty_db, "SELECT id FROM ref.location WHERE code='GBG'")[0][0]
    execute(empty_db, 'UPDATE ref.market SET config=\'{"routing":{"fallback_retry_min":10}}\'')
    calls: list[httpx.Request] = []
    provider = _counting(calls, False)
    transact(empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), provider, now=NOW))
    after_first = len(calls)
    at = NOW + timedelta(minutes=11)
    route = transact(empty_db, lambda s: ensure_route(s, wh, Decimal(59), Decimal(18), provider, now=at))
    assert route.provider == "fallback" and len(calls) > after_first  # ORS được thử lại
    row = fetch(empty_db, "SELECT provider, computed_at FROM plan.route_matrix")[0]
    assert row[0] == "fallback" and row[1] == at  # computed_at mới → lần thử kế tiếp bị giới hạn


@pytest.mark.parametrize("value", [0, -5])
def test_fallback_retry_min_must_be_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        MarketConfig.model_validate({"routing": {"fallback_retry_min": value}})
