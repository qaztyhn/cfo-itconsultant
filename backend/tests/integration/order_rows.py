"""Dữ liệu và tiện ích cho test đơn/ánh xạ (giả lập, không PII — 09 bất biến 25).

Market 1 = SE (seed 0008). rows.REF_HR: nhân viên 1–2, product_global 1 (G-1, nhóm N1). Danh mục SE:
SE-OK-1 confirmed (G-1, units_to_base 2.5), SE-NEW-77 pending, SE-REJ rejected.
"""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.errors import DomainError
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch


def product_sql(sku: str, status: str, global_id: str = "NULL", mapped_by: str = "NULL") -> str:
    return (
        "INSERT INTO ref.product_se (local_sku, name, category, sale_unit, units_to_base, unit_price, "
        f"global_product_id, mapping_status, mapped_by) VALUES ('{sku}', 'Product {sku}', 'Test', 'pcs', "
        f"2.5, 10, {global_id}, '{status}', {mapped_by})"
    )


def order_sql(no: int, status: str, skus: tuple[str, ...]) -> list[str]:
    stmts = [
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "delivery_address, delivery_lat, delivery_lon, date_mode, date_to, order_date, currency, "
        f"submitted_at, status) VALUES ('SE-{no:06d}', 1, 'P-{no}', 1, 'Contact', 'Address', 59.0, 18.0, "
        f"'latest', '2026-11-30', '2026-11-04T09:00Z', 'SEK', '2026-11-04T09:00Z', '{status}')"
    ]
    for line_no, sku in enumerate(skus, start=1):
        stmts.append(
            "INSERT INTO ops.order_line (order_id, line_no, local_sku, qty_sale, unit_price, line_total) "
            f"VALUES ({no}, {line_no}, '{sku}', 4, 10, 40)"
        )
    return stmts


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *rows.REF_HR,
        product_sql("SE-OK-1", "confirmed", "1", "1"),
        product_sql("SE-NEW-77", "pending"),
        product_sql("SE-REJ", "rejected"),
    )
    yield empty_db


def run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    """Chạy fn trong một transaction rồi commit (lỗi → rollback, không ghi gì)."""

    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def error_of(fn: Callable[[], object]) -> DomainError:
    with pytest.raises(DomainError) as caught:
        fn()
    return caught.value


def status_of(dsn: str, order_id: int) -> tuple[str, str | None]:
    row = fetch(dsn, "SELECT status::text, block_reason FROM ops.customer_order WHERE id = $1", order_id)[0]
    return row["status"], row["block_reason"]


def tasks(dsn: str) -> list[tuple[str, int, str]]:
    return [
        (r["local_sku"], r["blocked_order_count"], r["status"])
        for r in fetch(
            dsn,
            "SELECT local_sku, blocked_order_count, status::text FROM ref.mapping_task ORDER BY local_sku",
        )
    ]
