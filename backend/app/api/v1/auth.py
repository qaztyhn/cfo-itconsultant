"""Xác thực (06 mục 4).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M0.
"""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import log_event
from app.core.security import issue_token, login_rate_limiter, token_ttl
from app.deps import AuthUser, CurrentUser, DbSession
from app.services.auth_service import UserProfile, authenticate

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"email": "dispatcher1@cfo.test", "password": "********"}]}
    )

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    """`user` trong 06 mục 4 (cũng là phản hồi GET /auth/me)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 12,
                    "employee_id": 55,
                    "name": "Anna Lind",
                    "roles": ["dispatcher"],
                    "market": "SE",
                    "location_ids": [7],
                    "locale": "en",
                    "kpi_scopes": ["ops"],
                }
            ]
        }
    )

    id: int
    employee_id: int | None
    name: str | None
    roles: list[str]
    market: str | None
    location_ids: list[int]
    locale: str
    kpi_scopes: list[str]

    @classmethod
    def of(cls, user: UserProfile | CurrentUser) -> "UserOut":
        return cls(
            id=user.id,
            employee_id=user.employee_id,
            name=user.name,
            roles=list(user.roles),
            market=user.market or None,
            location_ids=list(user.location_ids),
            locale=user.locale,
            kpi_scopes=list(user.kpi_scopes),
        )


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    responses={401: {"description": "AUTH_INVALID"}, 429: {"description": "Too many attempts"}},
)
async def login(body: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    """POST /auth/login — Đổi email/mật khẩu lấy JWT; sai → 401 AUTH_INVALID; > 5 lần/phút → 429."""
    login_rate_limiter.hit(request.client.host if request.client else "unknown")
    profile = await authenticate(db, body.email, body.password)
    log_event("api", "auth.login", user_id=profile.id)
    return LoginResponse(
        access_token=issue_token(profile.id, profile.claims()),
        expires_in=int(token_ttl().total_seconds()),
        user=UserOut.of(profile),
    )


@router.get("/auth/me", response_model=UserOut, responses={401: {"description": "AUTH_INVALID"}})
async def me(user: AuthUser) -> UserOut:
    """GET /auth/me — Thông tin người dùng, vai trò, địa điểm, kpi_scopes."""
    return UserOut.of(user)


@router.post("/auth/logout", status_code=204, responses={401: {"description": "AUTH_INVALID"}})
async def logout(user: AuthUser) -> Response:
    """POST /auth/logout — No-op phía server, ghi log."""
    log_event("api", "auth.logout", user_id=user.id)
    return Response(status_code=204)
