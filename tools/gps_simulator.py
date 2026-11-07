"""US-GPS-01 AC4: send a synthetic route as a driver, never log coordinates/tokens.

Run with the backend venv: python tools/gps_simulator.py --help.
Route JSON is an array of {lat,lon} objects; token comes from CFO_DRIVER_TOKEN.
The API remains responsible for driver ownership, on-road state and GPS consent.
Owner: Dev 2 (M6).
"""

import argparse
import asyncio
import json
import math
import os
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core import clock  # noqa: E402


def read_route(path: Path) -> list[tuple[float, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Route must be a nonempty array")
    points = []
    for point in data:
        if not isinstance(point, dict):
            raise ValueError("Invalid route point")
        lat, lon = point.get("lat"), point.get("lon")
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lat, lon)
        ):
            raise ValueError("Invalid coordinates")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Coordinates out of bounds")
        points.append((float(lat), float(lon)))
    return points


async def simulate(
    base_url: str,
    trip_id: int,
    token: str,
    points: Sequence[tuple[float, float]],
    *,
    started_at: datetime,
    interval_seconds: int = 60,
    transport: httpx.AsyncBaseTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    url = httpx.URL(base_url)
    if url.scheme not in ("http", "https") or not url.host or url.userinfo or url.query or url.fragment:
        raise ValueError("Invalid API base URL")
    if not token.strip() or trip_id <= 0 or not 60 <= interval_seconds <= 120 or started_at.tzinfo is None:
        raise ValueError("Invalid simulator configuration")
    if not points or any(not math.isfinite(v) for point in points for v in point):
        raise ValueError("Invalid route")
    if any(not -90 <= lat <= 90 or not -180 <= lon <= 180 for lat, lon in points):
        raise ValueError("Coordinates out of bounds")
    async with httpx.AsyncClient(timeout=10, transport=transport, follow_redirects=False) as client:
        for index, (lat, lon) in enumerate(points):
            if index:
                await sleep(interval_seconds)
            response = await client.post(
                str(url).rstrip("/") + f"/trips/{trip_id}/positions",
                headers={"Authorization": "Bearer " + token},
                json={
                    "positions": [
                        {
                            "lat": lat,
                            "lon": lon,
                            "source": "simulator",
                            "recorded_at": (
                                started_at + timedelta(seconds=index * interval_seconds)
                            ).isoformat(),
                        }
                    ]
                },
            )
            response.raise_for_status()
    return len(points)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send synthetic GPS points using a driver token")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--trip-id", required=True, type=int)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--interval-seconds", type=int, choices=range(60, 121), default=60)
    args = parser.parse_args()
    try:
        clock.init_from_settings(os.environ.get("APP_NOW"))
        count = asyncio.run(
            simulate(
                args.base_url,
                args.trip_id,
                os.environ.get("CFO_DRIVER_TOKEN", ""),
                read_route(args.route),
                started_at=clock.now(),
                interval_seconds=args.interval_seconds,
            )
        )
    except (ValueError, OSError, httpx.HTTPError, httpx.InvalidURL):
        print("GPS simulation failed; check route, credentials, API availability and trip/GPS state.")
        return 1
    except KeyboardInterrupt:
        print("GPS simulation stopped.")
        return 130
    print(f"GPS simulation complete: {count} points accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
