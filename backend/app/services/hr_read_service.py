"""Truy vấn đọc nhân sự, địa điểm, xe theo phạm vi (06 mục 13.1; quyết định Q1–Q4 PR #12).

Mọi hàm nhận `HrReadScope` đã giải ở `hr_scope.resolve_hr_scope`. Ngoài phạm vi hoặc không tồn tại → 404.
Ngày hiệu lực (hôm nay theo market): phân công start_date ≤ d ≤ end_date|null;
quản lý valid_from ≤ d ≤ valid_to|null.
Không ghi tên/email/điện thoại nhân viên vào log (09 bất biến 16).

Owner: Dev 1 (A) — M1.
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.domain.models.hr import Employee, LocationManager
from app.domain.models.ref import Location, Market
from app.services.hr_scope import HrReadScope
from app.services.query_utils import parse_sort

LOCATION_SORT = {"code": Location.code, "name": Location.name, "type": Location.type}
LOCATION_TYPES = frozenset({"warehouse", "store", "dispatch_center", "head_office"})


def not_found(entity: str) -> DomainError:
    return DomainError("NOT_FOUND", f"{entity} not found.")


def _person(employee_id: int | None, names: dict[int, str]) -> dict[str, object] | None:
    if employee_id is None or employee_id not in names:
        return None
    return {"employee_id": employee_id, "name": names[employee_id]}


async def _names(session: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await session.execute(
        select(Employee.id, Employee.first_name, Employee.last_name).where(Employee.id.in_(ids))
    )
    return {i: f"{first} {last}" for i, first, last in rows.all()}


def manager_effective(d: date) -> ColumnElement[bool]:
    return and_(
        LocationManager.valid_from <= d,
        or_(LocationManager.valid_to.is_(None), LocationManager.valid_to >= d),
    )


def _location_scope(query: Select[Location, str], scope: HrReadScope) -> Select[Location, str]:
    if scope.market_id is not None:
        query = query.where(Location.market_id == scope.market_id)
    if scope.role == "warehouse":
        query = query.where(Location.id.in_(scope.location_ids))
    return query


async def _location_views(
    session: AsyncSession, scope: HrReadScope, rows: Sequence[tuple[Location, str]]
) -> list[dict[str, object]]:
    ids = [loc.id for loc, _ in rows]
    managers: dict[tuple[int, str], int] = {}
    if ids:
        result = await session.execute(
            select(LocationManager.location_id, LocationManager.level, LocationManager.employee_id)
            .where(LocationManager.location_id.in_(ids), manager_effective(scope.today))
            .order_by(LocationManager.valid_from.desc(), LocationManager.id.desc())
        )
        for loc_id, level, emp_id in result.all():
            managers.setdefault((loc_id, level), emp_id)
    owner_ids = {loc.owner_employee_id for loc, _ in rows if loc.owner_employee_id is not None}
    names = await _names(session, owner_ids | set(managers.values()))
    views: list[dict[str, object]] = []
    for loc, market_code in rows:
        views.append(
            {
                "id": loc.id,
                "market": market_code.strip(),
                "type": loc.type,
                "code": loc.code,
                "name": loc.name,
                "address": loc.address,
                "lat": float(loc.lat) if loc.lat is not None else None,
                "lon": float(loc.lon) if loc.lon is not None else None,
                "loading_cutoff_time": (
                    loc.loading_cutoff_time.strftime("%H:%M") if loc.loading_cutoff_time else None
                ),
                "is_active": loc.is_active,
                "owner": _person(loc.owner_employee_id, names),
                "managers": {
                    "primary": _person(managers.get((loc.id, "primary")), names),
                    "deputy": _person(managers.get((loc.id, "deputy")), names),
                },
            }
        )
    return views


async def list_locations(
    session: AsyncSession,
    scope: HrReadScope,
    *,
    type_: str | None,
    is_active: bool,
    q: str | None,
    sort: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], int]:
    """Danh sách địa điểm trong phạm vi (mặc định đang hoạt động), lọc type/q, sắp xếp, phân trang."""
    if type_ is not None and type_ not in LOCATION_TYPES:
        raise DomainError("VALIDATION_ERROR", f"Unknown location type '{type_}'.")
    order = parse_sort(sort, frozenset(LOCATION_SORT), "code")
    query = _location_scope(
        select(Location, Market.code).join(Market, Market.id == Location.market_id), scope
    ).where(Location.is_active.is_(is_active))
    if type_ is not None:
        query = query.where(Location.type == type_)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Location.code.ilike(pattern), Location.name.ilike(pattern)))
    columns = [LOCATION_SORT[f].desc() if desc else LOCATION_SORT[f].asc() for f, desc in order]
    query = query.order_by(*columns, Location.id)
    total = (
        await session.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    ).scalar_one()
    rows = (await session.execute(query.limit(page_size).offset((page - 1) * page_size))).all()
    return await _location_views(session, scope, [(loc, code) for loc, code in rows]), int(total)


async def get_location(session: AsyncSession, scope: HrReadScope, location_id: int) -> dict[str, object]:
    """Một địa điểm trong phạm vi; không tồn tại hoặc ngoài phạm vi → 404."""
    query = _location_scope(
        select(Location, Market.code).join(Market, Market.id == Location.market_id), scope
    ).where(Location.id == location_id)
    row = (await session.execute(query)).first()
    if row is None:
        raise not_found("Location")
    return (await _location_views(session, scope, [(row[0], row[1])]))[0]
