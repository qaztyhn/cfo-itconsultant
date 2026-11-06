"""Xác thực (06 mục 4).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M0.
"""

from fastapi import APIRouter

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
async def login() -> dict[str, object]:
    """POST /auth/login — Đổi email/mật khẩu lấy JWT; sai → 401 AUTH_INVALID; > 5 lần/phút → 429."""
    raise NotImplementedError


@router.get("/auth/me")
async def me() -> dict[str, object]:
    """GET /auth/me — Thông tin người dùng, vai trò, địa điểm, kpi_scopes."""
    raise NotImplementedError


@router.post("/auth/logout")
async def logout() -> dict[str, object]:
    """POST /auth/logout — No-op phía server, ghi log."""
    raise NotImplementedError
