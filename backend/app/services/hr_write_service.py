"""Ghi nhân sự cho admin (06 mục 13; US-EMP-01 AC2–AC5, US-EMP-03 AC4; BR-EMP-01/02).

- assign(): chuyển công tác — đóng phân công đang mở (end_date = start_date − 1), mở phân công mới.
- terminate(): nghỉ việc — status terminated, khóa tài khoản, đóng phân công; giữ lịch sử (không xóa).
- set_managers(): quản lý chính/phó; người được gán phải có phân công hiệu lực tại nơi đó hôm nay (AC5);
  owner mặc định theo quản lý chính (AC4).
- set_owner(): admin gán lại owner.

Chỉ admin (resolve_hr_scope → role admin); bản ghi ngoài market của admin → 404. Vi phạm quy tắc → 422
VALIDATION_ERROR kèm details.field (06 mục 13 "Quy tắc kiểm tra khi ghi"). "Hôm nay" theo múi giờ market
của bản ghi (09 bất biến 17). Các quy tắc chưa có trong 06 ghi ở ASM-006. Không commit: router/use case giữ
transaction.

Owner: Dev 1 (A) — M3.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.hr import Employee, EmployeeAssignment, LocationManager
from app.domain.models.ref import AppUser, Location, Market
from app.services.hr_read_service import not_found
from app.services.hr_scope import HrReadScope

ONE_DAY = timedelta(days=1)


def _invalid(field: str, message: str) -> DomainError:
    return DomainError("VALIDATION_ERROR", message, {"field": field})


def _require_admin(scope: HrReadScope) -> None:
    if scope.role != "admin":
        raise DomainError("FORBIDDEN", "Only admin may change HR records.")


def _in_scope(scope: HrReadScope, market_id: int) -> bool:
    return scope.market_id is None or scope.market_id == market_id


async def _market_today(session: AsyncSession, market_id: int) -> date:
    tz = await session.scalar(select(Market.timezone).where(Market.id == market_id))
    return clock.now().astimezone(ZoneInfo(tz or "UTC")).date()


async def _employee(session: AsyncSession, scope: HrReadScope, employee_id: int) -> Employee:
    employee = await session.scalar(select(Employee).where(Employee.id == employee_id).with_for_update())
    if employee is None or not _in_scope(scope, employee.market_id):
        raise not_found("Employee")
    return employee


async def _location(session: AsyncSession, scope: HrReadScope, location_id: int) -> Location:
    location = await session.scalar(select(Location).where(Location.id == location_id).with_for_update())
    if location is None or not _in_scope(scope, location.market_id):
        raise not_found("Location")
    return location


async def _open_assignment(session: AsyncSession, employee_id: int) -> EmployeeAssignment | None:
    return await session.scalar(
        select(EmployeeAssignment)
        .where(EmployeeAssignment.employee_id == employee_id, EmployeeAssignment.end_date.is_(None))
        .with_for_update()
    )


async def _manages(
    session: AsyncSession, employee_id: int, on_or_after: date, location_id: int | None = None
) -> bool:
    """Có bản ghi quản lý còn hiệu lực hoặc sắp hiệu lực từ ngày `on_or_after` trở đi."""
    query = select(LocationManager.id).where(
        LocationManager.employee_id == employee_id,
        or_(LocationManager.valid_to.is_(None), LocationManager.valid_to >= on_or_after),
    )
    if location_id is not None:
        query = query.where(LocationManager.location_id == location_id)
    return await session.scalar(query.limit(1)) is not None


async def assign(
    session: AsyncSession,
    scope: HrReadScope,
    employee_id: int,
    location_id: int,
    start_date: date,
    *,
    actor_user_id: int | None = None,
    actor_employee_id: int | None = None,
) -> None:
    """POST /employees/{id}/assignments (US-EMP-01 AC1/AC2; ux_one_active_assignment).

    ASM-006: ghi EMPLOYEE_ASSIGNMENT_CHANGED (actor, trước/sau) trong cùng transaction.
    """
    _require_admin(scope)
    employee = await _employee(session, scope, employee_id)
    if employee.status == "terminated":
        raise _invalid("employee_id", "Terminated employees cannot be assigned.")
    location = await session.get(Location, location_id)
    if location is None or location.market_id != employee.market_id:
        raise _invalid("location_id", "Location not found in the employee's market.")
    if not location.is_active:
        raise _invalid("location_id", "Location is inactive.")
    today = await _market_today(session, employee.market_id)
    if start_date < max(today, employee.hire_date):
        raise _invalid("start_date", "start_date must be today or later and not before the hire date.")
    current = await _open_assignment(session, employee_id)
    if current is not None:
        if current.location_id == location_id:
            raise _invalid("location_id", "Employee is already assigned to this location.")
        if current.start_date >= start_date:
            raise _invalid("start_date", "start_date must be after the current assignment's start date.")
        if await _manages(session, employee_id, start_date, current.location_id):
            raise _invalid(
                "employee_id", "Employee manages the current location; replace the managers first."
            )
        current.end_date = start_date - ONE_DAY
        await session.flush()
    session.add(EmployeeAssignment(employee_id=employee_id, location_id=location_id, start_date=start_date))
    await session.flush()
    await record_decision(
        session,
        Action.EMPLOYEE_ASSIGNMENT_CHANGED,
        "employee",
        str(employee_id),
        before=(
            None
            if current is None
            else {"location_id": current.location_id, "start_date": current.start_date, "end_date": None}
        ),
        after={
            "closed": (
                None
                if current is None
                else {"location_id": current.location_id, "end_date": current.end_date}
            ),
            "new": {"location_id": location_id, "start_date": start_date},
        },
        actor_user_id=actor_user_id,
        actor_employee_id=actor_employee_id,
        actor_role="admin",
    )


async def terminate(session: AsyncSession, scope: HrReadScope, employee_id: int) -> None:
    """POST /employees/{id}/terminate (US-EMP-03 AC4): khóa tài khoản, giữ lịch sử."""
    _require_admin(scope)
    employee = await _employee(session, scope, employee_id)
    if employee.status == "terminated":
        raise _invalid("employee_id", "Employee is already terminated.")
    today = await _market_today(session, employee.market_id)
    if await _manages(session, employee_id, today):
        raise _invalid("employee_id", "Employee is a location manager; replace the managers first.")
    future = await session.scalar(
        select(EmployeeAssignment.id).where(
            EmployeeAssignment.employee_id == employee_id, EmployeeAssignment.start_date > today
        )
    )
    if future is not None:
        raise _invalid("employee_id", "Employee has an assignment starting in the future.")
    await session.execute(
        update(EmployeeAssignment)
        .where(
            EmployeeAssignment.employee_id == employee_id,
            or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date > today),
        )
        .values(end_date=today)
    )
    employee.status, employee.end_date = "terminated", today
    await session.execute(update(AppUser).where(AppUser.employee_id == employee_id).values(is_active=False))
    await session.flush()


async def _check_manager(
    session: AsyncSession, field: str, employee_id: int, location: Location, today: date
) -> None:
    """AC5: nhân viên active cùng market, có phân công hiệu lực tại địa điểm hôm nay."""
    employee = await session.get(Employee, employee_id)
    if employee is None or employee.market_id != location.market_id or employee.status == "terminated":
        raise _invalid(field, "Employee not found or not active in this market.")
    assigned = await session.scalar(
        select(EmployeeAssignment.id).where(
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.location_id == location.id,
            EmployeeAssignment.start_date <= today,
            or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= today),
        )
    )
    if assigned is None:
        raise _invalid(field, "Employee has no effective assignment at this location.")


async def set_managers(
    session: AsyncSession,
    scope: HrReadScope,
    location_id: int,
    primary_employee_id: int,
    deputy_employee_id: int | None,
) -> None:
    """PUT /locations/{id}/managers (US-EMP-01 AC3–AC5; ux_one_primary_manager).

    Bản ghi đang mở của mỗi cấp mà đổi người → valid_to = hôm qua (bản ghi bắt đầu từ hôm nay trở đi thành
    không bao giờ hiệu lực, vẫn giữ lịch sử); người mới valid_from = hôm nay. Owner trống hoặc đang là quản lý
    chính cũ → chuyển sang quản lý chính mới (AC4).
    """
    _require_admin(scope)
    location = await _location(session, scope, location_id)
    if deputy_employee_id is not None and deputy_employee_id == primary_employee_id:
        raise _invalid("deputy_employee_id", "Deputy must differ from the primary manager.")
    today = await _market_today(session, location.market_id)
    await _check_manager(session, "primary_employee_id", primary_employee_id, location, today)
    if deputy_employee_id is not None:
        await _check_manager(session, "deputy_employee_id", deputy_employee_id, location, today)
    open_rows = (
        await session.scalars(
            select(LocationManager)
            .where(LocationManager.location_id == location_id, LocationManager.valid_to.is_(None))
            .with_for_update()
        )
    ).all()
    wanted = {"primary": primary_employee_id, "deputy": deputy_employee_id}
    old_primary: int | None = None
    keep: set[str] = set()
    for row in open_rows:
        if row.level == "primary":
            old_primary = row.employee_id
        if wanted.get(row.level) == row.employee_id:
            keep.add(row.level)
            continue
        row.valid_to = max(row.valid_from, today) - ONE_DAY
    await session.flush()
    for level, employee_id in wanted.items():
        if employee_id is not None and level not in keep:
            session.add(
                LocationManager(
                    location_id=location_id, employee_id=employee_id, level=level, valid_from=today
                )
            )
    if location.owner_employee_id is None or location.owner_employee_id == old_primary:
        location.owner_employee_id = primary_employee_id
    await session.flush()


async def set_owner(
    session: AsyncSession, scope: HrReadScope, location_id: int, owner_employee_id: int
) -> None:
    """PATCH /locations/{id}/owner (US-EMP-01 AC4): admin gán lại owner (nhân viên active cùng market)."""
    _require_admin(scope)
    location = await _location(session, scope, location_id)
    employee = await session.get(Employee, owner_employee_id)
    if employee is None or employee.market_id != location.market_id or employee.status == "terminated":
        raise _invalid("owner_employee_id", "Employee not found or not active in this market.")
    location.owner_employee_id = owner_employee_id
    await session.flush()
