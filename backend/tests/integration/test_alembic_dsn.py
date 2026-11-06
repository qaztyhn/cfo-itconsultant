"""DSN có ký tự `%` (mật khẩu URL-encode) phải đi qua Alembic ConfigParser nguyên vẹn."""

import asyncio
import secrets
import uuid
from collections.abc import Iterator
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from alembic.script import ScriptDirectory

from alembic import command
from tests.integration.conftest import _admin_exec, _with_database, alembic_config, fetch

ENCODED_DSN = "postgresql+asyncpg://cfo:p%40ss%25w0rd%3A@db.example:5432/cfo_test?ssl=prefer"


def test_alembic_config_keeps_percent_encoded_dsn() -> None:
    cfg = alembic_config(ENCODED_DSN)
    assert cfg.get_main_option("sqlalchemy.url") == ENCODED_DSN
    ScriptDirectory.from_config(cfg)  # đọc lại toàn bộ config không lỗi nội suy


def _dsn_for(server_dsn: str, user: str, password: str, dbname: str) -> str:
    parts = urlsplit(_with_database(server_dsn, dbname))
    host = parts.hostname or "localhost"
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}" + (
        f":{parts.port}" if parts.port else ""
    )
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@pytest.fixture
def percent_user_db(server_dsn: str) -> Iterator[str]:
    """Role tạm có mật khẩu chứa `@ % : /` (sinh lúc chạy, không ghi vào mã) và DB trống do role đó sở hữu."""
    suffix = uuid.uuid4().hex[:10]
    user, dbname = f"cfo_pct_{suffix}", f"cfo_pct_{suffix}"
    password = secrets.token_urlsafe(12) + "@%:/"
    literal = password.replace("'", "''")
    asyncio.run(_admin_exec(server_dsn, f"CREATE ROLE \"{user}\" LOGIN PASSWORD '{literal}'"))
    asyncio.run(_admin_exec(server_dsn, f'CREATE DATABASE "{dbname}" OWNER "{user}"'))
    try:
        yield _dsn_for(server_dsn, user, password, dbname)
    finally:
        asyncio.run(_admin_exec(server_dsn, f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        asyncio.run(_admin_exec(server_dsn, f'DROP ROLE IF EXISTS "{user}"'))


@pytest.mark.integration
def test_alembic_upgrade_with_percent_encoded_password(percent_user_db: str) -> None:
    assert "%40" in percent_user_db and "%25" in percent_user_db
    command.upgrade(alembic_config(percent_user_db), "0001")
    assert [r["version_num"] for r in fetch(percent_user_db, "SELECT version_num FROM alembic_version")] == [
        "0001"
    ]
