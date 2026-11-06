"""GET /health — công khai (06 mục 1, 15). Smoke/uptime dùng `status` và `db` (tools/m0_smoke.py).

Router mỏng: gọi health_service; DB lỗi → 503 với status=error, db=unavailable.

Owner: Dev 1 (A) — M0.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.deps import DbSession
from app.services import health_service

router = APIRouter(tags=["admin"])


class HealthOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"status": "ok", "db": "ok", "last_sync_age_min": 3, "notify_queue": 0}]
        }
    )

    status: str
    db: str
    last_sync_age_min: int | None
    notify_queue: int | None


@router.get("/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
async def health(db: DbSession) -> JSONResponse:
    """GET /health — Công khai: db, last_sync_age_min, notify_queue."""
    result = await health_service.check(db)
    body = HealthOut(
        status="ok" if result.db_ok else "error",
        db="ok" if result.db_ok else "unavailable",
        last_sync_age_min=result.last_sync_age_min,
        notify_queue=result.notify_queue,
    )
    return JSONResponse(status_code=200 if result.db_ok else 503, content=body.model_dump())
