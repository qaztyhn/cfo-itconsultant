"""Ngữ cảnh hàng/tuyến cho engine từ DB.

US-ATP-01 AC1/AC3; 05 mục 7 quy tắc giữ chỗ 5; 09 mục 8 (route_matrix).
"""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.engine.types import InboundCtx, RouteInfo
from app.services.planning_context import available_stock, confirmed_inbound, route_info
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,
        "INSERT INTO ref.product_global (code, name, category, base_unit, weight_kg, volume_m3, "
        "handling_group_id) VALUES ('G-2', 'Product 2', 'Test', 'pcs', 1, 0.01, 1)",
        "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
        "VALUES (1, 'warehouse', 'WH-2', 'Warehouse 2', 57.7, 11.9, '15:00')",  # location 3
        "INSERT INTO ops.stock_snapshot (warehouse_id, global_product_id, on_hand, wms_reserved, as_of) "
        "VALUES (1, 1, 100, 20, now()), (1, 2, 5, 0, now()), (3, 1, 7, 0, now())",
        rows.order_sql(1),
        rows.order_sql(2),
        rows.order_sql(3),
        rows.order_sql(4),
        *(rows.run_sql(o, 1) for o in (1, 2, 3, 4)),
        "UPDATE plan.planning_run SET hold_expires_at = '2026-11-04T09:20Z' WHERE order_id = 2",
        "UPDATE plan.planning_run SET hold_expires_at = '2026-11-04T09:00Z' WHERE order_id = 3",
    )
    yield empty_db


def _run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _res(order: int, qty: str, status: str, warehouse: int = 1, product: int = 1) -> str:
    return (
        "INSERT INTO plan.stock_reservation (run_id, order_id, warehouse_id, global_product_id, qty, status) "
        f"VALUES ({order}, {order}, {warehouse}, {product}, {qty}, '{status}')"
    )


def test_US_ATP_01_AC1_available_excludes_wms_reserved_and_other_orders_holds(db: str) -> None:
    execute(
        db,
        _res(1, "10", "committed"),
        _res(2, "20", "held"),  # còn hạn → trừ
        _res(3, "40", "held"),  # hết hạn → không trừ
        _res(4, "15", "released"),
    )
    stock = _run(db, lambda s: available_stock(s, [1, 3], [1, 2], now=NOW, exclude_order_id=None))
    # 100 − 20 − 10 − 20 = 50
    assert stock == {1: {1: Decimal(50), 2: Decimal(5)}, 3: {1: Decimal(7), 2: Decimal(0)}}


def test_own_order_reservations_not_subtracted_and_never_negative(db: str) -> None:
    execute(db, _res(1, "30", "committed"), _res(2, "200", "held"))
    stock = _run(db, lambda s: available_stock(s, [1], [1], now=NOW, exclude_order_id=1))
    assert stock == {1: {1: Decimal(0)}}  # 100 − 20 − 200 < 0 → 0 (giữ chỗ held được phép vượt)
    own = _run(db, lambda s: available_stock(s, [1], [1], now=NOW, exclude_order_id=2))
    assert own == {1: {1: Decimal(50)}}  # 100 − 20 − 30


def test_US_ATP_01_AC3_only_confirmed_not_received_inbound(db: str) -> None:
    execute(
        db,
        "INSERT INTO ops.inbound_shipment (inbound_ref, warehouse_id, global_product_id, qty, eta_date, "
        "confirmed, received) VALUES ('INB-OK', 1, 1, 40, '2026-11-05', true, false), "
        "('INB-UNCONF', 1, 1, 50, '2026-11-05', false, false), "
        "('INB-DONE', 1, 2, 60, '2026-11-03', true, true), "
        "('INB-OTHER', 3, 1, 70, '2026-11-06', true, false)",
    )
    inbound = _run(db, lambda s: confirmed_inbound(s, [1, 3], [1, 2]))
    assert inbound == {
        1: (InboundCtx(1, Decimal("40.000"), date(2026, 11, 5), "INB-OK"),),
        3: (InboundCtx(1, Decimal("70.000"), date(2026, 11, 6), "INB-OTHER"),),
    }


def test_route_info_from_route_matrix_or_none(db: str) -> None:
    execute(
        db,
        "INSERT INTO plan.route_matrix (warehouse_id, to_lat, to_lon, distance_km, duration_min, provider) "
        "VALUES (1, 59.00000, 18.00000, 42.50, 55, 'ors')",
    )
    routes = _run(db, lambda s: route_info(s, [1, 3], Decimal("59.00000"), Decimal("18.00000")))
    assert routes == {1: RouteInfo(Decimal("42.50"), 55, "ors"), 3: None}
