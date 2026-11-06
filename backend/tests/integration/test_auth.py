"""/auth/* và RBAC trên PostgreSQL thật (06 mục 3–4; US-EMP-03 AC1, AC4)."""

import secrets
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

import jwt
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.core.config import get_settings
from app.core.db import session_scope, to_async_url
from app.core.security import hash_password, login_rate_limiter
from app.deps import CurrentUser, get_db, require_kpi_scope, require_roles
from app.main import create_app
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Ctx:
    client: TestClient
    dsn: str
    password: str  # sinh lúc chạy, không ghi vào mã (09 bất biến 25)


def _users(password_hash: str) -> tuple[str, ...]:
    return (
        *rows.REF_HR,
        # E1 = dispatcher, phân công hiệu lực tại location 1; phân công cũ (đã đóng) tại location 2
        "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date, end_date) "
        "VALUES (1, 2, '2025-01-01', '2025-12-31')",
        "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date) "
        "VALUES (1, 1, '2026-01-01')",
        f"UPDATE ref.app_user SET password_hash = '{password_hash}', kpi_scopes = '{{ops}}' WHERE id = 1",
        "INSERT INTO ref.app_user (employee_id, email, password_hash, roles) "
        f"VALUES (2, 'sales1@cfo.test', '{password_hash}', '{{sales}}')",
        "INSERT INTO ref.app_user (email, password_hash, roles, is_active) "
        f"VALUES ('inactive@cfo.test', '{password_hash}', '{{dispatcher}}', false)",
        "INSERT INTO ref.app_user (email, password_hash, roles) "
        f"VALUES ('admin@cfo.test', '{password_hash}', '{{admin}}')",
    )


DISPATCHER_ONLY = require_roles("dispatcher")
OPS_SCOPE = require_kpi_scope("ops")


def _probe_router() -> APIRouter:
    """Endpoint chỉ dùng trong test để kiểm dependency RBAC (không thuộc hợp đồng 06)."""
    probe = APIRouter()

    @probe.get("/_probe/dispatcher-only")
    async def dispatcher_only(user: Annotated[CurrentUser, Depends(DISPATCHER_ONLY)]) -> dict[str, int]:
        return {"id": user.id}

    @probe.get("/_probe/ops-kpi")
    async def ops_kpi(user: Annotated[CurrentUser, Depends(OPS_SCOPE)]) -> dict[str, int]:
        return {"id": user.id}

    return probe


@pytest.fixture
def ctx(empty_db: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Ctx]:
    command.upgrade(alembic_config(empty_db), "head")
    password = secrets.token_urlsafe(16)
    execute(empty_db, *_users(hash_password(password)))
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(32))
    get_settings.cache_clear()
    login_rate_limiter.reset()
    maker = async_sessionmaker(create_async_engine(to_async_url(empty_db), poolclass=NullPool))

    async def test_db() -> AsyncIterator[AsyncSession]:
        async for session in session_scope(maker):
            yield session

    app: FastAPI = create_app()
    app.include_router(_probe_router(), prefix="/api/v1")
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        yield Ctx(client, empty_db, password)
    login_rate_limiter.reset()
    get_settings.cache_clear()


def _login(ctx: Ctx, email: str = "user1@cfo.test", password: str | None = None) -> dict[str, object]:
    response = ctx.client.post(
        "/api/v1/auth/login", json={"email": email, "password": password or ctx.password}
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def _auth(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_error(response: object, status: int, code: str) -> None:
    assert response.status_code == status, response.text  # type: ignore[attr-defined]
    error = response.json()["error"]  # type: ignore[attr-defined]
    assert error["code"] == code and error["correlation_id"]


# --- đăng nhập ---------------------------------------------------------------------------------------


def test_US_EMP_03_AC1_login_returns_8h_jwt_with_roles_and_location_ids(ctx: Ctx) -> None:
    body = _login(ctx, email="USER1@cfo.test")  # email không phân biệt hoa thường
    assert body["token_type"] == "bearer" and body["expires_in"] == 8 * 3600
    assert body["user"] == {
        "id": 1,
        "employee_id": 1,
        "name": "Test One",
        "roles": ["dispatcher"],
        "market": "SE",
        "location_ids": [1],  # chỉ phân công đang hiệu lực
        "locale": "en",
        "kpi_scopes": ["ops"],
    }
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})  # type: ignore[arg-type]
    assert (
        claims["roles"] == ["dispatcher"]
        and claims["location_ids"] == [1]
        and claims["kpi_scopes"] == ["ops"]
    )
    assert claims["exp"] - claims["iat"] == 8 * 3600


def test_login_wrong_password_or_unknown_email_401(ctx: Ctx) -> None:
    for email, password in (("user1@cfo.test", ctx.password + "x"), ("nobody@cfo.test", ctx.password)):
        response = ctx.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        _assert_error(response, 401, "AUTH_INVALID")
        assert response.json()["error"]["message"] == "Invalid email or password."


def test_login_inactive_account_401(ctx: Ctx) -> None:
    response = ctx.client.post(
        "/api/v1/auth/login", json={"email": "inactive@cfo.test", "password": ctx.password}
    )
    _assert_error(response, 401, "AUTH_INVALID")


def test_login_more_than_5_per_minute_429(ctx: Ctx) -> None:
    for _ in range(5):
        ctx.client.post("/api/v1/auth/login", json={"email": "user1@cfo.test", "password": "wrong"})
    response = ctx.client.post(
        "/api/v1/auth/login", json={"email": "user1@cfo.test", "password": ctx.password}
    )
    assert response.status_code == 429


# --- /auth/me ----------------------------------------------------------------------------------------


def test_auth_me_returns_contract_user(ctx: Ctx) -> None:
    body = _login(ctx)
    response = ctx.client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert response.status_code == 200 and response.json() == body["user"]
    assert response.headers["X-Correlation-ID"]


def test_auth_me_system_account_without_employee(ctx: Ctx) -> None:
    body = _login(ctx, email="admin@cfo.test")
    me = ctx.client.get("/api/v1/auth/me", headers=_auth(body["access_token"])).json()
    assert me["roles"] == ["admin"] and me["employee_id"] is None and me["location_ids"] == []


def test_auth_me_rejects_missing_invalid_forged_and_expired_tokens(ctx: Ctx) -> None:
    token = _login(ctx)["access_token"]
    forged = jwt.encode({"sub": "1", "exp": 4102444800}, secrets.token_urlsafe(32), algorithm="HS256")
    for headers in ({}, _auth("garbage"), _auth(forged), {"Authorization": f"Basic {token}"}):
        _assert_error(ctx.client.get("/api/v1/auth/me", headers=headers), 401, "AUTH_INVALID")
    clock.set_now(clock.now() + timedelta(hours=8))
    _assert_error(ctx.client.get("/api/v1/auth/me", headers=_auth(token)), 401, "AUTH_INVALID")


def test_US_EMP_03_AC4_deactivated_or_terminated_user_token_rejected_next_call(ctx: Ctx) -> None:
    token = _login(ctx)["access_token"]
    assert ctx.client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 200
    execute(ctx.dsn, "UPDATE hr.employee SET status = 'terminated' WHERE id = 1")
    _assert_error(ctx.client.get("/api/v1/auth/me", headers=_auth(token)), 401, "AUTH_INVALID")
    execute(ctx.dsn, "UPDATE hr.employee SET status = 'active' WHERE id = 1")
    execute(ctx.dsn, "UPDATE ref.app_user SET is_active = false WHERE id = 1")
    _assert_error(ctx.client.get("/api/v1/auth/me", headers=_auth(token)), 401, "AUTH_INVALID")


def test_auth_me_reflects_current_roles_in_db(ctx: Ctx) -> None:
    token = _login(ctx)["access_token"]
    execute(ctx.dsn, "UPDATE ref.app_user SET roles = '{viewer}', kpi_scopes = '{}' WHERE id = 1")
    me = ctx.client.get("/api/v1/auth/me", headers=_auth(token)).json()
    assert me["roles"] == ["viewer"] and me["kpi_scopes"] == []


def test_logout_requires_auth_and_returns_204(ctx: Ctx) -> None:
    token = _login(ctx)["access_token"]
    assert ctx.client.post("/api/v1/auth/logout", headers=_auth(token)).status_code == 204
    _assert_error(ctx.client.post("/api/v1/auth/logout"), 401, "AUTH_INVALID")


# --- RBAC (06 mục 3: kiểm ở máy chủ) -----------------------------------------------------------------


def test_require_roles_allows_role_and_forbids_others(ctx: Ctx) -> None:
    dispatcher = _login(ctx)["access_token"]
    sales = _login(ctx, email="sales1@cfo.test")["access_token"]
    assert ctx.client.get("/api/v1/_probe/dispatcher-only", headers=_auth(dispatcher)).status_code == 200
    _assert_error(ctx.client.get("/api/v1/_probe/dispatcher-only", headers=_auth(sales)), 403, "FORBIDDEN")
    _assert_error(ctx.client.get("/api/v1/_probe/dispatcher-only"), 401, "AUTH_INVALID")


def test_require_kpi_scope_ops_admin_or_scope_only(ctx: Ctx) -> None:
    dispatcher = _login(ctx)["access_token"]  # kpi_scopes = {ops}
    admin = _login(ctx, email="admin@cfo.test")["access_token"]
    sales = _login(ctx, email="sales1@cfo.test")["access_token"]
    assert ctx.client.get("/api/v1/_probe/ops-kpi", headers=_auth(dispatcher)).status_code == 200
    assert ctx.client.get("/api/v1/_probe/ops-kpi", headers=_auth(admin)).status_code == 200
    _assert_error(ctx.client.get("/api/v1/_probe/ops-kpi", headers=_auth(sales)), 403, "FORBIDDEN")
