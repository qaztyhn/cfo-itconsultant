"""Nhân sự, điểm danh, xe (06 mục 13). Không có endpoint thiết bị (v1.1).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M3.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from app.api.v1.common import Page, PageNo, PageSize, SortParam
from app.deps import AuthUser, DbSession
from app.services import hr_read_service, hr_service, hr_write_service
from app.services.hr_scope import resolve_hr_scope

router = APIRouter(tags=["hr"])

_READ_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "AUTH_INVALID"},
    403: {"description": "FORBIDDEN — role cannot read this resource"},
    404: {"description": "NOT_FOUND — missing or outside the caller's scope"},
    422: {"description": "VALIDATION_ERROR"},
}


class PersonRef(BaseModel):
    employee_id: int
    name: str


class PositionRef(BaseModel):
    code: str
    name: str


class AssignmentRef(BaseModel):
    location_id: int
    location_code: str
    location_name: str
    start_date: str


class AssignmentHistoryItem(BaseModel):
    location_id: int
    location_code: str
    start_date: str
    end_date: str | None


class WarehouseStaffOut(BaseModel):
    role: str
    counts_in_capacity: bool


class DriverStaffOut(BaseModel):
    licence_class: str
    licence_expires_on: str
    home_warehouse_id: int
    adr: bool


class SalesStaffOut(BaseModel):
    role: str


class DispatcherStaffOut(BaseModel):
    can_send_delay_notice: bool


class CsStaffOut(BaseModel):
    team: str | None


class EmployeeOut(BaseModel):
    """06 mục 13.1. Trường không hiển thị cho vai trò bị BỎ khỏi phản hồi (không phải null).

    Mọi vai trò: id, first_name, last_name, position, assignment. Dispatcher: + driver_staff.
    Warehouse: + warehouse_staff. Admin: mọi trường; chi tiết thêm weekly_hours, reports_to_employee_id,
    assignment_history.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 55, "first_name": "Anna", "last_name": "Lind",
                    "position": {"code": "DRIVER", "name": "Driver"},
                    "assignment": {"location_id": 7, "location_code": "STO", "location_name": "Stockholm DC",
                                   "start_date": "2025-03-01"},
                    "driver_staff": {"licence_class": "C", "licence_expires_on": "2027-01-31",
                                     "home_warehouse_id": 7, "adr": False},
                }
            ]
        }
    )  # fmt: skip

    id: int
    first_name: str
    last_name: str
    position: PositionRef
    assignment: AssignmentRef | None
    warehouse_staff: WarehouseStaffOut | None = None
    sales_staff: SalesStaffOut | None = None
    dispatcher_staff: DispatcherStaffOut | None = None
    driver_staff: DriverStaffOut | None = None
    cs_staff: CsStaffOut | None = None
    employee_no: str | None = None
    status: str | None = None
    employment_type: str | None = None
    hire_date: str | None = None
    end_date: str | None = None
    work_email: str | None = None
    work_phone: str | None = None
    weekly_hours: float | None = None
    reports_to_employee_id: int | None = None
    assignment_history: list[AssignmentHistoryItem] | None = None


class WarehouseRef(BaseModel):
    id: int
    code: str
    name: str


class GroupRef(BaseModel):
    id: int
    code: str


class VehicleOut(BaseModel):
    """06 mục 13.1. `allowed_groups: []` = chở được mọi nhóm."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 3, "code": "STO-CR-01", "plate": "…", "name": "Crane truck",
                    "home_warehouse": {"id": 7, "code": "STO", "name": "Stockholm DC"},
                    "capacity_kg": 8000.0, "capacity_m3": 30.0, "capabilities": ["crane"],
                    "required_licence": "C", "allowed_groups": [{"id": 4, "code": "N4"}],
                    "status": "available",
                }
            ]
        }
    )  # fmt: skip

    id: int
    code: str
    plate: str
    name: str
    home_warehouse: WarehouseRef
    capacity_kg: float
    capacity_m3: float
    capabilities: list[str]
    required_licence: str
    allowed_groups: list[GroupRef]
    status: str


class LocationManagers(BaseModel):
    primary: PersonRef | None
    deputy: PersonRef | None


class LocationOut(BaseModel):
    """06 mục 13.1 — cùng schema cho danh sách và chi tiết."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 7, "market": "SE", "type": "warehouse", "code": "STO", "name": "Stockholm DC",
                    "address": "…", "lat": 59.3293, "lon": 18.0686, "loading_cutoff_time": "15:00",
                    "is_active": True, "owner": {"employee_id": 40, "name": "…"},
                    "managers": {"primary": {"employee_id": 40, "name": "…"}, "deputy": None},
                }
            ]
        }
    )  # fmt: skip

    id: int
    market: str
    type: str
    code: str
    name: str
    address: str | None
    lat: float | None
    lon: float | None
    loading_cutoff_time: str | None
    is_active: bool
    owner: PersonRef | None
    managers: LocationManagers


@router.get(
    "/employees", response_model=Page[EmployeeOut], response_model_exclude_unset=True, responses=_READ_ERRORS
)
async def list_employees(
    user: AuthUser,
    db: DbSession,
    position_code: str | None = None,
    location_id: int | None = None,
    status: Annotated[str | None, Query(description="active | on_leave | terminated")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: SortParam = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[EmployeeOut]:
    """GET /employees — admin; dispatcher (market); warehouse (kho mình) — 06 mục 13.1."""
    scope = await resolve_hr_scope(db, user)
    items, total = await hr_read_service.list_employees(
        db,
        scope,
        position_code=position_code,
        location_id=location_id,
        status=status,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page[EmployeeOut](
        items=[EmployeeOut.model_validate(i) for i in items], page=page, page_size=page_size, total=total
    )


@router.post("/employees")
async def create_employee() -> dict[str, object]:
    """POST /employees — admin."""
    raise NotImplementedError


@router.get(
    "/employees/{employee_id}",
    response_model=EmployeeOut,
    response_model_exclude_unset=True,
    responses=_READ_ERRORS,
)
async def get_employee(employee_id: int, user: AuthUser, db: DbSession) -> EmployeeOut:
    """GET /employees/{employee_id} — theo phạm vi; ngoài phạm vi → 404."""
    scope = await resolve_hr_scope(db, user)
    return EmployeeOut.model_validate(await hr_read_service.get_employee(db, scope, employee_id))


class AssignmentIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"example": {"location_id": 3, "start_date": "2026-11-20"}}
    )
    location_id: int
    start_date: date


class ManagersIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"example": {"primary_employee_id": 40, "deputy_employee_id": 41}}
    )
    primary_employee_id: int
    deputy_employee_id: int | None = None


class OwnerIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"owner_employee_id": 40}})
    owner_employee_id: int


_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_READ_ERRORS,
    403: {"description": "FORBIDDEN — admin only"},
    422: {"description": "VALIDATION_ERROR — details.field names the rule that failed"},
}


@router.post(
    "/employees/{employee_id}/assignments",
    response_model=EmployeeOut,
    response_model_exclude_unset=True,
    responses=_WRITE_ERRORS,
)
async def assign_employee(employee_id: int, body: AssignmentIn, user: AuthUser, db: DbSession) -> EmployeeOut:
    """POST /employees/{id}/assignments — admin; đóng phân công cũ (US-EMP-01 AC2)."""
    scope = await resolve_hr_scope(db, user)
    await hr_write_service.assign(
        db,
        scope,
        employee_id,
        body.location_id,
        body.start_date,
        actor_user_id=user.id,
        actor_employee_id=user.employee_id,
    )
    return EmployeeOut.model_validate(await hr_read_service.get_employee(db, scope, employee_id))


@router.post(
    "/employees/{employee_id}/terminate",
    response_model=EmployeeOut,
    response_model_exclude_unset=True,
    responses=_WRITE_ERRORS,
)
async def terminate_employee(employee_id: int, user: AuthUser, db: DbSession) -> EmployeeOut:
    """POST /employees/{id}/terminate — admin; khóa tài khoản, giữ lịch sử (US-EMP-03 AC4)."""
    scope = await resolve_hr_scope(db, user)
    await hr_write_service.terminate(db, scope, employee_id)
    return EmployeeOut.model_validate(await hr_read_service.get_employee(db, scope, employee_id))


@router.get("/locations", response_model=Page[LocationOut], responses=_READ_ERRORS)
async def list_locations(
    user: AuthUser,
    db: DbSession,
    type: Annotated[
        str | None, Query(description="warehouse | store | dispatch_center | head_office")
    ] = None,
    is_active: bool = True,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: SortParam = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[LocationOut]:
    """GET /locations — admin, dispatcher (market), warehouse (nơi được phân công) — 06 mục 13.1."""
    scope = await resolve_hr_scope(db, user)
    items, total = await hr_read_service.list_locations(
        db, scope, type_=type, is_active=is_active, q=q, sort=sort, page=page, page_size=page_size
    )
    return Page[LocationOut](
        items=[LocationOut.model_validate(i) for i in items], page=page, page_size=page_size, total=total
    )


@router.get("/locations/{location_id}", response_model=LocationOut, responses=_READ_ERRORS)
async def get_location(location_id: int, user: AuthUser, db: DbSession) -> LocationOut:
    """GET /locations/{id} — như danh sách; ngoài phạm vi → 404."""
    scope = await resolve_hr_scope(db, user)
    return LocationOut.model_validate(await hr_read_service.get_location(db, scope, location_id))


@router.put("/locations/{location_id}/managers", response_model=LocationOut, responses=_WRITE_ERRORS)
async def set_managers(location_id: int, body: ManagersIn, user: AuthUser, db: DbSession) -> LocationOut:
    """PUT /locations/{id}/managers — admin; quản lý phải có phân công tại đó (US-EMP-01 AC3–AC5)."""
    scope = await resolve_hr_scope(db, user)
    await hr_write_service.set_managers(
        db, scope, location_id, body.primary_employee_id, body.deputy_employee_id
    )
    return LocationOut.model_validate(await hr_read_service.get_location(db, scope, location_id))


@router.patch("/locations/{location_id}/owner", response_model=LocationOut, responses=_WRITE_ERRORS)
async def set_owner(location_id: int, body: OwnerIn, user: AuthUser, db: DbSession) -> LocationOut:
    """PATCH /locations/{id}/owner — admin gán lại owner (US-EMP-01 AC4)."""
    scope = await resolve_hr_scope(db, user)
    await hr_write_service.set_owner(db, scope, location_id, body.owner_employee_id)
    return LocationOut.model_validate(await hr_read_service.get_location(db, scope, location_id))


class AttendanceItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int
    status: str


class AttendanceIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "date": "2026-11-12",
                "all_present": True,
                "items": [{"employee_id": 120, "status": "absent"}],
            }
        },
    )
    date: date
    all_present: bool = False
    items: list[AttendanceItemIn] = []


class ShiftRef(BaseModel):
    id: int
    start: str
    end: str


class AttendanceRow(BaseModel):
    employee_id: int
    name: str
    position: str
    counts_in_capacity: bool
    shift: ShiftRef | None
    status: str
    on_approved_leave: bool


class AttendanceOut(BaseModel):
    warehouse_id: int
    date: date
    counts: dict[str, int]
    items: list[AttendanceRow]


class ShiftCapacityOut(BaseModel):
    start: str
    end: str
    present: int
    useful_hours: float


class DayCapacityOut(BaseModel):
    date: date
    holiday: bool
    shifts: list[ShiftCapacityOut]
    labour_cap_hours: float
    booked_hours: dict[str, float]
    free_hours: float


class CapacityOut(BaseModel):
    warehouse_id: int
    days: list[DayCapacityOut]


@router.get("/warehouses/{warehouse_id}/attendance", response_model=AttendanceOut, responses=_READ_ERRORS)
async def get_attendance(
    warehouse_id: int, user: AuthUser, db: DbSession, work_date: Annotated[date, Query(alias="date")]
) -> AttendanceOut:
    """GET /warehouses/{id}/attendance?date= — warehouse (kho mình), dispatcher, admin (06 mục 13.2)."""
    scope = await resolve_hr_scope(db, user)
    return AttendanceOut.model_validate(await hr_service.get_attendance(db, scope, warehouse_id, work_date))


@router.put("/warehouses/{warehouse_id}/attendance", response_model=AttendanceOut, responses=_WRITE_ERRORS)
async def put_attendance(
    warehouse_id: int, body: AttendanceIn, user: AuthUser, db: DbSession
) -> AttendanceOut:
    """PUT /warehouses/{id}/attendance — chỉ warehouse của kho đó; ghi ATTENDANCE_CHANGED (US-WH-01)."""
    await hr_service.set_attendance(
        db,
        user,
        warehouse_id,
        body.date,
        all_present=body.all_present,
        items=[(i.employee_id, i.status) for i in body.items],
    )
    scope = await resolve_hr_scope(db, user)
    return AttendanceOut.model_validate(await hr_service.get_attendance(db, scope, warehouse_id, body.date))


@router.get("/warehouses/{warehouse_id}/capacity", response_model=CapacityOut, responses=_READ_ERRORS)
async def get_capacity(
    warehouse_id: int,
    user: AuthUser,
    db: DbSession,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> CapacityOut:
    """GET /warehouses/{id}/capacity?from=&to= — tối đa 31 ngày (06 mục 13.2; US-WH-02)."""
    scope = await resolve_hr_scope(db, user)
    return CapacityOut.model_validate(await hr_service.capacity(db, scope, warehouse_id, date_from, date_to))


@router.post("/absences")
async def create_absence() -> dict[str, object]:
    """POST /absences — warehouse, admin."""
    raise NotImplementedError


@router.get("/warehouses/{warehouse_id}/shift-templates")
async def get_shift_templates(warehouse_id: int) -> dict[str, object]:
    """GET /warehouses/{warehouse_id}/shift-templates — warehouse, admin."""
    raise NotImplementedError


@router.put("/warehouses/{warehouse_id}/shift-templates")
async def put_shift_templates(warehouse_id: int) -> dict[str, object]:
    """PUT /warehouses/{warehouse_id}/shift-templates — warehouse, admin."""
    raise NotImplementedError


@router.get("/vehicles", response_model=Page[VehicleOut], responses=_READ_ERRORS)
async def list_vehicles(
    user: AuthUser,
    db: DbSession,
    home_warehouse_id: int | None = None,
    status: Annotated[str | None, Query(description="available | maintenance | retired")] = None,
    capability: Annotated[str | None, Query(max_length=50)] = None,
    sort: SortParam = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[VehicleOut]:
    """GET /vehicles — admin; dispatcher (market); warehouse (xe có kho gốc thuộc kho mình) — 06 mục 13.1."""
    scope = await resolve_hr_scope(db, user)
    items, total = await hr_read_service.list_vehicles(
        db,
        scope,
        home_warehouse_id=home_warehouse_id,
        status=status,
        capability=capability,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page[VehicleOut](
        items=[VehicleOut.model_validate(i) for i in items], page=page, page_size=page_size, total=total
    )


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut, responses=_READ_ERRORS)
async def get_vehicle(vehicle_id: int, user: AuthUser, db: DbSession) -> VehicleOut:
    """GET /vehicles/{id} — theo phạm vi; ngoài phạm vi → 404."""
    scope = await resolve_hr_scope(db, user)
    return VehicleOut.model_validate(await hr_read_service.get_vehicle(db, scope, vehicle_id))


@router.post("/vehicles")
async def create_vehicle() -> dict[str, object]:
    """POST /vehicles — admin."""
    raise NotImplementedError


@router.get("/users")
async def list_users() -> dict[str, object]:
    """GET /users — admin."""
    raise NotImplementedError


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int) -> dict[str, object]:
    """POST /users/{user_id}/reset-password — admin."""
    raise NotImplementedError
