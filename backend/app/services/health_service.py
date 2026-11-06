"""Kiểm tra sức khỏe hệ thống cho GET /health (06 mục 15; 04 mục 10).

DB (truy vấn thật), độ tươi lượt đồng bộ thành công gần nhất, số thông báo đang chờ gửi. Không trả dữ liệu
cá nhân hay bí mật; lỗi DB không làm lộ chi tiết kết nối.

Owner: Dev 1 (luồng A) — M0.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.logging import log_event

_STATUS_SQL = text("""
SELECT (SELECT max(finished_at) FROM stg.sync_run WHERE status IN ('ok', 'partial')) AS last_sync,
       (SELECT count(*) FROM ops.notification WHERE status = 'queued') AS queued
""")


@dataclass(frozen=True)
class Health:
    db_ok: bool
    last_sync_age_min: int | None
    notify_queue: int | None


def _age_min(finished: datetime | None) -> int | None:
    if finished is None:
        return None
    return max(0, int((clock.now() - finished).total_seconds() // 60))


async def check(session: AsyncSession) -> Health:
    """Chạy truy vấn thật; DB lỗi → db_ok False (router trả 503)."""
    try:
        row = (await session.execute(_STATUS_SQL)).one()
    except Exception as exc:  # noqa: BLE001 — health không được ném lỗi ra ngoài
        log_event("api", "health.db_unavailable", level="error", error=type(exc).__name__)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return Health(db_ok=False, last_sync_age_min=None, notify_queue=None)
    return Health(db_ok=True, last_sync_age_min=_age_min(row.last_sync), notify_queue=int(row.queued))
