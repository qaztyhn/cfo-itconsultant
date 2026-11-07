"""Transactional market onboarding (US-INT-04 AC1); exact per-country product schema."""

import re
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def add_market(session: AsyncSession, code: str, *, name: str, timezone: str, currency: str) -> None:
    """Caller owns the transaction. Existing configuration is never overwritten."""
    if not re.fullmatch(r"[A-Z]{2}", code) or not re.fullmatch(r"[A-Z]{3}", currency) or not name.strip():
        raise ValueError("Supply uppercase market/currency codes and a name")
    ZoneInfo(timezone)
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('add_market', 0))"))
    existing = (
        await session.execute(
            text("SELECT name, timezone, currency FROM ref.market WHERE code=:code"),
            {"code": code},
        )
    ).one_or_none()
    if existing and tuple(existing) != (name, timezone, currency):
        raise ValueError("Existing market configuration differs")
    await session.execute(
        text("""INSERT INTO ref.market(code,name,timezone,currency,shadow_mode)
        VALUES (:code,:name,:timezone,:currency,true) ON CONFLICT (code) DO NOTHING"""),
        {"code": code, "name": name, "timezone": timezone, "currency": currency},
    )
    table = "product_" + code.lower()  # Strict ASCII identifiers validated above; not user SQL.
    exists = await session.scalar(text("SELECT to_regclass(:table)"), {"table": "ref." + table})
    if not exists:
        await session.execute(text(f"CREATE TABLE ref.{table} (LIKE ref.product_se INCLUDING ALL)"))
        await session.execute(text(f"ALTER TABLE ref.{table} ALTER COLUMN currency SET DEFAULT '{currency}'"))
        # PostgreSQL LIKE copies CHECK/index/default definitions, but not foreign keys/triggers.
        await session.execute(
            text(
                f"ALTER TABLE ref.{table} ADD FOREIGN KEY (global_product_id) "
                "REFERENCES ref.product_global(id)"
            )
        )
        await session.execute(
            text(f"ALTER TABLE ref.{table} ADD FOREIGN KEY (mapped_by) " "REFERENCES hr.employee(id)")
        )
        await session.execute(
            text(
                f"CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON ref.{table} "
                "FOR EACH ROW EXECUTE FUNCTION audit.set_updated_at()"
            )
        )
    codes = (await session.execute(text("""SELECT m.code FROM ref.market m
        JOIN information_schema.tables t ON t.table_schema='ref'
          AND t.table_name='product_' || lower(m.code)
        WHERE m.code ~ '^[A-Z]{2}$' ORDER BY m.code"""))).scalars().all()
    fields = (
        "local_sku,name,category,gtin,sale_unit,units_to_base,unit_price,currency,"
        "global_product_id,mapping_status"
    )
    selects = [f"SELECT '{c}'::char(2) AS market_code,{fields} FROM ref.product_{c.lower()}" for c in codes]
    await session.execute(
        text("CREATE OR REPLACE VIEW ref.v_product_local AS " + " UNION ALL ".join(selects))
    )
