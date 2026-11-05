"""GPS (06 mục 9). Đọc CHỈ dispatcher (09 bất biến 4).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 2 (B) — M6.
"""

from fastapi import APIRouter

router = APIRouter(tags=["gps"])


@router.post("/trips/{trip_id}/positions")
async def post_positions(trip_id: int) -> dict[str, object]:
    """POST /trips/{trip_id}/positions — driver (chuyến mình); 403 GPS_DISABLED / 409 NOT_ON_TRIP."""
    raise NotImplementedError


@router.get("/trips/{trip_id}/positions")
async def get_positions(trip_id: int) -> dict[str, object]:
    """GET /trips/{trip_id}/positions — dispatcher."""
    raise NotImplementedError


@router.get("/gps/live")
async def gps_live() -> dict[str, object]:
    """GET /gps/live — dispatcher."""
    raise NotImplementedError


@router.get("/markets/{code}/gps-settings")
async def get_gps_settings(code: str) -> dict[str, object]:
    """GET /markets/{code}/gps-settings — admin."""
    raise NotImplementedError


@router.put("/markets/{code}/gps-settings")
async def put_gps_settings(code: str) -> dict[str, object]:
    """PUT /markets/{code}/gps-settings — admin; warnings DPIA_MISSING."""
    raise NotImplementedError


@router.get("/compliance-records")
async def list_compliance() -> dict[str, object]:
    """GET /compliance-records — admin."""
    raise NotImplementedError


@router.post("/compliance-records")
async def create_compliance() -> dict[str, object]:
    """POST /compliance-records — admin."""
    raise NotImplementedError
