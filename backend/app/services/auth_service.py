"""Xác thực người dùng và dựng hồ sơ phiên (06 mục 4; US-EMP-03 AC1, AC4).

- Đăng nhập: email (không phân biệt hoa thường) + mật khẩu argon2. Sai email, sai mật khẩu, tài khoản khóa
  hoặc nhân viên `terminated` đều trả cùng một lỗi 401 AUTH_INVALID (không lộ tài khoản nào tồn tại).
- Hồ sơ luôn đọc lại từ DB ở mỗi request (không tin vai trò cũ trong token): tài khoản bị khóa thì token đang
  dùng bị từ chối ngay lần gọi kế tiếp (US-EMP-03 AC4).
- location_ids = địa điểm của phân công đang hiệu lực (hôm nay theo múi giờ market — 09 bất biến 17).
- Truy vấn tham số hóa (09 mục 6). Model SQLAlchemy thuộc M1 nên dùng SQL text tối thiểu ở đây.

Owner: Dev 1 (luồng A) — M0.
"""

from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.core.security import hash_password, verify_password

_INVALID = "Invalid email or password."

_USER_SQL = """
SELECT u.id, u.employee_id, u.email, u.password_hash, u.roles::text[] AS roles, u.kpi_scopes, u.is_active,
       e.first_name, e.last_name, e.status::text AS employee_status,
       m.code AS market, m.locale, m.timezone
FROM ref.app_user u
LEFT JOIN hr.employee e ON e.id = u.employee_id
LEFT JOIN ref.market m ON m.id = e.market_id
WHERE {where}
"""

_LOCATIONS_SQL = """
SELECT location_id FROM hr.employee_assignment
WHERE employee_id = :employee_id AND start_date <= :today AND (end_date IS NULL OR end_date >= :today)
ORDER BY location_id
"""


@dataclass(frozen=True)
class UserProfile:
    """Thông tin phiên của người dùng (khớp `user` trong 06 mục 4)."""

    id: int
    employee_id: int | None
    name: str | None
    roles: tuple[str, ...]
    market: str | None
    location_ids: tuple[int, ...]
    locale: str
    kpi_scopes: tuple[str, ...]

    def claims(self) -> dict[str, object]:
        """Claims JWT (06 mục 4): roles, employee_id, location_ids, market, kpi_scopes."""
        return {
            "roles": list(self.roles),
            "employee_id": self.employee_id,
            "location_ids": list(self.location_ids),
            "market": self.market,
            "kpi_scopes": list(self.kpi_scopes),
        }


@lru_cache
def _dummy_hash() -> str:
    # Băm một giá trị ngẫu nhiên để thời gian xử lý email không tồn tại gần bằng email tồn tại.
    import secrets

    return hash_password(secrets.token_urlsafe(16))


async def _profile(session: AsyncSession, row: object) -> UserProfile:
    r = row._mapping  # type: ignore[attr-defined]
    location_ids: tuple[int, ...] = ()
    if r["employee_id"] is not None:
        today = clock.now().astimezone(ZoneInfo(r["timezone"] or "UTC")).date()
        result = await session.execute(
            text(_LOCATIONS_SQL), {"employee_id": r["employee_id"], "today": today}
        )
        location_ids = tuple(int(x) for x in result.scalars())
    name = f"{r['first_name']} {r['last_name']}" if r["first_name"] is not None else None
    return UserProfile(
        id=int(r["id"]),
        employee_id=r["employee_id"],
        name=name,
        roles=tuple(r["roles"]),
        market=r["market"].strip() if r["market"] else None,
        location_ids=location_ids,
        locale=r["locale"] or "en",
        kpi_scopes=tuple(r["kpi_scopes"]),
    )


def _is_usable(row: object) -> bool:
    r = row._mapping  # type: ignore[attr-defined]
    return bool(r["is_active"]) and r["employee_status"] != "terminated"


async def authenticate(session: AsyncSession, email: str, password: str) -> UserProfile:
    """Kiểm email/mật khẩu; đúng → cập nhật last_login_at và trả hồ sơ; sai → 401 AUTH_INVALID."""
    result = await session.execute(
        text(_USER_SQL.format(where="lower(u.email) = lower(:email)")), {"email": email.strip()}
    )
    row = result.first()
    if row is None:
        verify_password(password, _dummy_hash())
        raise DomainError("AUTH_INVALID", _INVALID)
    if not verify_password(password, row._mapping["password_hash"]) or not _is_usable(row):
        raise DomainError("AUTH_INVALID", _INVALID)
    await session.execute(
        text("UPDATE ref.app_user SET last_login_at = :now WHERE id = :id"),
        {"now": clock.now(), "id": row._mapping["id"]},
    )
    return await _profile(session, row)


async def load_active_profile(session: AsyncSession, user_id: int) -> UserProfile:
    """Hồ sơ hiện tại từ DB cho một token hợp lệ; không còn tồn tại/bị khóa → 401 AUTH_INVALID."""
    result = await session.execute(text(_USER_SQL.format(where="u.id = :id")), {"id": user_id})
    row = result.first()
    if row is None or not _is_usable(row):
        raise DomainError("AUTH_INVALID", "Invalid or expired token.")
    return await _profile(session, row)
