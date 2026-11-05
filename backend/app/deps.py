"""FastAPI dependencies dùng chung.

- get_db(): AsyncSession theo request (một use case một transaction, 09 mục 5).
- get_current_user(): giải JWT → CurrentUser(roles, location_ids, can_view_revenue).
- require_roles(*roles): kiểm vai trò ở máy chủ (06 mục 3).
- scope_filter(): giới hạn dữ liệu theo phạm vi địa điểm; ngoài phạm vi → 404 (06 mục 1).
- idempotency(): bắt buộc header Idempotency-Key cho endpoint ghi ở 06 mục 1.

Owner: Dev 1 (luồng A) — M0.
"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CurrentUser:
    """Người dùng đã xác thực, lấy từ JWT (06 mục 4)."""

    id: int
    employee_id: int | None
    roles: tuple[str, ...]
    market: str
    location_ids: tuple[int, ...] = field(default_factory=tuple)
    can_view_revenue: bool = False


async def get_current_user() -> CurrentUser:
    """Giải và kiểm JWT HS256 (hết hạn 8 giờ); tài khoản bị khóa → 401. TODO(#M0-auth)."""
    raise NotImplementedError


def require_roles(*roles: str) -> Callable[..., object]:
    """Trả dependency từ chối 403 FORBIDDEN nếu user không có một trong `roles`. TODO(#M0-auth)."""
    raise NotImplementedError
