"""Database lifecycle and a bounded connectivity probe; never log connection URLs."""

import asyncio

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"timeout": 3, "command_timeout": 3},
        execution_options={"schema_translate_map": {"source": settings.source_schema}},
    )


async def database_ready(request: Request) -> bool:
    engine: AsyncEngine = request.app.state.engine
    try:
        async with asyncio.timeout(4):
            async with engine.connect() as connection:
                return bool(await connection.scalar(text("SELECT 1")) == 1)
    except Exception:
        # Driver connection/authentication errors are not always wrapped by SQLAlchemy.
        # Any failed probe is unhealthy; never expose the original exception to clients.
        return False
