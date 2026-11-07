"""revenue_service trên PostgreSQL (05 mục 8; 06 mục 14.1; US-REV-01 AC1–AC7, AC10).

Market 1 = SE (Europe/Stockholm, seed 0008). Địa điểm: 1 kho WH-1 (rows.REF_HR), 2 ST-1 (rows), 3 ST-022,
4 kho GBG. Owner: ST-1 ← nhân viên 1, GBG ← nhân viên 3; nhân viên 2 không là owner.
"""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.errors import DomainError
from app.services import revenue_service as rs
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute

pytestmark = pytest.mark.integration
TODAY = date(2026, 11, 20)
NOV = rs.Period(date(2026, 11, 1), date(2026, 11, 30))


@dataclass(frozen=True)
class Viewer:
    roles: tuple[str, ...]
    kpi_scopes: tuple[str, ...] = ()
    employee_id: int | None = None


OWNER_BUSINESS = Viewer(("viewer",), ("revenue_all",))
ADMIN = Viewer(("admin",))
STORE_OWNER = Viewer(("sales",), employee_id=1)
WAREHOUSE_OWNER = Viewer(("warehouse",), ("ops",), employee_id=3)
DISPATCHER = Viewer(("dispatcher",), ("ops",), employee_id=2)
PROJECT_LEAD = Viewer(("viewer",), ("ops",), employee_id=99)


def _order(no: int, status: str, amount: str, store: int | None, *, delivered: str | None = None,
           committed: str | None = None) -> str:  # fmt: skip
    return (
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "delivery_address, delivery_lat, delivery_lon, date_mode, date_to, order_date, currency, "
        "submitted_at, status, total_amount, origin_store_id, delivered_at, committed_date) VALUES "
        f"('SE-{no:06d}', 1, 'R-{no}', 1, 'Contact', 'Address', 59.0, 18.0, 'latest', '2026-11-30', "
        f"'2026-11-01T08:00Z', 'SEK', '2026-11-01T08:00Z', '{status}', {amount}, {store or 'NULL'}, "
        f"{repr(delivered) if delivered else 'NULL'}, {repr(committed) if committed else 'NULL'})"
    )


# (order_no, status, amount, store, warehouse, delivered_at, committed_date)
ORDERS = [
    (1, "DELIVERED", "1000.00", 2, 1, "2026-11-10T22:50Z", None),  # 23:50 Stockholm 10/11 (AC10)
    (2, "DELIVERED", "500.50", 2, 4, "2026-11-10T23:30Z", None),  # 00:30 Stockholm 11/11
    (3, "DELIVERED", "250.00", 3, 4, "2026-11-12T09:00Z", None),
    (4, "DELIVERED", "100.00", None, 1, "2026-11-13T09:00Z", None),  # không có cửa hàng
    (5, "FAILED", "999.00", 2, 1, None, None),
    (6, "CANCELLED", "888.00", 2, 1, None, None),
    (7, "APPROVED", "300.00", 2, 1, None, "2026-11-25"),
    (8, "DISPATCHED", "200.00", 3, 4, None, "2026-11-21"),
    (9, "DELIVERED", "777.00", 2, 1, "2026-10-31T10:00Z", None),  # ngoài kỳ
]


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    stmts: list[str] = [
        *rows.REF_HR,
        "INSERT INTO ref.location (market_id, type, code, name, lat, lon) "
        "VALUES (1, 'store', 'ST-022', 'Store 22', 59.5, 18.2)",  # 3
        "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
        "VALUES (1, 'warehouse', 'GBG', 'Göteborg DC', 57.7, 11.9, '15:00')",  # 4
        "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
        "VALUES (1, 'E3', 'Test', 'Three', 'TEST_POS', '2026-01-01')",
        "UPDATE ref.location SET owner_employee_id = 1 WHERE id = 2",
        "UPDATE ref.location SET owner_employee_id = 3 WHERE id = 4",
    ]
    for no, status, amount, store, wh, delivered, committed in ORDERS:
        stmts += [
            _order(no, status, amount, store, delivered=delivered, committed=committed),
            rows.run_sql(no, 1),
            rows.plan_sql(no, no, 1, "approved"),
            f"UPDATE plan.fulfilment_plan SET warehouse_id = {wh} WHERE id = {no}",
            f"UPDATE ops.customer_order SET approved_plan_id = {no} WHERE id = {no}",
        ]
    execute(empty_db, *stmts)
    yield empty_db


def run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def summary(dsn: str, viewer: Viewer, view: str, location_id: int | None = None) -> rs.RevenueSummary:
    return run(
        dsn, lambda s: rs.summary(s, viewer, market_id=1, view=view, location_id=location_id, period=NOV)
    )


def error_of(fn: Callable[[], object]) -> DomainError:
    with pytest.raises(DomainError) as caught:
        fn()
    return caught.value


def test_US_REV_01_AC1_business_owner_sees_all_and_share(db: str) -> None:
    total = summary(db, OWNER_BUSINESS, "store")
    assert (total.recognised, total.orders_delivered, total.booked_not_delivered) == (
        Decimal("1850.50"),
        4,
        Decimal("500.00"),
    )
    one = summary(db, OWNER_BUSINESS, "store", 2)
    assert one.recognised == Decimal("1500.50") and one.share_of_market_pct == Decimal("81.1")
    assert one.avg_order_value == Decimal("750.25") and one.currency == "SEK"


def test_US_REV_01_AC7_store_total_equals_warehouse_total(db: str) -> None:
    stores = summary(db, OWNER_BUSINESS, "store")
    warehouses = summary(db, OWNER_BUSINESS, "warehouse")
    assert (stores.recognised, stores.booked_not_delivered) == (
        warehouses.recognised,
        warehouses.booked_not_delivered,
    )
    by_store = run(db, lambda s: rs.by_location(s, OWNER_BUSINESS, market_id=1, view="store", period=NOV))
    assert sum(r.recognised for r in by_store.rows) == stores.recognised
    unassigned = [r for r in by_store.rows if r.location_id is None]
    assert len(unassigned) == 1 and unassigned[0].name == "Unassigned store"
    assert unassigned[0].recognised == Decimal("100.00")


def test_US_REV_01_AC2_store_owner_only_own_store(db: str) -> None:
    own = summary(db, STORE_OWNER, "store")
    assert own.recognised == Decimal("1500.50") and own.share_of_market_pct is None
    assert error_of(lambda: summary(db, STORE_OWNER, "store", 3)).http_status == 404
    rows_ = run(db, lambda s: rs.by_location(s, STORE_OWNER, market_id=1, view="store", period=NOV)).rows
    assert [(r.location_id, r.share_pct) for r in rows_] == [(2, None)]


def test_US_REV_01_AC3_warehouse_owner_view_rules(db: str) -> None:
    assert summary(db, WAREHOUSE_OWNER, "warehouse").recognised == Decimal("750.50")
    assert error_of(lambda: summary(db, WAREHOUSE_OWNER, "store", 4)).http_status == 422
    assert error_of(lambda: summary(db, WAREHOUSE_OWNER, "store")).http_status == 403
    assert error_of(lambda: summary(db, WAREHOUSE_OWNER, "warehouse", 1)).http_status == 404


@pytest.mark.parametrize(
    "viewer",
    [
        DISPATCHER,
        PROJECT_LEAD,
        Viewer(("sales",), employee_id=2),
        Viewer(("driver",), employee_id=99),
        Viewer(()),
    ],
)
def test_US_REV_01_AC4_non_owners_forbidden_admin_all(db: str, viewer: Viewer) -> None:
    assert error_of(lambda: summary(db, viewer, "store")).http_status == 403
    assert summary(db, ADMIN, "warehouse").recognised == Decimal("1850.50")


def test_US_REV_01_AC5_only_delivered_recognised_booked_approved_to_dispatched(db: str) -> None:
    s = summary(db, ADMIN, "store", 2)
    assert s.recognised == Decimal("1500.50")  # FAILED 999 và CANCELLED 888 không tính
    assert s.booked_not_delivered == Decimal("300.00")  # APPROVED theo committed_date


def test_US_REV_01_AC10_stockholm_day_boundary(db: str) -> None:
    points = run(
        db, lambda s: rs.daily(s, ADMIN, market_id=1, view="store", location_id=2, period=NOV)
    ).points
    by_day = {p.day: p.recognised for p in points}
    assert by_day[date(2026, 11, 10)] == Decimal("1000.00")  # 22:50Z = 23:50 Stockholm
    assert by_day[date(2026, 11, 11)] == Decimal("500.50")  # 23:30Z = 00:30 ngày sau
    assert len(points) == 30 and by_day[date(2026, 11, 1)] == Decimal(0)  # chuỗi đủ ngày cho biểu đồ


def test_period_defaults_and_validation() -> None:
    assert rs.Period.resolve(None, None, TODAY) == rs.Period(date(2026, 10, 22), TODAY)
    for start, end in ((date(2026, 11, 30), date(2026, 11, 1)), (date(2025, 1, 1), date(2026, 11, 1))):
        with pytest.raises(DomainError) as caught:
            rs.Period.resolve(start, end, TODAY)
        assert caught.value.http_status == 422


def test_invalid_view_rejected(db: str) -> None:
    assert error_of(lambda: summary(db, ADMIN, "region")).http_status == 422
