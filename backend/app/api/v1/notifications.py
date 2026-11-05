"""Thông báo khách (06 mục 10, Phụ lục A).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 2 (B) — M7.
"""

from fastapi import APIRouter

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def list_notifications() -> dict[str, object]:
    """GET /notifications — dispatcher, CS, admin."""
    raise NotImplementedError


@router.get("/notifications/{notification_id}")
async def get_notification(notification_id: int) -> dict[str, object]:
    """GET /notifications/{notification_id} — Bản xem trước đã che người nhận."""
    raise NotImplementedError


@router.post("/notifications/{notification_id}/send")
async def send_notification(notification_id: int) -> dict[str, object]:
    """POST /notifications/{notification_id}/send — dispatcher; DELAY draft; Idempotency-Key."""
    raise NotImplementedError


@router.post("/notifications/{notification_id}/discard")
async def discard_notification(notification_id: int) -> dict[str, object]:
    """POST /notifications/{notification_id}/discard — dispatcher; reason_text bắt buộc."""
    raise NotImplementedError
