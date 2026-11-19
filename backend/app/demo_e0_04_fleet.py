"""Load one explicit synthetic fleet classification into a disposable demo only.

The reviewed offline D7 fixture supplies mass, context and scope independently
of payload/type. This is a synthetic planning input, never legal certification.
"""

import asyncio
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.domain.models.ref import AppUser, Location, Vehicle

FIXTURE = Path("/srv/e0_04_d7/vehicles.json")


async def run() -> int:
    settings = get_settings()
    if (
        settings.app_env != "test"
        or settings.app_now != "2026-12-01T10:05:00+01:00"
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or os.environ.get("DEMO_D7_FIXTURE_DIR") != str(FIXTURE.parent)
    ):
        raise ValueError("Disposable E0-04 fleet context required")
    raw = FIXTURE.read_bytes()
    document = json.loads(raw)
    rows = [r for r in document["records"] if r["vehicle_code"] == "STO-12-04"]
    if document["source"] != "synthetic_demo" or len(rows) != 1:
        raise ValueError("Synthetic fleet record missing")
    item = rows[0]
    context = item["transport_context"]
    if (
        item["market"] != "SE"
        or item["warehouse_code"] != "STO"
        or item["required_licence"] != "C"
        or item["regulation_561_scope"] != "in_scope"
        or item["scope_evidence"] != "synthetic_checked_context"
        or context
        != {
            "country": "SE",
            "operation": "domestic_goods",
            "trailer_attached": False,
            "trailer_max_permissible_mass_kg": None,
            "exception_claim": None,
        }
    ):
        raise ValueError("Synthetic transport context is not the reviewed E0-04 case")
    clock.init_from_settings(settings.app_now)
    try:
        async with get_sessionmaker()() as session, session.begin():
            warehouse = await session.scalar(
                select(Location).where(Location.code == "STO", Location.type == "warehouse")
            )
            vehicle = await session.scalar(
                select(Vehicle).where(Vehicle.code == "STO-12-04").with_for_update()
            )
            admin = await session.get(AppUser, 2)
            if (
                warehouse is None
                or vehicle is None
                or admin is None
                or not admin.is_active
                or "admin" not in admin.roles
                or vehicle.home_warehouse_id != warehouse.id
                or vehicle.required_licence != item["required_licence"]
                or vehicle.capacity_kg != Decimal(item["capacity_kg"])
            ):
                raise ValueError("Stored vehicle does not match synthetic fixture")
            mass = Decimal(item["max_permissible_mass_kg"])
            if vehicle.regulation_561_scope == "in_scope" and vehicle.max_permissible_mass_kg == mass:
                return vehicle.id
            if vehicle.regulation_561_scope != "unknown" or vehicle.max_permissible_mass_kg is not None:
                raise ValueError("Existing vehicle classification must not be overwritten")
            vehicle.max_permissible_mass_kg = mass
            vehicle.regulation_561_scope = "in_scope"
            await record_decision(
                session,
                Action.CONFIG_CHANGED,
                "vehicle",
                str(vehicle.id),
                reason_text="E0-04 synthetic-only declared transport context",
                snapshot={
                    "fixture_sha256": hashlib.sha256(raw).hexdigest(),
                    "legal_verified": False,
                },
                before={
                    "max_permissible_mass_kg": None,
                    "regulation_561_scope": "unknown",
                },
                after={
                    "max_permissible_mass_kg": str(mass),
                    "regulation_561_scope": "in_scope",
                },
                actor_user_id=admin.id,
                actor_employee_id=admin.employee_id,
                actor_role="admin",
            )
            return vehicle.id
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    try:
        vehicle_id = asyncio.run(run())
    except Exception:
        print("BLOCKED: E0-04 synthetic vehicle classification failed; unknown scope remains blocked.")
        raise SystemExit(2) from None
    print(f"PASS: STO-12-04 synthetic classification loaded; vehicle_id={vehicle_id}.")
