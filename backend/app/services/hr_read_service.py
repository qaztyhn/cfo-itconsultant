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
from app.domain.models.hr import (
    CsStaff,
    DispatcherStaff,
    DriverStaff,
    Employee,
    EmployeeAssignment,
    LocationManager,
    Position,
    SalesStaff,
    WarehouseStaff,
)
from app.domain.models.ref import HandlingGroup, Location, Market, Vehicle
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


# --- nhân viên (06 mục 13.1; Q4 = C có điều chỉnh) ------------------------------------------------------

EMPLOYEE_STATUSES = frozenset({"active", "on_leave", "terminated"})
_EMPLOYEE_SORT_BASE = {
    "last_name": Employee.last_name,
    "first_name": Employee.first_name,
    "position_code": Employee.position_code,
}
_EMPLOYEE_SORT_ADMIN = {
    **_EMPLOYEE_SORT_BASE,
    "employee_no": Employee.employee_no,
    "hire_date": Employee.hire_date,
}


def assignment_effective(d: date) -> ColumnElement[bool]:
    return and_(
        EmployeeAssignment.start_date <= d,
        or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= d),
    )


def _assigned_at(locations: frozenset[int] | set[int], d: date) -> ColumnElement[bool]:
    """Nhân viên có phân công hiệu lực ngày `d` tại một trong `locations`."""
    return (
        select(EmployeeAssignment.id)
        .where(
            EmployeeAssignment.employee_id == Employee.id,
            EmployeeAssignment.location_id.in_(locations),
            assignment_effective(d),
        )
        .exists()
    )


def _employee_scope(query: Select[Employee, str], scope: HrReadScope) -> Select[Employee, str]:
    if scope.market_id is not None:
        query = query.where(Employee.market_id == scope.market_id)
    if scope.role != "admin":
        query = query.where(Employee.status != "terminated")
    if scope.role == "warehouse":
        query = query.where(_assigned_at(scope.location_ids, scope.today))
    return query


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _employee_views(
    session: AsyncSession, scope: HrReadScope, rows: Sequence[tuple[Employee, str]], *, detail: bool
) -> list[dict[str, object]]:
    ids = [e.id for e, _ in rows]
    current: dict[int, dict[str, object]] = {}
    history: dict[int, list[dict[str, object]]] = {i: [] for i in ids}
    if ids:
        assignments = await session.execute(
            select(EmployeeAssignment, Location.code, Location.name)
            .join(Location, Location.id == EmployeeAssignment.location_id)
            .where(EmployeeAssignment.employee_id.in_(ids))
            .order_by(EmployeeAssignment.start_date.desc(), EmployeeAssignment.id.desc())
        )
        for a, code, name in assignments.all():
            effective = a.start_date <= scope.today and (a.end_date is None or a.end_date >= scope.today)
            if effective and a.employee_id not in current:
                current[a.employee_id] = {
                    "location_id": a.location_id,
                    "location_code": code,
                    "location_name": name,
                    "start_date": a.start_date.isoformat(),
                }
            history[a.employee_id].append(
                {"location_id": a.location_id, "location_code": code, "start_date": a.start_date.isoformat(),
                 "end_date": _iso(a.end_date)}
            )  # fmt: skip
    staff = await _staff_blocks(session, scope, ids)
    views: list[dict[str, object]] = []
    for e, position_name in rows:
        view: dict[str, object] = {
            "id": e.id,
            "first_name": e.first_name,
            "last_name": e.last_name,
            "position": {"code": e.position_code, "name": position_name},
            "assignment": current.get(e.id),
        }
        for block, values in staff.items():
            view[block] = values.get(e.id)
        if scope.role == "admin":
            view |= {
                "employee_no": e.employee_no,
                "status": e.status,
                "employment_type": e.employment_type,
                "hire_date": e.hire_date.isoformat(),
                "end_date": _iso(e.end_date),
                "work_email": e.work_email,
                "work_phone": e.work_phone,
            }
            if detail:
                view |= {
                    "weekly_hours": float(e.weekly_hours),
                    "reports_to_employee_id": e.reports_to_employee_id,
                    "assignment_history": history.get(e.id, []),
                }
        views.append(view)
    return views


async def _staff_blocks(
    session: AsyncSession, scope: HrReadScope, ids: list[int]
) -> dict[str, dict[int, dict[str, object]]]:
    """Khối `*_staff` theo vai trò: admin cả 5; dispatcher driver_staff; warehouse warehouse_staff."""
    visible = {
        "admin": ("warehouse_staff", "sales_staff", "dispatcher_staff", "driver_staff", "cs_staff"),
        "dispatcher": ("driver_staff",),
        "warehouse": ("warehouse_staff",),
    }[scope.role]
    blocks: dict[str, dict[int, dict[str, object]]] = {name: {} for name in visible}
    if not ids:
        return blocks
    if "warehouse_staff" in blocks:
        for ws in (
            await session.execute(select(WarehouseStaff).where(WarehouseStaff.employee_id.in_(ids)))
        ).scalars():
            blocks["warehouse_staff"][ws.employee_id] = {
                "role": ws.role,
                "counts_in_capacity": ws.counts_in_capacity,
            }
    if "driver_staff" in blocks:
        for ds in (
            await session.execute(select(DriverStaff).where(DriverStaff.employee_id.in_(ids)))
        ).scalars():
            blocks["driver_staff"][ds.employee_id] = {
                "licence_class": ds.licence_class,
                "licence_expires_on": ds.licence_expires_on.isoformat(),
                "home_warehouse_id": ds.home_warehouse_id,
                "adr": ds.adr,
            }
    if "sales_staff" in blocks:
        for ss in (
            await session.execute(select(SalesStaff).where(SalesStaff.employee_id.in_(ids)))
        ).scalars():
            blocks["sales_staff"][ss.employee_id] = {"role": ss.role}
    if "dispatcher_staff" in blocks:
        result = await session.execute(select(DispatcherStaff).where(DispatcherStaff.employee_id.in_(ids)))
        for dsp in result.scalars():
            blocks["dispatcher_staff"][dsp.employee_id] = {"can_send_delay_notice": dsp.can_send_delay_notice}
    if "cs_staff" in blocks:
        for cs in (await session.execute(select(CsStaff).where(CsStaff.employee_id.in_(ids)))).scalars():
            blocks["cs_staff"][cs.employee_id] = {"team": cs.team}
    return blocks


def _employee_base() -> Select[Employee, str]:
    return select(Employee, Position.name).join(Position, Position.code == Employee.position_code)


async def list_employees(
    session: AsyncSession,
    scope: HrReadScope,
    *,
    position_code: str | None,
    location_id: int | None,
    status: str | None,
    q: str | None,
    sort: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], int]:
    """Danh sách nhân viên trong phạm vi; lọc vị trí, nơi phân công hiệu lực hôm nay, trạng thái, tên."""
    if status is not None and status not in EMPLOYEE_STATUSES:
        raise DomainError("VALIDATION_ERROR", f"Unknown employee status '{status}'.")
    sortable = _EMPLOYEE_SORT_ADMIN if scope.role == "admin" else _EMPLOYEE_SORT_BASE
    order = parse_sort(sort, frozenset(sortable), "last_name,first_name")
    query = _employee_scope(_employee_base(), scope)
    if position_code:
        query = query.where(Employee.position_code == position_code)
    if location_id is not None:
        query = query.where(_assigned_at({location_id}, scope.today))
    if status is not None:
        query = query.where(Employee.status == status)
    if q:
        pattern = f"%{q.strip()}%"
        conditions = [
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            (Employee.first_name + " " + Employee.last_name).ilike(pattern),
        ]
        if scope.role == "admin":
            conditions.append(Employee.employee_no.ilike(pattern))
        query = query.where(or_(*conditions))
    columns = [sortable[f].desc() if desc else sortable[f].asc() for f, desc in order]
    query = query.order_by(*columns, Employee.id)
    total = (
        await session.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    ).scalar_one()
    rows = (await session.execute(query.limit(page_size).offset((page - 1) * page_size))).all()
    return await _employee_views(session, scope, [(e, n) for e, n in rows], detail=False), int(total)


async def get_employee(session: AsyncSession, scope: HrReadScope, employee_id: int) -> dict[str, object]:
    """Một nhân viên trong phạm vi (admin có thêm trường chi tiết); không tồn tại/ngoài phạm vi → 404."""
    row = (
        await session.execute(_employee_scope(_employee_base(), scope).where(Employee.id == employee_id))
    ).first()
    if row is None:
        raise not_found("Employee")
    return (await _employee_views(session, scope, [(row[0], row[1])], detail=True))[0]


# --- xe (06 mục 13.1; Q2 = A) ----------------------------------------------------------------------------

VEHICLE_STATUSES = frozenset({"available", "maintenance", "retired"})
VEHICLE_SORT = {"code": Vehicle.code, "capacity_kg": Vehicle.capacity_kg, "status": Vehicle.status}


def _vehicle_base() -> Select[Vehicle, Location]:
    return select(Vehicle, Location).join(Location, Location.id == Vehicle.home_warehouse_id)


def _vehicle_scope(query: Select[Vehicle, Location], scope: HrReadScope) -> Select[Vehicle, Location]:
    if scope.market_id is not None:
        query = query.where(Location.market_id == scope.market_id)
    if scope.role == "warehouse":
        query = query.where(Vehicle.home_warehouse_id.in_(scope.location_ids))
    return query


async def _vehicle_views(
    session: AsyncSession, rows: Sequence[tuple[Vehicle, Location]]
) -> list[dict[str, object]]:
    group_ids = {g for v, _ in rows for g in v.allowed_group_ids}
    codes: dict[int, str] = {}
    if group_ids:
        result = await session.execute(
            select(HandlingGroup.id, HandlingGroup.code).where(HandlingGroup.id.in_(group_ids))
        )
        codes = {i: c for i, c in result.all()}
    return [
        {
            "id": v.id,
            "code": v.code,
            "plate": v.plate,
            "name": v.name,
            "home_warehouse": {"id": wh.id, "code": wh.code, "name": wh.name},
            "capacity_kg": float(v.capacity_kg),
            "capacity_m3": float(v.capacity_m3),
            "capabilities": list(v.capabilities),
            "required_licence": v.required_licence,
            "allowed_groups": [
                {"id": g, "code": codes[g]} for g in sorted(v.allowed_group_ids) if g in codes
            ],
            "status": v.status,
        }
        for v, wh in rows
    ]


async def list_vehicles(
    session: AsyncSession,
    scope: HrReadScope,
    *,
    home_warehouse_id: int | None,
    status: str | None,
    capability: str | None,
    sort: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], int]:
    """Danh sách xe trong phạm vi: dispatcher theo market, warehouse theo kho gốc thuộc nơi của mình."""
    if status is not None and status not in VEHICLE_STATUSES:
        raise DomainError("VALIDATION_ERROR", f"Unknown vehicle status '{status}'.")
    order = parse_sort(sort, frozenset(VEHICLE_SORT), "code")
    query = _vehicle_scope(_vehicle_base(), scope)
    if home_warehouse_id is not None:
        query = query.where(Vehicle.home_warehouse_id == home_warehouse_id)
    if status is not None:
        query = query.where(Vehicle.status == status)
    if capability:
        query = query.where(Vehicle.capabilities.contains([capability]))
    columns = [VEHICLE_SORT[f].desc() if desc else VEHICLE_SORT[f].asc() for f, desc in order]
    query = query.order_by(*columns, Vehicle.id)
    total = (
        await session.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    ).scalar_one()
    rows = (await session.execute(query.limit(page_size).offset((page - 1) * page_size))).all()
    return await _vehicle_views(session, [(v, wh) for v, wh in rows]), int(total)


async def get_vehicle(session: AsyncSession, scope: HrReadScope, vehicle_id: int) -> dict[str, object]:
    """Một xe trong phạm vi; không tồn tại hoặc ngoài phạm vi → 404."""
    row = (
        await session.execute(_vehicle_scope(_vehicle_base(), scope).where(Vehicle.id == vehicle_id))
    ).first()
    if row is None:
        raise not_found("Vehicle")
    return (await _vehicle_views(session, [(row[0], row[1])]))[0]
