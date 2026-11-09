"""Idempotently bind only the Swedish *disposable* demo to its local Source API.

The M0 reference migration seeds source_api_key_ref, not source_base_url.
This CLI never changes credentials, stock, routes, other markets or an
already different source URL. It is NOT a production configuration endpoint.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.domain.models.ref import Market

APP_NOW = "2026-11-04T10:05:00+01:00"
SOURCE_URL = "http://source-se:8100/api/v1"


async def configure() -> int:
    settings = get_settings()
    if (
        settings.app_env != "test"
        or settings.app_now != APP_NOW
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or settings.source_se_base_url != SOURCE_URL
    ):
        print("BLOCKED: expected disposable Swedish demo settings not present.")
        return 2
    try:
        async with get_sessionmaker()() as session, session.begin():
            market = await session.scalar(select(Market).where(Market.code == "SE").with_for_update())
            if market is None or market.source_api_key_ref != "SOURCE_SE_API_KEY":
                print("BLOCKED: approved Swedish Source credential reference missing.")
                return 2
            if market.source_base_url not in (None, SOURCE_URL):
                print("BLOCKED: Swedish Source already targets a different adapter.")
                return 2
            market.source_base_url = SOURCE_URL
        print("PASS: Swedish disposable Source URL bound without writing a key or changing another market.")
        return 0
    except Exception:
        print("BLOCKED: Source configuration could not be verified; no details or credentials exposed.")
        return 2
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(configure()))
