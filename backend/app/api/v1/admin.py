"""Cấu hình market, đồng bộ (06 mục 15, Phụ lục A).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 2 (B) — M2/M8.
"""

from fastapi import APIRouter

router = APIRouter(tags=["admin"])


@router.get("/markets/{code}/config")
async def get_market_config(code: str) -> dict[str, object]:
    """GET /markets/{code}/config — admin."""
    raise NotImplementedError


@router.put("/markets/{code}/config")
async def put_market_config(code: str) -> dict[str, object]:
    """PUT /markets/{code}/config — admin; validate MarketConfig; CONFIG_CHANGED."""
    raise NotImplementedError


@router.get("/sync-runs")
async def list_sync_runs() -> dict[str, object]:
    """GET /sync-runs — admin."""
    raise NotImplementedError


@router.post("/sync/{entity}/run")
async def run_sync(entity: str) -> dict[str, object]:
    """POST /sync/{entity}/run — admin; đang chạy → 409 SYNC_IN_PROGRESS."""
    raise NotImplementedError


@router.get("/sync-runs/{run_id}/rejects")
async def sync_rejects(run_id: int) -> dict[str, object]:
    """GET /sync-runs/{run_id}/rejects — admin."""
    raise NotImplementedError


@router.get("/integration/overview")
async def integration_overview() -> dict[str, object]:
    """GET /integration/overview — Thẻ nguồn (unmapped tách khỏi rejected)."""
    raise NotImplementedError


@router.get("/health")
async def health() -> dict[str, object]:
    """GET /health — Công khai: db, last_sync_age_min, notify_queue."""
    raise NotImplementedError
