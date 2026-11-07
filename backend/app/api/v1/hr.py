"""Nhân sự, điểm danh, xe (06 mục 13). Không có endpoint thiết bị (v1.1).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M3.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from app.api.v1.common import Page, PageNo, PageSize, SortParam
from app.deps import AuthUser, DbSession
from app.services import hr_read_service
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


@router.post("/employees/{employee_id}/assignments")
async def assign_employee(employee_id: int) -> dict[str, object]:
    """POST /employees/{employee_id}/assignments — admin; đóng phân công cũ."""
    raise NotImplementedError


@router.post("/employees/{employee_id}/terminate")
async def terminate_employee(employee_id: int) -> dict[str, object]:
    """POST /employees/{employee_id}/terminate — admin."""
    raise NotImplementedError


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


@router.put("/locations/{location_id}/managers")
async def set_managers(location_id: int) -> dict[str, object]:
    """PUT /locations/{location_id}/managers — admin; một quản lý chính."""
    raise NotImplementedError


@router.get("/warehouses/{warehouse_id}/attendance")
async def get_attendance(warehouse_id: int) -> dict[str, object]:
    """GET /warehouses/{warehouse_id}/attendance — warehouse (kho mình), dispatcher, admin."""
    raise NotImplementedError


@router.put("/warehouses/{warehouse_id}/attendance")
async def put_attendance(warehouse_id: int) -> dict[str, object]:
    """PUT /warehouses/{warehouse_id}/attendance — warehouse; ATTENDANCE_CHANGED."""
    raise NotImplementedError


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
