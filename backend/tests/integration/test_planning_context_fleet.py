"""Ngữ cảnh xe/tài xế cho engine (04 mục 6.2 bước 2d; US-PLN-03 AC3–AC5; 09 bất biến 11)."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.engine.types import DriverCtx, VehicleCtx
from app.services.planning_context import fleet_context
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
WED, THU = date(2026, 11, 4), date(2026, 11, 5)


def ts(day: date, h: int) -> datetime:
    return datetime(day.year, day.month, day.day, h, tzinfo=UTC)


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,  # xe 1 (V-1), 2 (V-2) ở kho 1; nhân viên 1, 2
        "UPDATE ref.vehicle SET capabilities = '{crane}', allowed_group_ids = '{1,2}', "
        "required_licence = 'CE' WHERE id = 1",
        "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, "
        "required_licence, status) "
        "VALUES (1, 'V-3', 'TST003', 'In maintenance', 8000, 30, 'C', 'maintenance')",
        "INSERT INTO ref.vehicle_availability (vehicle_id, during, kind) "
        "VALUES (2, '[2026-11-05 06:00+00, 2026-11-05 10:00+00)', 'maintenance')",
        "INSERT INTO hr.driver_staff (employee_id, home_warehouse_id, licence_class, licence_expires_on) "
        "VALUES (1, 1, 'CE', '2027-01-31'), (2, 1, 'C', '2026-11-04')",
        "INSERT INTO hr.attendance (employee_id, work_date, status) VALUES "
        "(1, '2026-11-04', 'present'), (1, '2026-11-05', 'planned'), (2, '2026-11-04', 'planned'), "
        "(2, '2026-11-05', 'planned')",
        "INSERT INTO hr.absence (employee_id, start_date, end_date, type, approved) "
        "VALUES (2, '2026-11-05', '2026-11-05', 'leave', true)",
        rows.order_sql(1),
        rows.order_sql(2),
        rows.order_sql(3),
        *(rows.run_sql(o, 1) for o in (1, 2, 3)),
        "UPDATE plan.planning_run SET hold_expires_at = '2026-11-04T09:20Z' WHERE order_id = 2",
        "UPDATE plan.planning_run SET hold_expires_at = '2026-11-04T09:00Z' WHERE order_id = 3",
        *(rows.plan_sql(r, r, 1) for r in (1, 2, 3)),
        *(rows.plan_vehicle_sql(p, 1, 1, 1) for p in (1, 2, 3)),
        rows.vehicle_res_sql(1, 1, 1, 1, 1, 1, "[2026-11-05 11:00+00, 2026-11-05 14:00+00)", "committed"),
        rows.vehicle_res_sql(2, 2, 2, 2, 1, 1, "[2026-11-05 15:00+00, 2026-11-05 17:00+00)", "held"),
        rows.vehicle_res_sql(3, 3, 3, 3, 1, 1, "[2026-11-05 18:00+00, 2026-11-05 20:00+00)", "held"),
    )
    yield empty_db


def _fleet(
    dsn: str, exclude_order_id: int | None = None
) -> tuple[tuple[VehicleCtx, ...], tuple[DriverCtx, ...]]:
    async def go() -> tuple[tuple[VehicleCtx, ...], tuple[DriverCtx, ...]]:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session:
                return await fleet_context(
                    session, 1, [WED, THU], now=NOW, today=WED, exclude_order_id=exclude_order_id
                )
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_only_available_vehicles_with_group_codes_and_capabilities(db: str) -> None:
    vehicles, _ = _fleet(db)
    assert [v.code for v in vehicles] == ["V-1", "V-2"]  # V-3 đang bảo trì (status)
    v1 = vehicles[0]
    assert (v1.capabilities, v1.allowed_group_codes, v1.required_licence) == (
        frozenset({"crane"}),
        frozenset({"N1", "N2"}),  # id 1, 2 = N1, N2 (seed 0008)
        "CE",
    )
    assert vehicles[1].allowed_group_codes == frozenset()  # rỗng = mọi nhóm


def test_vehicle_busy_from_calendar_and_other_orders_reservations(db: str) -> None:
    vehicles, _ = _fleet(db)
    v1, v2 = vehicles
    assert v1.busy == ((ts(THU, 11), ts(THU, 14)), (ts(THU, 15), ts(THU, 17)))  # held hết hạn không tính
    assert v2.busy == ((ts(THU, 6), ts(THU, 10)),)  # lịch bảo trì
    v1_own, _ = _fleet(db, exclude_order_id=2)
    assert v1_own[0].busy == ((ts(THU, 11), ts(THU, 14)),)  # giữ chỗ của chính đơn không chặn


def test_drivers_days_licence_hours_and_busy(db: str) -> None:
    _, drivers = _fleet(db)
    d1, d2 = drivers
    assert (d1.employee_id, d1.licence_class, d1.licence_expires_on) == (1, "CE", date(2027, 1, 31))
    assert d1.available_days == frozenset({WED, THU})
    assert d1.booked_hours_by_day == {THU: Decimal(5)}  # 3 h committed + 2 h held còn hạn
    assert d1.busy == ((ts(THU, 11), ts(THU, 14)), (ts(THU, 15), ts(THU, 17)))
    # tài xế 2: hôm nay chỉ 'planned' (không tính), Thứ Năm nghỉ phép đã duyệt
    assert d2.available_days == frozenset() and d2.booked_hours_by_day == {}
