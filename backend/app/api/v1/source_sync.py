"""Explicit Sales Sync & Check — approved Source GET to Dev 1's transactional route.

Requires Dev 1 source_handoff (#202). Never lets polling choose routing and
never writes POS/WMS, plans or approvals. Source list API has no by-ID GET,
so both complete status feeds are checked conservatively before acceptance.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.adapters.order_wire import SourceCancellation, SourceOrder
from app.adapters.registry import AdapterConfigurationError, AdapterRegistry
from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError
from app.core.errors import DomainError
from app.deps import AuthUser, DbSession
from app.domain.models.ref import Market
from app.services import source_handoff

router = APIRouter(tags=["integration"])


class SyncNowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_ref: str = Field(min_length=1, max_length=120)


class SyncNowOutput(BaseModel):
    order_id: int | None
    external_ref: str
    source_version: int
    routing_status: str
    sync_status: str
    already_decided: bool


async def _read_submitted(reader: RestMarketAdapter, external_ref: str) -> SourceOrder | None:
    """Demo bridge: fully read both D1 status lists; contradictory source status blocks routing."""
    # The concrete authenticated RestMarketAdapter owns HTTP validation/page guards.
    submitted: SourceOrder | None = None
    async for row in reader._pages(
        "orders",
        None,
        SourceOrder,
        key_fields=("id",),
        page_size=200,
        filters={"status": "SUBMITTED_FOR_PLANNING"},
    ):
        if row.id == external_ref:
            submitted = row
    cancelled = False
    async for row in reader._pages(  # type: ignore[attr-defined]
        "orders",
        None,
        SourceCancellation,
        key_fields=("id",),
        page_size=200,
        filters={"status": "CANCELLED"},
    ):
        if row.id == external_ref:
            cancelled = True
    if submitted is not None and cancelled:
        raise SourceReadError("Source changed during the routing lookup")
    return None if cancelled else submitted


@router.post(
    "/integration/orders/sync-now",
    response_model=SyncNowOutput,
    responses={
        403: {"description": "Forbidden role"},
        404: {"description": "Out-of-scope or unavailable Source order"},
        409: {"description": "Immutable routing or idempotency conflict"},
        422: {"description": "Invalid request or Source order"},
        503: {"description": "Source adapter unavailable; no routing decision written"},
    },
)
async def sync_now(
    body: SyncNowInput,
    user: AuthUser,
    session: DbSession,
    idempotency_key: Annotated[UUID, Header(description="Stable UUID for identical retries")],
) -> SyncNowOutput:
    if not {"sales", "dispatcher"}.intersection(user.roles):
        raise DomainError("FORBIDDEN", "Sales or Dispatcher permission is required.")
    if not user.market:
        raise DomainError("FORBIDDEN", "An assigned market is required.")
    market = await session.scalar(select(Market).where(Market.code == user.market))
    if market is None:
        raise DomainError("NOT_FOUND", "Market is unavailable.")
    registry = AdapterRegistry()
    try:
        registry.configure(
            market.code,
            market.source_base_url,
            market.source_api_key_ref,
            market_timezone=market.timezone,
        )
        reader = registry.get(market.code)
        source = await _read_submitted(reader, body.external_ref)
    except (AdapterConfigurationError, SourceReadError, ValueError):
        # Never echo a remote URL, key, Source record or personal contact info.
        raise DomainError(
            "INTERNAL_ERROR", "Source order check is temporarily unavailable.", http_status=503
        ) from None
    if source is None:
        raise DomainError("NOT_FOUND", "Submitted Source order is unavailable.")
    answer = await source_handoff.accept_source_order(
        session,
        user,
        source,
        str(idempotency_key),
    )
    return SyncNowOutput.model_validate(answer)
