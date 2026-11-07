"""Đọc hàng đợi ánh xạ và danh mục sản phẩm cục bộ (06 v1.4 mục 12.2; US-PRD-01, US-PRD-05).

Quyền theo ma trận 06 mục 3: admin, dispatcher, warehouse đọc trong market của mình (admin không gắn nhân
viên: mọi market) — dùng chung HrReadScope (cùng ba vai trò, cùng quy tắc market). Task ngoài market → 404.

Owner: Dev 1 (A) — M2.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.domain.enums import OrderStatus
from app.domain.models.ops import CustomerOrder, OrderLine
from app.domain.models.ref import HandlingGroup, HandlingGroupRule, MappingTask, Market, ProductGlobal
from app.engine.mapping_candidates import suggest_group
from app.services.hr_scope import HrReadScope
from app.services.order_scope import warehouse_orders
from app.services.query_utils import parse_sort

TASK_STATUSES = frozenset({"open", "in_progress", "done"})
MAPPING_STATUSES = frozenset({"pending", "suggested", "confirmed", "rejected"})
TASK_SORT = frozenset({"blocked_order_count", "local_sku", "id"})
PRODUCT_SORT = frozenset({"local_sku", "name", "category", "mapping_status"})

_LOCAL = text("""
SELECT market_code, local_sku, name, category, gtin, sale_unit, units_to_base, unit_price, currency,
       global_product_id, mapping_status::text AS mapping_status
FROM ref.v_product_local
WHERE market_code = ANY(:markets) AND local_sku = ANY(:skus)
""")


def _invalid(field: str, message: str) -> DomainError:
    return DomainError("VALIDATION_ERROR", message, {"field": field})


async def _market_codes(session: AsyncSession, scope: HrReadScope, market: str | None) -> list[str]:
    """Market được đọc: của người gọi; admin hệ thống mọi market (lọc thêm bằng `market`)."""
    query = select(Market.code)
    if scope.market_id is not None:
        query = query.where(Market.id == scope.market_id)
    codes = [c.strip() for c in (await session.scalars(query)).all()]
    if market is not None:
        codes = [c for c in codes if c == market.upper()]
    return codes


def _task_market(scope: HrReadScope) -> ColumnElement[bool] | None:
    return None if scope.market_id is None else MappingTask.market_id == scope.market_id


async def _views(session: AsyncSession, rows: list[tuple[MappingTask, str]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    markets = sorted({code.strip() for _, code in rows})
    skus = sorted({task.local_sku for task, _ in rows})
    local = {
        (r["market_code"].strip(), r["local_sku"]): r
        for r in (await session.execute(_LOCAL, {"markets": markets, "skus": skus})).mappings()
    }
    global_ids = {int(c["global_product_id"]) for task, _ in rows for c in task.candidates}
    globals_ = {
        g.id: g
        for g in (await session.scalars(select(ProductGlobal).where(ProductGlobal.id.in_(global_ids))))
    }
    out = []
    for task, code in rows:
        product = local.get((code.strip(), task.local_sku))
        out.append(
            {
                "id": task.id,
                "market": code.strip(),
                "local_sku": task.local_sku,
                "name": product["name"] if product else None,
                "category": product["category"] if product else None,
                "gtin": product["gtin"] if product else None,
                "sale_unit": product["sale_unit"] if product else None,
                "mapping_status": product["mapping_status"] if product else None,
                "status": task.status,
                "blocked_order_count": task.blocked_order_count,
                "candidates": [
                    {
                        "global_product_id": int(c["global_product_id"]),
                        "code": globals_[int(c["global_product_id"])].code,
                        "name": globals_[int(c["global_product_id"])].name,
                        "reason": c["reason"],
                        "score": float(c["score"]),
                    }
                    for c in task.candidates
                    if int(c["global_product_id"]) in globals_
                ],
                "resolved_by": task.resolved_by,
                "resolved_at": task.resolved_at,
            }
        )
    return out


def _task_base(scope: HrReadScope) -> Select[MappingTask, str]:
    query = select(MappingTask, Market.code).join(Market, Market.id == MappingTask.market_id)
    condition = _task_market(scope)
    return query if condition is None else query.where(condition)


async def list_tasks(
    session: AsyncSession,
    scope: HrReadScope,
    *,
    status: str | None,
    market: str | None,
    q: str | None,
    sort: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    """GET /mapping/tasks — mặc định status=open; sắp `-blocked_order_count,local_sku`."""
    wanted = status or "open"
    if wanted not in TASK_STATUSES:
        raise _invalid("status", "Unknown task status.")
    query = _task_base(scope).where(MappingTask.status == wanted)
    if market is not None:
        query = query.where(Market.code == market.upper())
    if q:
        query = query.where(MappingTask.local_sku.ilike(f"%{q.strip()}%"))
    columns = {"blocked_order_count": MappingTask.blocked_order_count, "local_sku": MappingTask.local_sku,
               "id": MappingTask.id}  # fmt: skip
    order = [columns[f].desc() if desc else columns[f].asc() for f, desc in parse_sort(sort, TASK_SORT,
             "-blocked_order_count,local_sku")]  # fmt: skip
    total = int(
        (
            await session.execute(select(func.count()).select_from(query.order_by(None).subquery()))
        ).scalar_one()
    )
    rows = (
        await session.execute(
            query.order_by(*order, MappingTask.id).limit(page_size).offset((page - 1) * page_size)
        )
    ).all()
    return await _views(session, [(t, c) for t, c in rows]), total


async def get_task(session: AsyncSession, scope: HrReadScope, task_id: int) -> dict[str, Any]:
    """GET /mapping/tasks/{id}: + suggested_handling_group, blocked_orders (warehouse: đơn trong phạm vi)."""
    row = (await session.execute(_task_base(scope).where(MappingTask.id == task_id))).first()
    if row is None:
        raise DomainError("NOT_FOUND", "Mapping task not found.")
    task, code = row
    [view] = await _views(session, [(task, code)])
    weight = (
        await session.execute(
            text(
                f"SELECT category, weight_kg FROM ref.product_{code.strip().lower()} WHERE local_sku = :sku"
            ),
            {"sku": task.local_sku},
        )
    ).first()
    view["suggested_handling_group"] = None
    if weight is not None:
        rules = [
            (r.priority, r.category_like, r.min_weight_kg, r.max_weight_kg, g)
            for r, g in (
                await session.execute(
                    select(HandlingGroupRule, HandlingGroup.code)
                    .join(HandlingGroup, HandlingGroup.id == HandlingGroupRule.handling_group_id)
                    .order_by(HandlingGroupRule.priority, HandlingGroupRule.id)
                )
            ).all()
        ]
        if weight.weight_kg is None:  # không biết khối lượng: chỉ dùng quy tắc không có khoảng khối lượng
            rules = [r for r in rules if r[2] is None and r[3] is None]
        view["suggested_handling_group"] = suggest_group(
            weight.category, Decimal(weight.weight_kg or 0), rules
        )
    orders = (
        select(CustomerOrder.id, CustomerOrder.order_no)
        .where(
            CustomerOrder.market_id == task.market_id,
            CustomerOrder.status == OrderStatus.BLOCKED_UNMAPPED_SKU.value,
            select(OrderLine.id)
            .where(
                OrderLine.order_id == CustomerOrder.id,
                OrderLine.local_sku == task.local_sku,
                OrderLine.global_product_id.is_(None),
            )
            .exists(),
        )
        .order_by(CustomerOrder.submitted_at, CustomerOrder.id)
    )
    if scope.role == "warehouse":
        orders = orders.where(warehouse_orders(scope.location_ids))
    view["blocked_orders"] = [{"id": i, "order_no": n} for i, n in (await session.execute(orders)).all()]
    return view


async def list_local_products(
    session: AsyncSession,
    scope: HrReadScope,
    *,
    market: str | None,
    mapping_status: str | None,
    q: str | None,
    sort: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    """GET /products/local (US-PRD-05 AC1): cột của ref.v_product_local, phân trang, mặc định `local_sku`."""
    if mapping_status is not None and mapping_status not in MAPPING_STATUSES:
        raise _invalid("mapping_status", "Unknown mapping status.")
    order = ", ".join(
        f"{field} {'DESC' if desc else 'ASC'}" for field, desc in parse_sort(sort, PRODUCT_SORT, "local_sku")
    )  # tên cột đã kiểm theo PRODUCT_SORT nên ghép an toàn
    where = ["market_code = ANY(:markets)"]
    params: dict[str, object] = {"markets": await _market_codes(session, scope, market)}
    if mapping_status is not None:
        where.append("mapping_status = CAST(:status AS ref.mapping_status)")
        params["status"] = mapping_status
    if q:
        where.append("(local_sku ILIKE :q OR name ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    clause = " AND ".join(where)
    total = int(
        (
            await session.execute(text(f"SELECT count(*) FROM ref.v_product_local WHERE {clause}"), params)
        ).scalar_one()
    )
    rows = (
        await session.execute(
            text(
                "SELECT market_code, local_sku, name, category, gtin, sale_unit, units_to_base, unit_price, "
                "currency, global_product_id, mapping_status::text AS mapping_status "
                f"FROM ref.v_product_local WHERE {clause} "
                f"ORDER BY {order}, market_code, local_sku LIMIT :limit OFFSET :offset"
            ),
            params | {"limit": page_size, "offset": (page - 1) * page_size},
        )
    ).mappings()
    items = [dict(r) | {"market": r["market_code"].strip()} for r in rows]
    for item in items:
        item.pop("market_code")
    return items, total
