"""Giai đoạn giữ hàng WMS mô phỏng trước khi duyệt (E1, DEC-WMS-RESERVE-SYNC-20261109).

Không commit APPROVED. Mỗi bước dùng transaction riêng: lưu intent trước khi gọi WMS,
rồi ghi ACK sau khi WMS trả lời. Lỗi không rõ kết quả được ghi là 'unknown' để retry
cùng khóa idempotency.
"""

from app.adapters.disposable_wms_client import DisposableWmsPort
from app.adapters.wms_reservation import WmsDisabled, WmsRejected, WmsTimeout, WmsUnavailable
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan
from app.services.wms_intent import begin_intent, record_ack, record_unknown
from app.services.wms_mode import simulated_enabled
from app.services.wms_request import build_simulated_request


async def reserve_simulated(order_id: int, plan_id: int) -> str:
    """Trả 'acked' khi đã có ACK hợp lệ. Ném DomainError nếu không giữ được hàng."""
    if not simulated_enabled():
        raise DomainError("PLAN_NOT_APPROVABLE", "Simulated WMS reservation is not permitted.")
    settings = get_settings()
    if not settings.synthetic_wms_url or not settings.synthetic_wms_api_key:
        raise DomainError("PLAN_NOT_APPROVABLE", "Simulated WMS is not configured.")

    # Transaction 1: dựng yêu cầu từ dữ liệu server, lưu intent, commit trước khi gọi WMS.
    async with get_sessionmaker()() as db, db.begin():
        order = await db.get(CustomerOrder, order_id)
        plan = await db.get(FulfilmentPlan, plan_id)
        if order is None or plan is None:
            raise DomainError("NOT_FOUND", "Plan not found.")
        built = await build_simulated_request(db, order, plan)
        intent = await begin_intent(db, built.request, synthetic=True)
        if intent.status in ("acked", "refreshed"):
            return "acked"
        request = built.request
        source_version = built.source_version
        source_ref = built.source_ref

    # Gọi WMS giả lập ngoài transaction (không giữ khóa DB trong lúc chờ HTTP).
    port = DisposableWmsPort(
        settings.synthetic_wms_url,
        settings.synthetic_wms_api_key,
        source_version=source_version,
        source_ref=source_ref,
    )
    try:
        ack = await port.reserve(request)
    except (WmsTimeout, WmsUnavailable):
        async with get_sessionmaker()() as db, db.begin():
            await record_unknown(db, request.idempotency_key)
        raise DomainError(
            "RESOURCE_CONFLICT", "WMS reservation outcome is unknown; retry with the same key."
        ) from None
    except (WmsDisabled, WmsRejected):
        raise DomainError("PLAN_NOT_APPROVABLE", "WMS reservation was rejected.") from None

    # Transaction 2: xác minh ACK với yêu cầu đã lưu rồi ghi vào ledger.
    async with get_sessionmaker()() as db, db.begin():
        await record_ack(db, request.idempotency_key, ack)
    return "acked"
