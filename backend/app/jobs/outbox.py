"""Gửi notification queued (email), giờ yên lặng, thử lại 3 lần.

Owner: Dev 2 (B) — M7.
"""

from app.core.logging import log_event
from app.services.notification_delivery import process_outbox


async def run(*, market_code: str | None = None) -> int:
    count = await process_outbox(market_code=market_code)
    log_event("notify", "outbox_processed", rows_processed=count)
    return count
