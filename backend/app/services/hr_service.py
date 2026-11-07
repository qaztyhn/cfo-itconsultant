"""Nhân sự, điểm danh, công suất (06 mục 13; US-WH-01/02, US-EMP-01..04).

Một phân công hiệu lực/người, một quản lý chính/địa điểm (422); chuyển công tác đóng phân công cũ;
terminate khóa tài khoản. Điểm danh All present một lần ghi (ATTENDANCE_CHANGED); capacity() theo công
thức 90%, không thiết bị.

Owner: Dev 1 (A) — M3.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.hr import (
    Absence,
    Attendance,
    Employee,
    EmployeeAssignment,
    ShiftTemplate,
    WarehouseStaff,
)
from app.domain.models.plan import PlanningRun, PrepReservation
from app.domain.models.ref import Location
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


ATTENDANCE_STATUSES = frozenset({"present", "absent", "leave"})  # 'planned' chỉ do attendance_gen sinh


class AttendanceActor(Protocol):
    """Người gọi (CurrentUser thỏa mãn)."""

    @property
    def id(self) -> int: ...
    @property
    def employee_id(self) -> int | None: ...
    @property
    def roles(self) -> tuple[str, ...]: ...
    @property
    def location_ids(self) -> tuple[int, ...]: ...


@dataclass(frozen=True)
class AttendanceResult:
    work_date: date
    counts: dict[str, int]  # số người theo trạng thái sau khi ghi (roster của kho)
    changed_employee_ids: tuple[int, ...]


def _assigned_on(warehouse_id: int, work_date: date) -> ColumnElement[bool]:
    return (
        select(EmployeeAssignment.id)
        .where(
            EmployeeAssignment.employee_id == Attendance.employee_id,
            EmployeeAssignment.location_id == warehouse_id,
            EmployeeAssignment.start_date <= work_date,
            or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= work_date),
        )
        .exists()
    )


async def set_attendance(
    session: AsyncSession,
    actor: AttendanceActor,
    warehouse_id: int,
    work_date: date,
    *,
    all_present: bool,
    items: Sequence[tuple[int, str]] = (),
) -> AttendanceResult:
    """PUT /warehouses/{id}/attendance (US-WH-01 AC1–AC4; FR-PRP-05; BR-PRP-05).

    Chỉ vai trò warehouse của chính kho đó (06 mục 13); kho khác/không phải kho → 404, vai trò khác → 403.
    Roster = các dòng attendance của ngày mà nhân viên có phân công hiệu lực tại kho hôm đó (AC3: người ở cửa
    hàng không xuất hiện). `all_present` đặt mọi dòng không phải `leave` thành `present` trong MỘT câu UPDATE
    (AC1), rồi `items` ghi đè từng người. Người không có dòng trong roster, trạng thái lạ hoặc trùng → 422.
    Ghi ATTENDANCE_CHANGED (trước/sau theo số đếm; chỉ id nhân viên, không tên — 09 mục 5). Không commit.
    Công suất đọc lại qua day_capacities (AC2/AC4: chỉ `counts_in_capacity`). Quy tắc biên: ASM-007.
    """
    if "warehouse" not in actor.roles:
        raise DomainError("FORBIDDEN", "Only warehouse staff record attendance.")
    is_warehouse = await session.scalar(
        select(Location.id).where(Location.id == warehouse_id, Location.type == "warehouse")
    )
    if is_warehouse is None or warehouse_id not in actor.location_ids:
        raise DomainError("NOT_FOUND", "Warehouse not found.")
    wanted: dict[int, str] = {}
    for employee_id, status in items:
        if status not in ATTENDANCE_STATUSES or employee_id in wanted:
            raise DomainError("VALIDATION_ERROR", "Invalid or duplicate attendance item.", {"field": "items"})
        wanted[employee_id] = status

    roster_filter = and_(
        Attendance.work_date == work_date,
        _assigned_on(warehouse_id, work_date),
        select(Employee.id)
        .where(Employee.id == Attendance.employee_id, Employee.status != "terminated")
        .exists(),
    )
    before = dict(
        (
            await session.execute(
                select(Attendance.employee_id, Attendance.status).where(roster_filter).with_for_update()
            )
        ).all()
    )
    if missing := sorted(set(wanted) - set(before)):
        raise DomainError(
            "VALIDATION_ERROR",
            "Employees are not on this warehouse's attendance for the date.",
            {"field": "items", "employee_ids": missing},
        )
    now = clock.now()
    stamp = {"recorded_by": actor.employee_id, "recorded_at": now}
    if all_present:
        await session.execute(
            update(Attendance)
            .where(roster_filter, Attendance.status != "leave")
            .values(status="present", **stamp)
            .execution_options(synchronize_session=False)
        )
    for employee_id, status in wanted.items():
        await session.execute(
            update(Attendance)
            .where(Attendance.employee_id == employee_id, Attendance.work_date == work_date)
            .values(status=status, **stamp)
            .execution_options(synchronize_session=False)
        )
    after = {e: ("present" if all_present and s != "leave" else s) for e, s in before.items()} | wanted
    changed = tuple(sorted(e for e in before if before[e] != after[e]))
    counts = {k: sum(1 for v in after.values() if v == k) for k in ("planned", *sorted(ATTENDANCE_STATUSES))}
    await record_decision(
        session,
        Action.ATTENDANCE_CHANGED,
        "attendance",
        f"{warehouse_id}:{work_date.isoformat()}",
        before={k: sum(1 for v in before.values() if v == k) for k in counts},
        after=dict(counts),
        snapshot={"all_present": all_present, "changed_employee_ids": list(changed)},
        actor_user_id=actor.id,
        actor_employee_id=actor.employee_id,
        actor_role="warehouse",
    )
    return AttendanceResult(work_date, counts, changed)


async def capacity(warehouse_id: int, date_from: object, date_to: object) -> list[dict[str, object]]:
    """TODO(#hr-capacity)."""
    raise NotImplementedError
