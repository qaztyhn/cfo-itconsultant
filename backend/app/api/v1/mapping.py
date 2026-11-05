"""Sản phẩm, ánh xạ, nhóm xử lý (06 mục 12). Ghi CHỈ admin.

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M2.
"""

from fastapi import APIRouter

router = APIRouter(tags=["mapping"])


@router.get("/mapping/tasks")
async def list_tasks() -> dict[str, object]:
    """GET /mapping/tasks — Hàng đợi + blocked_order_count + candidates."""
    raise NotImplementedError


@router.get("/mapping/tasks/{task_id}")
async def get_task(task_id: int) -> dict[str, object]:
    """GET /mapping/tasks/{task_id} — Chi tiết."""
    raise NotImplementedError


@router.post("/mapping/tasks/{task_id}/confirm")
async def confirm_task(task_id: int) -> dict[str, object]:
    """POST /mapping/tasks/{task_id}/confirm — admin; N6+FRAGILE → 422."""
    raise NotImplementedError


@router.post("/mapping/tasks/{task_id}/reject")
async def reject_task(task_id: int) -> dict[str, object]:
    """POST /mapping/tasks/{task_id}/reject — admin; reason_text bắt buộc."""
    raise NotImplementedError


@router.get("/products/local")
async def list_local_products() -> dict[str, object]:
    """GET /products/local — Lọc market, mapping_status."""
    raise NotImplementedError


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
