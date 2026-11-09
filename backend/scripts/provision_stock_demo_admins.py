"""Provision two dedicated SE demo Admin identities, without Stock Admin grants."""

import argparse
import asyncio
import os

from sqlalchemy import text

from app.core.db import get_engine, get_sessionmaker
from app.seed.m0_accounts import seed_accounts

DEMO_ACCOUNTS = (
    ("stockoperator", "IT_INTEGRATION", "HQ", "head_office"),
    ("stockapprover", "IT_INTEGRATION", "HQ", "head_office"),
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if os.environ.get("DEMO_DISPOSABLE") != "1":
        raise SystemExit("Disposable demo marker is required")
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    if not password.strip():
        raise SystemExit("SEED_DEMO_PASSWORD is required")
    if not args.execute:
        print("Would provision dedicated SE stock operator and approver accounts; no changes made.")
        return
    async with get_sessionmaker()() as session, session.begin():
        await seed_accounts(session, password, accounts=DEMO_ACCOUNTS)
        rows = (
            await session.execute(
                text("""SELECT u.id, e.employee_no FROM ref.app_user u
                         JOIN hr.employee e ON e.id = u.employee_id
                         JOIN ref.market m ON m.id = e.market_id
                         WHERE m.code = 'SE' AND e.employee_no IN
                           ('DEMO-STOCKOPERATOR', 'DEMO-STOCKAPPROVER')
                         ORDER BY e.employee_no""")
            )
        ).all()
        if len(rows) != 2:
            raise SystemExit("Dedicated identity verification failed; transaction rolled back")
        for row in rows:
            print(f"{row.employee_no}: app_user.id={row.id}; no stock grant created")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
