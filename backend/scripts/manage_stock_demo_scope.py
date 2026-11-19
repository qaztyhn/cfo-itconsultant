"""Author or independently approve a disposable SE stock scope through governance services."""

import argparse
import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_engine, get_sessionmaker
from app.deps import CurrentUser
from app.domain.models.hr import Employee
from app.domain.models.ref import AppUser, Location, Market, ProductSE
from app.services.stock_scope_service import approve_scope, create_scope
from scripts._stock_demo_clock import require_current_demo_clock


async def _actor(session: AsyncSession, user_id: int, market: Market) -> CurrentUser:
    user = await session.get(AppUser, user_id)
    employee = await session.get(Employee, user.employee_id) if user and user.employee_id else None
    if (
        user is None
        or not user.is_active
        or "admin" not in user.roles
        or employee is None
        or employee.market_id != market.id
        or employee.status != "active"
    ):
        raise SystemExit("Actor must be an active Admin in the requested market")
    return CurrentUser(
        id=user.id,
        employee_id=user.employee_id,
        roles=tuple(user.roles),
        market=market.code,
        location_ids=(),
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True)
    parser.add_argument("--actor-id", required=True, type=int)
    parser.add_argument("--execute", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("--sku", action="append", required=True)
    create.add_argument("--warehouse-id", action="append", required=True, type=int)
    create.add_argument("--reason", required=True)
    approve = sub.add_parser("approve")
    approve.add_argument("--scope-id", required=True, type=int)
    args = parser.parse_args()
    if os.environ.get("DEMO_DISPOSABLE") != "1" or args.market != "SE":
        raise SystemExit("This command is limited to disposable SE")
    async with get_sessionmaker()() as session:
        await require_current_demo_clock(session)
        market = await session.scalar(select(Market).where(Market.code == args.market))
        if market is None:
            raise SystemExit("Market not found")
        actor = await _actor(session, args.actor_id, market)
        if args.action == "create":
            skus = sorted(set(args.sku))
            warehouses = sorted(set(args.warehouse_id))
            products = (await session.scalars(select(ProductSE).where(ProductSE.local_sku.in_(skus)))).all()
            locations = (await session.scalars(select(Location).where(Location.id.in_(warehouses)))).all()
            if len(products) != len(skus) or any(
                p.mapping_status != "confirmed" or p.global_product_id is None for p in products
            ):
                raise SystemExit("Every scoped SKU needs a confirmed global mapping")
            if len(locations) != len(warehouses) or any(
                w.market_id != market.id or w.type != "warehouse" or not w.is_active for w in locations
            ):
                raise SystemExit("Every scope location must be an active market warehouse")
            if not args.execute:
                print(f"Preflight passed: {len(skus)} SKUs x {len(warehouses)} warehouses; no write")
                return
            row = await create_scope(
                session, actor, skus=skus, warehouse_ids=warehouses, reason_text=args.reason
            )
        else:
            if not args.execute:
                print("Approval preflight only; no write. Review draft, author and expected coverage.")
                return
            row = await approve_scope(session, actor, args.scope_id)
        await session.commit()
        print(
            f"Scope id={row.id} version={row.version} status={row.status} effective_from={row.effective_from}"
        )
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
