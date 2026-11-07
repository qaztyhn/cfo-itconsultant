"""Prepare route_matrix for an existing CFO order; no planning or approval side effects.

Use the backend venv. DATABASE_URL is required; ORS_API_KEY and APP_NOW are optional.
--offline avoids ORS requests and still respects the market's allow_fallback policy.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core import clock  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine, get_sessionmaker  # noqa: E402
from app.providers.routing_ors import OrsRoutingProvider  # noqa: E402
from app.services.routing_service import prepare_order_routes  # noqa: E402


async def run(order_id: int, *, offline: bool) -> tuple[int, int]:
    settings = get_settings()
    clock.init_from_settings(settings.app_now)
    provider = OrsRoutingProvider("" if offline else settings.ors_api_key or "")
    try:
        async with get_sessionmaker()() as session, session.begin():
            routes = await prepare_order_routes(session, order_id, provider, now=clock.now())
        return (
            sum(route.provider == "ors" for route in routes.values()),
            sum(route.provider == "fallback" for route in routes.values()),
        )
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", type=int, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        ors, fallback = asyncio.run(run(args.order_id, offline=args.offline))
    except Exception:
        print("Route preparation failed; check order, warehouse data, database and routing configuration.")
        return 1
    print(f"Route pairs prepared: {ors + fallback} (ORS {ors}, fallback {fallback}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
