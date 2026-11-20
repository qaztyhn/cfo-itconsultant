"""M8 operational KPI and decision-log read models (docs/05 §8, docs/06 §§3,14–15).

No revenue data, raw customer fields, or unapproved default KPI numbers are used.
All market, warehouse and audit scopes are enforced before aggregation/pagination.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.audit import DecisionLog, KpiBaseline
from app.domain.models.hr import Employee
from app.domain.models.ops import CustomerOrder, Notification
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.ref import Location, Market

# DEC-R3-03 / API §19.8: exactly five published operational KPI keys.
METRICS: tuple[str, ...] = (
    "planning_time_min",
    "on_time_rate",
    "plan_acceptance_rate",
    "manual_intervention_rate",
    "eta_error_min",
)
BASELINE_METRICS = frozenset({"planning_time_min", "manual_intervention_rate"})
UNITS = {"planning_time_min": "min", "manual_intervention_rate": "ratio"}
ETA_TARGET = {"median": 20, "p90": 60}

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
    if "admin" not in roles and "ops" not in user.kpi_scopes:
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
) -> tuple[dict[date, dict[str, Measure]], dict[str, dict[str, Measure]], dict[str, Measure]]:
    """Aggregate one row per current committed order; do not synthesize missing evidence."""
    days = _measure_map(period.days())
    by_path = {
        metric: {"sales": Measure(), "dispatcher": Measure()}
        for metric in ("planning_time_min", "plan_acceptance_rate", "order_to_commit_min")
    }
    supporting = {"counter_commit_rate": Measure(), "manual_plan_count": Measure()}
    p, o = FulfilmentPlan, CustomerOrder
    constraints = [o.market_id == market.id]
    if warehouses is not None:
        constraints.append(p.warehouse_id.in_(warehouses))
    if warehouse_id is not None:
        constraints.append(p.warehouse_id == warehouse_id)
    if store_id is not None:
        constraints.append(o.origin_store_id == store_id)
    orders = (
        (
            await session.execute(
                select(
                    o.id,
                    o.status,
                    o.created_at,
                    o.approved_at,
                    o.delivered_at,
                    o.promise_start,
                    o.promise_end,
                    o.committed_date,
                    p.id.label("plan_id"),
                    p.rank,
                    p.status.label("plan_status"),
                    p.manual_reason_code,
                )
                .select_from(o)
                .outerjoin(p, p.id == o.approved_plan_id)
                .where(*constraints)
            )
        )
        .mappings()
        .all()
    )
    plan_ids = [row.plan_id for row in orders if row.plan_id is not None]
    order_ids = [row.id for row in orders]
    approvals: dict[int, str] = {}
    manual_actions: set[int] = set()
    if plan_ids:
        decisions = (
            await session.execute(
                select(DecisionLog.plan_id, DecisionLog.action, DecisionLog.actor_role)
                .where(
                    DecisionLog.plan_id.in_(plan_ids),
                    DecisionLog.action.in_(("PLAN_APPROVED", "MANUAL_PLAN_CREATED")),
                )
                .order_by(DecisionLog.ts, DecisionLog.id)
            )
        ).all()
        for plan_id, action, actor_role in decisions:
            if action == "MANUAL_PLAN_CREATED":
                manual_actions.add(plan_id)
            elif actor_role in ("sales", "dispatcher"):
                approvals[plan_id] = actor_role
    confirmed: dict[int, datetime] = {}
    if order_ids:
        notices = (
            await session.execute(
                select(Notification.order_id, Notification.sent_at)
                .where(
                    Notification.order_id.in_(order_ids),
                    Notification.template == "CONFIRMED",
                    Notification.status == "sent",
                    Notification.sent_at.is_not(None),
                )
                .order_by(Notification.sent_at, Notification.id)
            )
        ).all()
        for order_id, sent_at in notices:
            confirmed.setdefault(order_id, sent_at)
    for row in orders:
        approved_day = _day(row.approved_at, zone)
        committed = row.plan_id is not None and row.committed_date is not None and row.approved_at is not None
        if committed and approved_day in days:
            bucket = days[approved_day]
            manual = (
                row.plan_status == "manual"
                or row.manual_reason_code is not None
                or row.plan_id in manual_actions
            )
            path = "dispatcher" if manual else approvals.get(row.plan_id)
            # No start/end timestamps for actual human planning interaction are persisted.
            bucket["planning_time_min"].add(None)
            if path in ("sales", "dispatcher"):
                by_path["planning_time_min"][path].add(None)
            if path not in ("sales", "dispatcher") or row.rank is None:
                bucket["plan_acceptance_rate"].add(None)
            else:
                accepted = Decimal(int(row.rank == 1 and not manual))
                bucket["plan_acceptance_rate"].add(accepted)
                by_path["plan_acceptance_rate"][path].add(accepted)
            bucket["manual_intervention_rate"].add(Decimal(int(manual)))
            supporting["manual_plan_count"].add(Decimal(int(manual)))
            first_confirmed = confirmed.get(row.id)
            minutes = None
            if first_confirmed is not None and row.created_at is not None:
                elapsed = (first_confirmed - row.created_at).total_seconds()
                if elapsed >= 0:
                    minutes = Decimal(str(elapsed)) / Decimal(60)
            if path in ("sales", "dispatcher"):
                by_path["order_to_commit_min"][path].add(minutes)
            # No explicit persisted counter commitment event exists.
            supporting["counter_commit_rate"].add(None)
        delivered_day = _day(row.delivered_at, zone) if row.status == "DELIVERED" else None
        if delivered_day in days:
            if row.promise_start is None or row.promise_end is None or row.delivered_at is None:
                days[delivered_day]["on_time_rate"].add(None)
            else:
                within = row.promise_start <= row.delivered_at <= row.promise_end
                days[delivered_day]["on_time_rate"].add(Decimal(int(within)))
            # ETA forecast currently persists only an order ETA, not the pre-Dispatch trip ETA.
            days[delivered_day]["eta_error_min"].add(None)
    return days, by_path, supporting


def _value(data: dict[str, Measure], metric: str) -> float | int | None:
    return data[metric].value()


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
    days, by_path, supporting = await _collect(session, market, period, zone, scope, warehouse_id, store_id)
    totals = {name: Measure() for name in METRICS}
    for group in days.values():
        for metric in METRICS:
            totals[metric].combine(group[metric])
    baselines = (await session.scalars(select(KpiBaseline).where(KpiBaseline.market_id == market.id))).all()
    baseline_by_metric = {b.metric: b for b in baselines}
    output: dict[str, dict[str, object]] = {}
    for key in METRICS:
        if key == "eta_error_min":
            output[key] = {"median": None, "p90": None, "target": ETA_TARGET}
            continue
        value = totals[key].value()
        item: dict[str, object] = {"value": value}
        if key in ("planning_time_min", "plan_acceptance_rate"):
            item["by_path"] = {path: by_path[key][path].value() for path in ("sales", "dispatcher")}
        baseline = baseline_by_metric.get(key)
        if baseline is not None and key in BASELINE_METRICS:
            item["baseline"] = float(baseline.value)
            item["change"] = float(Decimal(str(value)) - baseline.value) if value is not None else None
        output[key] = item
    manual_count = supporting["manual_plan_count"]
    return {
        "period": {"from": period.start.isoformat(), "to": period.end.isoformat()},
        "metrics": output,
        "supporting": {
            "order_to_commit_min": {
                "by_path": {
                    path: by_path["order_to_commit_min"][path].value() for path in ("sales", "dispatcher")
                }
            },
            "counter_commit_rate": {"value": supporting["counter_commit_rate"].value()},
            "manual_plan_count": {"value": int(manual_count.sum) if manual_count.count else None},
        },
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
    data, _, _ = await _collect(session, market, period, zone, scope, None, None)
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
    if metric not in BASELINE_METRICS or not value.is_finite() or value < 0:
        raise DomainError("VALIDATION_ERROR", "Invalid baseline metric or value.")
    previous = await session.get(KpiBaseline, (market.id, metric))
    today = clock.now().astimezone(zone).date()
    stmt = (
        insert(KpiBaseline)
        .values(
            market_id=market.id,
            metric=metric,
            value=value,
            unit=UNITS[metric],
            source="manual",
            measured_on=today,
        )
        .on_conflict_do_update(
            index_elements=[KpiBaseline.market_id, KpiBaseline.metric],
            set_={"value": value, "unit": UNITS[metric], "source": "manual", "measured_on": today},
        )
    )
    await session.execute(stmt)
    # CONFIG_CHANGED is the existing approved action for configuration inputs.
    await record_decision(
        session,
        Action.CONFIG_CHANGED,
        entity="kpi_baseline",
        entity_id=f"{market.code.strip()}:{metric}",
        before={"value": str(previous.value)} if previous is not None else None,
        after={"value": str(value), "unit": UNITS[metric], "measured_on": today.isoformat()},
        actor_user_id=user.id,
        actor_employee_id=user.employee_id,
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
    same_market_order = (
        select(CustomerOrder.id)
        .where(CustomerOrder.id == DecisionLog.order_id, CustomerOrder.market_id == market.id)
        .exists()
    )
    same_market_employee = (
        select(Employee.id)
        .where(Employee.id == DecisionLog.actor_employee_id, Employee.market_id == market.id)
        .exists()
    )
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
    total = int((await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))) or 0)
    records = (
        await session.scalars(
            stmt.order_by(DecisionLog.ts.desc(), DecisionLog.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
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
            "actor_role": (
                entry.actor_role
                if entry.actor_role
                in {
                    "admin",
                    "dispatcher",
                    "warehouse",
                    "sales",
                    "driver",
                    "customer_service",
                    "viewer",
                }
                else None
            ),
            "entity": (
                entry.entity
                if entry.entity
                in {
                    "order",
                    "plan",
                    "stock",
                    "transfer",
                    "kpi_baseline",
                    "reservation",
                    "notification",
                    "mapping",
                    "employee",
                    "location",
                    "routing",
                }
                else None
            ),
            "order_id": entry.order_id,
            "plan_id": entry.plan_id,
            "reason_code": (
                entry.reason_code if entry.reason_code and CODE.fullmatch(entry.reason_code) else None
            ),
        }
        for entry in records
    ]
    return {"items": items, "page": page, "page_size": page_size, "total": total}
