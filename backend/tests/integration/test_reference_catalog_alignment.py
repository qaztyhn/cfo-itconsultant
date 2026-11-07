import runpy
import secrets
from dataclasses import astuple
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.seed.catalog import seed_catalog
from app.seed.m0_accounts import seed_accounts
from tests.integration.conftest import alembic_config, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration


def test_US_SRC_01_AC1_source_fixture_matches_all_cfo_local_catalog_fields(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    password = secrets.token_urlsafe(24)

    async def seed(session: AsyncSession) -> None:
        await seed_accounts(session, password)
        await seed_catalog(session, now=datetime(2026, 11, 4, tzinfo=UTC))

    transact(empty_db, seed)
    # Test-only loading: independently packaged applications do not import each
    # other at runtime, but their reference data must describe the same products.
    fixture_path = Path(__file__).resolve().parents[3] / "source_system/seed/se/catalog.py"
    factory = runpy.run_path(str(fixture_path))["catalog_products"]
    expected = sorted(astuple(product) for product in factory())
    actual = [
        tuple(row)
        for row in fetch(
            empty_db,
            "SELECT local_sku,name,category,gtin,sale_unit,units_to_base,unit_price,weight_kg,volume_m3 "
            "FROM ref.product_se ORDER BY local_sku",
        )
    ]
    assert len(actual) == len(expected) == 100
    assert actual == expected
