"""Kết nối PostgreSQL (SQLAlchemy 2.0 async) và tiện ích khóa.

- engine/sessionmaker async; một use case một transaction (09 mục 5).
- advisory_lock(session, key): pg_advisory_xact_lock(hashtextextended(key, 0)) — dùng cho
  `stock:<kho>:<sản phẩm>` và `labour:<kho>:<ngày>` (05 mục 7, 04 mục 7 quy tắc 8).
- v1.2: CHỈ khóa khi DUYỆT; lúc lập kế hoạch giữ chỗ không khóa và được phép vượt.
- Thứ tự khóa bắt buộc: kho → sản phẩm → ngày → mọi xe → mọi tài xế của phương án (09 mục 5).

Owner: Dev 1 (luồng A) — M0, dùng ở M5.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def to_async_url(url: str) -> str:
    """Chuẩn hóa URL Postgres sang driver asyncpg (`postgresql://` → `postgresql+asyncpg://`)."""
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


@lru_cache
def get_engine() -> AsyncEngine:
    """Engine async dùng chung theo tiến trình; URL từ DATABASE_URL (không ghi log URL)."""
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_async_engine(to_async_url(url), pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def session_scope(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Một use case = một transaction: commit khi xong, rollback khi có lỗi (09 mục 5)."""
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def advisory_lock(session: object, key: str) -> None:
    """Lấy khóa giao dịch theo chuỗi `key`; tự nhả khi commit/rollback. TODO(#M5-locks)."""
    raise NotImplementedError


def lock_keys_in_order(warehouse_ids: list[int], product_ids: list[int], dates: list[str]) -> list[str]:
    """Sinh danh sách key khóa theo thứ tự cố định kho → sản phẩm → ngày (tránh deadlock)."""
    keys: list[str] = []
    for w in sorted(warehouse_ids):
        keys += [f"stock:{w}:{p}" for p in sorted(product_ids)]
        keys += [f"labour:{w}:{d}" for d in sorted(dates)]
    return keys
