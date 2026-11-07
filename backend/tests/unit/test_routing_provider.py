import json
import secrets
from decimal import Decimal

import httpx
import pytest

from app.providers.routing_fallback import estimate, haversine_km
from app.providers.routing_ors import (
    OrsRoutingProvider,
    RoutingUnavailable,
    route_with_fallback,
)


async def test_US_INT_05_AC1_hgv_matrix_uses_lon_lat_and_rounds_minutes_up() -> None:
    key = secrets.token_urlsafe(24)

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/matrix/driving-hgv"
        assert request.headers["Authorization"] == key
        assert json.loads(request.content)["locations"] == [[12, 57], [18, 59]]
        return httpx.Response(200, json={"distances": [[42.125]], "durations": [[120.1]]})

    result = await route_with_fallback(
        OrsRoutingProvider(key, transport=httpx.MockTransport(respond)),
        57,
        12,
        59,
        18,
        allow_fallback=True,
    )
    assert (result.distance_km, result.duration_min, result.provider) == (
        Decimal("42.12"),
        3,
        "ors",
    )


@pytest.mark.parametrize("status", [401, 429, 500, 503, 302])
async def test_US_INT_05_AC2_fallback_on_failure_and_disabled_policy(
    status: int,
) -> None:
    key = secrets.token_urlsafe(24)
    provider = OrsRoutingProvider(
        key, transport=httpx.MockTransport(lambda _: httpx.Response(status, text=key))
    )
    result = await route_with_fallback(provider, 57, 12, 59, 18, allow_fallback=True)
    assert result.provider == "fallback"
    assert float(result.distance_km) == estimate(57, 12, 59, 18)[0]
    with pytest.raises(RoutingUnavailable) as error:
        await route_with_fallback(provider, 57, 12, 59, 18, allow_fallback=False)
    assert key not in str(error.value)


@pytest.mark.parametrize("metric", [None, -1, "x", True, float("inf")])
async def test_bad_ors_response_never_becomes_valid_route(metric: object) -> None:
    payload = json.dumps({"distances": [[metric]], "durations": [[20]]})
    provider = OrsRoutingProvider(
        secrets.token_urlsafe(24),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload)),
    )
    with pytest.raises(RoutingUnavailable):
        await provider.route(57, 12, 59, 18)


async def test_timeout_and_missing_key_fallback() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private", request=request)

    for provider in (
        OrsRoutingProvider(""),
        OrsRoutingProvider(secrets.token_urlsafe(24), transport=httpx.MockTransport(timeout)),
    ):
        assert (await route_with_fallback(provider, 0, 0, 0, 0, allow_fallback=True)).duration_min == 0


def test_antipodal_fallback_is_finite() -> None:
    assert 20000 < haversine_km(90, 0, -90, 180) < 20100
