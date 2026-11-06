"""Model ref/hr dùng được qua ORM trên DB đã migrate.

Kiểm identity, mảng enum, tstzrange và updated_at do trigger.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.domain.models.hr import Employee, EmployeeAssignment
from app.domain.models.ref import AppUser, Location, Market, Vehicle, VehicleAvailability
from tests.integration.conftest import alembic_config, async_url

pytestmark = pytest.mark.integration


@pytest.fixture
def head_db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    yield empty_db


def test_orm_round_trip_ref_hr(head_db: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_url(head_db), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session, session.begin():
                se = (await session.execute(select(Market).where(Market.code == "SE"))).scalar_one()
                wh = Location(
                    market_id=se.id, type="warehouse", code="WH-T", name="Test DC",
                    lat=Decimal("59.32930"), lon=Decimal("18.06860"), loading_cutoff_time=time(15, 0),
                )  # fmt: skip
                session.add(wh)
                await session.flush()
                emp = Employee(
                    market_id=se.id, employee_no="T1", first_name="Test", last_name="User",
                    position_code="DISPATCHER", hire_date=date(2026, 1, 1),
                )  # fmt: skip
                session.add(emp)
                await session.flush()
                session.add_all(
                    [
                        EmployeeAssignment(
                            employee_id=emp.id, location_id=wh.id, start_date=date(2026, 1, 1)
                        ),
                        AppUser(
                            employee_id=emp.id, email="t1@cfo.test", password_hash="not-a-real-hash",
                            roles=["dispatcher"], kpi_scopes=["ops"],
                        ),  # fmt: skip
                    ]
                )
                vehicle = Vehicle(
                    home_warehouse_id=wh.id, code="T-01", plate="TST001", name="Truck",
                    capacity_kg=Decimal("8000"), capacity_m3=Decimal("30"), required_licence="C",
                    capabilities=["crane"],
                )  # fmt: skip
                session.add(vehicle)
                await session.flush()
                window = Range(datetime(2026, 11, 10, 8, tzinfo=UTC), datetime(2026, 11, 10, 12, tzinfo=UTC))
                session.add(VehicleAvailability(vehicle_id=vehicle.id, during=window, kind="maintenance"))

            async with maker() as session, session.begin():
                user = (
                    await session.execute(select(AppUser).where(AppUser.email == "t1@cfo.test"))
                ).scalar_one()
                assert user.roles == ["dispatcher"] and user.kpi_scopes == ["ops"] and user.is_active is True
                loaded = await session.get(Location, wh.id)
                assert loaded is not None and loaded.efficiency_factor == Decimal("1.00")
                before = loaded.updated_at
                loaded.name = "Renamed DC"
                await session.flush()  # trigger set_updated_at đặt lại updated_at; ORM đọc lại (FetchedValue)
                await session.refresh(loaded, ["updated_at"])
                assert loaded.updated_at >= before and loaded.created_at <= loaded.updated_at
                avail = (await session.execute(select(VehicleAvailability))).scalar_one()
                assert avail.during.lower == datetime(2026, 11, 10, 8, tzinfo=UTC)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
