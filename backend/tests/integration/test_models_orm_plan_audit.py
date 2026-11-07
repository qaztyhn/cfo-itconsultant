"""Model plan/audit qua ORM: phương án nhiều xe (v1.2), giữ chỗ xe tstzrange, decision_log chỉ thêm."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.domain.models.audit import DecisionLog
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan, PlanVehicle, VehicleReservation
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1),
        "INSERT INTO audit.decision_log (correlation_id, action, entity) "
        "VALUES ('6c0f6c0f-0000-4000-8000-000000000009', 'PLAN_PROPOSED', 'order')",
    )
    yield empty_db


def test_orm_plan_with_two_vehicles_and_reservations(seeded: str) -> None:
    window = Range(datetime(2026, 11, 10, 6, 30, tzinfo=UTC), datetime(2026, 11, 10, 11, tzinfo=UTC))

    async def scenario() -> None:
        engine = create_async_engine(async_url(seeded), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session, session.begin():
                plan = (await session.execute(select(FulfilmentPlan))).scalar_one()
                for seq, (vehicle_id, driver_id) in enumerate(((1, 1), (2, 2)), start=1):
                    pv = PlanVehicle(
                        plan_id=plan.id, seq=seq, vehicle_id=vehicle_id, driver_employee_id=driver_id,
                        load_kg=1000, load_m3=2, load_lines=[{"line_no": 1, "qty_base": 10}],
                        loading_start_at=window.lower, depart_at=window.lower, eta_at=window.upper,
                        trip_end_at=window.upper,
                    )  # fmt: skip
                    session.add(pv)
                    await session.flush()
                    session.add(
                        VehicleReservation(
                            run_id=plan.run_id, plan_id=plan.id, plan_vehicle_id=pv.id,
                            order_id=plan.order_id,
                            vehicle_id=vehicle_id, driver_employee_id=driver_id, during=window,
                        )  # fmt: skip
                    )
                order = await session.get(CustomerOrder, plan.order_id)
                assert order is not None
                order.approved_plan_id = plan.id  # fk_order_plan (use_alter) hoạt động qua ORM

            async with maker() as session:
                res = (await session.execute(select(VehicleReservation))).scalars().all()
                assert [r.status for r in res] == ["held", "held"] and res[0].during == window
                assert (await session.execute(select(FulfilmentPlan.vehicle_count))).scalar_one() == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_orm_cannot_update_decision_log(seeded: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_url(seeded), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session:
                row = (await session.execute(select(DecisionLog))).scalar_one()
                assert row.correlation_id == uuid.UUID("6c0f6c0f-0000-4000-8000-000000000009")
            with pytest.raises(DBAPIError, match="append-only table"):
                async with maker() as session, session.begin():
                    row = (await session.execute(select(DecisionLog))).scalar_one()
                    row.reason_text = "edited"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
