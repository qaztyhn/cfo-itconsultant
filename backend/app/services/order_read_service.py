"""Đọc đơn theo vai trò (06 v1.4 mục 5.1–5.4; US-ORD-02 AC1–AC3, US-ORD-06 AC1; BR-ORD-05; 09 bất biến 27).

- resolve_order_scope(): vai trò đọc rộng nhất (admin > dispatcher > warehouse > customer_service > sales >
  driver), market, địa điểm; viewer/không vai trò → 403.
- Phạm vi (mục 5.2) là điều kiện SQL; đơn ngoài phạm vi → 404 (không lộ sự tồn tại).
- Trường theo vai trò (mục 5.3): bậc "full" (admin, dispatcher, warehouse), "store" (sales, customer_service),
  "driver". Trường bị cấm bị BỎ khỏi dict (router dùng exclude_unset). Không có GPS ở đây.
- Danh sách mặc định sắp theo thứ tự đặt `submitted_at, id` (FIFO hiển thị, không ép FIFO thực thi).

Owner: Dev 1 (A) — M2.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Select, and_, case, false, func, or_, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.domain.enums import OrderStatus as S
from app.domain.models.audit import DecisionLog
from app.domain.models.hr import Employee
from app.domain.models.ops import (
    Alert,
    CustomerOrder,
    DeliveryTrip,
    EtaForecast,
    MilestoneEvent,
    Notification,
    OrderLine,
    TripStop,
)
from app.domain.models.plan import FulfilmentPlan, PlanningRun
from app.domain.models.ref import Customer, HandlingGroup, Location, Market, ProductGlobal, Vehicle
from app.services.order_scope import LIVE_PLAN_STATUSES, warehouse_orders
from app.services.query_utils import parse_sort

OrderRole = Literal["admin", "dispatcher", "warehouse", "customer_service", "sales", "driver"]
Tier = Literal["full", "store", "driver"]
_PRECEDENCE: tuple[OrderRole, ...] = (
    "admin",
    "dispatcher",
    "warehouse",
    "customer_service",
    "sales",
    "driver",
)
_TIER: dict[OrderRole, Tier] = {
    "admin": "full",
    "dispatcher": "full",
    "warehouse": "full",
    "customer_service": "store",
    "sales": "store",
    "driver": "driver",
}
IN_EXECUTION = (S.APPROVED, S.PREPARING, S.GOODS_READY, S.LOADED, S.DISPATCHED)
ORDER_SORT = frozenset({"submitted_at", "date_to", "promise_end", "committed_date", "order_no", "status"})
DEFAULT_SORT = "submitted_at"  # + id: thứ tự đặt hàng (BR-ORD-05)
RISK_COLORS = frozenset({"green", "yellow", "orange", "red"})
DATE_MODES = frozenset({"exact", "range", "latest"})


class OrderReader(Protocol):
    @property
    def roles(self) -> tuple[str, ...]: ...
    @property
    def market(self) -> str: ...
    @property
    def location_ids(self) -> tuple[int, ...]: ...
    @property
    def employee_id(self) -> int | None: ...


@dataclass(frozen=True)
class OrderScope:
    role: OrderRole
    market_id: int | None  # None: admin không gắn nhân viên → mọi market
    location_ids: frozenset[int]
    employee_id: int | None
    today: date
    tz: ZoneInfo

    @property
    def tier(self) -> Tier:
        return _TIER[self.role]


async def resolve_order_scope(session: AsyncSession, user: OrderReader) -> OrderScope:
    role = next((r for r in _PRECEDENCE if r in user.roles), None)
    if role is None:
        raise DomainError("FORBIDDEN", "Role cannot read orders.")
    market = None
    if user.market:
        market = await session.scalar(select(Market).where(Market.code == user.market))
    if market is None and role != "admin":
        raise DomainError("FORBIDDEN", "Role cannot read orders.")
    tz = ZoneInfo(market.timezone) if market is not None else ZoneInfo("UTC")
    return OrderScope(
        role=role,
        market_id=market.id if market is not None else None,
        location_ids=frozenset(user.location_ids),
        employee_id=user.employee_id,
        today=clock.now().astimezone(tz).date(),
        tz=tz,
    )


def _not_found() -> DomainError:
    return DomainError("NOT_FOUND", "Order not found.")


def scope_condition(scope: OrderScope) -> ColumnElement[bool]:
    """06 mục 5.2 dưới dạng điều kiện SQL trên ops.customer_order."""
    market = true() if scope.market_id is None else CustomerOrder.market_id == scope.market_id
    if scope.role in ("admin", "dispatcher", "customer_service"):
        return market
    if scope.role == "warehouse":
        return and_(market, warehouse_orders(scope.location_ids)) if scope.location_ids else false()
    if scope.role == "sales":
        if not scope.location_ids:
            return false()
        return and_(market, CustomerOrder.origin_store_id.in_(sorted(scope.location_ids)))
    if scope.employee_id is None:  # driver
        return false()
    on_my_trip = (
        select(TripStop.id)
        .join(DeliveryTrip, DeliveryTrip.id == TripStop.trip_id)
        .where(
            TripStop.order_id == CustomerOrder.id,
            TripStop.status != "cancelled",
            DeliveryTrip.driver_employee_id == scope.employee_id,
        )
        .exists()
    )
    return and_(market, on_my_trip)


def _hhmm(value: time | None) -> str | None:
    return None if value is None else value.strftime("%H:%M")


def _site(address: str) -> str:
    return address.rsplit(",", 1)[-1].strip()


def _latest_risk() -> Select[Any]:
    ranked = select(
        EtaForecast,
        func.row_number()
        .over(partition_by=EtaForecast.order_id, order_by=EtaForecast.version.desc())
        .label("rn"),
    ).subquery()
    return select(ranked).where(ranked.c.rn == 1)


async def _risks(session: AsyncSession, order_ids: Sequence[int]) -> dict[int, Any]:
    if not order_ids:
        return {}
    sub = _latest_risk().subquery()
    rows = (await session.execute(select(sub).where(sub.c.order_id.in_(order_ids)))).all()
    return {r.order_id: r for r in rows}


def _risk_view(row: Any, tier: Tier) -> dict[str, object] | None:
    if row is None:
        return None
    if tier == "store":
        return {"status": row.risk_status, "color": row.risk_color, "forecast_eta": row.forecast_eta}
    return {
        "status": row.risk_status,
        "color": row.risk_color,
        "forecast_eta": row.forecast_eta,
        "planned_eta": row.planned_eta,
        "commitment_deadline": row.commitment_deadline,
        "slack_min": row.slack_min,
        "consumption_pct": float(row.consumption_pct),
    }


async def _warehouses(session: AsyncSession, orders: Sequence[CustomerOrder]) -> dict[int, dict[str, object]]:
    """Kho hiển thị: kế hoạch đã duyệt, nếu chưa thì kế hoạch proposed rank 1 (mục 5.4)."""
    ids = [o.id for o in orders]
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(FulfilmentPlan.order_id, FulfilmentPlan.id, FulfilmentPlan.status, FulfilmentPlan.rank,
                   Location.id, Location.code)  # fmt: skip
            .join(Location, Location.id == FulfilmentPlan.warehouse_id)
            .where(FulfilmentPlan.order_id.in_(ids), FulfilmentPlan.status.in_(LIVE_PLAN_STATUSES))
            .order_by(FulfilmentPlan.order_id, FulfilmentPlan.id.desc())
        )
    ).all()
    approved = {o.id: o.approved_plan_id for o in orders}
    out: dict[int, dict[str, object]] = {}
    for order_id, plan_id, status, rank, loc_id, loc_code in rows:
        ref = {"id": loc_id, "code": loc_code}
        if plan_id == approved.get(order_id) or status in ("approved", "manual"):
            out[order_id] = ref
        elif order_id not in out and status == "proposed" and rank == 1:
            out[order_id] = ref
    return out


def _sort_columns(sort: str | None) -> list[Any]:
    columns: dict[str, Any] = {
        "submitted_at": CustomerOrder.submitted_at,
        "date_to": CustomerOrder.date_to,
        "promise_end": CustomerOrder.promise_end,
        "committed_date": CustomerOrder.committed_date,
        "order_no": CustomerOrder.order_no,
        "status": CustomerOrder.status,
    }
    order: list[Any] = []
    fields = parse_sort(sort, ORDER_SORT, DEFAULT_SORT)
    for field, desc in fields:
        column = columns[field]
        order.append((column.desc() if desc else column.asc()).nulls_last())
    if "submitted_at" not in {f for f, _ in fields}:
        order.append(CustomerOrder.submitted_at.asc())  # hòa thì theo thứ tự đặt (BR-ORD-05)
    return [*order, CustomerOrder.id.asc()]


async def list_orders(
    session: AsyncSession,
    scope: OrderScope,
    *,
    status: str | None = None,
    risk_color: str | None = None,
    committed_date_from: date | None = None,
    committed_date_to: date | None = None,
    warehouse_id: int | None = None,
    store_id: int | None = None,
    date_mode: str | None = None,
    q: str | None = None,
    blocked: bool | None = None,
    sort: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, object]], int]:
    """GET /orders (06 mục 5, 5.4). Mặc định `submitted_at ASC, id ASC`."""
    query = (
        select(CustomerOrder, Customer.name, Location.code)
        .join(Customer, Customer.id == CustomerOrder.customer_id)
        .outerjoin(Location, Location.id == CustomerOrder.origin_store_id)
        .where(scope_condition(scope))
    )
    if status is not None:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if not statuses or any(s not in S.__members__ for s in statuses):
            raise DomainError("VALIDATION_ERROR", "Unknown order status.", {"field": "status"})
        query = query.where(CustomerOrder.status.in_(statuses))
    if blocked is not None:
        flag = CustomerOrder.status == S.BLOCKED_UNMAPPED_SKU.value
        query = query.where(flag if blocked else ~flag)
    if date_mode is not None:
        if date_mode not in DATE_MODES:
            raise DomainError("VALIDATION_ERROR", "Unknown date mode.", {"field": "date_mode"})
        query = query.where(CustomerOrder.date_mode == date_mode)
    if committed_date_from is not None:
        query = query.where(CustomerOrder.committed_date >= committed_date_from)
    if committed_date_to is not None:
        query = query.where(CustomerOrder.committed_date <= committed_date_to)
    if store_id is not None:
        query = query.where(CustomerOrder.origin_store_id == store_id)
    if warehouse_id is not None:
        query = query.where(warehouse_orders([warehouse_id]))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                CustomerOrder.order_no.ilike(like),
                CustomerOrder.external_ref.ilike(like),
                Customer.name.ilike(like),
            )
        )
    if risk_color is not None:
        if risk_color not in RISK_COLORS:
            raise DomainError("VALIDATION_ERROR", "Unknown risk color.", {"field": "risk_color"})
        latest = _latest_risk().subquery()
        query = query.join(latest, latest.c.order_id == CustomerOrder.id).where(
            latest.c.risk_color == risk_color
        )
    order_by = _sort_columns(sort)
    total = int(
        (
            await session.execute(select(func.count()).select_from(query.order_by(None).subquery()))
        ).scalar_one()
    )
    rows = (
        await session.execute(query.order_by(*order_by).limit(page_size).offset((page - 1) * page_size))
    ).all()
    orders = [r[0] for r in rows]
    risks = await _risks(session, [o.id for o in orders])
    warehouses = await _warehouses(session, orders)
    items = []
    for order, customer_name, store_code in rows:
        item: dict[str, object] = {
            "id": order.id,
            "order_no": order.order_no,
            "status": order.status,
            "customer_name": customer_name,
            "site": _site(order.delivery_address),
            "warehouse": warehouses.get(order.id),
            "origin_store": None if order.origin_store_id is None else {"id": order.origin_store_id,
                                                                        "code": store_code},  # fmt: skip
            "date_request": {"mode": order.date_mode, "date_from": order.date_from, "date_to": order.date_to},
            "committed_date": order.committed_date,
            "promise_end": order.promise_end,
            "risk_color": getattr(risks.get(order.id), "risk_color", None),
            "block_reason": order.block_reason,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "submitted_at": order.submitted_at,
        }
        if scope.tier == "driver":
            for key in (
                "origin_store",
                "date_request",
                "block_reason",
                "total_amount",
                "currency",
                "risk_color",
            ):
                item.pop(key)
        elif scope.tier == "store":
            item.pop("warehouse")
        items.append(item)
    return items, total


_LOCAL_NAMES = text("""
SELECT p.local_sku, p.name, p.sale_unit FROM ref.v_product_local p JOIN ref.market m ON m.code = p.market_code
WHERE m.id = :market_id AND p.local_sku = ANY(:skus)
""")


async def get_order(session: AsyncSession, scope: OrderScope, order_id: int) -> dict[str, object]:
    """GET /orders/{id} (06 mục 5.1) với trường theo vai trò (mục 5.3)."""
    row = (
        await session.execute(
            select(CustomerOrder, Customer, Market.code)
            .join(Customer, Customer.id == CustomerOrder.customer_id)
            .join(Market, Market.id == CustomerOrder.market_id)
            .where(CustomerOrder.id == order_id, scope_condition(scope))
        )
    ).first()
    if row is None:
        raise _not_found()
    order, customer, market_code = row
    tier = scope.tier
    lines = (
        await session.execute(
            select(OrderLine, ProductGlobal, HandlingGroup.code)
            .outerjoin(ProductGlobal, ProductGlobal.id == OrderLine.global_product_id)
            .outerjoin(HandlingGroup, HandlingGroup.id == ProductGlobal.handling_group_id)
            .where(OrderLine.order_id == order_id)
            .order_by(OrderLine.line_no)
        )
    ).all()
    local = {
        r.local_sku: r
        for r in await session.execute(
            _LOCAL_NAMES, {"market_id": order.market_id, "skus": [line.local_sku for line, _, _ in lines]}
        )
    }
    weight = sum(
        (Decimal(line.qty_base or 0) * g.weight_kg for line, g, _ in lines if g is not None), Decimal(0)
    )
    volume = sum(
        (Decimal(line.qty_base or 0) * g.volume_m3 for line, g, _ in lines if g is not None), Decimal(0)
    )
    line_views: list[dict[str, object]] = []
    for line, product, group in lines:
        name = local[line.local_sku].name if line.local_sku in local else (product.name if product else None)
        sale_unit = local[line.local_sku].sale_unit if line.local_sku in local else None
        view: dict[str, object] = {
            "line_no": line.line_no,
            "local_sku": line.local_sku,
            "global_code": product.code if product else None,
            "name": name,
            "qty_sale": line.qty_sale,
            "sale_unit": sale_unit,
            "qty_base": line.qty_base,
            "unit_price": line.unit_price,
            "line_total": line.line_total,
            "handling_group": group,
            "flags": list(product.flags) if product else [],
        }
        if tier == "store":
            view.pop("handling_group")
            view.pop("flags")
        elif tier == "driver":
            view = {k: view[k] for k in ("line_no", "name", "qty_sale", "sale_unit")}
        line_views.append(view)

    names: dict[int, str] = {}
    if order.sales_employee_id is not None:
        emp = await session.get(Employee, order.sales_employee_id)
        if emp is not None:
            names[emp.id] = f"{emp.first_name} {emp.last_name}"
    store = await session.get(Location, order.origin_store_id) if order.origin_store_id else None
    latest_run = await session.scalar(
        select(func.max(PlanningRun.id)).where(PlanningRun.order_id == order_id)
    )
    risk = (await _risks(session, [order_id])).get(order_id)
    result: dict[str, object] = {
        "id": order.id,
        "order_no": order.order_no,
        "external_ref": order.external_ref,
        "status": order.status,
        "market": market_code.strip(),
        "customer": {"id": customer.id, "name": customer.name, "type": customer.type},
        "contact": {"name": order.contact_name, "phone": order.contact_phone, "email": order.contact_email},
        "delivery": {
            "address": order.delivery_address,
            "lat": float(order.delivery_lat),
            "lon": float(order.delivery_lon),
            "receiving_restrictions": order.receiving_restrictions,
            "special_requirements": order.special_requirements,
        },
        "date_request": {
            "mode": order.date_mode,
            "date_from": order.date_from,
            "date_to": order.date_to,
            "window": (
                None
                if order.window_start is None
                else {"start": _hhmm(order.window_start), "end": _hhmm(order.window_end)}
            ),
        },
        "committed": {
            "date": order.committed_date,
            "promise_start": order.promise_start,
            "promise_end": order.promise_end,
        },
        "origin_store": None if store is None else {"id": store.id, "name": store.name},
        "sales": (
            None
            if order.sales_employee_id is None
            else {"id": order.sales_employee_id, "name": names.get(order.sales_employee_id, "")}
        ),
        "lines": line_views,
        "totals": {
            "weight_kg": float(weight),
            "volume_m3": float(volume),
            "amount": order.total_amount,
            "currency": order.currency,
        },
        "block_reason": order.block_reason,
        "approved_plan_id": order.approved_plan_id,
        "latest_run_id": latest_run,
        "risk": _risk_view(risk, tier),
        "version": order.version,
        "submitted_at": order.submitted_at,
    }
    if tier == "store":
        for key in ("approved_plan_id", "latest_run_id"):
            result.pop(key)
        result["totals"] = {"amount": order.total_amount, "currency": order.currency}
    elif tier == "driver":
        hidden = (
            "external_ref",
            "origin_store",
            "sales",
            "block_reason",
            "approved_plan_id",
            "latest_run_id",
            "risk",
        )
        for key in hidden:
            result.pop(key)
        result["customer"] = {"name": customer.name}
        result["date_request"] = {"window": result["date_request"]["window"]}  # type: ignore[index]
        result["totals"] = {"weight_kg": float(weight), "volume_m3": float(volume)}
    return result


def _start_of_day(scope: OrderScope) -> datetime:
    return datetime.combine(scope.today, time.min, tzinfo=scope.tz)


async def counts(session: AsyncSession, scope: OrderScope) -> dict[str, object]:
    """GET /orders/counts (Phụ lục A; bucket theo 06 mục 5.4).

    BLOCKED_UNMAPPED_SKU là bản ghi legacy (ASM-005): không thuộc `all`, `needs_plan` hay hàng đợi Dispatcher.
    """
    start = _start_of_day(scope)
    latest = _latest_risk().subquery()
    pending_suggestion = (
        select(FulfilmentPlan.id)
        .join(PlanningRun, PlanningRun.id == FulfilmentPlan.run_id)
        .where(
            FulfilmentPlan.order_id == CustomerOrder.id,
            PlanningRun.kind == "replan_suggestion",
            FulfilmentPlan.status == "proposed",
        )
        .exists()
    )

    def bucket(condition: ColumnElement[bool]) -> Any:
        return func.count(case((condition, 1)))

    closed = CustomerOrder.status.in_((S.DELIVERED.value, S.CANCELLED.value))
    closed_before_today = and_(
        closed,
        func.coalesce(CustomerOrder.closed_at, CustomerOrder.delivered_at, CustomerOrder.updated_at) < start,
    )
    row = (
        await session.execute(
            select(
                bucket(and_(~closed_before_today, CustomerOrder.status != S.BLOCKED_UNMAPPED_SKU.value)),
                bucket(CustomerOrder.status == S.SUBMITTED.value),
                bucket(CustomerOrder.status == S.PLANNED.value),
                bucket(CustomerOrder.status == S.NO_FEASIBLE_DATE.value),
                bucket(CustomerOrder.status.in_([s.value for s in IN_EXECUTION])),
                bucket(pending_suggestion),
                bucket(and_(CustomerOrder.status == S.DELIVERED.value, CustomerOrder.delivered_at >= start)),
                bucket(
                    and_(
                        CustomerOrder.status.in_([s.value for s in IN_EXECUTION]),
                        latest.c.risk_color.in_(("orange", "red")),
                    )
                ),
            )
            .select_from(CustomerOrder)
            .outerjoin(latest, latest.c.order_id == CustomerOrder.id)
            .where(scope_condition(scope))
        )
    ).one()
    all_, needs_plan, awaiting, nfd, in_exec, replan, delivered_today, at_risk = (int(v) for v in row)
    alert_scope = (
        Alert.order_id.in_(select(CustomerOrder.id).where(scope_condition(scope)))
        if scope.role not in ("admin", "dispatcher")
        else (true() if scope.market_id is None else Alert.market_id == scope.market_id)
    )
    exceptions = int(
        await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.resolved_at.is_(None), Alert.type.in_(("EXCEPTION", "REPLAN_SUGGESTED")), alert_scope
            )
        )
        or 0
    )
    return {
        "all": all_,
        "needs_plan": needs_plan,
        "awaiting_approval": awaiting,
        "no_feasible_date": nfd,
        "in_execution": in_exec,
        "replan_suggested": replan,
        "delivered_today": delivered_today,
        "nav": {
            "order_queue": needs_plan + awaiting + nfd if scope.role == "dispatcher" else 0,
            "exceptions": exceptions,
            "tracking_risk": at_risk,
        },
    }


TIMELINE_ROLES = frozenset({"admin", "dispatcher", "warehouse", "customer_service"})
_KIND_ORDER = {
    "order_submitted": 0,
    "planning_run": 1,
    "decision": 2,
    "milestone": 3,
    "notification": 4,
    "eta": 5,
}


def _title(text_: str) -> str:
    return text_.replace("_", " ").capitalize()


async def timeline(session: AsyncSession, scope: OrderScope, order_id: int) -> dict[str, object]:
    """GET /orders/{id}/timeline (06 v1.4 mục 5.5; US-ORD-03 AC1/AC2).

    Vai trò: admin, dispatcher, warehouse, customer_service; khác → 403; đơn ngoài phạm vi → 404.
    CS không thấy lần chạy kế hoạch và quyết định nội bộ; không ai thấy điểm số, GPS, payload sự kiện,
    người nhận thông báo, snapshot/before/after.
    """
    if scope.role not in TIMELINE_ROLES:
        raise DomainError("FORBIDDEN", "Role cannot read the order timeline.")
    order = await session.scalar(
        select(CustomerOrder).where(CustomerOrder.id == order_id, scope_condition(scope))
    )
    if order is None:
        raise _not_found()
    cs = scope.role == "customer_service"
    items: list[dict[str, object]] = [
        {"at": order.submitted_at, "kind": "order_submitted", "title": "Order submitted", "detail": {},
         "actor": None}  # fmt: skip
    ]
    if not cs:
        for run in await session.scalars(select(PlanningRun).where(PlanningRun.order_id == order_id)):
            items.append(
                {
                    "at": run.created_at,
                    "kind": "planning_run",
                    "title": f"Planning run {run.run_no} ({run.kind})",
                    "detail": {
                        "run_id": run.id,
                        "run_no": run.run_no,
                        "kind": run.kind,
                        "result": run.result,
                    },
                    "actor": None,
                }
            )
        decisions = await session.execute(
            select(DecisionLog, Employee.first_name, Employee.last_name)
            .outerjoin(Employee, Employee.id == DecisionLog.actor_employee_id)
            .where(DecisionLog.order_id == order_id)
        )
        for log, first, last in decisions.all():
            items.append(
                {
                    "at": log.ts,
                    "kind": "decision",
                    "title": _title(log.action),
                    "detail": {
                        "action": log.action,
                        "plan_id": log.plan_id,
                        "reason_code": log.reason_code,
                        "reason_text": log.reason_text,
                    },
                    "actor": (
                        None
                        if log.actor_role is None and log.actor_employee_id is None
                        else {
                            "role": log.actor_role,
                            "employee_id": log.actor_employee_id,
                            "name": None if first is None else f"{first} {last}",
                        }
                    ),
                }
            )
    events = await session.execute(
        select(MilestoneEvent, Vehicle.code)
        .outerjoin(DeliveryTrip, DeliveryTrip.id == MilestoneEvent.trip_id)
        .outerjoin(Vehicle, Vehicle.id == DeliveryTrip.vehicle_id)
        .where(MilestoneEvent.order_id == order_id)
    )
    for event, vehicle_code in events.all():
        items.append(
            {
                "at": event.occurred_at,
                "kind": "milestone",
                "title": _title(event.event_type),
                "detail": {"type": event.event_type, "vehicle_code": vehicle_code},
                "actor": None,
            }
        )
    for note in await session.scalars(select(Notification).where(Notification.order_id == order_id)):
        items.append(
            {
                "at": note.sent_at or note.scheduled_for,
                "kind": "notification",
                "title": f"Notification {note.template}",
                "detail": {"template": note.template, "channel": note.channel, "status": note.status},
                "actor": None,
            }
        )
    for eta in await session.scalars(select(EtaForecast).where(EtaForecast.order_id == order_id)):
        detail: dict[str, object] = {"forecast_eta": eta.forecast_eta, "risk_status": eta.risk_status}
        if not cs:
            detail |= {"version": eta.version, "risk_color": eta.risk_color, "trigger": eta.trigger}
        items.append(
            {
                "at": eta.computed_at,
                "kind": "eta",
                "title": f"ETA v{eta.version}",
                "detail": detail,
                "actor": None,
            }
        )
    items.sort(key=lambda i: (i["at"], _KIND_ORDER[str(i["kind"])]))
    return {"items": items}
