"""Chuyển kho (04 mục 6.4; US-ATP-02/03).

suggested → approved (dispatcher, TRANSFER_APPROVED) → source_confirmed (quản lý kho nguồn có can_approve;
tạo inbound_shipment source=transfer confirmed=true; TRANSFER_CONFIRMED) → received (kho đích). Hủy cần lý
do.

Owner: Dev 1 (A) — M5.
"""


async def approve(order_id: int, actor: object, payload: dict[str, object]) -> int:
    """TODO(#transfer-approve)."""
    raise NotImplementedError


async def confirm_source(transfer_id: int, actor: object) -> None:
    """TODO(#transfer-confirm_source)."""
    raise NotImplementedError


async def receive(transfer_id: int, actor: object) -> None:
    """TODO(#transfer-receive)."""
    raise NotImplementedError


async def cancel(transfer_id: int, actor: object, reason_text: str) -> None:
    """TODO(#transfer-cancel)."""
    raise NotImplementedError
