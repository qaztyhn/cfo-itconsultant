"""RoutingProvider dùng OpenRouteService (driving-hgv) — tính ma trận (kho, điểm giao) và chỉ đường
còn lại cho GPS (04 mục 3, 5.2 bước 9; US-INT-05). Engine KHÔNG gọi module này.

Owner: Dev 2 (luồng B) — M2.
"""

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import httpx

from app.providers.routing_fallback import estimate


class RoutingUnavailable(RuntimeError):
    """Safe provider failure without request coordinates, keys or response bodies."""


@dataclass(frozen=True)
class RouteEstimate:
    distance_km: Decimal
    duration_min: int
    provider: Literal["ors", "fallback"]


class OrsRoutingProvider:
    """One origin/destination matrix; units km/seconds per ORS Matrix API."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not 0 < timeout_seconds < math.inf:
            raise ValueError("Routing timeout must be finite and positive")
        self._key = api_key
        self._timeout = timeout_seconds
        self._transport = transport

    async def route(self, lat1: float, lon1: float, lat2: float, lon2: float) -> RouteEstimate:
        if not self._key.strip():
            raise RoutingUnavailable("Routing credentials unavailable")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.post(
                    "https://api.openrouteservice.org/v2/matrix/driving-hgv",
                    headers={"Authorization": self._key},
                    json={
                        "locations": [[lon1, lat1], [lon2, lat2]],
                        "sources": [0],
                        "destinations": [1],
                        "metrics": ["distance", "duration"],
                        "units": "km",
                    },
                )
                response.raise_for_status()
                body = response.json()
                distance, seconds = body["distances"][0][0], body["durations"][0][0]
                if any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
                    for v in (distance, seconds)
                ):
                    raise ValueError("Invalid metric")
                return RouteEstimate(
                    Decimal(str(distance)).quantize(Decimal("0.01")),
                    math.ceil(seconds / 60),
                    "ors",
                )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise RoutingUnavailable("Routing service unavailable") from None


async def route_with_fallback(
    provider: OrsRoutingProvider,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    allow_fallback: bool,
) -> RouteEstimate:
    """Use the documented fallback only when the market permits it."""
    for lat, lon in ((lat1, lon1), (lat2, lon2)):
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid route coordinates")
    try:
        return await provider.route(lat1, lon1, lat2, lon2)
    except RoutingUnavailable:
        if not allow_fallback:
            raise
    km, minutes = estimate(lat1, lon1, lat2, lon2)
    return RouteEstimate(Decimal(str(km)), minutes, "fallback")
