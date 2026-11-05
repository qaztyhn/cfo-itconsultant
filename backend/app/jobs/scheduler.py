"""APScheduler in-process; đăng ký mọi job theo MarketConfig.sync.interval_min (5 phút). Không Celery/Redis.

Owner: Dev 2 (B) — M2.
"""


async def run() -> int:
    """Chạy một lượt; trả số bản ghi xử lý. TODO(#scheduler)."""
    raise NotImplementedError
