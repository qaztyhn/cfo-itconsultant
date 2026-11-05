"""Nhân sự, điểm danh, xe (06 mục 13). Không có endpoint thiết bị (v1.1).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M3.
"""

from fastapi import APIRouter

router = APIRouter(tags=["hr"])


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


@router.get("/locations")
async def list_locations() -> dict[str, object]:
    """GET /locations — Theo phạm vi."""
    raise NotImplementedError


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
