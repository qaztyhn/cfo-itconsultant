"""D3 GPS HTTP contract: authenticated trip-duty device collection.

Dispatcher coordinates remain fail-closed until a reviewed persisted
dispatcher-to-trip authorization mapping exists. No GPS payload is logged.
"""

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.v1.common import PageNo, PageSize
from app.deps import AuthUser, DbSession
from app.services import gps_service

router = APIRouter(tags=["gps"])
TripId = Annotated[int, Path(gt=0)]


class DevicePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: Decimal = Field(ge=-90, le=90, max_digits=8, decimal_places=5)
    lon: Decimal = Field(ge=-180, le=180, max_digits=8, decimal_places=5)
    accuracy_m: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=1)
    recorded_at: AwareDatetime
    # Simulator cadence requires a separately reviewed authenticated provider.
    source: Literal["device"]


class DevicePositionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    positions: list[DevicePosition] = Field(min_length=1)


@router.post("/trips/{trip_id}/positions", status_code=202)
async def post_positions(
    trip_id: TripId, body: DevicePositionBatch, user: AuthUser, db: DbSession
) -> dict[str, object]:
    """US-GPS-01: 202 acknowledgement, only verified driver and active trip/shift."""
    return await gps_service.ingest_positions(
        trip_id, user, [point.model_dump() for point in body.positions], session=db
    )


@router.get("/trips/{trip_id}/positions")
async def get_positions(
    trip_id: TripId,
    user: AuthUser,
    db: DbSession,
    since: Annotated[AwareDatetime | None, Query()] = None,
    until: Annotated[AwareDatetime | None, Query()] = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> dict[str, object]:
    """D3 forbids reading even within market without explicit dispatcher assignment."""
    return await gps_service.trip_positions(
        trip_id, user, session=db, since=since, until=until, page=page, page_size=page_size
    )


@router.get("/gps/live")
async def gps_live(user: AuthUser, db: DbSession) -> list[dict[str, object]]:
    """D3: read blocked until durable dispatcher-to-trip mapping is approved."""
    return await gps_service.live(user, session=db)


@router.get("/markets/{code}/gps-settings")
async def get_gps_settings(code: str) -> dict[str, object]:
    """Existing admin configuration endpoint; owned by separate settings work."""
    raise NotImplementedError


@router.put("/markets/{code}/gps-settings")
async def put_gps_settings(code: str) -> dict[str, object]:
    """Existing admin setting/change audit workflow; not authorized in GPS M6."""
    raise NotImplementedError


@router.get("/compliance-records")
async def list_compliance() -> dict[str, object]:
    """Existing admin compliance-contract stub, outside M6 collection scope."""
    raise NotImplementedError


@router.post("/compliance-records")
async def create_compliance() -> dict[str, object]:
    """Existing admin compliance-contract stub, outside M6 collection scope."""
    raise NotImplementedError
