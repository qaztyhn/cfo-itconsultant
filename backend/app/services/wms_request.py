"""Dựng yêu cầu giữ hàng WMS HOÀN TOÀN từ dữ liệu phía server (E1, DEC-WMS-REVERSE-SKU-20261109).

Không nhận SKU/đơn vị/số lượng từ client. SKU WMS gốc chỉ lấy từ fixture của WMS giả lập
(SYNTHETIC_WMS_FIXTURE, đường dẫn tuyệt đối, do server cấu hình), đối chiếu với dòng đơn gốc,
catalog ProductSE đã confirmed và kho của plan. Bất kỳ điểm nào không khớp -> 409 PLAN_NOT_APPROVABLE.
"""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.wms_reservation import ReservationRequest, build_request
from app.adapters.wms_sku import (
    ConfirmedMapping,
    OrderLineRef,
    ReverseSkuError,
    WmsSkuRelation,
    resolve_reservation_lines,
)
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder, OrderLine
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.ref import Location, Market, ProductSE


@dataclass(frozen=True)
class BuiltRequest:
    request: ReservationRequest
    source_ref: str
    source_version: int


def _reject(message: str) -> DomainError:
    return DomainError("PLAN_NOT_APPROVABLE", message)


def load_fixture() -> dict[str, Any]:
    raw = os.environ.get("SYNTHETIC_WMS_FIXTURE", "")
    path = Path(raw)
    if not raw or not path.is_absolute() or not path.is_file():
        raise _reject("Synthetic WMS fixture is not configured.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _reject("Synthetic WMS fixture is unreadable.") from None
    if not isinstance(data, dict) or data.get("source_kind") != "synthetic_demo":
        raise _reject("Synthetic WMS fixture is not a disposable demo fixture.")
    return data


def native_evidence(
    fixture: Mapping[str, Any],
    market: str,
    warehouse_code: str,
    units_to_base: Mapping[str, Decimal],
) -> tuple[list[WmsSkuRelation], dict[str, str], set[tuple[str, str]]]:
    """Quan hệ POS<->WMS, phiên bản mapping theo POS SKU và các (kho, SKU WMS) có trong kho."""
    if fixture.get("market") != market:
        raise _reject("Synthetic WMS fixture belongs to another market.")
    relations: list[WmsSkuRelation] = []
    versions: dict[str, str] = {}
    try:
        for row in fixture["mapping"]:
            if row["market"] != market or row["warehouse_code"] != warehouse_code:
                continue
            pos_sku = str(row["pos_sku"])
            if pos_sku not in units_to_base:
                continue
            versions[pos_sku] = str(row["mapping_version"])
            relations.append(
                WmsSkuRelation(
                    market,
                    warehouse_code,
                    pos_sku,
                    str(row["wms_sku"]),
                    str(row["wms_unit"]),
                    units_to_base[pos_sku],
                    False,
                    row.get("confirmed") is True,
                )
            )
        warehouse_skus = {(str(r["warehouse_code"]), str(r["wms_sku"])) for r in fixture["stock"]}
    except (KeyError, TypeError):
        raise _reject("Synthetic WMS fixture is malformed.") from None
    return relations, versions, warehouse_skus


async def build_simulated_request(
    session: AsyncSession, order: CustomerOrder, plan: FulfilmentPlan
) -> BuiltRequest:
    market = await session.get(Market, order.market_id)
    warehouse = await session.get(Location, plan.warehouse_id)
    if market is None or warehouse is None or warehouse.market_id != market.id:
        raise _reject("Order market or plan warehouse is invalid.")
    code = warehouse.code.strip()
    originals = (
        await session.scalars(select(OrderLine).where(OrderLine.order_id == order.id).order_by(OrderLine.id))
    ).all()
    if not originals or any(row.global_product_id is None or row.qty_base is None for row in originals):
        raise _reject("Original order lines are incomplete.")
    products = {
        p.local_sku: p
        for p in (
            await session.scalars(
                select(ProductSE).where(ProductSE.local_sku.in_({row.local_sku for row in originals}))
            )
        ).all()
    }
    relations, versions, warehouse_skus = native_evidence(
        load_fixture(), market.code, code, {sku: p.units_to_base for sku, p in products.items()}
    )
    refs: list[OrderLineRef] = []
    mappings: dict[str, ConfirmedMapping] = {}
    for row in originals:
        product = products.get(row.local_sku)
        version = versions.get(row.local_sku)
        if product is None or product.global_product_id is None or version is None:
            raise _reject("An order line has no verified WMS mapping.")
        assert row.global_product_id is not None and row.qty_base is not None
        refs.append(OrderLineRef(row.id, row.local_sku, row.global_product_id, row.qty_base, version))
        mappings[row.local_sku] = ConfirmedMapping(
            row.local_sku,
            product.global_product_id,
            product.sale_unit,
            product.units_to_base,
            product.mapping_status == "confirmed",
            version,
        )
    try:
        lines = resolve_reservation_lines(market.code, code, refs, mappings, relations, warehouse_skus)
    except ReverseSkuError as error:
        raise _reject(f"WMS reservation lines are not verified ({error.code}).") from None
    return BuiltRequest(
        build_request(market.code, order.id, plan.id, lines), order.external_ref, order.source_version
    )
