"""Run an implemented Dev 2 maintenance job explicitly, without enabling stub jobs.

Use the backend virtualenv. Requires DATABASE_URL; optional APP_NOW pins the clock.
This CLI does not implement /internal/tick or register periodic background jobs.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core import clock  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.logging import log_event  # noqa: E402
from app.jobs import gps_lost, gps_retention, outbox, stale_data  # noqa: E402

JOBS = {
    "gps-lost": gps_lost.run,
    "gps-retention": gps_retention.run,
    "stale-stock": stale_data.run,
    "outbox": outbox.run,
}


async def run(name: str) -> int:
    clock.init_from_settings(get_settings().app_now)
    try:
        return await JOBS[name]()
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=sorted(JOBS))
    args = parser.parse_args()
    try:
        count = asyncio.run(run(args.job))
    except Exception:
        log_event("scheduler", "maintenance_job_failed", level="error", job=args.job)
        return 1
    print(f"Maintenance job completed: {count} rows processed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
