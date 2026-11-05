"""Cảnh báo (06 mục 10).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M7.
"""

from fastapi import APIRouter

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
async def list_alerts() -> dict[str, object]:
    """GET /alerts — dispatcher, warehouse, CS, admin; critical trước."""
    raise NotImplementedError


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int) -> dict[str, object]:
    """POST /alerts/{alert_id}/ack — dispatcher, admin."""
    raise NotImplementedError
