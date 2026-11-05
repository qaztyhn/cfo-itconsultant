"""GPS (FR-GPS-01; BR-GPS-01; US-GPS-01..03).

Nhận lô vị trí chỉ khi market.gps_enabled (403 GPS_DISABLED) và chuyến on_road (409 NOT_ON_TRIP), tài xế
của chuyến. Đọc vị trí CHỈ cho dispatcher; không tổng hợp theo tài xế. lost_check (> 60' → GPS_LOST),
purge sau retention_days kể từ khi chuyến kết thúc.

Owner: Dev 2 (B) — M6.
"""


async def ingest_positions(
    trip_id: int, actor: object, positions: list[dict[str, object]]
) -> dict[str, object]:
    """TODO(#gps-ingest_positions)."""
    raise NotImplementedError


async def live(actor: object) -> list[dict[str, object]]:
    """TODO(#gps-live)."""
    raise NotImplementedError


async def lost_check() -> int:
    """TODO(#gps-lost_check)."""
    raise NotImplementedError


async def purge_expired() -> int:
    """TODO(#gps-purge_expired)."""
    raise NotImplementedError
