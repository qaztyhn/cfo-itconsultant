"""Nhân sự, điểm danh, công suất (06 mục 13; US-WH-01/02, US-EMP-01..04).

Một phân công hiệu lực/người, một quản lý chính/địa điểm (422); chuyển công tác đóng phân công cũ;
terminate khóa tài khoản. Điểm danh All present một lần ghi (ATTENDANCE_CHANGED); capacity() theo công
thức 90%, không thiết bị.

Owner: Dev 1 (A) — M3.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig
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
from app.domain.models.ref import Location, Market, MarketHoliday
from app.engine.capacity import free_hours, labour_capacity
from app.engine.types import DayCapacity, ShiftCapacity
from app.services.hr_scope import HrReadScope
from app.services.planning_service import engine_config


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


MAX_CAPACITY_DAYS = 31  # 06 v1.4 mục 13.2
GEN_DAYS = 14  # attendance_gen: 14 ngày tới (04 mục 4, jobs/attendance_gen.py)


async def _warehouse_in_scope(session: AsyncSession, scope: HrReadScope, warehouse_id: int) -> Location:
    """Kho trong phạm vi đọc (warehouse: kho được phân công; admin/dispatcher: market); khác → 404."""
    location = await session.get(Location, warehouse_id)
    if (
        location is None
        or location.type != "warehouse"
        or (scope.market_id is not None and location.market_id != scope.market_id)
        or (scope.role == "warehouse" and warehouse_id not in scope.location_ids)
    ):
        raise DomainError("NOT_FOUND", "Warehouse not found.")
    return location


async def get_attendance(
    session: AsyncSession, scope: HrReadScope, warehouse_id: int, work_date: date
) -> dict[str, object]:
    """GET /warehouses/{id}/attendance?date= (06 v1.4 mục 13.2): số đếm + từng người trong roster."""
    await _warehouse_in_scope(session, scope, warehouse_id)
    approved_leave = (
        select(Absence.id)
        .where(
            Absence.employee_id == Attendance.employee_id,
            Absence.approved.is_(True),
            Absence.start_date <= work_date,
            Absence.end_date >= work_date,
        )
        .exists()
    )
    rows = (
        await session.execute(
            select(
                Attendance,
                Employee,
                WarehouseStaff.counts_in_capacity,
                ShiftTemplate,
                approved_leave.label("on_leave"),
            )
            .join(Employee, Employee.id == Attendance.employee_id)
            .outerjoin(WarehouseStaff, WarehouseStaff.employee_id == Attendance.employee_id)
            .outerjoin(ShiftTemplate, ShiftTemplate.id == Attendance.shift_template_id)
            .where(
                Attendance.work_date == work_date,
                _assigned_on(warehouse_id, work_date),
                Employee.status != "terminated",
            )
            .order_by(Employee.last_name, Employee.first_name, Employee.id)
        )
    ).all()
    counts = {k: 0 for k in ("planned", "present", "absent", "leave")}
    items: list[dict[str, object]] = []
    for att, emp, counts_flag, shift, on_leave in rows:
        counts[att.status] = counts.get(att.status, 0) + 1
        items.append(
            {
                "employee_id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "position": emp.position_code,
                "counts_in_capacity": bool(counts_flag),
                "shift": (
                    None
                    if shift is None
                    else {
                        "id": shift.id,
                        "start": f"{shift.start_time:%H:%M}",
                        "end": f"{shift.end_time:%H:%M}",
                    }
                ),
                "status": att.status,
                "on_approved_leave": bool(on_leave),
            }
        )
    return {"warehouse_id": warehouse_id, "date": work_date, "counts": counts, "items": items}


async def capacity(
    session: AsyncSession, scope: HrReadScope, warehouse_id: int, date_from: date, date_to: date
) -> dict[str, object]:
    """GET /warehouses/{id}/capacity?from=&to= (06 v1.4 mục 13.2; US-WH-02 AC1–AC3).

    labour_cap_hours dùng đúng engine.capacity (người × giờ hữu ích × delivery_share; ngày nghỉ/lễ = 0);
    booked_hours tách committed/held của MỌI đơn (held còn hạn); free_hours = engine.free_hours (không âm).
    """
    location = await _warehouse_in_scope(session, scope, warehouse_id)
    if date_to < date_from or (date_to - date_from).days + 1 > MAX_CAPACITY_DAYS:
        raise DomainError("VALIDATION_ERROR", f"Range must be 1–{MAX_CAPACITY_DAYS} days.", {"field": "to"})
    market = await session.get(Market, location.market_id)
    assert market is not None
    holidays = set(
        (
            await session.scalars(
                select(MarketHoliday.holiday_date).where(
                    MarketHoliday.market_id == market.id,
                    MarketHoliday.holiday_date.between(date_from, date_to),
                )
            )
        ).all()
    )
    cfg = engine_config(MarketConfig.model_validate(market.config or {}), holidays)
    now = clock.now()
    today = now.astimezone(ZoneInfo(market.timezone)).date()
    days = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]
    caps = await day_capacities(session, warehouse_id, days, now=now, today=today)
    booked_rows = await session.execute(
        select(PrepReservation.work_date, PrepReservation.status, func.sum(PrepReservation.hours))
        .join(PlanningRun, PlanningRun.id == PrepReservation.run_id)
        .where(
            PrepReservation.warehouse_id == warehouse_id,
            PrepReservation.work_date.between(date_from, date_to),
            or_(
                PrepReservation.status == "committed",
                and_(PrepReservation.status == "held", PlanningRun.hold_expires_at > now),
            ),
        )
        .group_by(PrepReservation.work_date, PrepReservation.status)
    )
    booked: dict[date, dict[str, Decimal]] = defaultdict(
        lambda: {"committed": Decimal(0), "held": Decimal(0)}
    )
    for d, status, hours in booked_rows.all():
        booked[d][status] = Decimal(hours)
    out = []
    for d in days:
        cap = caps[d]
        out.append(
            {
                "date": d,
                "holiday": d in holidays,
                "shifts": [
                    {"start": f"{s.start:%H:%M}", "end": f"{s.end:%H:%M}", "present": s.present_staff,
                     "useful_hours": float(s.useful_hours_per_staff)}  # fmt: skip
                    for s in cap.shifts
                ],
                "labour_cap_hours": float(labour_capacity(cap, cfg)),
                "booked_hours": {k: float(v) for k, v in booked[d].items()},
                "free_hours": float(free_hours(cap, cfg)),
            }
        )
    return {"warehouse_id": warehouse_id, "days": out}


async def generate_attendance(session: AsyncSession, *, days: int = GEN_DAYS) -> int:
    """Job attendance_gen (06 v1.4 mục 13.2, Q11 = B): sinh dòng `planned` cho 14 ngày tới.

    Mỗi kho đang hoạt động, mỗi ngày (từ hôm nay theo múi giờ market): nhân viên `counts_in_capacity`, chưa
    nghỉ việc, có phân công hiệu lực tại kho hôm đó, chưa có dòng attendance ngày đó → chia lần lượt vào các
    ca mẫu theo `start_time`, tối đa `expected_staff` mỗi ca (đã tính người có sẵn dòng), theo `employee_no`;
    dư vào ca cuối. Không ghi đè dòng có sẵn. Trả số dòng tạo mới. Không commit.
    """
    created = 0
    now = clock.now()
    warehouses = (
        await session.execute(
            select(Location, Market.timezone)
            .join(Market, Market.id == Location.market_id)
            .where(Location.type == "warehouse", Location.is_active.is_(True))
            .order_by(Location.id)
        )
    ).all()
    for warehouse, tz in warehouses:
        start = now.astimezone(ZoneInfo(tz)).date()
        templates = (
            await session.scalars(select(ShiftTemplate).where(ShiftTemplate.warehouse_id == warehouse.id))
        ).all()
        for offset in range(days):
            day = start + timedelta(days=offset)
            shifts = sorted(
                (t for t in templates if t.weekday == day.isoweekday()), key=lambda t: t.start_time
            )
            if not shifts:
                continue
            existing = dict(
                (
                    await session.execute(
                        select(Attendance.shift_template_id, func.count())
                        .where(
                            Attendance.work_date == day,
                            Attendance.shift_template_id.in_([t.id for t in shifts]),
                        )
                        .group_by(Attendance.shift_template_id)
                    )
                ).all()
            )
            staff = (
                await session.scalars(
                    select(Employee.id)
                    .join(WarehouseStaff, WarehouseStaff.employee_id == Employee.id)
                    .join(EmployeeAssignment, EmployeeAssignment.employee_id == Employee.id)
                    .where(
                        WarehouseStaff.counts_in_capacity.is_(True),
                        Employee.status != "terminated",
                        EmployeeAssignment.location_id == warehouse.id,
                        EmployeeAssignment.start_date <= day,
                        or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= day),
                        ~select(Attendance.id)
                        .where(Attendance.employee_id == Employee.id, Attendance.work_date == day)
                        .exists(),
                    )
                    .order_by(Employee.employee_no, Employee.id)
                )
            ).all()
            filled = {t.id: int(existing.get(t.id, 0)) for t in shifts}
            for employee_id in staff:
                target = next((t for t in shifts if filled[t.id] < t.expected_staff), shifts[-1])
                filled[target.id] += 1
                session.add(
                    Attendance(
                        employee_id=employee_id, work_date=day, shift_template_id=target.id, status="planned"
                    )
                )
                created += 1
    await session.flush()
    return created
