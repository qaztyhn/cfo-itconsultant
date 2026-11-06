"""Explicit, additive source schema bootstrap. Never run this during app startup."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import CreateSchema

from app.config import Settings
from app.db import create_engine
from app.models import Base


async def initialize(engine: AsyncEngine, schema: str) -> None:
    # Validate identifiers even when called directly by development tools/tests.
    Settings("postgresql+asyncpg://localhost/source", schema)
    quoted_schema = engine.dialect.identifier_preparer.quote(schema)
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(schema, if_not_exists=True))
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text(f"""
            CREATE OR REPLACE FUNCTION {quoted_schema}.set_updated_at()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN NEW.updated_at = clock_timestamp(); RETURN NEW; END;
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
