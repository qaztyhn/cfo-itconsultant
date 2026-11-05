"""Chuyển kho (06 mục 7).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M5.
"""

from fastapi import APIRouter

router = APIRouter(tags=["transfers"])


@router.post("/orders/{order_id}/transfers")
async def approve_transfer(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/transfers — dispatcher → stock_transfer(approved)."""
    raise NotImplementedError


@router.get("/transfers")
async def list_transfers() -> dict[str, object]:
    """GET /transfers — dispatcher, warehouse."""
    raise NotImplementedError


@router.post("/transfers/{transfer_id}/confirm-source")
async def confirm_source(transfer_id: int) -> dict[str, object]:
    """POST /transfers/{transfer_id}/confirm-source — warehouse kho nguồn, can_approve."""
    raise NotImplementedError


@router.post("/transfers/{transfer_id}/receive")
async def receive_transfer(transfer_id: int) -> dict[str, object]:
    """POST /transfers/{transfer_id}/receive — warehouse kho đích."""
    raise NotImplementedError


@router.post("/transfers/{transfer_id}/cancel")
async def cancel_transfer(transfer_id: int) -> dict[str, object]:
    """POST /transfers/{transfer_id}/cancel — dispatcher, cần lý do."""
    raise NotImplementedError
