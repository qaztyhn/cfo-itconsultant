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


@router.get("/employees")
async def list_employees() -> dict[str, object]:
    """GET /employees — admin; R: dispatcher, warehouse (kho mình)."""
    raise NotImplementedError


@router.post("/employees")
async def create_employee() -> dict[str, object]:
    """POST /employees — admin."""
    raise NotImplementedError


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: int) -> dict[str, object]:
    """GET /employees/{employee_id} — Theo phạm vi."""
    raise NotImplementedError


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


@router.get("/vehicles")
async def list_vehicles() -> dict[str, object]:
    """GET /vehicles — admin; R dispatcher."""
    raise NotImplementedError


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
