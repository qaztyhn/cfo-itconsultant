"""M8 operational KPI and decision-log read models (docs/05 §8, docs/06 §§3,14–15).

No revenue data, raw customer fields, or unapproved default KPI numbers are used.
All market, warehouse and audit scopes are enforced before aggregation/pagination.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.audit import DecisionLog, ImprovementLog, KpiBaseline
from app.domain.models.hr import Attendance, Employee, ShiftTemplate, WarehouseStaff
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan, PrepReservation
from app.domain.models.ref import Location, Market, MarketHoliday


# The current docs call these "8 KPI", but docs/05 and the docs/06 JSON
# individually name ten keys. Keep all ten as written; owner must reconcile count.
METRICS: tuple[str, ...] = (
    "planning_time_min", "on_time_rate", "labour_hours_per_delivery",
    "km_per_delivery", "prep_error_min", "eta_error_min",
    "plan_acceptance_rate", "failed_delivery_rate", "capacity_utilisation",
    "manual_plan_count",
)
UNITS = {
    "planning_time_min": "min", "on_time_rate": "ratio",
    "labour_hours_per_delivery": "hours", "km_per_delivery": "km",
    "prep_error_min": "min", "eta_error_min": "min",
    "plan_acceptance_rate": "ratio", "failed_delivery_rate": "ratio",
    "capacity_utilisation": "ratio", "manual_plan_count": "count",
}
CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @classmethod
    def resolve(cls, start: date | None, end: date | None, today: date) -> "Period":
        final = end or today
        first = start or final - timedelta(days=29)
        if first > final or (final - first).days >= 366:
            raise DomainError("VALIDATION_ERROR", "Invalid KPI date range (maximum 366 days).")
        return cls(first, final)

    def days(self) -> list[date]:
        return [self.start + timedelta(days=n) for n in range((self.end - self.start).days + 1)]


@dataclass
class Measure:
    sum: Decimal = Decimal(0)
    count: Decimal = Decimal(0)
    missing: bool = False

    def add(self, value: Decimal | None, denominator: Decimal = Decimal(1)) -> None:
        if value is None:
            self.missing = True
        else:
            self.sum += value
            self.count += denominator

    def combine(self, other: "Measure") -> None:
        self.sum += other.sum
        self.count += other.count
        self.missing |= other.missing

    def value(self, *, count_metric: bool = False) -> float | int | None:
        if self.missing:
            return None
        if count_metric:
            return int(self.sum)
        return float(self.sum / self.count) if self.count else None


def _day(instant: object, zone: ZoneInfo) -> date | None:
    from datetime import datetime
    if not isinstance(instant, datetime):
        return None
    if instant.tzinfo is None or instant.utcoffset() is None:
        return None
    return instant.astimezone(zone).date()


async def _context(
    session: AsyncSession, user: CurrentUser, *, audit: bool = False
) -> tuple[Market, ZoneInfo]:
    roles = set(user.roles)
    if not (("admin" in roles) or (
        "ops" in user.kpi_scopes and
        bool(roles.intersection({"dispatcher", "warehouse", "viewer"}))
    )):
        raise DomainError("FORBIDDEN", "Operational KPI access denied.")
    if audit and not roles.intersection({"admin", "dispatcher", "viewer"}):
        raise DomainError("FORBIDDEN", "Decision-log access denied.")
    # No market selector exists in docs/06; never silently combine markets or currencies.
    if not user.market:
        raise DomainError("FORBIDDEN", "An authorized market context is required.")
    market = await session.scalar(select(Market).where(Market.code == user.market))
    if market is None:
        raise DomainError("FORBIDDEN", "An authorized market context is required.")
    try:
        zone = ZoneInfo(market.timezone)
    except (ValueError, KeyError) as exc:
        raise DomainError("VALIDATION_ERROR", "Market time zone is invalid.") from exc
    return market, zone


async def _scope(
    session: AsyncSession,
    user: CurrentUser,
    market_id: int,
    warehouse_id: int | None,
    store_id: int | None,
) -> tuple[int, ...] | None:
    for loc_id, kind in ((warehouse_id, "warehouse"), (store_id, "store")):
        if loc_id is None:
            continue
        loc = await session.get(Location, loc_id)
        if loc is None or loc.market_id != market_id or not loc.is_active:
            raise DomainError("NOT_FOUND", "Location not found.")
        # Check ownership before disclosing location type to warehouse users.
        if (
            "warehouse" in user.roles
            and "admin" not in user.roles
            and "dispatcher" not in user.roles
            and loc_id not in user.location_ids
            and kind == "warehouse"
        ):
            raise DomainError("NOT_FOUND", "Location not found.")
        if loc.type != kind:
            raise DomainError("VALIDATION_ERROR", "Location type does not match KPI filter.")
    if "warehouse" in user.roles and not ({"admin", "dispatcher"} & set(user.roles)):
        locations = (
            await session.scalars(
                select(Location.id).where(
                    Location.market_id == market_id,
                    Location.type == "warehouse",
                    Location.is_active.is_(True),
                    Location.id.in_(user.location_ids or (-1,)),
                )
            )
        ).all()
        if not locations:
            raise DomainError("FORBIDDEN", "No managed warehouse scope.")
        if warehouse_id is not None and warehouse_id not in locations:
            raise DomainError("NOT_FOUND", "Location not found.")
        return tuple(locations)
    return None


def _measure_map(days: list[date]) -> dict[date, dict[str, Measure]]:
    return {day: {metric: Measure() for metric in METRICS} for day in days}


async def _collect(
    session: AsyncSession,
    market: Market,
    period: Period,
    zone: ZoneInfo,
    warehouses: tuple[int, ...] | None,
    warehouse_id: int | None,
    store_id: int | None,
) -> dict[date, dict[str, Measure]]:
    """Compute from approved order/plan, improvement, reservation and attendance facts.

    Missing denominator/evidence remains null; zero is reserved for a proven count.
    Each KPI uses its source event's market-local date, never UTC day boundaries.
    """
    all_days = _measure_map(period.days())
    p, o = FulfilmentPlan, CustomerOrder
    constraints = [o.market_id == market.id]
    if warehouses is not None:
        constraints.append(p.warehouse_id.in_(warehouses))
    if warehouse_id is not None:
        constraints.append(p.warehouse_id == warehouse_id)
    if store_id is not None:
        constraints.append(o.origin_store_id == store_id)
    result = await session.execute(
        select(
            o.id, o.status, o.submitted_at, o.approved_at, o.delivered_at,
            o.closed_at, o.promise_end, o.committed_date,
            p.id.label("plan_id"), p.rank, p.status.label("plan_status"),
            p.manual_reason_code, p.prep_hours, p.distance_km,
        )
        .select_from(o)
        .outerjoin(p, p.id == o.approved_plan_id)
        .where(*constraints)
    )
    orders = result.mappings().all()
    # Improvement rows are per trip_stop; do not join them onto orders (multi-
    # vehicle deliveries would multiply all order-level KPI denominators).
    accepted: dict[int, list[bool | None]] = defaultdict(list)
    imp_rows = (
        await session.execute(
            select(
                ImprovementLog.order_id, ImprovementLog.delivered_at,
                ImprovementLog.prep_error_min, ImprovementLog.eta_error_min,
                ImprovementLog.accepted_unchanged,
            )
            .select_from(ImprovementLog)
            .join(o, o.id == ImprovementLog.order_id)
            .outerjoin(p, p.id == o.approved_plan_id)
            .where(*constraints)
        )
    ).all()
    for oid, delivered, prep_err, eta_err, unchanged in imp_rows:
        accepted[oid].append(unchanged)
        day = _day(delivered, zone)
        if day is not None and day in all_days:
            bucket = all_days[day]
            bucket["prep_error_min"].add(abs(Decimal(prep_err)) if prep_err is not None else None)
            bucket["eta_error_min"].add(abs(Decimal(eta_err)) if eta_err is not None else None)

    for row in orders:
        approved_day = _day(row.approved_at, zone)
        if approved_day in all_days:
            current = all_days[approved_day]
            if row.submitted_at is None:
                current["planning_time_min"].add(None)
            else:
                seconds = (row.approved_at - row.submitted_at).total_seconds()
                current["planning_time_min"].add(Decimal(str(seconds)) / Decimal(60) if seconds >= 0 else None)
            if row.plan_id is None:
                current["plan_acceptance_rate"].add(None)
            else:
                flags = accepted.get(row.id, [])
                if not flags or any(flag is None for flag in flags):
                    current["plan_acceptance_rate"].add(None)
                else:
                    accepted_rank_one = row.rank == 1 and all(flags) and row.manual_reason_code is None
                    current["plan_acceptance_rate"].add(Decimal(int(accepted_rank_one)))
            if row.plan_status == "manual" or row.manual_reason_code is not None:
                current["manual_plan_count"].sum += 1

        delivered_day = _day(row.delivered_at, zone) if row.status == "DELIVERED" else None
        if delivered_day in all_days:
            bucket = all_days[delivered_day]
            on_time = (
                row.promise_end is not None
                and row.committed_date is not None
                and row.delivered_at <= row.promise_end
                and delivered_day == row.committed_date
            )
            bucket["on_time_rate"].add(
                Decimal(int(on_time))
                if row.promise_end is not None and row.committed_date is not None else None
            )
            bucket["failed_delivery_rate"].add(Decimal(0))
            bucket["labour_hours_per_delivery"].add(
                Decimal(row.prep_hours) if row.prep_hours is not None else None
            )
            bucket["km_per_delivery"].add(
                Decimal(row.distance_km) if row.distance_km is not None else None
            )
        failed_day = _day(row.closed_at, zone) if row.status == "FAILED" else None
        if failed_day in all_days:
            all_days[failed_day]["failed_delivery_rate"].add(Decimal(1))

    # Actual presence, not expected_staff: do not fabricate a warehouse roster.
    res_filters = [
        PrepReservation.work_date.between(period.start, period.end),
        PrepReservation.status == "committed",
        PrepReservation.resource == "labour",
        Location.market_id == market.id,
    ]
    attendance_filters = [
        Attendance.work_date.between(period.start, period.end),
        Attendance.status == "present",
        WarehouseStaff.counts_in_capacity.is_(True),
        Location.market_id == market.id,
    ]
    for col, value in ((Location.id, warehouse_id),):
        if value is not None:
            res_filters.append(col == value)
            attendance_filters.append(col == value)
    if warehouses is not None:
        res_filters.append(Location.id.in_(warehouses))
        attendance_filters.append(Location.id.in_(warehouses))
    committed = (
        await session.execute(
            select(
                PrepReservation.work_date, PrepReservation.warehouse_id,
                func.sum(PrepReservation.hours),
            )
            .join(Location, Location.id == PrepReservation.warehouse_id)
            .where(*res_filters)
            .group_by(PrepReservation.work_date, PrepReservation.warehouse_id)
        )
    ).all()
    staffed = (
        await session.execute(
            select(
                Attendance.work_date, ShiftTemplate.warehouse_id,
                func.sum(ShiftTemplate.useful_hours_per_staff),
            )
            .join(ShiftTemplate, ShiftTemplate.id == Attendance.shift_template_id)
            .join(WarehouseStaff, WarehouseStaff.employee_id == Attendance.employee_id)
            .join(Location, Location.id == ShiftTemplate.warehouse_id)
            .where(*attendance_filters)
            .group_by(Attendance.work_date, ShiftTemplate.warehouse_id)
        )
    ).all()
    holidays = set(
        (await session.scalars(
            select(MarketHoliday.holiday_date).where(
                MarketHoliday.market_id == market.id,
                MarketHoliday.holiday_date.between(period.start, period.end),
            )
        )).all()
    )
    try:
        share = Decimal(str(MarketConfig.model_validate(market.config or {}).delivery_share))
    except ValueError as exc:
        raise DomainError("VALIDATION_ERROR", "Market capacity configuration is invalid.") from exc
    committed_map = {(d, w): Decimal(h) for d, w, h in committed}
    staffed_map = {
        (d, w): Decimal(0) if d in holidays else Decimal(h) * share
        for d, w, h in staffed
    }
    for day, wh in committed_map.keys() | staffed_map.keys():
        booked = committed_map.get((day, wh), Decimal(0))
        capacity = staffed_map.get((day, wh))
        # Missing attendance does not imply 0% utilization. Sum numerators
        # and denominators separately to weight warehouses by available hours.
        if capacity is None or capacity <= 0:
            all_days[day]["capacity_utilisation"].add(None)
        else:
            all_days[day]["capacity_utilisation"].add(booked, capacity)
    return all_days


def _value(data: dict[str, Measure], metric: str) -> float | int | None:
    return data[metric].value(count_metric=metric == "manual_plan_count")


async def summary(
    session: AsyncSession,
    user: CurrentUser,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse_id: int | None = None,
    store_id: int | None = None,
) -> dict[str, object]:
    market, zone = await _context(session, user)
    scope = await _scope(session, user, market.id, warehouse_id, store_id)
    period = Period.resolve(date_from, date_to, clock.now().astimezone(zone).date())
    rows = await _collect(session, market, period, zone, scope, warehouse_id, store_id)
    totals = {name: Measure() for name in METRICS}
    for group in rows.values():
        for metric in METRICS:
            totals[metric].combine(group[metric])
    baselines = (
        await session.scalars(select(KpiBaseline).where(KpiBaseline.market_id == market.id))
    ).all()
    baseline_by_metric = {b.metric: b for b in baselines}
    output: dict[str, dict[str, float | int | None]] = {}
    for key in METRICS:
        value = _value(totals, key)
        baseline = baseline_by_metric.get(key)
        item: dict[str, float | int | None] = {"value": value}
        if baseline is not None:
            item["baseline"] = float(baseline.value)
            item["change"] = float(Decimal(str(value)) - baseline.value) if value is not None else None
        output[key] = item
    return {
        "period": {"from": period.start.isoformat(), "to": period.end.isoformat()},
        "metrics": output,
    }


async def daily(
    session: AsyncSession,
    user: CurrentUser,
    *,
    metric: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, object]:
    if metric not in METRICS:
        raise DomainError("VALIDATION_ERROR", "Unknown operational KPI metric.")
    market, zone = await _context(session, user)
    scope = await _scope(session, user, market.id, None, None)
    period = Period.resolve(date_from, date_to, clock.now().astimezone(zone).date())
    data = await _collect(session, market, period, zone, scope, None, None)
    return {
        "metric": metric,
        "points": [{"day": day.isoformat(), "value": _value(data[day], metric)} for day in period.days()],
    }


async def diagnostics(session: AsyncSession, user: CurrentUser) -> dict[str, object]:
    await _context(session, user)
    # Neither metric has an approved DDL/formula: failed planning checks are NOT
    # violations of approved constraints, and Alert has no source-event FK.
    # Return explicit unavailable values; never invent a violation count or latency.
    return {"hard_constraint_violations": None, "event_to_alert_latency_s_median": None}


async def put_baseline(
    session: AsyncSession,
    user: CurrentUser,
    *,
    metric: str,
    value: Decimal,
) -> dict[str, object]:
    if "admin" not in user.roles:
        raise DomainError("FORBIDDEN", "Only admin may update KPI baselines.")
    market, zone = await _context(session, user)
    if metric not in METRICS or not value.is_finite():
        raise DomainError("VALIDATION_ERROR", "Invalid baseline metric or value.")
    previous = await session.get(KpiBaseline, (market.id, metric))
    today = clock.now().astimezone(zone).date()
    stmt = (
        insert(KpiBaseline)
        .values(
            market_id=market.id, metric=metric, value=value,
            unit=UNITS[metric], source="manual", measured_on=today,
        )
        .on_conflict_do_update(
            index_elements=[KpiBaseline.market_id, KpiBaseline.metric],
            set_={"value": value, "unit": UNITS[metric], "source": "manual", "measured_on": today},
        )
    )
    await session.execute(stmt)
    # CONFIG_CHANGED is the existing approved action for configuration inputs.
    await record_decision(
        session, Action.CONFIG_CHANGED, entity="kpi_baseline",
        entity_id=f"{market.code.strip()}:{metric}",
        before={"value": str(previous.value)} if previous is not None else None,
        after={"value": str(value), "unit": UNITS[metric], "measured_on": today.isoformat()},
        actor_user_id=user.id, actor_employee_id=user.employee_id,
        actor_role="admin",
    )
    return {"metric": metric, "value": float(value), "unit": UNITS[metric], "measured_on": today.isoformat()}


async def decision_log(
    session: AsyncSession,
    user: CurrentUser,
    *,
    order_id: int | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    market, zone = await _context(session, user, audit=True)
    period = Period.resolve(date_from, date_to, clock.now().astimezone(zone).date())
    local_day = cast(func.timezone(market.timezone, DecisionLog.ts), Date)
    same_market_order = select(CustomerOrder.id).where(
        CustomerOrder.id == DecisionLog.order_id, CustomerOrder.market_id == market.id
    ).exists()
    same_market_employee = select(Employee.id).where(
        Employee.id == DecisionLog.actor_employee_id, Employee.market_id == market.id
    ).exists()
    stmt = select(DecisionLog).where(
        or_(
            same_market_order,
            and_(DecisionLog.order_id.is_(None), same_market_employee),
        ),
        local_day.between(period.start, period.end),
    )
    if order_id is not None:
        stmt = stmt.where(DecisionLog.order_id == order_id)
    if action is not None:
        if not CODE.fullmatch(action):
            raise DomainError("VALIDATION_ERROR", "Invalid decision action filter.")
        stmt = stmt.where(DecisionLog.action == action)
    total = int(
        (await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))) or 0
    )
    records = (
        await session.scalars(
            stmt.order_by(DecisionLog.ts.desc(), DecisionLog.id.desc())
            .limit(page_size).offset((page - 1) * page_size)
        )
    ).all()
    # Decision snapshots and reason_text are JSON/free text that may contain
    # contact/address/customer PII. Never serialise them directly.
    items = [
        {
            "id": entry.id,
            "ts": entry.ts.isoformat(),
            "correlation_id": str(entry.correlation_id),
            "action": entry.action if CODE.fullmatch(entry.action) else None,
            "actor_role": entry.actor_role
            if entry.actor_role in {"admin", "dispatcher", "warehouse", "sales", "driver", "customer_service", "viewer"} else None,
            "entity": entry.entity if entry.entity in {
                "order", "plan", "stock", "transfer", "kpi_baseline", "reservation",
                "notification", "mapping", "employee", "location", "routing",
            } else None,
            "order_id": entry.order_id,
            "plan_id": entry.plan_id,
            "reason_code": entry.reason_code if entry.reason_code and CODE.fullmatch(entry.reason_code) else None,
        }
        for entry in records
    ]
    return {"items": items, "page": page, "page_size": page_size, "total": total}
