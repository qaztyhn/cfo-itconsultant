"""D3 / US-GPS-03 AC2 (DEC-GPS-RET-20261109): raw GPS retention job.

Invalid points (outside the verified duty/trip window) are removed immediately; valid collected points are
kept at most 7 days (absolute 168 h) and then deleted. Idempotent; the schedule itself (D8) stays unapproved,
so nothing here activates a production cron. Device/offline-queue and backup erasure are separate handoffs.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.db import get_sessionmaker
from app.core.logging import log_event
from app.services import gps_service


async def purge_positions(session: AsyncSession, *, now: datetime) -> int:
    return await gps_service.purge_expired(session=session, now=now)


async def run() -> int:
    async with get_sessionmaker()() as session, session.begin():
        count = await purge_positions(session, now=clock.now())
    log_event("scheduler", "gps_retention", rows_processed=count)
    return count
