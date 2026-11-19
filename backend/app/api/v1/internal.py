"""Authenticated manual execution of enabled demo/staging jobs."""

import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.models.ref import Market
from app.jobs import hold_expiry, outbox

router = APIRouter(tags=["internal"])


@router.post("/internal/tick")
async def tick(
    request: Request,
    job: str = Query(...),
    market: str | None = Query(None),
    internal_key: str | None = Header(None, alias="X-Internal-Key"),
) -> dict[str, object]:
    """Run only ready jobs; authentication precedes all job access."""
    settings = get_settings()
    configured = settings.internal_tick_key
    if not configured or not internal_key or not hmac.compare_digest(configured, internal_key):
        raise DomainError("AUTH_INVALID", "Internal key is missing or invalid.")
    if settings.app_env not in {"local", "test", "staging"}:
        raise DomainError("FORBIDDEN", "Internal tick is unavailable in this environment.")
    if job not in {"notify_outbox", "hold_expiry"}:
        raise DomainError("VALIDATION_ERROR", "Job is not available.")
    if job == "hold_expiry":
        if market is not None:
            raise DomainError("VALIDATION_ERROR", "Global job does not accept market.")
    else:
        if not market:
            raise DomainError("VALIDATION_ERROR", "Market is required.")
        async with get_sessionmaker()() as session:
            exists = await session.scalar(select(Market.id).where(Market.code == market))
        if exists is None:
            raise DomainError("VALIDATION_ERROR", "Market is not available.")

    started = datetime.now(UTC)
    try:
        processed = (
            await outbox.run(market_code=market) if job == "notify_outbox" else await hold_expiry.run()
        )
    except Exception as exc:
        # SMTP/DB exception text can contain private data.
        raise DomainError("INTERNAL_ERROR", "Job failed.", http_status=503) from exc
    return {
        "job": job,
        "market": market,
        "status": "ok",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "processed": processed,
        "correlation_id": request.state.correlation_id,
    }
