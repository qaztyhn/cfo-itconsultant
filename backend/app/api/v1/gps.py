"""Round 3 GPS HTTP: one driver-initiated point, assigned Dispatcher live scope.

The HTTP layer never accepts source/device flags or returns GPS history.
All persistence and risk side effects share the request transaction.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.deps import AuthUser, DbSession
from app.services import gps_service

router = APIRouter(tags=["gps"])
TripId = Annotated[int, Path(gt=0)]
IdempotencyHeader = Annotated[UUID, Header(alias="Idempotency-Key")]


class DriverPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(strict=True, ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(strict=True, ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float = Field(strict=True, gt=0, allow_inf_nan=False)
    recorded_at: AwareDatetime


@router.post("/trips/{trip_id}/positions", status_code=202)
async def post_positions(
    trip_id: TripId,
    body: DriverPosition,
    user: AuthUser,
    db: DbSession,
    idempotency_key: IdempotencyHeader,
) -> dict[str, object]:
    """US-GPS-01: 202 only after single point and risk are committed."""
    return await gps_service.post_driver_position(
        db,
        trip_id,
        user,
        body.model_dump(mode="python"),
        str(idempotency_key),
    )


@router.get("/gps/live")
async def gps_live(user: AuthUser, db: DbSession) -> list[dict[str, object]]:
    """US-GPS-02: no general market GPS access, no historical route."""
    return await gps_service.live(user, session=db)


@router.get("/markets/{code}/gps-settings")
async def get_gps_settings(code: str) -> dict[str, object]:
    """Existing admin compliance-contract stub, outside T13 collection scope."""
    raise NotImplementedError
