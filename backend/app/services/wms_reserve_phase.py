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
from app.adapters.wms_reservation import (
    WmsDisabled,
    WmsRejected,
    WmsTimeout,
    WmsUnavailable,
)
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder, StockWriteRun
from app.domain.models.plan import FulfilmentPlan, PlanningRun
from app.domain.models.ref import Market, ProductSE
from app.domain.models.wms import WmsReservationIntent
from app.services.wms_intent import (
    begin_intent,
    mark_refreshed,
    record_ack,
    record_unknown,
)
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
        # A previous attempt can have reached WMS even when CFO lost its ACK.
        # Query the same immutable request key before any reserve retry.
        ack = await port.status(request.market, request.idempotency_key)
        if ack is None:
            ack = await port.reserve(request)
    except (WmsTimeout, WmsUnavailable):
        async with get_sessionmaker()() as db, db.begin():
            await record_unknown(db, request.idempotency_key)
        raise DomainError(
            "RESOURCE_CONFLICT",
            "WMS reservation outcome is unknown; retry with the same key.",
        ) from None
    except (WmsDisabled, WmsRejected):
        raise DomainError("PLAN_NOT_APPROVABLE", "WMS reservation was rejected.") from None

    # Transaction 2: xác minh ACK với yêu cầu đã lưu rồi ghi vào ledger.
    async with get_sessionmaker()() as db, db.begin():
        await record_ack(db, request.idempotency_key, ack)
    return "acked"


async def fetch_verified_batch(
    order_id: int, plan_id: int
) -> tuple[int, StockSnapshotDTO, dict[str, object]]:
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
        (str(row["warehouse_code"]), str(row["wms_sku"])): (
            str(row["pos_sku"]),
            str(row["wms_unit"]),
        )
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
    if batch.get("as_of") != settings.app_now or batch.get("batch_id", 0) < intent.reflected_in_batch_id:
        raise DomainError(
            "PLAN_NOT_APPROVABLE",
            "WMS batch does not match the acknowledged demo clock.",
        )
    try:
        snapshot = snapshot_from_wms_batch(batch, native_to_pos)
    except WmsBatchRejected as error:
        raise DomainError("PLAN_NOT_APPROVABLE", f"WMS batch rejected: {error}") from None
    if snapshot.batch_id is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "WMS batch has no batch id.")
    return snapshot.batch_id, snapshot, batch


async def refresh_simulated(order_id: int, plan_id: int) -> None:
    """Ingest the signed post-ACK WMS batch through T07 scope checks, then bind its accepted write."""
    from app.adapters.wms_batch_stock import WmsBatchStockAdapter
    from app.services.ingest_service import sync_entity

    batch_id, snapshot, batch = await fetch_verified_batch(order_id, plan_id)
    async with get_sessionmaker()() as db:
        order = await db.get(CustomerOrder, order_id)
        market = await db.get(Market, order.market_id) if order else None
        if order is None or market is None:
            raise DomainError("NOT_FOUND", "Order market is unavailable.")
        skus = {row.sku for row in snapshot.items}
        products = (await db.scalars(select(ProductSE).where(ProductSE.local_sku.in_(skus)))).all()
        if {p.local_sku for p in products} != skus:
            raise DomainError("PLAN_NOT_APPROVABLE", "WMS stock unit catalogue is incomplete.")
        catalog = [
            {
                "sku": p.local_sku,
                "name": p.name,
                "category": p.category,
                "gtin": p.gtin,
                "sale_unit": p.sale_unit,
                "units_to_base": p.units_to_base,
                "unit_price": p.unit_price,
                "weight_kg": p.weight_kg,
                "volume_m3": p.volume_m3,
                "updated_at": p.source_updated_at or snapshot.as_of,
            }
            for p in products
        ]
        market_code = market.code
    result = await sync_entity(
        market_code,
        "stock",
        adapter=WmsBatchStockAdapter(market_code, snapshot, catalog),
        stock_origin="wms_synthetic",
        now=snapshot.as_of,
    )
    if result.status != "ok":
        raise DomainError("RESOURCE_CONFLICT", "WMS stock batch was not accepted by CFO ingestion.")
    async with get_sessionmaker()() as db, db.begin():
        intent = await db.scalar(
            select(WmsReservationIntent).where(WmsReservationIntent.order_id == order_id).with_for_update()
        )
        write = (
            await db.scalar(
                select(StockWriteRun).where(
                    StockWriteRun.market_id == intent.market_id,
                    StockWriteRun.source_kind == "wms_synthetic",
                    StockWriteRun.source_batch_id == batch_id,
                    StockWriteRun.status == "accepted",
                )
            )
            if intent
            else None
        )
        if intent is None or write is None:
            raise DomainError("PLAN_NOT_APPROVABLE", "Accepted WMS stock write is missing.")
        await mark_refreshed(
            db,
            intent.request_key,
            batch_id=batch_id,
            inclusion_proven=True,
            write_run_id=write.id,
            batch_sha256=str(batch["sha256"]),
            batch_payload=batch,
        )


async def release_invalid_plan(plan_id: int) -> None:
    """Release a verified WMS hold only when the plan can no longer commit."""
    settings = get_settings()
    async with get_sessionmaker()() as db:
        plan = await db.get(FulfilmentPlan, plan_id)
        if plan is None:
            return
        order = await db.get(CustomerOrder, plan.order_id)
        market = await db.get(Market, order.market_id) if order else None
        intent = (
            await db.scalar(select(WmsReservationIntent).where(WmsReservationIntent.order_id == order.id))
            if order
            else None
        )
        if order is None or market is None or intent is None or intent.plan_id != plan_id:
            return
        if intent.status not in ("acked", "refreshed") or not intent.reservation_id:
            return
        run = await db.get(PlanningRun, plan.run_id)
        invalid = (
            run is None
            or order.status != "PLANNED"
            or plan.status != "proposed"
            or order.version != intent.order_version
            or order.source_version != intent.source_version
            or run.hold_expires_at is None
            or run.hold_expires_at <= clock.now()
        )
        if not invalid:
            return
        key, reservation_id, source_ref, source_version, market_code = (
            intent.request_key,
            intent.reservation_id,
            order.external_ref,
            intent.source_version,
            market.code,
        )
    if not settings.synthetic_wms_url or not settings.synthetic_wms_api_key:
        return
    port = DisposableWmsPort(
        settings.synthetic_wms_url,
        settings.synthetic_wms_api_key,
        source_version=source_version,
        source_ref=source_ref,
    )
    ack = await port.release(market_code, reservation_id, key + ":release")
    if ack.status != "released" or ack.reservation_id != reservation_id:
        raise DomainError("RESOURCE_CONFLICT", "WMS release outcome is not verified.")
    async with get_sessionmaker()() as db, db.begin():
        intent = await db.scalar(
            select(WmsReservationIntent).where(WmsReservationIntent.request_key == key).with_for_update()
        )
        if intent is not None and intent.status in ("acked", "refreshed"):
            intent.status = "released"
