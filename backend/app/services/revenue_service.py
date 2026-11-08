"""Doanh thu chỉ đọc (05 mục 8; 06 mục 14.1; US-REV-01).

Chỉ tiền hàng (total_amount = Σ line_total); không phí giao/đóng gói/nhân công/giá vốn/lợi nhuận.
recognised = đơn DELIVERED theo delivered_at ở múi giờ market (audit.v_revenue_daily); booked =
APPROVED…DISPATCHED theo committed_date (audit.v_revenue_pending). Hai góc nhìn store/warehouse, mỗi truy
vấn GROUP BY một chiều, không cộng với nhau; đơn không có cửa hàng → 'Unassigned store'.
resolve_revenue_scope: admin hoặc revenue_all → all; nếu không, location có owner_employee_id =
user.employee_id; rỗng → 403; ngoài phạm vi → 404; view không khớp loại nơi → 422. share_of_market_pct chỉ
cho Business owner/admin. Business owner không nhận customer_name. Export CSV (UTF-8 BOM) ghi decision_log
REVENUE_EXPORTED. Không PII trong log/file xuất của Business owner.

Owner: Dev 1 (A) — M8.
"""

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Date, Table, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.ref import Customer, Location, Market
from app.domain.models.views import v_revenue_daily, v_revenue_pending

VIEWS = ("store", "warehouse")
BOOKED_STATUSES = ("APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED")
DEFAULT_DAYS = 30
MAX_DAYS = 366
UNASSIGNED_STORE = "Unassigned store"
_CENT, _TENTH = Decimal("0.01"), Decimal("0.1")


class RevenueViewer(Protocol):
    """Thuộc tính tối thiểu của người gọi (CurrentUser của app.deps thỏa giao diện này)."""

    @property
    def roles(self) -> tuple[str, ...]: ...

    @property
    def kpi_scopes(self) -> tuple[str, ...]: ...

    @property
    def employee_id(self) -> int | None: ...

    @property
    def market(self) -> str: ...

    @property
    def id(self) -> int: ...


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @classmethod
    def resolve(cls, start: date | None, end: date | None, today: date) -> "Period":
        """Mặc định 30 ngày gần nhất (tính cả hôm nay theo múi giờ market); from ≤ to; tối đa 366 ngày."""
        end = end or today
        start = start or end - timedelta(days=DEFAULT_DAYS - 1)
        if start > end:
            raise DomainError("VALIDATION_ERROR", "`from` must not be after `to`.")
        if (end - start).days + 1 > MAX_DAYS:
            raise DomainError("VALIDATION_ERROR", f"Period must not exceed {MAX_DAYS} days.")
        return cls(start, end)

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]


@dataclass(frozen=True)
class RevenueScope:
    all: bool
    store_ids: frozenset[int]
    warehouse_ids: frozenset[int]


@dataclass(frozen=True)
class RevenueSummary:
    period: Period
    view: str
    location_id: int | None
    currency: str
    recognised: Decimal
    booked_not_delivered: Decimal
    orders_delivered: int
    avg_order_value: Decimal | None
    share_of_market_pct: Decimal | None  # chỉ Business owner/admin, khi hỏi một nơi


@dataclass(frozen=True)
class RevenuePoint:
    day: date
    recognised: Decimal
    booked: Decimal


@dataclass(frozen=True)
class RevenueDaily:
    currency: str
    points: tuple[RevenuePoint, ...]


@dataclass(frozen=True)
class RevenueRow:
    location_id: int | None  # None = "Unassigned store"
    code: str | None
    name: str
    orders_delivered: int
    recognised: Decimal
    booked_not_delivered: Decimal
    share_pct: Decimal | None


@dataclass(frozen=True)
class RevenueByLocation:
    view: str
    currency: str
    rows: tuple[RevenueRow, ...]


async def resolve_revenue_scope(session: AsyncSession, viewer: RevenueViewer, market_id: int) -> RevenueScope:
    """admin hoặc `revenue_all` → mọi nơi; nếu không, nơi `owner_employee_id = employee_id` đang hoạt động
    (owner cửa hàng → góc nhìn store, owner kho → warehouse); rỗng → 403 (05 mục 8; 06 mục 3.1)."""
    if "admin" in viewer.roles or "revenue_all" in viewer.kpi_scopes:
        return RevenueScope(True, frozenset(), frozenset())
    if viewer.employee_id is None:
        raise DomainError("FORBIDDEN", "You do not have access to revenue.")
    owned = (
        await session.execute(
            select(Location.id, Location.type).where(
                Location.market_id == market_id,
                Location.owner_employee_id == viewer.employee_id,
                Location.is_active.is_(True),
            )
        )
    ).all()
    stores = frozenset(i for i, t in owned if t == "store")
    warehouses = frozenset(i for i, t in owned if t == "warehouse")
    if not stores and not warehouses:
        raise DomainError("FORBIDDEN", "You do not have access to revenue.")
    return RevenueScope(False, stores, warehouses)


async def _targets(
    session: AsyncSession, scope: RevenueScope, market_id: int, view: str, location_id: int | None
) -> frozenset[int] | None:
    """Tập nơi được tính (None = mọi nơi của market, kể cả 'Unassigned store' ở góc nhìn store)."""
    if view not in VIEWS:
        raise DomainError("VALIDATION_ERROR", "`view` must be 'store' or 'warehouse'.")
    owned = scope.store_ids if view == "store" else scope.warehouse_ids
    if location_id is not None:
        location = await session.get(Location, location_id)
        if location is None or location.market_id != market_id:
            raise DomainError("NOT_FOUND", "Location not found.")
        if location.type != view:
            raise DomainError("VALIDATION_ERROR", f"Location {location.code} is not a {view}.")
        if not scope.all and location_id not in owned:
            raise DomainError("NOT_FOUND", "Location not found.")
        return frozenset({location_id})
    if scope.all:
        return None
    if not owned:
        raise DomainError("FORBIDDEN", f"You do not have access to the {view} view.")
    return owned


def _column(view_table: Table, view: str) -> ColumnElement[int]:
    return view_table.c.store_id if view == "store" else view_table.c.warehouse_id


def _filtered(
    view_table: Table, view: str, market_id: int, period: Period, targets: frozenset[int] | None
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        view_table.c.market_id == market_id,
        view_table.c.day.between(period.start, period.end),
    ]
    if targets is not None:
        conditions.append(_column(view_table, view).in_(targets))
    return conditions


async def _currency(session: AsyncSession, market_id: int) -> str:
    market = await session.get(Market, market_id)
    if market is None:
        raise DomainError("NOT_FOUND", "Market not found.")
    return market.currency


async def _totals(
    session: AsyncSession, market_id: int, view: str, period: Period, targets: frozenset[int] | None
) -> tuple[Decimal, int, Decimal]:
    d = v_revenue_daily
    recognised, orders = (
        await session.execute(
            select(
                func.coalesce(func.sum(d.c.revenue_recognised), 0),
                func.coalesce(func.sum(d.c.orders_delivered), 0),
            ).where(*_filtered(d, view, market_id, period, targets))
        )
    ).one()
    p = v_revenue_pending
    booked = (
        await session.execute(
            select(func.coalesce(func.sum(p.c.revenue_booked), 0)).where(
                *_filtered(p, view, market_id, period, targets)
            )
        )
    ).scalar_one()
    return Decimal(recognised), int(orders), Decimal(booked)


def _pct(part: Decimal, total: Decimal) -> Decimal | None:
    return (part / total * 100).quantize(_TENTH, rounding=ROUND_HALF_UP) if total else None


async def summary(
    session: AsyncSession,
    viewer: RevenueViewer,
    *,
    market_id: int,
    view: str,
    location_id: int | None,
    period: Period,
) -> RevenueSummary:
    """GET /revenue/summary — thẻ số liệu của kỳ (06 mục 14.1)."""
    scope = await resolve_revenue_scope(session, viewer, market_id)
    targets = await _targets(session, scope, market_id, view, location_id)
    recognised, orders, booked = await _totals(session, market_id, view, period, targets)
    share = None
    if scope.all and location_id is not None:
        market_total, _, _ = await _totals(session, market_id, view, period, None)
        share = _pct(recognised, market_total)
    avg = (recognised / orders).quantize(_CENT, rounding=ROUND_HALF_UP) if orders else None
    return RevenueSummary(
        period, view, location_id, await _currency(session, market_id), recognised, booked, orders, avg, share
    )


async def daily(
    session: AsyncSession,
    viewer: RevenueViewer,
    *,
    market_id: int,
    view: str,
    location_id: int | None,
    period: Period,
) -> RevenueDaily:
    """GET /revenue/daily — chuỗi theo ngày (đủ mọi ngày của kỳ, ngày theo múi giờ market)."""
    scope = await resolve_revenue_scope(session, viewer, market_id)
    targets = await _targets(session, scope, market_id, view, location_id)
    d, p = v_revenue_daily, v_revenue_pending
    recognised = dict(
        (
            await session.execute(
                select(d.c.day, func.sum(d.c.revenue_recognised))
                .where(*_filtered(d, view, market_id, period, targets))
                .group_by(d.c.day)
            )
        ).all()
    )
    booked = dict(
        (
            await session.execute(
                select(p.c.day, func.sum(p.c.revenue_booked))
                .where(*_filtered(p, view, market_id, period, targets))
                .group_by(p.c.day)
            )
        ).all()
    )
    points = tuple(
        RevenuePoint(day, Decimal(recognised.get(day, 0)), Decimal(booked.get(day, 0)))
        for day in period.days()
    )
    return RevenueDaily(await _currency(session, market_id), points)


async def by_location(
    session: AsyncSession,
    viewer: RevenueViewer,
    *,
    market_id: int,
    view: str,
    period: Period,
    location_id: int | None = None,
) -> RevenueByLocation:
    """GET /revenue/by-location — một dòng mỗi nơi của góc nhìn (owner chỉ nơi mình; 'Unassigned store')."""
    scope = await resolve_revenue_scope(session, viewer, market_id)
    targets = await _targets(session, scope, market_id, view, location_id)
    d, p = v_revenue_daily, v_revenue_pending
    rec = {
        loc: (Decimal(amount), int(n))
        for loc, amount, n in (
            await session.execute(
                select(_column(d, view), func.sum(d.c.revenue_recognised), func.sum(d.c.orders_delivered))
                .where(*_filtered(d, view, market_id, period, targets))
                .group_by(_column(d, view))
            )
        ).all()
    }
    bkd = {
        loc: Decimal(amount)
        for loc, amount in (
            await session.execute(
                select(_column(p, view), func.sum(p.c.revenue_booked))
                .where(*_filtered(p, view, market_id, period, targets))
                .group_by(_column(p, view))
            )
        ).all()
    }
    location_query = select(Location).where(Location.market_id == market_id, Location.type == view)
    if targets is not None:
        location_query = location_query.where(Location.id.in_(targets))
    else:
        location_query = location_query.where(Location.is_active.is_(True))
    locations = (await session.execute(location_query)).scalars().all()
    # Market share must include the unassigned-store bucket, not only locations in the table.
    total = (await _totals(session, market_id, view, period, None))[0] if scope.all else Decimal(0)
    built: list[RevenueRow] = []
    for loc in locations:
        amount, n = rec.get(loc.id, (Decimal(0), 0))
        share = _pct(amount, total) if scope.all else None
        built.append(RevenueRow(loc.id, loc.code, loc.name, n, amount, bkd.get(loc.id, Decimal(0)), share))
    if view == "store" and targets is None and (None in rec or None in bkd):
        amount, n = rec.get(None, (Decimal(0), 0))
        built.append(
            RevenueRow(
                None, None, UNASSIGNED_STORE, n, amount, bkd.get(None, Decimal(0)), _pct(amount, total)
            )
        )
    built.sort(key=lambda r: (-r.recognised, r.code is None, r.code or ""))
    return RevenueByLocation(view, await _currency(session, market_id), tuple(built))


async def resolve_market_period(
    session: AsyncSession, viewer: RevenueViewer, start: date | None, end: date | None
) -> tuple[int, Period]:
    """Use the authenticated market to prevent cross-currency aggregation.

    The API contract has no market selector. A system admin without a market context
    must not silently combine currencies; the caller must use a market-scoped account.
    """
    if not viewer.market:
        raise DomainError("VALIDATION_ERROR", "Revenue requires a market-scoped account.")
    market = await session.scalar(select(Market).where(Market.code == viewer.market))
    if market is None:
        raise DomainError("FORBIDDEN", "Your account has no valid market.")
    today = clock.now().astimezone(ZoneInfo(market.timezone)).date()
    return market.id, Period.resolve(start, end, today)


async def orders(
    session: AsyncSession,
    viewer: RevenueViewer,
    *,
    market_id: int,
    view: str,
    location_id: int,
    period: Period,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, object]], int]:
    """GET /revenue/orders: only recognised or booked orders in the selected period.

    Never query customer PII for the Business owner. Both time and location filters
    are applied in SQL, before pagination, independent of T07/T14.
    """
    scope = await resolve_revenue_scope(session, viewer, market_id)
    targets = await _targets(session, scope, market_id, view, location_id)
    local_day = cast(func.timezone(Market.timezone, CustomerOrder.delivered_at), Date)
    in_period = or_(
        and_(CustomerOrder.status == "DELIVERED", local_day.between(period.start, period.end)),
        and_(
            CustomerOrder.status.in_(BOOKED_STATUSES),
            CustomerOrder.committed_date.between(period.start, period.end),
        ),
    )
    location_col = CustomerOrder.origin_store_id if view == "store" else FulfilmentPlan.warehouse_id
    filters = [
        CustomerOrder.market_id == market_id,
        in_period,
        location_col.in_(targets if targets is not None else frozenset({location_id})),
    ]
    show_customer = "admin" in viewer.roles or (
        not scope.all and location_id in (scope.store_ids if view == "store" else scope.warehouse_ids)
    )
    fields = [
        CustomerOrder.order_no,
        CustomerOrder.delivered_at,
        CustomerOrder.total_amount.label("amount"),
        CustomerOrder.currency,
        CustomerOrder.status,
    ]
    if show_customer:
        fields.append(Customer.name.label("customer_name"))
    stmt = (
        select(*fields)
        .select_from(CustomerOrder)
        .join(FulfilmentPlan, FulfilmentPlan.id == CustomerOrder.approved_plan_id)
        .join(Market, Market.id == CustomerOrder.market_id)
    )
    if show_customer:
        stmt = stmt.join(Customer, Customer.id == CustomerOrder.customer_id)
    stmt = stmt.where(*filters)
    total = int(
        (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    )
    records = (
        (
            await session.execute(
                stmt.order_by(CustomerOrder.order_no, CustomerOrder.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .mappings()
        .all()
    )
    result: list[dict[str, object]] = []
    for row in records:
        item: dict[str, object] = {
            "order_no": row["order_no"],
            "delivered_at": row["delivered_at"],
            "amount": row["amount"],
            "currency": row["currency"],
            "status": row["status"],
        }
        if show_customer:
            item["customer_name"] = row["customer_name"]
        result.append(item)
    return result, total


def _csv_safe(value: str) -> str:
    """Prevent spreadsheet formula interpretation for user-controlled labels."""
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


async def export_csv(
    session: AsyncSession,
    viewer: RevenueViewer,
    *,
    market_id: int,
    view: str,
    location_id: int | None,
    period: Period,
) -> bytes:
    """One day/location per row; audit the exact filters and row count in the same transaction."""
    scope = await resolve_revenue_scope(session, viewer, market_id)
    targets = await _targets(session, scope, market_id, view, location_id)

    # Keyed by day/location/currency. Each view is selected independently, never
    # summed across store and warehouse, and never across markets.
    totals: dict[tuple[date, int | None, str], list[int | Decimal]] = {}
    for table, amount_column, count_column, amount_index in (
        (v_revenue_daily, "revenue_recognised", "orders_delivered", 1),
        (v_revenue_pending, "revenue_booked", "orders_pending", 2),
    ):
        loc_col = _column(table, view)
        rows = (
            await session.execute(
                select(
                    table.c.day,
                    loc_col,
                    table.c.currency,
                    func.sum(table.c[count_column]),
                    func.sum(table.c[amount_column]),
                )
                .where(*_filtered(table, view, market_id, period, targets))
                .group_by(table.c.day, loc_col, table.c.currency)
            )
        ).all()
        for day, loc_id, currency, count, amount in rows:
            key = (day, loc_id, currency)
            values = totals.setdefault(key, [0, Decimal(0), Decimal(0)])
            if amount_index == 1:
                values[0] = int(count)
            values[amount_index] = Decimal(amount)

    ids = {loc_id for _, loc_id, _ in totals if loc_id is not None}
    loc_names: dict[int, tuple[str, str]] = {}
    if ids:
        locations = (
            await session.execute(
                select(Location.id, Location.code, Location.name).where(
                    Location.market_id == market_id, Location.type == view, Location.id.in_(ids)
                )
            )
        ).all()
        loc_names = {i: (code, name) for i, code, name in locations}

    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        (
            "day",
            "view",
            "location_code",
            "location_name",
            "orders_delivered",
            "revenue_recognised",
            "revenue_booked",
            "currency",
        )
    )
    for (day, loc_id, currency), (count, recognised, booked) in sorted(
        totals.items(), key=lambda item: (item[0][0], item[0][1] is None, item[0][1] or 0)
    ):
        code, name = loc_names.get(loc_id, ("", UNASSIGNED_STORE if view == "store" else ""))
        # Quote risky spreadsheet-formula prefixes in free-text location labels.
        writer.writerow(
            (
                day.isoformat(),
                view,
                _csv_safe(code),
                _csv_safe(name),
                count,
                str(Decimal(recognised).quantize(_CENT)),
                str(Decimal(booked).quantize(_CENT)),
                currency,
            )
        )

    await record_decision(
        session,
        Action.REVENUE_EXPORTED,
        entity="revenue",
        entity_id=str(market_id),
        snapshot={
            "view": view,
            "location_id": location_id,
            "from": period.start.isoformat(),
            "to": period.end.isoformat(),
            "row_count": len(totals),
        },
        actor_user_id=viewer.id,
        actor_employee_id=viewer.employee_id,
        actor_role=viewer.roles[0] if viewer.roles else None,
    )
    return output.getvalue().encode("utf-8-sig")
