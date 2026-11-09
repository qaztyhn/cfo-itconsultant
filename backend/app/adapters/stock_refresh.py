"""Controlled CFO stock re-read right after a WMS reservation ACK (DEC-WMS-RESERVE-SYNC-20261109, step 5).

Does NOT replace the 5-minute poll or Sales Sync Now and never touches checkpoints or the database:
it only re-reads the published Source batch through the injected read function and validates it. A
batch that is unavailable (503), incomplete, older than the one already known, or rejected by the
validator is never accepted as fresh. If the batch still lags the ACK, the caller keeps the
conservative pending-inclusion protection (`stock_accounting`) and the answer is `included=False`;
only a version proof (batch id >= the ACK's `reflected_in_batch_id`) lifts it. A later `as_of`
timestamp alone is never proof.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.adapters.base import StockSnapshotDTO
from app.adapters.wms_reservation import ReservationAck


class StockRefreshFailed(Exception):
    """No valid complete batch could be read; previous stock stays and no commitment is lifted."""

    code = "STOCK_REFRESH_FAILED"


@dataclass(frozen=True)
class RefreshResult:
    snapshot: StockSnapshotDTO
    included: bool
    attempts: int


async def refresh_after_ack(
    fetch: Callable[[], Awaitable[StockSnapshotDTO]],
    ack: ReservationAck,
    *,
    validate: Callable[[StockSnapshotDTO], object],
    known_batch_id: int | None = None,
    attempts: int = 3,
    pause: Callable[[int], Awaitable[None]] | None = None,
    retryable: tuple[type[Exception], ...] = (Exception,),
) -> RefreshResult:
    best: StockSnapshotDTO | None = None
    for attempt in range(1, attempts + 1):
        snapshot: StockSnapshotDTO | None
        try:
            snapshot = await fetch()
            validate(snapshot)  # completeness/scope/units: raises on a partial or inconsistent batch
        except retryable:
            snapshot = None
        if snapshot is not None and isinstance(snapshot.batch_id, int):
            if known_batch_id is None or snapshot.batch_id >= known_batch_id:
                best = snapshot
                proven = (
                    ack.reflected_in_batch_id is not None and snapshot.batch_id >= ack.reflected_in_batch_id
                )
                if proven:
                    return RefreshResult(snapshot, True, attempt)
        if pause is not None and attempt < attempts:
            await pause(attempt)
    if best is None:
        raise StockRefreshFailed()
    return RefreshResult(best, False, attempts)
