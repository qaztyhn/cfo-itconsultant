"""Fixture PostgreSQL thật cho integration test (09 mục 11: không mock DB cho ràng buộc/trigger).

Đặt `TEST_DATABASE_URL` trỏ tới một server PostgreSQL 16 mà user có quyền CREATE DATABASE
(ví dụ service postgres trong CI). Mỗi phiên test tạo một database TRỐNG tên ngẫu nhiên và xóa khi xong,
nên không bao giờ đụng vào dữ liệu có sẵn. Thiếu biến → test integration bị bỏ qua kèm lý do rõ ràng
(không phải "xanh giả": báo cáo phải ghi NOT VERIFIED).
"""

import asyncio
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DB_ENV = "TEST_DATABASE_URL"


def _plain_dsn(url: str) -> str:
    """asyncpg cần DSN `postgresql://` (không có hậu tố driver SQLAlchemy)."""
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def _with_database(dsn: str, dbname: str) -> str:
    base, _, query = dsn.partition("?")
    base = base.rsplit("/", 1)[0] + "/" + dbname
    return f"{base}?{query}" if query else base


async def _admin_exec(dsn: str, sql: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def server_dsn() -> str:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} not set: PostgreSQL integration tests NOT VERIFIED")
    return _plain_dsn(url)


@pytest.fixture
def empty_db(server_dsn: str) -> Iterator[str]:
    """DSN của một database PostgreSQL trống, tạo riêng cho test và xóa sau đó."""
    name = f"cfo_it_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(server_dsn, f'CREATE DATABASE "{name}"'))
    try:
        yield _with_database(server_dsn, name)
    finally:
        asyncio.run(_admin_exec(server_dsn, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def alembic_config(dsn: str) -> Config:
    """Config alembic trỏ vào DB test (không đọc DATABASE_URL của môi trường).

    Alembic lưu option qua ConfigParser có nội suy `%(...)s`, nên `%` trong DSN (mật khẩu URL-encode như
    `%40`) phải escape thành `%%`; `get_main_option` trả lại đúng DSN gốc.
    """
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    return cfg


def fetch(dsn: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    """Chạy một truy vấn đọc đồng bộ (test migration là hàm sync vì alembic tự chạy event loop)."""

    async def _run() -> list[asyncpg.Record]:
        conn = await asyncpg.connect(dsn)
        try:
            return list(await conn.fetch(sql, *args))
        finally:
            await conn.close()

    return asyncio.run(_run())


def execute(dsn: str, *statements: str) -> None:
    """Chạy các lệnh ghi trong MỘT transaction (lỗi ràng buộc → asyncpg exception, rollback)."""

    async def _run() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            async with conn.transaction():
                for statement in statements:
                    await conn.execute(statement)
        finally:
            await conn.close()

    asyncio.run(_run())
