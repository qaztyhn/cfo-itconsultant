"""Ánh xạ SKU, chỉ IT (09 bất biến 9; US-PRD-01..05).

Tạo/cập nhật mapping_task (blocked_order_count), tính ứng viên (engine.mapping_candidates + pg_trgm),
confirm (chọn hoặc tạo global; N6 không được có FRAGILE → 422) → mở khóa đơn BLOCKED_UNMAPPED_SKU → lập kế
hoạch; reject bắt buộc lý do. Ghi MAPPING_CONFIRMED/MAPPING_REJECTED.

Owner: Dev 1 (A) — M2.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import ensure_reason, record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.enums import OrderStatus
from app.domain.models.ops import CustomerOrder, OrderLine
from app.domain.models.ref import HandlingGroup, MappingTask, Market, ProductGlobal, SpecialFlag
from app.domain.transitions import SYSTEM_ROLE, transition
from app.engine.mapping_candidates import build_candidates

MAPPER_ROLE = "admin"  # BR-PRD-02: chỉ IT (vai trò admin) xác nhận/từ chối ánh xạ
N6_CODE, FRAGILE = "N6", "FRAGILE"  # BR-PRD-04: N6 đã tính độ dễ vỡ trong định mức
_MARKET_CODE = re.compile(r"[A-Z]{2}")

_UPSERT_TASK = text("""
INSERT INTO ref.mapping_task AS t (market_id, local_sku, blocked_order_count)
VALUES (:market_id, :local_sku, (
    SELECT count(DISTINCT o.id) FROM ops.customer_order o JOIN ops.order_line l ON l.order_id = o.id
    WHERE o.market_id = :market_id AND o.status = 'BLOCKED_UNMAPPED_SKU' AND l.local_sku = :local_sku
      AND l.global_product_id IS NULL))
ON CONFLICT (market_id, local_sku) DO UPDATE SET blocked_order_count = EXCLUDED.blocked_order_count
RETURNING t.id
""")


NAME_SIM_THRESHOLD = Decimal("0.45")  # 04 mục 6.5: pg_trgm ≥ 0,45, cùng category

_GTIN_MATCHES = text("SELECT id FROM ref.product_global WHERE gtin = :gtin")
_NAME_SIMILAR = text("""
SELECT id, round(similarity(name, :name)::numeric, 4) AS score FROM ref.product_global
WHERE category = :category AND similarity(name, :name) >= :threshold
""")


async def _candidates(session: AsyncSession, market_code: str, sku: str) -> list[dict[str, object]]:
    """Ứng viên ánh xạ (US-PRD-01 AC3/AC4): GTIN trùng, tên gần giống cùng category; engine gộp và sắp."""
    product = (
        (
            await session.execute(
                text(
                    f"SELECT name, category, gtin FROM {_product_table(market_code)} WHERE local_sku = :sku"
                ),
                {"sku": sku},
            )
        )
        .mappings()
        .first()
    )
    if product is None:
        return []
    gtin = product["gtin"]
    gtin_ids = [int(i) for i in (await session.scalars(_GTIN_MATCHES, {"gtin": gtin})).all()] if gtin else []
    similar = [
        (int(row.id), Decimal(row.score))
        for row in await session.execute(
            _NAME_SIMILAR,
            {"name": product["name"], "category": product["category"], "threshold": NAME_SIM_THRESHOLD},
        )
    ]
    built = build_candidates(gtin, gtin_ids, similar, NAME_SIM_THRESHOLD)
    return [
        {"global_product_id": c.global_product_id, "reason": c.reason, "score": float(c.score)} for c in built
    ]


async def ensure_task(session: AsyncSession, market_id: int, local_sku: str) -> int:
    """Tạo hoặc cập nhật mapping_task cho (market, SKU); trả id (US-PRD-01 AC1–AC4).

    blocked_order_count được TÍNH LẠI = số đơn đang BLOCKED_UNMAPPED_SKU của market có dòng chứa SKU chưa ánh
    xạ (global_product_id NULL; đơn còn bị chặn vì SKU khác không tính cho SKU đã xác nhận), thay vì
    cộng dồn, nên gọi lại cho cùng một đơn (nhập lại, chạy lại) không đếm trùng. `candidates` được tính lại từ
    danh mục hiện tại. Gọi SAU khi đơn đã chuyển trạng thái, trong cùng transaction. Không đổi
    status/assigned_to của task đã có. Không commit.
    """
    result = await session.execute(_UPSERT_TASK, {"market_id": market_id, "local_sku": local_sku})
    task_id = int(result.scalar_one())
    market_code = await session.scalar(select(Market.code).where(Market.id == market_id))
    if market_code and _MARKET_CODE.fullmatch(market_code):
        await session.execute(
            update(MappingTask)
            .where(MappingTask.id == task_id)
            .values(candidates=await _candidates(session, market_code, local_sku))
            .execution_options(synchronize_session=False)
        )
    return task_id


class Mapper(Protocol):
    """Người gọi (CurrentUser thỏa mãn)."""

    @property
    def id(self) -> int: ...
    @property
    def employee_id(self) -> int | None: ...
    @property
    def roles(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class NewGlobal:
    """`create_global` của 06 mục 12.1."""

    code: str
    name: str
    category: str
    base_unit: str
    weight_kg: Decimal
    volume_m3: Decimal
    handling_group_code: str
    gtin: str | None = None
    base_units_per_prep_unit: Decimal | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfirmInput:
    """Đúng một trong global_product_id / create_global; units_to_base > 0 (US-PRD-02 AC3)."""

    units_to_base: Decimal
    global_product_id: int | None = None
    create_global: NewGlobal | None = None


@dataclass(frozen=True)
class ConfirmResult:
    global_product_id: int
    ready_order_ids: tuple[int, ...] = ()  # đơn đã về SUBMITTED, đủ ánh xạ → caller lập kế hoạch (M4)
    still_blocked_order_ids: tuple[int, ...] = field(default=())  # còn SKU khác chưa ánh xạ


def _invalid(field_name: str, message: str) -> DomainError:
    return DomainError("VALIDATION_ERROR", message, {"field": field_name})


def _require_mapper(actor: Mapper) -> int:
    """Chỉ admin có hồ sơ nhân viên (mapped_by NOT NULL khi confirmed — ck_se_confirmed). Trả employee_id."""
    if MAPPER_ROLE not in actor.roles or actor.employee_id is None:
        raise DomainError("FORBIDDEN", "Only IT (admin with an employee record) may resolve mappings.")
    return actor.employee_id


async def _load_task(
    session: AsyncSession, task_id: int, market_id: int | None = None
) -> tuple[MappingTask, str]:
    """Task theo id; `market_id` (phạm vi admin gắn market) khác → 404 như không tồn tại."""
    row = (
        await session.execute(
            select(MappingTask, Market.code)
            .join(Market, Market.id == MappingTask.market_id)
            .where(MappingTask.id == task_id)
            .with_for_update(of=MappingTask)
        )
    ).first()
    if row is None or (market_id is not None and row[0].market_id != market_id):
        raise DomainError("NOT_FOUND", "Mapping task not found.")
    task, market_code = row
    if not _MARKET_CODE.fullmatch(market_code):
        raise DomainError("VALIDATION_ERROR", "Unsupported market code.")
    return task, market_code


def _product_table(market_code: str) -> str:
    """ref.product_<cc> (05: mỗi nước một bảng). Mã đã kiểm [A-Z]{2} nên ghép tên bảng an toàn."""
    return f"ref.product_{market_code.lower()}"


async def _local_product(session: AsyncSession, market_code: str, sku: str) -> dict[str, Any] | None:
    sql = text(
        f"SELECT local_sku, global_product_id, units_to_base, mapping_status::text AS mapping_status "
        f"FROM {_product_table(market_code)} WHERE local_sku = :sku FOR UPDATE"
    )
    row = (await session.execute(sql, {"sku": sku})).mappings().first()
    return None if row is None else dict(row)


def _snapshot(product: dict[str, Any]) -> dict[str, object]:
    return {
        "mapping_status": product["mapping_status"],
        "global_product_id": product["global_product_id"],
        "units_to_base": str(product["units_to_base"]),
    }


async def _create_global(session: AsyncSession, new: NewGlobal, employee_id: int) -> int:
    """Tạo product_global theo 06 mục 12.1 / US-PRD-02 AC3 / US-PRD-04 AC4."""
    for name in ("code", "name", "category", "base_unit"):
        if not str(getattr(new, name)).strip():
            raise _invalid(f"create_global.{name}", f"{name} is required.")
    if new.weight_kg <= 0:
        raise _invalid("create_global.weight_kg", "weight_kg must be > 0.")
    if new.volume_m3 <= 0:
        raise _invalid("create_global.volume_m3", "volume_m3 must be > 0.")
    group = await session.scalar(select(HandlingGroup).where(HandlingGroup.code == new.handling_group_code))
    if group is None:
        raise _invalid("create_global.handling_group_code", "Unknown handling group.")
    if group.prep_unit != "line" and (
        new.base_units_per_prep_unit is None or new.base_units_per_prep_unit <= 0
    ):
        raise _invalid("create_global.base_units_per_prep_unit", "Required (> 0) unless prep unit is 'line'.")
    flags = tuple(dict.fromkeys(new.flags))
    if group.code == N6_CODE and FRAGILE in flags:
        raise _invalid("create_global.flags", "Group N6 must not carry the FRAGILE flag.")
    known = set((await session.scalars(select(SpecialFlag.code).where(SpecialFlag.code.in_(flags)))).all())
    if unknown := [f for f in flags if f not in known]:
        raise _invalid("create_global.flags", f"Unknown flags: {', '.join(unknown)}.")
    clash = [ProductGlobal.code == new.code] + ([ProductGlobal.gtin == new.gtin] if new.gtin else [])
    taken = select(ProductGlobal.id).where(or_(*clash))
    if await session.scalar(taken) is not None:
        raise _invalid("create_global.code", "A global product with this code or GTIN already exists.")
    product = ProductGlobal(
        code=new.code,
        name=new.name,
        category=new.category,
        gtin=new.gtin,
        base_unit=new.base_unit,
        weight_kg=new.weight_kg,
        volume_m3=new.volume_m3,
        handling_group_id=group.id,
        base_units_per_prep_unit=new.base_units_per_prep_unit,
        flags=list(flags),
        created_by=employee_id,
    )
    session.add(product)
    await session.flush()
    return product.id


async def _blocked_orders(session: AsyncSession, market_id: int, sku: str) -> list[int]:
    query = (
        select(CustomerOrder.id)
        .where(
            CustomerOrder.market_id == market_id,
            CustomerOrder.status == OrderStatus.BLOCKED_UNMAPPED_SKU.value,
            select(OrderLine.id)
            .where(OrderLine.order_id == CustomerOrder.id, OrderLine.local_sku == sku)
            .exists(),
        )
        .order_by(CustomerOrder.id)
        .with_for_update()
    )
    return list((await session.scalars(query)).all())


async def confirm(
    session: AsyncSession,
    task_id: int,
    actor: Mapper,
    payload: ConfirmInput,
    *,
    market_id: int | None = None,
) -> ConfirmResult:
    """Xác nhận ánh xạ (06 mục 12.1; US-PRD-02 AC1–AC4; BR-PRD-02/04).

    product_<cc> → confirmed (global, units_to_base, mapped_by/mapped_at); task → done; các đơn
    BLOCKED_UNMAPPED_SKU chứa SKU → SUBMITTED (transition, vai trò system) rồi kiểm lại ánh xạ: đủ thì
    sẵn sàng lập kế hoạch (caller gọi PlanningService, M4), còn SKU khác thì bị chặn lại với lý do mới. Ghi
    MAPPING_CONFIRMED kèm trước/sau. Một transaction của caller; không commit.
    """
    from app.services.order_service import prepare_for_planning  # tránh vòng import order ↔ mapping

    employee_id = _require_mapper(actor)
    if payload.units_to_base <= 0:
        raise _invalid("units_to_base", "units_to_base must be > 0.")
    if (payload.global_product_id is None) == (payload.create_global is None):
        raise _invalid("global_product_id", "Provide exactly one of global_product_id or create_global.")
    task, market_code = await _load_task(session, task_id, market_id)
    product = await _local_product(session, market_code, task.local_sku)
    if product is None:
        raise _invalid("local_sku", "Local product is not in the catalogue yet; sync products first.")
    if payload.create_global is not None:
        global_id = await _create_global(session, payload.create_global, employee_id)
    else:
        global_id = int(payload.global_product_id or 0)
        if await session.get(ProductGlobal, global_id) is None:
            raise _invalid("global_product_id", "Global product not found.")
    now = clock.now()
    await session.execute(
        text(
            f"UPDATE {_product_table(market_code)} SET global_product_id = :gid, units_to_base = :utb, "
            "mapping_status = 'confirmed', mapped_by = :emp, mapped_at = :now WHERE local_sku = :sku"
        ),
        {
            "gid": global_id,
            "utb": payload.units_to_base,
            "emp": employee_id,
            "now": now,
            "sku": task.local_sku,
        },
    )
    ready: list[int] = []
    still_blocked: list[int] = []
    for order_id in await _blocked_orders(session, task.market_id, task.local_sku):
        await session.execute(
            update(CustomerOrder).where(CustomerOrder.id == order_id).values(block_reason=None)
        )
        await transition(session, order_id, OrderStatus.SUBMITTED, SYSTEM_ROLE)
        result = await prepare_for_planning(session, order_id)
        (ready if result.status == OrderStatus.SUBMITTED else still_blocked).append(order_id)
    task.status, task.resolved_by, task.resolved_at = "done", employee_id, now
    await session.flush()
    await ensure_task(session, task.market_id, task.local_sku)
    after = {
        "mapping_status": "confirmed",
        "global_product_id": global_id,
        "units_to_base": str(payload.units_to_base),
        "created_global": payload.create_global is not None,
        "ready_order_ids": ready,
        "still_blocked_order_ids": still_blocked,
    }
    await record_decision(
        session,
        Action.MAPPING_CONFIRMED,
        "mapping_task",
        str(task_id),
        before=_snapshot(product),
        after=after,
        snapshot={"market": market_code, "local_sku": task.local_sku},
        actor_user_id=actor.id,
        actor_employee_id=employee_id,
        actor_role=MAPPER_ROLE,
    )
    return ConfirmResult(global_id, tuple(ready), tuple(still_blocked))


async def reject(
    session: AsyncSession,
    task_id: int,
    actor: Mapper,
    reason_text: str | None,
    *,
    market_id: int | None = None,
) -> None:
    """Từ chối ánh xạ (06 mục 12; US-PRD-03 AC1/AC2; BR-GEN-04).

    Thiếu lý do → 422 REASON_REQUIRED (kiểm trước mọi thay đổi). SKU → rejected; task → done; đơn liên quan
    VẪN bị chặn, block_reason thêm lý do từ chối để dispatcher thấy. SKU đã confirmed không từ chối được
    (ASM-005).
    Ghi MAPPING_REJECTED. Không commit.
    """
    employee_id = _require_mapper(actor)
    ensure_reason(Action.MAPPING_REJECTED, None, reason_text)
    reason = (reason_text or "").strip()
    task, market_code = await _load_task(session, task_id, market_id)
    if task.status == "done":
        raise _invalid("status", "Mapping task is already resolved.")
    product = await _local_product(session, market_code, task.local_sku)
    if product is not None and product["mapping_status"] == "confirmed":
        raise _invalid("mapping_status", "A confirmed mapping cannot be rejected.")
    now = clock.now()
    if product is not None:
        await session.execute(
            text(
                f"UPDATE {_product_table(market_code)} SET mapping_status = 'rejected', mapped_at = :now "
                "WHERE local_sku = :sku"
            ),
            {"now": now, "sku": task.local_sku},
        )
    note = f" | REJECTED {task.local_sku}: {reason}"
    for order_id in await _blocked_orders(session, task.market_id, task.local_sku):
        await session.execute(
            update(CustomerOrder)
            .where(CustomerOrder.id == order_id)
            .values(block_reason=func.coalesce(CustomerOrder.block_reason, "").concat(note))
        )
    task.status, task.resolved_by, task.resolved_at = "done", employee_id, now
    await session.flush()
    await record_decision(
        session,
        Action.MAPPING_REJECTED,
        "mapping_task",
        str(task_id),
        reason_text=reason,
        before=None if product is None else _snapshot(product),
        after={"mapping_status": "rejected", "blocked_order_count": task.blocked_order_count},
        snapshot={"market": market_code, "local_sku": task.local_sku},
        actor_user_id=actor.id,
        actor_employee_id=employee_id,
        actor_role=MAPPER_ROLE,
    )
