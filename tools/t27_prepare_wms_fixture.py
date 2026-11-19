"""Build E1 native-SKU WMS fixture from the ACTUAL proposed E0-04 plan.

Used only after the browser has clicked Sales Sync + Check feasibility.
No plan, ACK, stock balance, or approval is invented by this helper.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import dotenv_values

from tools.e1_demo_accept import fixture, scenario

CLOCK = "2026-12-01T10:05:00+01:00"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or os.environ.get("APP_NOW") != CLOCK
    ):
        parser.error("The reviewed disposable E0-04 clock and test gates are required")
    database = data.get("DATABASE_URL", "")
    if not isinstance(database, str) or "@postgres:5432/cfo" not in database:
        parser.error("Private E0-04 Compose database URL required")
    # Same disposable database, host access only. Never rewrite any stock.
    os.environ["DATABASE_URL"] = database.replace("@postgres:5432/", "@127.0.0.1:5432/")
    actual = asyncio.run(scenario())
    if (actual["order_status"], actual["plan_status"]) != ("PLANNED", "proposed"):
        parser.error("Browser must have left the plan proposed")
    content = fixture(actual)  # Owner-reviewed, exact SKU and source-version matching E1.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.is_symlink() or args.output.exists():
        parser.error("Use a new private synthetic WMS fixture path")
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(content, stream, indent=2)
    print(f"E1 fixture PASS: order_id={actual['order_id']} plan_id={actual['plan_id']} proposed; synthetic only")


if __name__ == "__main__":
    main()
