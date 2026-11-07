"""Demo fleet from 08 section 5.3; does not create trip execution or reservation state."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ref import HandlingGroup, Location, Market, Vehicle

FLEET: tuple[tuple[str, str, int, int, str, list[str]], ...] = (
    ("GBG-03-02", "GBG", 3500, 10, "B", []),
    ("GBG-12-03", "GBG", 6000, 40, "C", []),
    ("STO-12-04", "STO", 6000, 40, "C", []),
    ("MLM-12-02", "MLM", 6000, 40, "C", []),
    ("GBG-18-01", "GBG", 10000, 50, "C", []),
    ("MLM-18-01", "MLM", 10000, 50, "C", []),
    ("GBG-26-01", "GBG", 16000, 65, "CE", []),
    ("STO-CR-01", "STO", 8000, 35, "C", ["crane"]),
    ("MLM-DUMP-01", "MLM", 12000, 12, "C", ["dump"]),
)


async def seed_fleet(session: AsyncSession) -> None:
    locations = {
        v.code: v.id
        for v in (
            await session.scalars(
                select(Location)
                .join(Market, Market.id == Location.market_id)
                .where(Market.code == "SE", Location.type == "warehouse")
            )
        ).all()
    }
    n4 = (await session.scalars(select(HandlingGroup.id).where(HandlingGroup.code == "N4"))).one()
    for index, (code, warehouse, kg, m3, licence, capabilities) in enumerate(FLEET):
        existing = (await session.scalars(select(Vehicle).where(Vehicle.code == code))).one_or_none()
        if existing is not None:
            if existing.home_warehouse_id != locations[warehouse]:
                raise ValueError("Conflicting demo vehicle identity")
            continue
        session.add(
            Vehicle(
                home_warehouse_id=locations[warehouse],
                code=code,
                plate=f"DEMO{index:03d}",
                name=code,
                capacity_kg=Decimal(kg),
                capacity_m3=Decimal(m3),
                required_licence=licence,
                capabilities=capabilities,
                allowed_group_ids=[n4] if "dump" in capabilities else [],
            )
        )
