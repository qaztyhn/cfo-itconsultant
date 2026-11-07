"""Add deterministic demo workforce/stores/drivers after M0 reference migrations (08 section 5)."""

from datetime import date
from decimal import Decimal
from random import Random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.domain.models.hr import (
    CsStaff,
    DispatcherStaff,
    DriverStaff,
    Employee,
    EmployeeAssignment,
    LocationManager,
    Position,
    SalesStaff,
    WarehouseStaff,
)
from app.domain.models.ref import AppUser, Location, Market
from app.seed.infrastructure import WAREHOUSES, seed_infrastructure
from app.seed.m0_accounts import seed_accounts

START = date(2026, 1, 1)


async def seed_workforce(session: AsyncSession, password: str) -> None:
    """Preserve existing identities/assignments/accounts, fail on incompatible identity."""
    await seed_accounts(session, password)
    await seed_infrastructure(session, year=2026)
    market = (await session.scalars(select(Market).where(Market.code == "SE"))).one()
    locations = {
        v.code: v
        for v in (await session.scalars(select(Location).where(Location.market_id == market.id))).all()
    }
    rng = Random(20261104)
    for index in range(1, 26):
        code = f"ST-{index:03d}"
        if code not in locations:
            _, _, lat, lon = WAREHOUSES[(index - 1) % 3]
            location = Location(
                market_id=market.id,
                type="store",
                code=code,
                name=f"Demo store {index:03d}",
                lat=Decimal(lat) + Decimal(rng.randint(-10000, 10000)) / 100000,
                lon=Decimal(lon) + Decimal(rng.randint(-10000, 10000)) / 100000,
            )
            session.add(location)
            await session.flush()
            locations[code] = location
    positions = {p.code: p for p in (await session.scalars(select(Position))).all()}

    async def employee(number: str, position: str, location_code: str, *, email: str | None = None) -> int:
        number = "DEMO-" + number
        person = (
            await session.scalars(
                select(Employee).where(Employee.market_id == market.id, Employee.employee_no == number)
            )
        ).one_or_none()
        if person is None:
            person = Employee(
                market_id=market.id,
                employee_no=number,
                first_name="Demo",
                last_name=number,
                position_code=position,
                hire_date=START,
            )
            session.add(person)
            await session.flush()
        elif person.position_code != position:
            raise ValueError("Conflicting demo employee identity")
        assignment = (
            await session.scalars(
                select(EmployeeAssignment).where(
                    EmployeeAssignment.employee_id == person.id,
                    EmployeeAssignment.end_date.is_(None),
                )
            )
        ).one_or_none()
        if assignment is None:
            session.add(
                EmployeeAssignment(
                    employee_id=person.id,
                    location_id=locations[location_code].id,
                    start_date=START,
                )
            )
        elif assignment.location_id != locations[location_code].id:
            raise ValueError("Conflicting demo employee assignment")
        p = positions[position]
        if p.default_roles:
            address = email or f"{number.lower()}@cfo.demo"
            user = (await session.scalars(select(AppUser).where(AppUser.email == address))).one_or_none()
            if user is None:
                session.add(
                    AppUser(
                        employee_id=person.id,
                        email=address,
                        password_hash=hash_password(password),
                        roles=p.default_roles,
                        kpi_scopes=p.default_kpi_scopes,
                    )
                )
            elif user.employee_id != person.id:
                raise ValueError("Conflicting demo account identity")
        return person.id

    async def manager(location_code: str, person_id: int, level: str) -> None:
        location = locations[location_code]
        existing = (
            await session.scalars(
                select(LocationManager).where(
                    LocationManager.location_id == location.id,
                    LocationManager.level == level,
                    LocationManager.valid_to.is_(None),
                )
            )
        ).one_or_none()
        if existing is None:
            session.add(
                LocationManager(
                    location_id=location.id,
                    employee_id=person_id,
                    level=level,
                    valid_from=START,
                )
            )
        if level == "primary" and location.owner_employee_id is None:
            location.owner_employee_id = existing.employee_id if existing else person_id

    for code, *_ in WAREHOUSES:
        for index, (position, role) in enumerate(
            [
                ("WAREHOUSE_MANAGER", "manager"),
                ("WAREHOUSE_DEPUTY", "deputy"),
                *(("WAREHOUSE_SUPERVISOR", "supervisor") for _ in range(2)),
                *(("WAREHOUSE_OPERATOR", "operator") for _ in range(11)),
            ]
        ):
            person = await employee(
                f"{code}-W{index:02d}",
                position,
                code,
                email="wm.got@cfo.demo" if code == "GBG" and index == 0 else None,
            )
            if await session.get(WarehouseStaff, person) is None:
                session.add(
                    WarehouseStaff(
                        employee_id=person,
                        role=role,
                        counts_in_capacity=role in ("operator", "supervisor"),
                    )
                )
            if index < 2:
                await manager(code, person, "primary" if index == 0 else "deputy")
    for index in range(1, 26):
        code = f"ST-{index:03d}"
        person = await employee(f"{code}-MGR", "STORE_MANAGER", code)
        await manager(code, person, "primary")
        for sales in range(3):
            # M0's sales account is the first member at ST-001.
            if index == 1 and sales == 0:
                continue
            await employee(f"{code}-S{sales}", "SALES_RETAIL", code)
    for index in range(1, 11):
        code = WAREHOUSES[(index - 1) % 3][0]
        person = await employee(f"DRIVER-{index}", "DRIVER", code, email=f"driver{index}@cfo.demo")
        if await session.get(DriverStaff, person) is None:
            session.add(
                DriverStaff(
                    employee_id=person,
                    home_warehouse_id=locations[code].id,
                    licence_class=("B", "C", "CE")[(index - 1) % 3],
                    licence_expires_on=(date(2026, 1, 1) if index == 10 else date(2030, 1, 1)),
                )
            )
    for index in (2, 3):
        await employee(f"DISPATCHER-{index}", "DISPATCHER", "DC")
    for index in (1, 2):
        await employee(
            f"CS-{index}",
            "CUSTOMER_SERVICE",
            "HQ",
            email="cs@cfo.demo" if index == 1 else None,
        )
    for member in (
        await session.scalars(
            select(Employee).where(Employee.market_id == market.id, Employee.employee_no.like("DEMO-%"))
        )
    ).all():
        if member.position_code in ("STORE_MANAGER", "SALES_RETAIL"):
            if await session.get(SalesStaff, member.id) is None:
                session.add(
                    SalesStaff(
                        employee_id=member.id,
                        role=("store_manager" if member.position_code == "STORE_MANAGER" else "retail"),
                    )
                )
        elif member.position_code == "DISPATCHER" and await session.get(DispatcherStaff, member.id) is None:
            session.add(DispatcherStaff(employee_id=member.id))
        elif member.position_code == "CUSTOMER_SERVICE" and await session.get(CsStaff, member.id) is None:
            session.add(CsStaff(employee_id=member.id, team="Demo"))
