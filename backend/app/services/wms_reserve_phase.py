"""Giai đoạn giữ hàng WMS mô phỏng trước khi duyệt (E1, DEC-WMS-RESERVE-SYNC-20261109).

Không commit APPROVED. Mỗi bước dùng transaction riêng: lưu intent trước khi gọi WMS,
rồi ghi ACK sau khi WMS trả lời. Lỗi không rõ kết quả được ghi là 'unknown' để retry
cùng khóa idempotency.
"""

from sqlalchemy import select

from app.adapters.base import StockSnapshotDTO
from app.adapters.disposable_wms_client import DisposableWmsPort
from app.adapters.disposable_wms_service import verify_batch
from app.adapters.wms_batch_stock import WmsBatchRejected, snapshot_from_wms_batch
from app.adapters.wms_reservation import WmsDisabled, WmsRejected, WmsTimeout, WmsUnavailable
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.ref import Market
from app.domain.models.wms import WmsReservationIntent
from app.services.wms_intent import begin_intent, record_ack, record_unknown
from app.services.wms_mode import simulated_enabled
from app.services.wms_request import build_simulated_request, load_fixture


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


async def fetch_verified_batch(order_id: int, plan_id: int) -> tuple[int, StockSnapshotDTO]:
    """Tải batch đã ký của WMS giả lập và xác minh nó chứa đúng lượt giữ hàng. Không ghi DB."""
    settings = get_settings()
    if not (
        settings.synthetic_wms_url and settings.synthetic_wms_api_key and settings.synthetic_wms_shared_key
    ):
        raise DomainError("PLAN_NOT_APPROVABLE", "Simulated WMS batch verification is not configured.")

    async with get_sessionmaker()() as db, db.begin():
        order = await db.get(CustomerOrder, order_id)
        plan = await db.get(FulfilmentPlan, plan_id)
        if order is None or plan is None:
            raise DomainError("NOT_FOUND", "Plan not found.")
        market = await db.get(Market, order.market_id)
        if market is None:
            raise DomainError("NOT_FOUND", "Market not found.")
        built = await build_simulated_request(db, order, plan)
        intent = await db.scalar(
            select(WmsReservationIntent).where(WmsReservationIntent.order_id == order.id)
        )
        if intent is None or not intent.reservation_id:
            raise DomainError("PLAN_NOT_APPROVABLE", "No acknowledged WMS reservation.")
        reservation_id = intent.reservation_id
        market_code = market.code

    fixture = load_fixture()
    native_to_pos = {
        (str(row["warehouse_code"]), str(row["wms_sku"])): (str(row["pos_sku"]), str(row["wms_unit"]))
        for row in fixture["mapping"]
        if row["market"] == market_code and row.get("confirmed") is True
    }
    port = DisposableWmsPort(
        settings.synthetic_wms_url,
        settings.synthetic_wms_api_key,
        source_version=built.source_version,
        source_ref=built.source_ref,
    )
    try:
        batch = await port.fetch_batch()
    except (WmsDisabled, WmsRejected, WmsTimeout, WmsUnavailable):
        raise DomainError("RESOURCE_CONFLICT", "WMS batch is unavailable; retry.") from None
    if not verify_batch(batch, settings.synthetic_wms_shared_key, expected_reservation_id=reservation_id):
        raise DomainError("PLAN_NOT_APPROVABLE", "WMS batch does not prove reservation inclusion.")
    try:
        snapshot = snapshot_from_wms_batch(batch, native_to_pos)
    except WmsBatchRejected as error:
        raise DomainError("PLAN_NOT_APPROVABLE", f"WMS batch rejected: {error}") from None
    if snapshot.batch_id is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "WMS batch has no batch id.")
    return snapshot.batch_id, snapshot
