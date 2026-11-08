"""Expire planning holds in one database transaction (US-RES-01 AC4).

Runs are locked with SKIP LOCKED; a second worker does not double-expire.
"""

from app.services.reservation_service import expire_due


async def run() -> int:
    """Run one expiry pass; return the number of planning runs changed."""
    return await expire_due()
