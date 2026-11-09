"""M6 thin execution API (06 §8, Appendix A); service owns business rules."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Header, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.deps import AuthUser, DbSession
from app.domain.enums import EventType
from app.services import execution_service

router = APIRouter(tags=["execution"])

IdempotencyHeader = Annotated[UUID, Header(alias="Idempotency-Key")]
RequestedDate = Annotated[date | None, Query(alias="date")]


class ExecutionEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: EventType
    occurred_at: AwareDatetime
    payload: dict[str, object] = Field(
        default_factory=dict,
        description=(
            "For DELIVERED/FAILED, trip_id identifies the assigned trip and trip_stop_id "
            "identifies the specific stop. trip_stop_id is required if this order has "
            "multiple stops on that trip; legacy single-stop payloads remain accepted. "
            "POD/terminal status is committed only after server-side validation."
        ),
    )


@router.post("/orders/{order_id}/events")
async def record_event(
    order_id: int,
    user: AuthUser,
    db: DbSession,
    idempotency_key: IdempotencyHeader,
    body: Annotated[ExecutionEventIn, Body()],
) -> dict[str, object]:
    return await execution_service.record_event(
        db,
        order_id,
        user,
        body.event_type.value,
        body.occurred_at,
        body.payload,
        str(idempotency_key),
    )


@router.get("/warehouses/{warehouse_id}/prep-queue")
async def prep_queue(
    warehouse_id: int,
    user: AuthUser,
    db: DbSession,
    date_value: RequestedDate = None,
) -> dict[str, object]:
    return await execution_service.prep_queue(db, warehouse_id, date_value, user)


@router.get("/prep-queue")
async def prep_queue_v2(
    user: AuthUser,
    db: DbSession,
    warehouse_id: Annotated[int, Query(gt=0)],
    date_value: RequestedDate = None,
) -> dict[str, object]:
    """Legacy alias (06 A.1): same service and same response as `/warehouses/{id}/prep-queue`."""
    return await execution_service.prep_queue(db, warehouse_id, date_value, user)


@router.get("/driver/trips")
async def driver_trips(user: AuthUser, db: DbSession, date_value: RequestedDate = None) -> dict[str, object]:
    return await execution_service.driver_trips(db, user, day=date_value)


@router.get("/driver/trips/{trip_id}")
async def driver_trip(trip_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    return await execution_service.driver_trips(db, user, trip_id=trip_id)
