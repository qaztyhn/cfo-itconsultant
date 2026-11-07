"""Hạ tầng test API trên PostgreSQL: app với get_db trỏ vào DB test, token JWT phát trực tiếp.

Hồ sơ người dùng vẫn được đọc lại từ DB qua get_current_user (vai trò, phạm vi, phân công hiệu lực).
Bí mật JWT sinh lúc chạy, không ghi vào mã (09 bất biến 25).
"""

import secrets
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings
from app.core.db import session_scope, to_async_url
from app.core.security import issue_token
from app.deps import get_db
from app.main import create_app
from tests.integration.conftest import alembic_config


@dataclass(frozen=True)
class Api:
    client: TestClient
    dsn: str

    def get(self, path: str, user_id: int | None, **params: object) -> Response:
        headers = {"Authorization": f"Bearer {issue_token(user_id, {})}"} if user_id is not None else {}
        response: Response = self.client.get(f"/api/v1{path}", headers=headers, params=params)
        return response

    def send(self, method: str, path: str, user_id: int | None, body: object = None) -> Response:
        """POST/PUT/PATCH với thân JSON (body None → không gửi thân)."""
        headers = {"Authorization": f"Bearer {issue_token(user_id, {})}"} if user_id is not None else {}
        response: Response = self.client.request(method, f"/api/v1{path}", headers=headers, json=body)
        return response


@pytest.fixture
def api(empty_db: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Api]:
    command.upgrade(alembic_config(empty_db), "head")
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(32))
    get_settings.cache_clear()
    maker = async_sessionmaker(create_async_engine(to_async_url(empty_db), poolclass=NullPool))

    async def test_db() -> AsyncIterator[AsyncSession]:
        async for session in session_scope(maker):
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        yield Api(client, empty_db)
    get_settings.cache_clear()


def assert_error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
