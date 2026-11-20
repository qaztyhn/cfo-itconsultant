"""R3 T15: market-scoped, audited single-trip Dispatcher handover."""

from typing import Annotated

from fastapi import APIRouter, Body, Path
from pydantic import BaseModel, ConfigDict, Field

from app.deps import AuthUser, DbSession
from app.services import dispatcher_assignment_service

router = APIRouter(tags=["trips"])


class TripHandoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_employee_id: int = Field(gt=0)
    reason_text: str = Field(min_length=1)


@router.post("/trips/{trip_id}/handover")
async def handover_trip(
    trip_id: Annotated[int, Path(gt=0)],
    body: Annotated[TripHandoverIn, Body()],
    user: AuthUser,
    db: DbSession,
) -> dict[str, int | str | None]:
    return await dispatcher_assignment_service.handover(
        trip_id, user, body.to_employee_id, body.reason_text, session=db
    )
