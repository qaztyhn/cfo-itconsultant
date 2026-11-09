"""Read-only integration monitoring, scoped by the authenticated admin market.

No ingestion, stock, scheduler or source-adapter writes. Only persisted evidence
is reported; lack of scheduler heartbeat or stock-scope evidence is UNKNOWN.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.plan import RouteMatrix
from app.domain.models.ref import Location, Market
from app.domain.models.stg import SyncCheckpoint, SyncReject, SyncRun

# T07 has writers for five feeds; stock is explicitly blocked.
FEEDS = ("orders", "customers", "products", "stock", "inbound", "fleet")
SUPPORTED = frozenset(("orders", "customers", "products", "inbound", "fleet"))


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _run(run: SyncRun) -> dict[str, Any]:
    """Explicit allowlist. No filenames, raw error, source keys or credentials."""
    return {
        "id": run.id,
        "market_id": run.market_id,
        "entity": run.entity,
        "kind": run.kind,
        "status": run.status,
        "started_at": _time(run.started_at),
        "finished_at": _time(run.finished_at),
        "checkpoint_from": _time(run.checkpoint_from),
        "checkpoint_to": _time(run.checkpoint_to),
        "data_as_of": _time(run.data_as_of),
        "rows_in": run.rows_in,
        "rows_ok": run.rows_ok,
        "rows_rejected": run.rows_rejected,
        "complete_success": run.status == "ok",
        "error_code": (run.error if run.error in {"INTERRUPTED_RUN", "SOURCE_SYNC_FAILED"} else None),
    }


def _safe_reason(value: str) -> str:
    """Stable code only. Free-text reason/raw/external_key are forbidden."""
    allowed = {
        "BAD_QTY",
        "BAD_DATE",
        "MISSING_COORDS",
        "UNKNOWN_WAREHOUSE",
        "INVALID_SOURCE_ROW",
        "UNIT_CONVERSION_CHANGED",
        "SKU_UNMAPPED",
        "PRODUCT_NOT_MAPPED",
        "BAD_UNIT",
        "BAD_PRICE",
        "BAD_REFERENCE",
    }
    return value if value in allowed else "UNVERIFIED"


async def _markets(session: AsyncSession, user: CurrentUser, market: str | None) -> list[Market]:
    if "admin" not in user.roles:
        raise DomainError("FORBIDDEN", "Admin access required.")
    query = select(Market).order_by(Market.code)
    if user.market:
        if market and market != user.market:
            raise DomainError("NOT_FOUND", "Market not found.")
        query = query.where(Market.code == user.market)
    elif market:
        query = query.where(Market.code == market)
    found = list((await session.scalars(query)).all())
    if market and not found:
        raise DomainError("NOT_FOUND", "Market not found.")
    return found


async def list_runs(
    session: AsyncSession,
    user: CurrentUser,
    *,
    market: str | None,
    entity: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    markets = await _markets(session, user, market)
    ids = [item.id for item in markets]
    if not ids:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    predicate = [SyncRun.market_id.in_(ids)]
    if entity:
        predicate.append(SyncRun.entity == entity)
    if status:
        predicate.append(SyncRun.status == status)
    total = await session.scalar(select(func.count()).select_from(SyncRun).where(*predicate))
    runs = (
        await session.scalars(
            select(SyncRun)
            .where(*predicate)
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [_run(run) for run in runs],
        "page": page,
        "page_size": page_size,
        "total": total or 0,
    }


async def list_rejects(
    session: AsyncSession,
    user: CurrentUser,
    *,
    run_id: int,
    market: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    markets = await _markets(session, user, market)
    run = await session.get(SyncRun, run_id)
    if run is None or run.market_id not in {item.id for item in markets}:
        raise DomainError("NOT_FOUND", "Sync run not found.")
    predicate = SyncReject.run_id == run.id
    total = await session.scalar(select(func.count()).select_from(SyncReject).where(predicate))
    rejects = (
        await session.scalars(
            select(SyncReject)
            .where(predicate)
            .order_by(SyncReject.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "run_id": run.id,
        "market_id": run.market_id,
        "entity": run.entity,
        "status": run.status,
        "page": page,
        "page_size": page_size,
        "total": total or 0,
        "items": [{"id": row.id, "reason_code": _safe_reason(row.reason_code)} for row in rejects],
        "privacy": "Raw values, external keys and free-text reasons withheld",
    }


async def _market_overview(session: AsyncSession, market: Market) -> dict[str, Any]:
    config = MarketConfig.model_validate(market.config)
    # Fetch at most two rows per feed, regardless of the lifetime run history.
    by_entity: dict[str, SyncRun] = {}
    successful: dict[str, SyncRun] = {}
    for entity in FEEDS:
        base = select(SyncRun).where(
            SyncRun.market_id == market.id,
            SyncRun.entity == entity,
        )
        order = (SyncRun.started_at.desc(), SyncRun.id.desc())
        current = await session.scalar(base.order_by(*order).limit(1))
        complete = await session.scalar(
            base.where(SyncRun.status == "ok").order_by(*order).limit(1)
        )
        if current is not None:
            by_entity[entity] = current
        if complete is not None:
            successful[entity] = complete
    checkpoints = (
        await session.scalars(select(SyncCheckpoint).where(SyncCheckpoint.market_id == market.id))
    ).all()
    checkpoint_by_entity = {cp.entity: _time(cp.last_updated_since) for cp in checkpoints}
    # The cross-market view is maintained by add_market.py. Pending SKU
    # count is not an ingestion rejection or proof of stock readiness.
    unmapped = await session.scalar(
        text(
            "SELECT count(*) FROM ref.v_product_local "
            "WHERE market_code = :code AND mapping_status = 'pending'"
        ),
        {"code": market.code},
    )
    route = (
        await session.execute(
            select(
                func.count().label("pairs"),
                func.count().filter(RouteMatrix.provider == "fallback").label("fallback_pairs"),
                func.max(RouteMatrix.computed_at).label("fetched_at"),
            )
            .select_from(RouteMatrix)
            .join(Location, RouteMatrix.warehouse_id == Location.id)
            .where(Location.market_id == market.id)
        )
    ).one()
    sources: list[dict[str, Any]] = []
    for entity in FEEDS:
        current = by_entity.get(entity)
        complete = successful.get(entity)
        supported = entity in SUPPORTED
        sources.append(
            {
                "entity": entity,
                "availability": "supported" if supported else "unconfigured",
                "status": ((current.status if current else "never_run") if supported else "unconfigured"),
                "rows": current.rows_in if current else None,
                "rows_ok": current.rows_ok if current else None,
                "rejected": current.rows_rejected if current else None,
                "unmapped": int(unmapped or 0) if entity == "products" else None,
                "last_run_at": _time(current.started_at) if current else None,
                "last_run_status": current.status if current else None,
                "last_successful_run_id": complete.id if complete else None,
                "last_successful_at": _time(complete.finished_at) if complete else None,
                "data_as_of": _time(current.data_as_of) if current else None,
                "checkpoint": checkpoint_by_entity.get(entity),
                "interval_min": config.sync.interval_min if supported else None,
                "stock_scope": "unconfigured" if entity == "stock" else None,
            }
        )
    return {
        "market": market.code,
        "market_id": market.id,
        "sources": sources,
        "route_matrix": {
            "pairs": route.pairs or 0,
            "fallback_pairs": route.fallback_pairs or 0,
            "fetched_at": _time(route.fetched_at),
            "provider": "mixed_or_unverified" if route.pairs else None,
        },
        "scheduler": {
            "tick_interval_min": config.sync.interval_min,
            "last_tick_at": None,
            "last_tick_status": "unknown",
            "runtime_health": "unverified",
            "jobs": [],
            "supported_feed_types": sorted(SUPPORTED),
            "explanation": (
                "No persisted scheduler heartbeat; configured cadence " "is not proof of execution."
            ),
        },
    }


async def overview(session: AsyncSession, user: CurrentUser, market: str | None) -> dict[str, Any]:
    markets = await _markets(session, user, market)
    results = [await _market_overview(session, row) for row in markets]
    return results[0] if len(results) == 1 else {"markets": results}
