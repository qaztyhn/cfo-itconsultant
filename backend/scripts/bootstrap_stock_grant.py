"""Controlled Stock Admin grant; run from backend with python -m scripts.bootstrap_stock_grant."""

import argparse
import asyncio
import os

from sqlalchemy import func, select, text

from app.core.db import get_engine, get_sessionmaker
from app.deps import CurrentUser
from app.domain.models.ref import AppUser, Market, StockAdminGrant
from app.services.stock_scope_service import grant_admin


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True)
    parser.add_argument("--operator-id", required=True, type=int)
    parser.add_argument("--recipient-id", required=True, type=int)
    parser.add_argument("--capability", required=True, choices=("scope", "evidence"))
    parser.add_argument("--reason", required=True)
    parser.add_argument("--expected-grants", required=True, type=int)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if os.environ.get("STOCK_GRANT_SYSTEM_ADMIN_USER_ID") != str(args.operator_id):
        raise SystemExit("Operator does not match reviewed deployment delegation")
    if os.environ.get("STOCK_GRANT_AUTHORIZED_MARKET") != args.market:
        raise SystemExit("Market does not match reviewed Owner delegation")
    if not os.environ.get("STOCK_GRANT_OWNER_AUTHORIZATION_REF", "").strip():
        raise SystemExit("Owner authorization reference is required")
    if args.operator_id == args.recipient_id:
        raise SystemExit("Self grant is forbidden")
    async with get_sessionmaker()() as session:
        market = await session.scalar(select(Market).where(Market.code == args.market))
        operator = await session.get(AppUser, args.operator_id)
        recipient = await session.get(AppUser, args.recipient_id)
        if market is None or operator is None or recipient is None:
            raise SystemExit("Market, operator, and recipient must exist")
        if not operator.is_active or "admin" not in operator.roles:
            raise SystemExit("Operator must be an active Admin account")
        if not recipient.is_active or "admin" not in recipient.roles:
            raise SystemExit("Recipient must be an active Admin account")
        await session.execute(text("SELECT pg_advisory_xact_lock(:ns, :key)"), {"ns": 2026, "key": market.id})
        existing = await session.scalar(
            select(func.count()).select_from(StockAdminGrant).where(StockAdminGrant.market_id == market.id)
        )
        if existing != args.expected_grants:
            raise SystemExit("Market grant count changed; stop and review before retrying")
        if not args.execute:
            print("Preflight passed; no database changes. Re-run with --execute after review.")
            return
        actor = CurrentUser(
            id=operator.id, employee_id=operator.employee_id, roles=tuple(operator.roles),
            market=market.code, location_ids=(),
        )
        grant = await grant_admin(
            session, actor, user_id=recipient.id, capability=args.capability, reason_text=args.reason
        )
        await session.commit()
        print(f"Created grant {grant.id} for market {market.code}; verify audit before scope work.")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

