"""FastAPI dependencies dùng chung.

- get_db(): AsyncSession theo request (một use case một transaction, 09 mục 5).
- get_current_user(): giải JWT → CurrentUser(roles, location_ids, kpi_scopes).
- require_kpi_scope("ops"): KPI vận hành và nhật ký chỉ cho admin hoặc người có scope `ops` (06 mục 3.1).
- require_roles(*roles): kiểm vai trò ở máy chủ (06 mục 3).
- scope_filter(): giới hạn dữ liệu theo phạm vi địa điểm; ngoài phạm vi → 404 (06 mục 1). TODO(#M1-scope)
- idempotency(): bắt buộc header Idempotency-Key cho endpoint ghi ở 06 mục 1. TODO(#M5-idempotency)

Vai trò/phạm vi lấy từ DB mỗi request (không chỉ tin token), nên khóa tài khoản có hiệu lực ngay
(US-EMP-03 AC4).

Owner: Dev 1 (luồng A) — M0.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker, session_scope
from app.core.errors import DomainError
from app.core.security import decode_token
from app.services.auth_service import UserProfile, load_active_profile

_bearer = HTTPBearer(auto_error=False, description="JWT from POST /auth/login")


@dataclass(frozen=True)
class CurrentUser:
    """Người dùng đã xác thực, lấy từ JWT (06 mục 4)."""

    id: int
    employee_id: int | None
    roles: tuple[str, ...]
    market: str
    location_ids: tuple[int, ...] = field(default_factory=tuple)
    kpi_scopes: tuple[str, ...] = field(default_factory=tuple)  # revenue_all | ops (không thêm vai trò mới)
    name: str | None = None
    locale: str = "en"

    def has_scope(self, scope: str) -> bool:
        """True nếu là admin hoặc có `scope` trong kpi_scopes."""
        return "admin" in self.roles or scope in self.kpi_scopes

    @classmethod
    def from_profile(cls, profile: UserProfile) -> "CurrentUser":
        return cls(
            id=profile.id,
            employee_id=profile.employee_id,
            roles=profile.roles,
            market=profile.market or "",
            location_ids=profile.location_ids,
            kpi_scopes=profile.kpi_scopes,
            name=profile.name,
            locale=profile.locale,
        )


async def get_db() -> AsyncIterator[AsyncSession]:
    """Session theo request: commit khi xử lý xong, rollback khi lỗi."""
    async for session in session_scope(get_sessionmaker()):
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """Giải và kiểm JWT HS256 (hết hạn 8 giờ); tài khoản bị khóa → 401."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise DomainError("AUTH_INVALID", "Authentication required.")
    payload = decode_token(credentials.credentials)
    try:
        user_id = int(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise DomainError("AUTH_INVALID", "Invalid or expired token.") from exc
    return CurrentUser.from_profile(await load_active_profile(db, user_id))


AuthUser = Annotated[CurrentUser, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Trả dependency từ chối 403 FORBIDDEN nếu user không có một trong `roles`."""
    allowed = frozenset(roles)

    async def _dependency(user: AuthUser) -> CurrentUser:
        if not allowed.intersection(user.roles):
            raise DomainError("FORBIDDEN", "You do not have permission for this action.")
        return user

    return _dependency


def require_kpi_scope(scope: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Trả dependency từ chối 403 nếu user không phải admin và không có `scope`."""

    async def _dependency(user: AuthUser) -> CurrentUser:
        if not user.has_scope(scope):
            raise DomainError("FORBIDDEN", "You do not have permission for this action.")
        return user

    return _dependency
