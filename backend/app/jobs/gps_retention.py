"""D3 / US-GPS-03 AC2: retain raw GPS only within a currently authorized on-road duty session.

Repair/cleanup callable, not a promise of immediate terminal-workflow integration. Dev 1 must call
cleanup in the completion transaction; scheduler D8 and device/backup erasure are separate handoffs.
"""

from datetime import datetime

from sqlalchemy import and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.db import get_sessionmaker
from app.core.logging import log_event
from app.domain.models.ops import VehiclePosition
from app.services.gps_duty import active_duty


async def purge_positions(session: AsyncSession, *, now: datetime) -> int:
    duty = await active_duty(session, now=now)
    authorized = or_(
        False,
        *(
            and_(
                VehiclePosition.trip_id == trip_id,
                VehiclePosition.recorded_at >= begins,
                VehiclePosition.recorded_at < ends,
                VehiclePosition.recorded_at <= now,
            )
            for trip_id, (begins, ends) in duty.items()
        ),
    )
    deleted = await session.scalars(delete(VehiclePosition).where(~authorized).returning(VehiclePosition.id))
    return len(deleted.all())


async def run() -> int:
    async with get_sessionmaker()() as session, session.begin():
        count = await purge_positions(session, now=clock.now())
    log_event("scheduler", "gps_retention", rows_processed=count)
    return count
