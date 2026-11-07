"""Phạm vi đọc nhân sự/địa điểm/xe (06 mục 13.1; Q2/Q3 PR #12) và phân trang trên PostgreSQL."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.ref import Location
from app.services.hr_scope import resolve_hr_scope
from app.services.query_utils import paginate
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class User:
    roles: tuple[str, ...]
    market: str = "SE"
    location_ids: tuple[int, ...] = field(default_factory=tuple)


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR)  # market 1 = SE (seed), market 2 = ZZ (rows)
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


def test_admin_dispatcher_warehouse_scopes(db: str) -> None:
    admin = run(db, lambda s: resolve_hr_scope(s, User(("admin",))))
    assert (admin.role, admin.market_id) == ("admin", 1)
    system_admin = run(db, lambda s: resolve_hr_scope(s, User(("admin",), market="")))
    assert system_admin.market_id is None  # tài khoản hệ thống: mọi market
    dispatcher = run(db, lambda s: resolve_hr_scope(s, User(("dispatcher",))))
    assert (dispatcher.role, dispatcher.market_id) == ("dispatcher", 1)
    warehouse = run(db, lambda s: resolve_hr_scope(s, User(("warehouse",), location_ids=(1,))))
    assert (warehouse.role, warehouse.market_id, warehouse.location_ids) == ("warehouse", 1, frozenset({1}))


def test_multiple_roles_use_broadest(db: str) -> None:
    scope = run(db, lambda s: resolve_hr_scope(s, User(("warehouse", "dispatcher"), location_ids=(1,))))
    assert scope.role == "dispatcher"


@pytest.mark.parametrize("role", ["sales", "driver", "customer_service", "viewer"])
def test_other_roles_forbidden(db: str, role: str) -> None:
    with pytest.raises(DomainError) as caught:
        run(db, lambda s: resolve_hr_scope(s, User((role,))))
    assert caught.value.code == "FORBIDDEN"


def test_non_admin_without_market_forbidden(db: str) -> None:
    with pytest.raises(DomainError) as caught:
        run(db, lambda s: resolve_hr_scope(s, User(("dispatcher",), market="")))
    assert caught.value.code == "FORBIDDEN"


def test_today_follows_market_timezone(db: str) -> None:
    clock.set_now(datetime(2026, 11, 4, 23, 30, tzinfo=UTC))  # 00:30 ngày 5/11 ở Stockholm
    scope = run(db, lambda s: resolve_hr_scope(s, User(("dispatcher",))))
    assert scope.today == date(2026, 11, 5)


def test_paginate_returns_items_and_total(db: str) -> None:
    execute(
        db,
        *(
            "INSERT INTO ref.location (market_id, type, code, name) "
            f"VALUES (1, 'dispatch_center', 'DC-{i:02d}', 'DC {i}')"
            for i in range(5)
        ),
    )
    query = select(Location).where(Location.type == "dispatch_center").order_by(Location.code)
    items, total = run(db, lambda s: paginate(s, query, page=2, page_size=2))
    assert total == 5 and [loc.code for loc in items] == ["DC-02", "DC-03"]
    empty, total = run(db, lambda s: paginate(s, query, page=9, page_size=2))
    assert empty == [] and total == 5
