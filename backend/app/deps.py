"""FastAPI dependencies dùng chung.

- get_db(): AsyncSession theo request (một use case một transaction, 09 mục 5).
- get_current_user(): giải JWT → CurrentUser(roles, location_ids, kpi_scopes).
- require_kpi_scope("ops"): KPI vận hành và nhật ký chỉ cho admin hoặc người có scope `ops` (06 mục 3.1).
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
    kpi_scopes: tuple[str, ...] = field(default_factory=tuple)  # revenue_all | ops (không thêm vai trò mới)

    def has_scope(self, scope: str) -> bool:
        """True nếu là admin hoặc có `scope` trong kpi_scopes."""
        return "admin" in self.roles or scope in self.kpi_scopes


async def get_current_user() -> CurrentUser:
    """Giải và kiểm JWT HS256 (hết hạn 8 giờ); tài khoản bị khóa → 401. TODO(#M0-auth)."""
    raise NotImplementedError


def require_roles(*roles: str) -> Callable[..., object]:
    """Trả dependency từ chối 403 FORBIDDEN nếu user không có một trong `roles`. TODO(#M0-auth)."""
    raise NotImplementedError


def require_kpi_scope(scope: str) -> Callable[..., object]:
    """Trả dependency từ chối 403 nếu user không phải admin và không có `scope`. TODO(#M8-kpi)."""
    raise NotImplementedError
