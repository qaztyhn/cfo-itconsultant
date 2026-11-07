import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import httpx

from tools.gps_simulator import read_route, simulate


class SimulatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_US_GPS_01_AC4_payload_interval_and_driver_authorization(self):
        requests, sleeps = [], []

        def receive(request):
            requests.append(request)
            return httpx.Response(200, json={})

        async def sleep(seconds):
            sleeps.append(seconds)

        count = await simulate(
            "http://api.test/api/v1",
            930,
            "synthetic-test-token",
            [(57.7, 11.9), (57.8, 12.0)],
            started_at=datetime(2026, 11, 4, tzinfo=UTC),
            interval_seconds=120,
            transport=httpx.MockTransport(receive),
            sleep=sleep,
        )
        self.assertEqual(count, 2)
        self.assertEqual(sleeps, [120])
        self.assertEqual(str(requests[0].url), "http://api.test/api/v1/trips/930/positions")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer synthetic-test-token")
        self.assertEqual(
            json.loads(requests[1].content),
            {
                "positions": [
                    {
                        "lat": 57.8,
                        "lon": 12.0,
                        "source": "simulator",
                        "recorded_at": "2026-11-04T00:02:00+00:00",
                    }
                ]
            },
        )

    async def test_denial_stops_without_replaying_or_logging_position(self):
        requests = []

        def receive(request):
            requests.append(request)
            return httpx.Response(403)

        with self.assertRaises(httpx.HTTPStatusError):
            await simulate(
                "http://api.test/api/v1",
                930,
                "synthetic-test-token",
                [(57.7, 11.9)],
                started_at=datetime(2026, 11, 4, tzinfo=UTC),
                transport=httpx.MockTransport(receive),
            )
        self.assertEqual(len(requests), 1)

    def test_route_rejects_invalid_or_nonfinite_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            for data in (
                [],
                [{"lat": True, "lon": 12}],
                [{"lat": 91, "lon": 12}],
                [{"lat": float("nan"), "lon": 12}],
                [{"lon": 12}],
            ):
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_route(path)
