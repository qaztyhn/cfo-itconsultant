"""Deterministic CFO demo fixture preparation (08 sections 5, 6.3, ASM-009).

The make seed command must not claim a complete demo until separate source/WMS
publication, ingestion, D7 proof contract and real E2E flows are verified.
Use --export-only to create the identical cross-service input manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, datetime
from pathlib import Path

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.seed.catalog import seed_catalog
from app.seed.driver_shifts import seed_driver_shifts
from app.seed.fleet import seed_fleet
from app.seed.roster import seed_roster
from app.seed.scenarios import (
    APP_NOW,
    RANDOM_SEED,
    DemoFixture,
    canonical_json,
    digest,
    generate,
    validate,
)
from app.seed.workforce import seed_workforce


def write_manifest(path: Path, fixture: DemoFixture) -> bool:
    """Create once; identical rerun is harmless, changed/colliding file is refused.

    Never replace a prior manifest or an operational data file. Exclusive create
    prevents a concurrent seed writer from silently overwriting another run.
    """
    validate(fixture)
    payload = canonical_json(fixture).encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("Demo manifest collision: existing file differs")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError("Demo manifest collision during concurrent write") from None
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
    return True


async def seed_local_reference(fixture: DemoFixture) -> tuple[int, int]:
    """Add synthetic reference and manager-attributed schedules in ONE transaction."""
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    if not password.strip():
        raise ValueError("SEED_DEMO_PASSWORD is required for reference accounts")
    configured_now = get_settings().app_now
    if configured_now is None or datetime.fromisoformat(configured_now) != datetime.fromisoformat(APP_NOW):
        raise ValueError("Set APP_NOW to the approved 2026-11-04 10:05 Stockholm demo clock")
    clock.init_from_settings(configured_now)
    try:
        async with get_sessionmaker()() as session, session.begin():
            await seed_workforce(session, password)
            await seed_fleet(session)
            await seed_catalog(session, now=clock.now())
            warehouse = await seed_roster(
                session, start=date(2026, 11, 4), end=date(2026, 11, 13), now=clock.now()
            )
            drivers = await seed_driver_shifts(
                session, shifts=fixture["driver_shifts"], now=clock.now()
            )
            return warehouse, drivers
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("demo-fixtures.json"))
    parser.add_argument(
        "--export-only", action="store_true",
        help="Only export synthetic source inputs; do not connect to CFO DB",
    )
    args = parser.parse_args()
    try:
        fixture = generate(RANDOM_SEED)
        validate(fixture)
        # Collision must be detected BEFORE changing any local DB records.
        if args.manifest.exists() and args.manifest.read_bytes() != canonical_json(fixture).encode("utf-8"):
            raise ValueError("Manifest collision: refusing any database changes")
        warehouse, drivers = (0, 0)
        if not args.export_only:
            warehouse, drivers = asyncio.run(seed_local_reference(fixture))
        created = write_manifest(args.manifest, fixture)
    except Exception:
        # Never print credentials, full exception (may include DSNs) or customer details.
        print("CFO demo preparation failed; no existing operational records were overwritten.")
        return 1
    print(
        f"Demo manifest {'created' if created else 'unchanged'} "
        f"(seed {RANDOM_SEED}, SHA256 {digest(fixture)}); "
        f"{warehouse} warehouse and {drivers} driver shifts added."
    )
    if args.export_only:
        return 0
    print(
        "NOT COMPLETE: run source_system/app/seed_demo.py with --manifest inside "
        "the source environment, ingest via approved adapters, then execute E2E "
        "flows. D7 proof and documented golden blockers remain unverified."
    )
    # make seed must never be mistaken for successful E2E/approved outcomes.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
