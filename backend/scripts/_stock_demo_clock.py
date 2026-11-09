"""Reject administrative timestamps earlier than PostgreSQL wall time."""

import os
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def require_current_demo_clock(session: AsyncSession) -> None:
    configured = os.environ.get("APP_NOW", "")
    if not configured:
        return
    try:
        app_now = datetime.fromisoformat(configured)
    except ValueError as exc:
        raise SystemExit("APP_NOW is invalid") from exc
    db_now = await session.scalar(text("SELECT clock_timestamp()"))
    if app_now.tzinfo is None or db_now is None or abs(app_now - db_now) > timedelta(minutes=5):
        raise SystemExit(
            "Frozen APP_NOW differs from PostgreSQL wall time; refuse new grant/scope timestamps"
        )
