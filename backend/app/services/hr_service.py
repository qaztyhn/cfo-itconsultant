"""Nhân sự, điểm danh, công suất (06 mục 13; US-WH-01/02, US-EMP-01..04).

Một phân công hiệu lực/người, một quản lý chính/địa điểm (422); chuyển công tác đóng phân công cũ;
terminate khóa tài khoản. Điểm danh All present một lần ghi (ATTENDANCE_CHANGED); capacity() theo công
thức 90%, không thiết bị.

Owner: Dev 1 (A) — M3.
"""


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
