"""Minimal M0 login fixtures, not the full M1 scenario seed. Owner: Dev 2.

Add missing demo records only. Existing accounts, passwords and assignments are
never reset; a conflicting identity aborts the entire transaction.
"""

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import to_async_url
from app.core.security import hash_password

ACCOUNTS = (
    ("dispatcher", "DISPATCHER", "DC", "dispatch_center"),
    ("admin", "IT_INTEGRATION", "HQ", "head_office"),
    ("sales", "SALES_RETAIL", "ST-001", "store"),
    ("owner", "BUSINESS_OWNER", "HQ", "head_office"),
    ("projectlead", "PROJECT_LEAD", "HQ", "head_office"),
)


async def seed_accounts(session: AsyncSession, password: str) -> None:
    """Caller owns the transaction. Roles/scopes come from migration 0008."""
    if not password.strip():
        raise ValueError("SEED_DEMO_PASSWORD is required")
    await session.execute(text("SELECT pg_advisory_xact_lock(20261104)"))
    market = (await session.execute(text("SELECT id FROM ref.market WHERE code='SE'"))).scalar_one()
    for name, position, location_code, location_type in ACCOUNTS:
        params = {"market": market, "code": location_code, "type": location_type}
        await session.execute(
            text("""INSERT INTO ref.location (market_id, type, code, name, lat, lon)
                    VALUES (:market, CAST(:type AS ref.location_type), :code, :code, 57.7089, 11.9746)
                    ON CONFLICT (market_id, code) DO NOTHING"""),
            params,
        )
        location = (
            await session.execute(
                text("SELECT id FROM ref.location WHERE market_id=:market AND code=:code AND type=:type"),
                params,
            )
        ).scalar_one()
        roles = (
            await session.execute(
                text("SELECT default_roles, default_kpi_scopes FROM hr.position WHERE code=:position"),
                {"position": position},
            )
        ).one()
        employee_no = "DEMO-" + name.upper()
        employee_params = {
            "market": market,
            "number": employee_no,
            "position": position,
            "name": name,
        }
        await session.execute(
            text("""
            INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date)
            VALUES (:market, :number, 'Demo', :name, :position, '2026-01-01')
            ON CONFLICT (market_id, employee_no) DO NOTHING
        """),
            employee_params,
        )
        employee = (
            await session.execute(
                text("""
            SELECT id FROM hr.employee WHERE market_id=:market AND employee_no=:number
              AND position_code=:position
        """),
                employee_params,
            )
        ).scalar_one()
        assignments = (
            (
                await session.execute(
                    text("""
            SELECT location_id FROM hr.employee_assignment WHERE employee_id=:employee AND end_date IS NULL
        """),
                    {"employee": employee},
                )
            )
            .scalars()
            .all()
        )
        if assignments and assignments != [location]:
            raise ValueError("Demo employee has a different active assignment")
        if not assignments:
            await session.execute(
                text("""
                INSERT INTO hr.employee_assignment (employee_id, location_id, start_date)
                VALUES (:employee, :location, '2026-01-01')
            """),
                {"employee": employee, "location": location},
            )
        email = name + "@cfo.demo"
        existing = (
            await session.execute(
                text("SELECT employee_id FROM ref.app_user WHERE lower(email)=:email"),
                {"email": email},
            )
        ).all()
        if existing:
            if len(existing) != 1 or existing[0].employee_id != employee:
                raise ValueError("Demo email belongs to a different identity")
            continue
        await session.execute(
            text("""
            INSERT INTO ref.app_user (employee_id, email, password_hash, roles, kpi_scopes)
            VALUES (:employee, :email, :hash, CAST(:roles AS ref.user_role[]), CAST(:scopes AS text[]))
        """),
            {
                "employee": employee,
                "email": email,
                "hash": hash_password(password),
                "roles": list(roles.default_roles),
                "scopes": list(roles.default_kpi_scopes),
            },
        )


async def run() -> None:
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    if not password.strip():
        raise ValueError("SEED_DEMO_PASSWORD is required")
    engine = create_async_engine(to_async_url(get_settings().database_url), hide_parameters=True)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            await seed_accounts(session, password)
    finally:
        await engine.dispose()


def main() -> int:
    try:
        asyncio.run(run())
    except Exception:
        # DB exceptions may contain credentials or bound password hashes.
        print("M0 seed failed; check migrations, configuration and demo identity conflicts.")
        return 1
    print("M0 account seed complete; full M1 scenario seed is not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
