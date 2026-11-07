"""Alembic environment.

Đọc DATABASE_URL từ app.core.config.Settings (hoặc `sqlalchemy.url` do test truyền vào). Mỗi migration
một ý, có upgrade/downgrade (09 mục 6). Thứ tự: 0001_extensions_schemas_enums → 0002_ref → 0003_hr →
0004_stg → 0005_ops → 0006_plan → 0007_audit_views_triggers → 0008_seed_reference (05 mục 11).

Migration viết TAY từ docs/05 (không autogenerate mù); target_metadata chỉ để tham chiếu.
Không in URL ra log (chứa mật khẩu — 09 bất biến 25).

Owner: Dev 1 (luồng A).
"""

import asyncio

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.core.db import to_async_url
from app.domain.models.base import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """URL từ cấu hình alembic (test) hoặc biến môi trường DATABASE_URL; thiếu → dừng rõ ràng."""
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return to_async_url(url)


def run_migrations_offline() -> None:
    """Sinh SQL không cần kết nối (alembic upgrade --sql)."""
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Chạy migration qua async engine; mỗi migration một transaction."""
    engine = create_async_engine(database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
