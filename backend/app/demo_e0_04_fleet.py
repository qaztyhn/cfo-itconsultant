"""Load synthetic vehicle classifications from t26-r3-v1 in the disposable demo."""

import asyncio
import hashlib
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.domain.models.ref import AppUser, Location, Market, Vehicle


async def run(path: Path) -> int:
    settings = get_settings()
    raw = path.read_bytes()
    fixture = json.loads(raw)
    if (
        settings.app_env != "test"
        or settings.app_now != fixture["app_now"]
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or fixture["version"] != "t26-r3-v1"
    ):
        raise ValueError("Disposable demo fleet context required")
    masses = fixture["driver_feed"]["vehicle_mass_kg"]
    clock.init_from_settings(settings.app_now)
    try:
        async with get_sessionmaker()() as session, session.begin():
            admin = await session.get(AppUser, 2)
            vehicles = (
                await session.scalars(
                    select(Vehicle)
                    .join(Location, Location.id == Vehicle.home_warehouse_id)
                    .join(Market, Market.id == Location.market_id)
                    .where(Market.code == fixture["market"], Vehicle.code.in_(masses))
                    .order_by(Vehicle.id)
                    .with_for_update(of=Vehicle)
                )
            ).all()
            if (
                len(vehicles) != len(masses)
                or admin is None
                or not admin.is_active
                or "admin" not in admin.roles
            ):
                raise ValueError("Stored fleet does not match synthetic fixture")
            for vehicle in vehicles:
                mass = Decimal(masses[vehicle.code])
                if vehicle.regulation_561_scope == "in_scope" and vehicle.max_permissible_mass_kg == mass:
                    continue
                if vehicle.regulation_561_scope != "unknown" or vehicle.max_permissible_mass_kg is not None:
                    raise ValueError("Existing vehicle classification must not be overwritten")
                vehicle.max_permissible_mass_kg = mass
                vehicle.regulation_561_scope = "in_scope"
                await record_decision(
                    session,
                    Action.CONFIG_CHANGED,
                    "vehicle",
                    str(vehicle.id),
                    reason_text="T26 synthetic-only declared transport context",
                    snapshot={"fixture_sha256": hashlib.sha256(raw).hexdigest(), "legal_verified": False},
                    before={"max_permissible_mass_kg": None, "regulation_561_scope": "unknown"},
                    after={"max_permissible_mass_kg": str(mass), "regulation_561_scope": "in_scope"},
                    actor_user_id=admin.id,
                    actor_employee_id=admin.employee_id,
                    actor_role="admin",
                )
            return len(vehicles)
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    try:
        count = asyncio.run(run(Path(sys.argv[1])))
    except (IndexError, OSError, ValueError):
        raise SystemExit("BLOCKED: verify disposable fleet context and t26-r3-v1 fixture.") from None
    print(f"T26 synthetic fleet classifications: {count}")
