"""Explicit, additive source schema bootstrap. Never run this during app startup."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.schema import CreateSchema

from app.config import Settings
from app.db import create_engine
from app.models import Base

ORDER_SNAPSHOT_COLUMNS = (
    ("address", "text"),
    ("lat", "numeric"),
    ("lon", "numeric"),
    ("contact_name", "text"),
    ("contact_phone", "text"),
    ("contact_email", "text"),
    ("receiving_restrictions", "text"),
    ("special_requirements", "text"),
)


async def _migrate_stock(connection: AsyncConnection, quoted_schema: str) -> None:
    """Staged, repeatable upgrade of `src_stock` to one row per (batch, warehouse, SKU); keeps legacy rows.

    Older instances have PRIMARY KEY (warehouse_code, sku) and may carry the rejected
    `physical_stock_pool_id` column of an unreleased draft. Legacy rows keep a NULL batch and are never
    served until a batch is published.
    """
    table = f"{quoted_schema}.src_stock"
    await connection.execute(
        text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS batch_id bigint "
            f"REFERENCES {quoted_schema}.src_stock_snapshot_batch(id)"
        )
    )
    await connection.execute(
        text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS id bigint GENERATED ALWAYS AS IDENTITY")
    )
    await connection.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS physical_stock_pool_id"))
    primary_key = (
        await connection.execute(
            text(
                "SELECT string_agg(a.attname, ',' ORDER BY a.attname) FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                "WHERE i.indrelid = CAST(:table AS regclass) AND i.indisprimary"
            ),
            {"table": table},
        )
    ).scalar_one()
    if primary_key != "id":  # the old composite key cannot hold several batches
        await connection.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS src_stock_pkey"))
        await connection.execute(text(f"ALTER TABLE {table} ADD PRIMARY KEY (id)"))
    await connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_src_stock_batch_key "
            f"ON {table} (batch_id, warehouse_code, sku)"
        )
    )


async def initialize(engine: AsyncEngine, schema: str) -> None:
    # Validate identifiers even when called directly by development tools/tests.
    Settings("postgresql+asyncpg://localhost/source", schema)
    quoted_schema = engine.dialect.identifier_preparer.quote(schema)
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(schema, if_not_exists=True))
        await connection.run_sync(Base.metadata.create_all)
        # create_all never alters existing tables: add the SRC-Q1 snapshot columns to older instances
        # (additive, keeps data, safe to repeat).
        for column, kind in ORDER_SNAPSHOT_COLUMNS:
            await connection.execute(
                text(f"ALTER TABLE {quoted_schema}.src_order ADD COLUMN IF NOT EXISTS {column} {kind}")
            )
        await connection.execute(
            text(
                f"ALTER TABLE {quoted_schema}.src_customer ADD COLUMN IF NOT EXISTS "
                "is_active boolean NOT NULL DEFAULT true"
            )
        )
        await connection.execute(
            text(f"ALTER TABLE {quoted_schema}.src_address ADD COLUMN IF NOT EXISTS receiving_hours jsonb")
        )
        await _migrate_stock(connection, quoted_schema)
        for column, kind in (("cancel_reason", "jsonb"), ("cancelled_at", "timestamptz")):
            await connection.execute(
                text(f"ALTER TABLE {quoted_schema}.src_order ADD COLUMN IF NOT EXISTS {column} {kind}")
            )
        await connection.execute(text(f"""
            CREATE OR REPLACE FUNCTION {quoted_schema}.keep_cancellation_provenance()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              IF OLD.status='CANCELLED' AND (NEW.status IS DISTINCT FROM OLD.status
                OR NEW.cancel_reason IS DISTINCT FROM OLD.cancel_reason
                OR NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at)
              THEN RAISE EXCEPTION 'Cancelled source order provenance is immutable' USING ERRCODE='23514';
              END IF; RETURN NEW; END $$;
        """))
        await connection.execute(text(f"""
            CREATE OR REPLACE TRIGGER trg_keep_cancellation BEFORE UPDATE ON {quoted_schema}.src_order
              FOR EACH ROW EXECUTE FUNCTION {quoted_schema}.keep_cancellation_provenance();
        """))
        await connection.execute(text(f"""
            CREATE OR REPLACE FUNCTION {quoted_schema}.set_updated_at()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN NEW.updated_at = COALESCE(NULLIF(current_setting('source.app_now', true),'')::timestamptz,
                                            clock_timestamp()); RETURN NEW; END;
            $$
        """))
        for table in Base.metadata.sorted_tables:
            quoted_table = engine.dialect.identifier_preparer.quote(table.name)
            await connection.execute(text(f"""
                CREATE OR REPLACE TRIGGER trg_updated_at
                BEFORE UPDATE ON {quoted_schema}.{quoted_table}
                FOR EACH ROW EXECUTE FUNCTION {quoted_schema}.set_updated_at()
            """))


async def main() -> None:
    settings = Settings.from_env()
    engine = create_engine(settings)
    try:
        await initialize(engine, settings.source_schema)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
