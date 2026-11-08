import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.schema import DropSchema

from app.config import Settings
from app.db import create_engine
from app.init_db import initialize
from app.models import Address, Customer, ReceivingCalendar
from app.receiving import CalendarConfig
from app.seed_reference import seed_customers, seed_receiving_calendar


async def test_US_SRC_01_AC1_calendar_seed_and_additive_upgrade_preserve_existing_data() -> None:
    url = os.environ.get("SOURCE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("SOURCE_TEST_DATABASE_URL is required")
    schema = "src_test_" + uuid4().hex
    engine = create_engine(Settings(url, schema))
    now = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
    try:
        await initialize(engine, schema)
        async with engine.begin() as c:
            await c.execute(insert(Customer).values(id="OLD", name="Synthetic", type="business"))
            await c.execute(insert(Address).values(id="OLD-A", customer_id="OLD", address="Synthetic"))
            await c.execute(text(f'ALTER TABLE "{schema}".src_address DROP COLUMN receiving_hours'))
            await c.execute(text(f'ALTER TABLE "{schema}".src_customer DROP COLUMN is_active'))
        await initialize(engine, schema)
        await initialize(engine, schema)
        async with engine.begin() as c:
            assert await c.scalar(select(Customer.is_active).where(Customer.id == "OLD")) is True
            assert await c.scalar(select(Address.receiving_hours).where(Address.id == "OLD-A")) is None
            for _ in range(2):
                await seed_customers(c, now=now)
                await seed_receiving_calendar(c, now=now)
            assert await c.scalar(select(func.count()).select_from(ReceivingCalendar)) == 1
            assert (
                await c.scalar(
                    select(func.count()).select_from(Address).where(Address.receiving_hours.is_not(None))
                )
                == 80
            )
            config = (await c.execute(select(ReceivingCalendar.__table__))).mappings().one()
            parsed = CalendarConfig.model_validate({key: config[key] for key in CalendarConfig.model_fields})
            assert parsed.timezone == "Europe/Stockholm" and parsed.valid_to.year == 2027
            await c.execute(update(ReceivingCalendar).values(working_days=[1, 2]))
            await c.execute(update(Customer).where(Customer.id == "OLD").values(is_active=False))
            await seed_receiving_calendar(c, now=now)
            assert await c.scalar(select(ReceivingCalendar.working_days)) == [1, 2]
            assert await c.scalar(select(Customer.is_active).where(Customer.id == "OLD")) is False
    finally:
        async with engine.begin() as c:
            await c.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()
