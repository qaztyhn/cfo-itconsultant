"""Prepare three E0-04 route pairs via the approved offline fallback provider."""

import asyncio
import os

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.providers.routing_ors import OrsRoutingProvider
from app.services.routing_service import prepare_order_routes


async def run(order_id: int) -> tuple[int, int]:
    settings = get_settings()
    if (
        settings.app_env != "test"
        or settings.app_now != "2026-12-01T10:05:00+01:00"
        or os.environ.get("DEMO_DISPOSABLE") != "1"
    ):
        raise ValueError("Disposable E0-04 clock required")
    clock.init_from_settings(settings.app_now)
    try:
        async with get_sessionmaker()() as session, session.begin():
            routes = await prepare_order_routes(
                session, order_id, OrsRoutingProvider(""), now=clock.now()
            )
        return len(routes), sum(
            route.provider == "fallback" for route in routes.values()
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", type=int, required=True)
    args = parser.parse_args()
    try:
        count, fallback = asyncio.run(run(args.order_id))
    except Exception:
        print(
            "BLOCKED: E0-04 route preparation failed; check order and approved fallback policy."
        )
        raise SystemExit(2) from None
    print(f"PASS: route pairs={count}; approved fallback estimates={fallback}.")
