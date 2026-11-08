"""T07 stock readiness gate (DEC-CFO-STOCK-SCOPE-001 / INDEPENDENCE-001).

The owner-approved SKU scope and independence policies have no reviewed persistence,
version/effectivity or evidence authority contract yet. #120 provides only a pure
normalizer proposal. Never derive scope from currently confirmed mappings, batch rows,
or a whole-market fallback; no canonical stock writes are authorized by this module.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ingestion_feed import StockFeedValue
from app.domain.models.ref import Market
from app.services.ingest_types import BatchRejected, RowOutcome


async def usable(session: AsyncSession, market_id: int, *, now: datetime) -> bool:
    """Without an approved versioned scope/evidence repository, cached stock is unverified.

    This is an explicit dependency gate, not an implemented stock-availability proof.
    T14/T16 must keep confirmation fail-closed until the reviewed handoff is delivered.
    """
    return False


async def apply(
    session: AsyncSession, market: Market, value: StockFeedValue, run_id: int, now: datetime
) -> RowOutcome:
    """Record a failed explicit stock diagnostic without clearing stock or advancing a checkpoint.

    Even a published empty Source batch cannot establish the unconfigured CFO scope.
    No scope/evidence schema, approval authority, config key or public API is invented.
    """
    raise BatchRejected("STOCK_SCOPE_NOT_CONFIGURED")
