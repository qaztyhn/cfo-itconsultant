"""Explicit, synthetic-only Source -> CFO reference synchronization for demo.

Uses the already merged T07 adapter/lease/checkpoints and never assigns routing,
creates an undecided order, approves a plan or writes to POS/WMS. Fails closed on
partial sync; the scheduler and live HTTP sync-now are not simulated here.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine
from app.services.ingest_service import sync_entity

DEMO_CLOCKS = {"2026-11-04T10:05:00+01:00", "2026-12-01T10:05:00+01:00"}
ENTITIES = ("customers", "products", "inbound", "fleet", "orders", "stock")


async def run(entity: str) -> int:
    settings = get_settings()
    if (
        settings.app_env != "test"
        or settings.app_now not in DEMO_CLOCKS
        or os.environ.get("DEMO_DISPOSABLE") != "1"
    ):
        print(
            "BLOCKED: demo ingestion requires disposable APP_ENV=test and approved APP_NOW."
        )
        return 2
    clock.init_from_settings(settings.app_now)
    try:
        result = await sync_entity("SE", entity)
        if result.status != "ok":
            print(
                f"BLOCKED: {entity} feed status={result.status}; inspect scoped sync-run diagnostics."
            )
            return 2
        print(
            f"PASS: {entity} feed finished (rows_ok={result.rows_ok}); no routing or approval inferred."
        )
        return 0
    except Exception:
        # Do not print source credentials, raw records, DSN or customer PII.
        print(
            f"BLOCKED: {entity} feed unavailable/invalid; no checkpoint success claimed."
        )
        return 2
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entity", choices=ENTITIES)
    args = parser.parse_args()
    return asyncio.run(run(args.entity))


if __name__ == "__main__":
    raise SystemExit(main())
