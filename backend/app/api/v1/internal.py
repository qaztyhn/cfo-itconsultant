"""Endpoint nội bộ, header X-Internal-Key (06 mục 15).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 2 (B) — M2.
"""

from fastapi import APIRouter

router = APIRouter(tags=["internal"])


@router.post("/internal/tick")
async def tick() -> dict[str, object]:
    """POST /internal/tick — Chạy một job theo ?job=… (cho dịch vụ ping 5 phút)."""
    raise NotImplementedError
