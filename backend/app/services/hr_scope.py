"""Phạm vi đọc nhân sự, địa điểm, xe theo vai trò và địa điểm (06 mục 13.1; quyết định Q2/Q3 PR #12).

- Vai trò được đọc: admin > dispatcher > warehouse (người nhiều vai trò dùng vai trò rộng nhất); khác → 403.
- Market: dispatcher/warehouse theo market của nhân viên; admin gắn nhân viên theo market của mình;
  admin hệ thống (không gắn nhân viên) mọi market.
- Warehouse: địa điểm có phân công hiệu lực hôm nay (`CurrentUser.location_ids`, tính ở auth theo ngày
  hiệu lực).
- `today` theo múi giờ market (09 bất biến 17) để kiểm ngày hiệu lực của phân công/quản lý.

Owner: Dev 1 (A) — M1.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.domain.models.ref import Market

ReadRole = Literal["admin", "dispatcher", "warehouse"]
_PRECEDENCE: tuple[ReadRole, ...] = ("admin", "dispatcher", "warehouse")


class HrReader(Protocol):
    """Thuộc tính tối thiểu của người gọi (app.deps.CurrentUser thỏa giao diện này)."""

    @property
    def roles(self) -> tuple[str, ...]: ...

    @property
    def market(self) -> str: ...

    @property
    def location_ids(self) -> tuple[int, ...]: ...


@dataclass(frozen=True)
class HrReadScope:
    role: ReadRole
    market_id: int | None  # None = mọi market (chỉ admin hệ thống)
    location_ids: frozenset[int]  # chỉ dùng cho warehouse
    today: date


def _forbidden() -> DomainError:
    return DomainError("FORBIDDEN", "You do not have permission to read this resource.")


async def resolve_hr_scope(session: AsyncSession, user: HrReader) -> HrReadScope:
    """Vai trò đọc, market và địa điểm được phép của người gọi; không có quyền → 403 FORBIDDEN."""
    role = next((r for r in _PRECEDENCE if r in user.roles), None)
    if role is None:
        raise _forbidden()
    market = None
    if user.market:
        market = (
            await session.execute(select(Market).where(Market.code == user.market))
        ).scalar_one_or_none()
    if market is None and role != "admin":
        raise _forbidden()
    tz = ZoneInfo(market.timezone) if market is not None else ZoneInfo("UTC")
    return HrReadScope(
        role=role,
        market_id=market.id if market is not None else None,
        location_ids=frozenset(user.location_ids) if role == "warehouse" else frozenset(),
        today=clock.now().astimezone(tz).date(),
    )
