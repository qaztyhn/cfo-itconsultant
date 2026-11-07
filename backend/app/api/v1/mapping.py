"""Sản phẩm, ánh xạ, nhóm xử lý (06 mục 12). Ghi CHỈ admin.

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M2.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.v1.common import Page, PageNo, PageSize, SortParam
from app.core.errors import DomainError
from app.deps import AuthUser, DbSession
from app.domain.models.ref import MappingTask
from app.services import mapping_read_service, mapping_service
from app.services.hr_scope import resolve_hr_scope

router = APIRouter(tags=["mapping"])


class CandidateOut(BaseModel):
    global_product_id: int
    code: str
    name: str
    reason: str
    score: float


class MappingTaskOut(BaseModel):
    id: int
    market: str
    local_sku: str
    name: str | None
    category: str | None
    gtin: str | None
    sale_unit: str | None
    mapping_status: str | None
    status: str
    blocked_order_count: int
    candidates: list[CandidateOut]
    resolved_by: int | None
    resolved_at: datetime | None
    suggested_handling_group: str | None = None


class NewGlobalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    gtin: str | None = Field(default=None, max_length=32)
    base_unit: str = Field(min_length=1, max_length=32)
    weight_kg: Decimal
    volume_m3: Decimal
    handling_group_code: str
    base_units_per_prep_unit: Decimal | None = None
    flags: list[str] = []


class ConfirmIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"example": {"global_product_id": 123, "units_to_base": 40}}
    )
    units_to_base: Decimal
    global_product_id: int | None = None
    create_global: NewGlobalIn | None = None


class ConfirmOut(BaseModel):
    task_id: int
    local_sku: str
    global_product_id: int
    mapping_status: Literal["confirmed"] = "confirmed"


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason_text: str | None = Field(default=None, max_length=1000)


class RejectOut(BaseModel):
    task_id: int
    local_sku: str
    mapping_status: Literal["rejected"] = "rejected"


class LocalProductOut(BaseModel):
    market: str
    local_sku: str
    name: str
    category: str
    gtin: str | None
    sale_unit: str
    units_to_base: Decimal
    unit_price: Decimal
    currency: str
    global_product_id: int | None
    mapping_status: str


_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "AUTH_INVALID"},
    403: {"description": "FORBIDDEN"},
    404: {"description": "NOT_FOUND — missing or outside the caller's market"},
    422: {"description": "VALIDATION_ERROR (details.field) / REASON_REQUIRED"},
}


async def _write_scope(db: DbSession, user: AuthUser) -> int | None:
    """Market của admin ghi; vai trò khác 403 (06 mục 3: chỉ admin ghi)."""
    scope = await resolve_hr_scope(db, user)
    if scope.role != "admin":
        raise DomainError("FORBIDDEN", "Only IT (admin) may resolve mappings.")
    return scope.market_id


@router.get("/mapping/tasks", response_model=Page[MappingTaskOut], response_model_exclude_unset=True,
            responses=_ERRORS)  # fmt: skip
async def list_tasks(
    user: AuthUser,
    db: DbSession,
    status: Annotated[str | None, Query(description="open (default) | in_progress | done")] = None,
    market: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: SortParam = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[MappingTaskOut]:
    """GET /mapping/tasks — admin, dispatcher, warehouse (market mình) — 06 mục 12.2."""
    scope = await resolve_hr_scope(db, user)
    items, total = await mapping_read_service.list_tasks(
        db, scope, status=status, market=market, q=q, sort=sort, page=page, page_size=page_size
    )
    return Page[MappingTaskOut](
        items=[MappingTaskOut.model_validate(i) for i in items], page=page, page_size=page_size, total=total
    )


@router.get("/mapping/tasks/{task_id}", response_model=MappingTaskOut, responses=_ERRORS)
async def get_task(task_id: int, user: AuthUser, db: DbSession) -> MappingTaskOut:
    """GET /mapping/tasks/{id} — kèm nhóm gợi ý; không liệt kê đơn khách (ASM-005)."""
    scope = await resolve_hr_scope(db, user)
    return MappingTaskOut.model_validate(await mapping_read_service.get_task(db, scope, task_id))


@router.post("/mapping/tasks/{task_id}/confirm", response_model=ConfirmOut, responses=_ERRORS)
async def confirm_task(task_id: int, body: ConfirmIn, user: AuthUser, db: DbSession) -> ConfirmOut:
    """POST /mapping/tasks/{id}/confirm — admin; N6+FRAGILE → 422 (06 mục 12.1–12.2)."""
    market_id = await _write_scope(db, user)
    new = body.create_global
    payload = mapping_service.ConfirmInput(
        units_to_base=body.units_to_base,
        global_product_id=body.global_product_id,
        create_global=(
            None
            if new is None
            else mapping_service.NewGlobal(**new.model_dump(exclude={"flags"}), flags=tuple(new.flags))
        ),
    )
    result = await mapping_service.confirm(db, task_id, user, payload, market_id=market_id)
    sku = await db.scalar(select(MappingTask.local_sku).where(MappingTask.id == task_id))
    return ConfirmOut(
        task_id=task_id,
        local_sku=str(sku),
        global_product_id=result.global_product_id,
    )


@router.post("/mapping/tasks/{task_id}/reject", response_model=RejectOut, responses=_ERRORS)
async def reject_task(task_id: int, body: RejectIn, user: AuthUser, db: DbSession) -> RejectOut:
    """POST /mapping/tasks/{id}/reject — admin; reason_text bắt buộc (422 REASON_REQUIRED)."""
    market_id = await _write_scope(db, user)
    await mapping_service.reject(db, task_id, user, body.reason_text, market_id=market_id)
    sku = await db.scalar(select(MappingTask.local_sku).where(MappingTask.id == task_id))
    return RejectOut(task_id=task_id, local_sku=str(sku))


@router.get("/products/local", response_model=Page[LocalProductOut], responses=_ERRORS)
async def list_local_products(
    user: AuthUser,
    db: DbSession,
    market: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    mapping_status: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: SortParam = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[LocalProductOut]:
    """GET /products/local — lọc market, mapping_status (US-PRD-05 AC1)."""
    scope = await resolve_hr_scope(db, user)
    items, total = await mapping_read_service.list_local_products(
        db,
        scope,
        market=market,
        mapping_status=mapping_status,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page[LocalProductOut](
        items=[LocalProductOut.model_validate(i) for i in items], page=page, page_size=page_size, total=total
    )


@router.get("/products/global")
async def list_global_products() -> dict[str, object]:
    """GET /products/global — Danh sách global."""
    raise NotImplementedError


@router.post("/products/global")
async def create_global_product() -> dict[str, object]:
    """POST /products/global — admin."""
    raise NotImplementedError


@router.patch("/products/global/{product_id}")
async def update_global_product(product_id: int) -> dict[str, object]:
    """PATCH /products/global/{product_id} — admin."""
    raise NotImplementedError


@router.get("/handling-groups")
async def list_handling_groups() -> dict[str, object]:
    """GET /handling-groups — N1–N6, một bộ chung."""
    raise NotImplementedError


@router.patch("/handling-groups/{group_id}")
async def update_handling_group(group_id: int) -> dict[str, object]:
    """PATCH /handling-groups/{group_id} — admin; HANDLING_GROUP_CHANGED."""
    raise NotImplementedError


@router.get("/handling-group-rules")
async def list_group_rules() -> dict[str, object]:
    """GET /handling-group-rules — Quy tắc gán nhóm."""
    raise NotImplementedError


@router.get("/special-flags")
async def list_special_flags() -> dict[str, object]:
    """GET /special-flags — Hệ số cờ."""
    raise NotImplementedError
