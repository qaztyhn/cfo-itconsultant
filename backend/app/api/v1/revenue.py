"""Revenue REST endpoints (06 §14.1; US-REV-01).

Authentication is mandatory. All owner and view restrictions are enforced by
revenue_service.resolve_revenue_scope(); handlers only validate and serialize.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from app.api.v1.common import Page, PageNo, PageSize
from app.deps import AuthUser, DbSession
from app.services import revenue_service as service

router = APIRouter(tags=["revenue"])

RevenueView = Literal["store", "warehouse"]
FromDate = Annotated[date | None, Query(alias="from")]
ToDate = Annotated[date | None, Query(alias="to")]
LocationId = Annotated[int | None, Query(gt=0)]
RequiredLocation = Annotated[int, Query(gt=0)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "AUTH_INVALID"},
    403: {"description": "FORBIDDEN — revenue scope absent"},
    404: {"description": "NOT_FOUND — location outside market/scope"},
    422: {"description": "VALIDATION_ERROR — period, view, or location type"},
}


def _money(value: Decimal) -> str:
    return format(value, ".2f")


class PeriodOut(BaseModel):
    from_: date = Field(alias="from")
    to: date


class RevenueSummaryOut(BaseModel):
    period: PeriodOut
    view: RevenueView
    location_id: int | None
    currency: str
    recognised: str
    booked_not_delivered: str
    orders_delivered: int
    avg_order_value: str | None
    share_of_market_pct: float | None


class RevenuePointOut(BaseModel):
    day: date
    recognised: str
    booked: str


class RevenueDailyOut(BaseModel):
    currency: str
    points: list[RevenuePointOut]


class RevenueLocationRowOut(BaseModel):
    location_id: int | None
    code: str | None
    name: str
    orders_delivered: int
    recognised: str
    booked_not_delivered: str
    share_pct: float | None


class RevenueByLocationOut(BaseModel):
    view: RevenueView
    currency: str
    rows: list[RevenueLocationRowOut]


class RevenueOrderOut(BaseModel):
    order_no: str
    delivered_at: datetime | None
    amount: str
    currency: str
    status: str
    customer_name: str | None = None


@router.get("/revenue/summary", response_model=RevenueSummaryOut, responses=_ERRORS)
async def revenue_summary(
    user: AuthUser,
    db: DbSession,
    view: RevenueView,
    date_from: FromDate = None,
    date_to: ToDate = None,
    location_id: LocationId = None,
) -> RevenueSummaryOut:
    market_id, period = await service.resolve_market_period(db, user, date_from, date_to)
    result = await service.summary(
        db, user, market_id=market_id, view=view, location_id=location_id, period=period
    )
    return RevenueSummaryOut(
        period=PeriodOut.model_validate({"from": result.period.start, "to": result.period.end}),
        view=result.view,
        location_id=result.location_id,
        currency=result.currency,
        recognised=_money(result.recognised),
        booked_not_delivered=_money(result.booked_not_delivered),
        orders_delivered=result.orders_delivered,
        avg_order_value=_money(result.avg_order_value) if result.avg_order_value is not None else None,
        share_of_market_pct=(
            float(result.share_of_market_pct) if result.share_of_market_pct is not None else None
        ),
    )


@router.get("/revenue/daily", response_model=RevenueDailyOut, responses=_ERRORS)
async def revenue_daily(
    user: AuthUser,
    db: DbSession,
    view: RevenueView,
    date_from: FromDate = None,
    date_to: ToDate = None,
    location_id: LocationId = None,
) -> RevenueDailyOut:
    market_id, period = await service.resolve_market_period(db, user, date_from, date_to)
    result = await service.daily(
        db, user, market_id=market_id, view=view, location_id=location_id, period=period
    )
    return RevenueDailyOut(
        currency=result.currency,
        points=[
            RevenuePointOut(day=p.day, recognised=_money(p.recognised), booked=_money(p.booked))
            for p in result.points
        ],
    )


@router.get("/revenue/by-location", response_model=RevenueByLocationOut, responses=_ERRORS)
async def revenue_by_location(
    user: AuthUser,
    db: DbSession,
    view: RevenueView,
    date_from: FromDate = None,
    date_to: ToDate = None,
    location_id: LocationId = None,
) -> RevenueByLocationOut:
    market_id, period = await service.resolve_market_period(db, user, date_from, date_to)
    result = await service.by_location(
        db, user, market_id=market_id, view=view, period=period, location_id=location_id
    )
    return RevenueByLocationOut(
        view=result.view,
        currency=result.currency,
        rows=[
            RevenueLocationRowOut(
                location_id=row.location_id,
                code=row.code,
                name=row.name,
                orders_delivered=row.orders_delivered,
                recognised=_money(row.recognised),
                booked_not_delivered=_money(row.booked_not_delivered),
                share_pct=float(row.share_pct) if row.share_pct is not None else None,
            )
            for row in result.rows
        ],
    )


@router.get(
    "/revenue/orders",
    response_model=Page[RevenueOrderOut],
    response_model_exclude_unset=True,
    responses=_ERRORS,
)
async def revenue_orders(
    user: AuthUser,
    db: DbSession,
    view: RevenueView,
    location_id: RequiredLocation,
    date_from: FromDate = None,
    date_to: ToDate = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[RevenueOrderOut]:
    market_id, period = await service.resolve_market_period(db, user, date_from, date_to)
    records, total = await service.orders(
        db,
        user,
        market_id=market_id,
        view=view,
        location_id=location_id,
        period=period,
        page=page,
        page_size=page_size,
    )
    return Page[RevenueOrderOut](
        items=[RevenueOrderOut.model_validate(row) for row in records],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/revenue/export.csv", responses=_ERRORS)
async def revenue_export_csv(
    user: AuthUser,
    db: DbSession,
    view: RevenueView,
    date_from: FromDate = None,
    date_to: ToDate = None,
    location_id: LocationId = None,
) -> Response:
    market_id, period = await service.resolve_market_period(db, user, date_from, date_to)
    data = await service.export_csv(
        db, user, market_id=market_id, view=view, location_id=location_id, period=period
    )
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="revenue.csv"'},
    )
