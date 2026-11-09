"""Read-only stock diagnosis for a disposable Swedish demo.

Usage (in the isolated Compose container):
  python -m app.demo_stock_preflight --external-ref SE-2026-000149

Never seeds, creates/approves scope, or writes ops.stock_snapshot.
"""

import argparse
import asyncio
import json
import os
from dataclasses import asdict

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.services.planning_stock_preflight import diagnose

DEMO_NOW = "2026-11-04T10:05:00+01:00"


async def run(external_ref: str) -> int:
    settings = get_settings()
    if (
        settings.app_env != "test"
        or settings.app_now != DEMO_NOW
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or not external_ref.startswith("SE-2026-")
    ):
        print('{"status":"BLOCKED","blockers":["DISPOSABLE_DEMO_CONTEXT_REQUIRED"]}')
        return 2
    clock.init_from_settings(settings.app_now)
    try:
        async with get_sessionmaker()() as session:
            outcome = await diagnose(
                session, market_code="SE", order_external_ref=external_ref, now=clock.now()
            )
        payload = asdict(outcome)
        if outcome.accepted_as_of is not None:
            payload["accepted_as_of"] = outcome.accepted_as_of.isoformat()
        # Avoid forwarding arbitrary failed-run exception text that may contain PII or secrets.
        payload["latest_sync_error"] = (
            outcome.latest_sync_error
            if outcome.latest_sync_error
            in {
                "STOCK_SCOPE_NOT_CONFIGURED",
                "STOCK_ROWS_MISSING",
                "STOCK_NORMALIZATION_REJECTED",
                "STOCK_BATCH_REJECTED",
                "BAD_DATE",
            }
            else None
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if outcome.status == "PASS" else 2
    except (ValueError, RuntimeError):
        print('{"status":"BLOCKED","blockers":["SCOPED_DATA_UNAVAILABLE"]}')
        return 2
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-ref", required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.external_ref))


if __name__ == "__main__":
    raise SystemExit(main())
