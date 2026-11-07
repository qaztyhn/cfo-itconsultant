"""Nhân sự, điểm danh, công suất (06 mục 13; US-WH-01/02, US-EMP-01..04).

Một phân công hiệu lực/người, một quản lý chính/địa điểm (422); chuyển công tác đóng phân công cũ;
terminate khóa tài khoản. Điểm danh All present một lần ghi (ATTENDANCE_CHANGED); capacity() theo công
thức 90%, không thiết bị.

Owner: Dev 1 (A) — M3.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.hr import Absence, Attendance, EmployeeAssignment, ShiftTemplate, WarehouseStaff
from app.domain.models.plan import PlanningRun, PrepReservation
from app.engine.types import DayCapacity, ShiftCapacity


async def day_capacities(
    session: AsyncSession,
    warehouse_id: int,
    days: Sequence[date],
    *,
    now: datetime,
    today: date,
    exclude_order_id: int | None = None,
) -> dict[date, DayCapacity]:
    """Ngữ cảnh công suất theo ngày cho engine (04 mục 6.2 bước 2b; 05 mục 4 quy tắc 5).

    - Ca: `hr.shift_template` theo thứ (ISO 1–7) của kho.
    - present_staff của ca = nhân viên `warehouse_staff.counts_in_capacity`, có phân công hiệu lực tại kho
      trong ngày, có điểm danh ở ca đó với trạng thái `present` (ngày đã qua/hôm nay) hoặc `present`/`planned`
      (ngày tương lai), và không có nghỉ phép ĐÃ DUYỆT phủ ngày đó. Điểm danh không gắn ca thì không tính.
    - booked_hours = Σ `prep_reservation.hours` của ĐƠN KHÁC: `committed`, hoặc `held` mà
      `planning_run.hold_expires_at > now` (giữ chỗ được phép vượt — chỉ duyệt mới chặn, 09 bất biến 11).
    `today` là ngày theo múi giờ market (09 bất biến 17); ngày không có ca → `shifts = ()`.
    """
    if not days:
        return {}
    day_set = sorted(set(days))
    first, last = day_set[0], day_set[-1]

    templates = (
        (await session.execute(select(ShiftTemplate).where(ShiftTemplate.warehouse_id == warehouse_id)))
        .scalars()
        .all()
    )
    by_weekday: dict[int, list[ShiftTemplate]] = defaultdict(list)
    for tpl in sorted(templates, key=lambda t: t.start_time):
        by_weekday[tpl.weekday].append(tpl)

    approved_leave = select(Absence.id).where(
        Absence.employee_id == Attendance.employee_id,
        Absence.approved.is_(True),
        Absence.start_date <= Attendance.work_date,
        Absence.end_date >= Attendance.work_date,
    )
    counted_status = or_(
        Attendance.status == "present",
        and_(Attendance.status == "planned", Attendance.work_date > today),
    )
    staff_rows = await session.execute(
        select(Attendance.work_date, Attendance.shift_template_id, func.count())
        .join(WarehouseStaff, WarehouseStaff.employee_id == Attendance.employee_id)
        .join(
            EmployeeAssignment,
            and_(
                EmployeeAssignment.employee_id == Attendance.employee_id,
                EmployeeAssignment.location_id == warehouse_id,
                EmployeeAssignment.start_date <= Attendance.work_date,
                or_(
                    EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= Attendance.work_date
                ),
            ),
        )
        .where(
            Attendance.work_date.between(first, last),
            Attendance.shift_template_id.is_not(None),
            WarehouseStaff.counts_in_capacity.is_(True),
            counted_status,
            ~approved_leave.exists(),
        )
        .group_by(Attendance.work_date, Attendance.shift_template_id)
    )
    present: dict[tuple[date, int], int] = {(d, sid): n for d, sid, n in staff_rows.all() if sid is not None}

    booked_query = (
        select(PrepReservation.work_date, func.coalesce(func.sum(PrepReservation.hours), 0))
        .join(PlanningRun, PlanningRun.id == PrepReservation.run_id)
        .where(
            PrepReservation.warehouse_id == warehouse_id,
            PrepReservation.work_date.between(first, last),
            or_(
                PrepReservation.status == "committed",
                and_(PrepReservation.status == "held", PlanningRun.hold_expires_at > now),
            ),
        )
        .group_by(PrepReservation.work_date)
    )
    if exclude_order_id is not None:
        booked_query = booked_query.where(PrepReservation.order_id != exclude_order_id)
    booked: dict[date, Decimal] = {d: Decimal(h) for d, h in (await session.execute(booked_query)).all()}

    return {
        d: DayCapacity(
            day=d,
            shifts=tuple(
                ShiftCapacity(
                    name=f"{tpl.start_time:%H:%M}-{tpl.end_time:%H:%M}",
                    start=tpl.start_time,
                    end=tpl.end_time,
                    present_staff=present.get((d, tpl.id), 0),
                    useful_hours_per_staff=tpl.useful_hours_per_staff,
                )
                for tpl in by_weekday.get(d.isoweekday(), [])
            ),
            booked_hours=booked.get(d, Decimal(0)),
        )
        for d in day_set
    }


async def set_attendance(warehouse_id: int, actor: object, payload: dict[str, object]) -> None:
    """TODO(#hr-set_attendance)."""
    raise NotImplementedError


async def capacity(warehouse_id: int, date_from: object, date_to: object) -> list[dict[str, object]]:
    """TODO(#hr-capacity)."""
    raise NotImplementedError


async def assign(employee_id: int, location_id: int, start_date: object, actor: object) -> None:
    """TODO(#hr-assign)."""
    raise NotImplementedError


async def terminate(employee_id: int, actor: object) -> None:
    """TODO(#hr-terminate)."""
    raise NotImplementedError
