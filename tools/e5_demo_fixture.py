"""Prepare one synthetic, approved-order DELAY draft in a fresh disposable demo DB.

This intentionally reuses the PostgreSQL integration fixture. It does not
simulate the upstream risk event or send a customer message.
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core import clock
from app.core.security import hash_password
from app.services import notify_service
from tests.integration.conftest import fetch
from tests.integration.dev2_helpers import transact
from tests.integration.test_notify_backend import WINDOW, actor, prepare


async def set_demo_password(dsn: str, password: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "UPDATE ref.app_user SET password_hash=$1 WHERE email='user1@cfo.test'",
            hash_password(password),
        )
    finally:
        await conn.close()


def main() -> None:
    if (
        os.getenv("APP_ENV") != "test"
        or os.getenv("DEMO_DISPOSABLE") != "1"
        or os.getenv("COMPOSE_PROJECT_NAME") != "cfo-demo-e5"
        or os.getenv("APP_NOW") != "2026-11-09T11:00:00+01:00"
    ):
        raise SystemExit(
            "E5 fixture requires the isolated disposable project and fixed clock."
        )
    url = os.environ.get("DATABASE_URL", "")
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    port = os.environ.get("POSTGRES_PORT", "")
    if "@postgres:5432/cfo" not in url or not password or port != "5434":
        raise SystemExit(
            "E5 fixture requires the named local Compose database and demo password."
        )
    dsn = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:5432/cfo", "@127.0.0.1:5434/cfo"
    )
    if fetch(dsn, "SELECT to_regclass('ref.market')")[0][0] is None:
        prepare(dsn)
    elif (
        fetch(dsn, "SELECT order_no FROM ops.customer_order WHERE id=1")[0][0]
        != "ZZ-000001"
    ):
        raise SystemExit("E5 fixture found unrelated data; choose a new project.")
    if fetch(dsn, "SELECT count(*) FROM ops.notification")[0][0] != 0:
        raise SystemExit("E5 fixture already has notifications; choose a new project.")
    asyncio.run(set_demo_password(dsn, password))
    clock.init_from_settings(os.environ["APP_NOW"])
    draft_id = transact(
        dsn,
        lambda session: notify_service.create_delay_draft(
            1, {**WINDOW, "version": 1}, session=session, actor=actor()
        ),
    )
    print(
        f"E5 fixture: order_id=1 order_no=ZZ-000001 draft_id={draft_id} login=user1@cfo.test"
    )


if __name__ == "__main__":
    main()
