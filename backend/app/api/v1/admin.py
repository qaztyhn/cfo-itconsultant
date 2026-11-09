"""Cấu hình market, đồng bộ (06 mục 15, Phụ lục A).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 2 (B) — M2/M8.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.deps import CurrentUser, DbSession, require_roles
from app.services import integration_monitor_service as monitor

Admin = Annotated[CurrentUser, Depends(require_roles("admin"))]
Feed = Literal["orders", "customers", "products", "stock", "inbound", "fleet"]
RunStatus = Literal["running", "ok", "partial", "failed"]

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
async def list_sync_runs(
    db: DbSession,
    user: Admin,
    market: str | None = Query(None, min_length=2, max_length=2),
    entity: Feed | None = None,
    status: RunStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, object]:
    """GET /sync-runs — admin, constrained by authenticated market."""
    return await monitor.list_runs(
        db,
        user,
        market=market,
        entity=entity,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/sync/{entity}/run")
async def run_sync(entity: str) -> dict[str, object]:
    """POST /sync/{entity}/run — admin; đang chạy → 409 SYNC_IN_PROGRESS."""
    raise NotImplementedError


@router.get("/sync-runs/{run_id}/rejects")
async def sync_rejects(
    run_id: int,
    db: DbSession,
    user: Admin,
    market: str | None = Query(None, min_length=2, max_length=2),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, object]:
    """GET rejects: safe reason codes only, never raw source payloads."""
    return await monitor.list_rejects(
        db, user, run_id=run_id, market=market, page=page, page_size=page_size
    )


@router.get("/integration/overview")
async def integration_overview(
    db: DbSession,
    user: Admin,
    market: str | None = Query(None, min_length=2, max_length=2),
) -> dict[str, object]:
    """GET overview: persisted source, route and scheduler evidence only."""
    return await monitor.overview(db, user, market)


# GET /health is owned by app/api/v1/health.py (Dev 1, M0).
