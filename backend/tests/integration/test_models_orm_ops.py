"""Model stg/ops dùng được qua ORM; bất biến DB vẫn có hiệu lực khi đi qua ORM (milestone_event chỉ thêm)."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.domain.models.ops import CustomerOrder, MilestoneEvent, OrderLine
from app.domain.models.stg import SyncRun
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute

pytestmark = pytest.mark.integration
T0 = datetime(2026, 11, 4, 9, tzinfo=UTC)


@pytest.fixture
def seeded(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR)
    yield empty_db


def test_orm_round_trip_stg_ops_and_append_only_event(seeded: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_url(seeded), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as session, session.begin():
                session.add(SyncRun(market_id=1, entity="orders", status="ok", finished_at=T0))
                order = CustomerOrder(
                    order_no="ZZ-000900", market_id=1, external_ref="EXT-900", customer_id=1,
                    contact_name="Contact", delivery_address="Address", delivery_lat=Decimal("59.0"),
                    delivery_lon=Decimal("18.0"), date_mode="latest", date_to=date(2026, 11, 18),
                    order_date=T0, currency="SEK", submitted_at=T0,
                )  # fmt: skip
                session.add(order)
                await session.flush()
                session.add(
                    OrderLine(
                        order_id=order.id, line_no=1, local_sku="SE-1", qty_sale=Decimal("2"),
                        unit_price=Decimal("10.00"), line_total=Decimal("20.00"),
                    )  # fmt: skip
                )
                session.add(
                    MilestoneEvent(
                        order_id=order.id, event_type="PREP_PAUSED", occurred_at=T0, actor_user_id=1,
                        idempotency_key="orm-k1",
                    )  # fmt: skip
                )

            async with maker() as session, session.begin():
                loaded = (await session.execute(select(CustomerOrder))).scalar_one()
                assert loaded.status == "SUBMITTED" and loaded.version == 1 and loaded.date_from is None
                event = (await session.execute(select(MilestoneEvent))).scalar_one()
                assert event.payload == {} and event.event_type == "PREP_PAUSED"

            with pytest.raises(DBAPIError, match="append-only table"):
                async with maker() as session, session.begin():
                    event = (await session.execute(select(MilestoneEvent))).scalar_one()
                    event.payload = {"note": "edited"}
        finally:
            await engine.dispose()

    asyncio.run(scenario())
