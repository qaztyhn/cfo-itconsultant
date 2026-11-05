"""Giữ chỗ (05 mục 7; BR-RES-01..04; US-RES-01).

Hold 15 phút cả 3 phương án; hàng/giờ công một lần cho (đơn, kho); xe/tài xế từng phương án (EXCLUDE).
Trước khi ghi: advisory lock stock:<kho>:<sp>, labour:<kho>:<ngày> theo thứ tự cố định rồi đọc lại phần
trống. extend ≤ 2 lần (HOLD_EXTENSION_LIMIT); expire_due() cho job hold_expiry; release_order() khi đóng
kế hoạch.

Owner: Dev 1 (A) — M5.
"""


async def hold(run_id: int) -> None:
    """TODO(#reservation-hold)."""
    raise NotImplementedError


async def extend(run_id: int, actor: object) -> None:
    """TODO(#reservation-extend)."""
    raise NotImplementedError


async def expire_due() -> int:
    """TODO(#reservation-expire_due)."""
    raise NotImplementedError


async def commit_plan(plan_id: int) -> None:
    """TODO(#reservation-commit_plan)."""
    raise NotImplementedError


async def release_order(order_id: int) -> None:
    """TODO(#reservation-release_order)."""
    raise NotImplementedError
