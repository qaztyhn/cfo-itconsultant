"""Standalone reference-data seed; full order/scenario generator remains separate."""

import asyncio
import os

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.seed.catalog import seed_catalog
from app.seed.fleet import seed_fleet
from app.seed.workforce import seed_workforce


async def run() -> None:
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    if not password.strip():
        raise ValueError("SEED_DEMO_PASSWORD is required")
    clock.init_from_settings(get_settings().app_now)
    try:
        async with get_sessionmaker()() as session, session.begin():
            await seed_workforce(session, password)
            await seed_fleet(session)
            await seed_catalog(session, now=clock.now())
    finally:
        await get_engine().dispose()


def main() -> int:
    try:
        asyncio.run(run())
    except Exception:
        print("Reference seed failed; check migrations, credentials and existing demo identities.")
        return 1
    print("Reference seed complete; full orders/scenario seed remains pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
