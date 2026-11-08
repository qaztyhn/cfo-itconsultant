"""T18 stock transfers (US-ATP-02/03; 04 §6.4, 05 §ops.stock_transfer, 06 §7).

All writes join the request transaction. An unverified source snapshot/route never
turns into a transfer suggestion. No order, stock snapshot or source-system writes.
"""
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.hr import LocationManager
from app.domain.models.ops import (
    CustomerOrder,
    IdempotencyKey,
    InboundShipment,
    OrderLine,
    StockSnapshot,
    StockTransfer,
    StockTransferLine,
)
from app.domain.models.plan import PlanningRun, RouteMatrix
from app.domain.models.ref import Location, Market, MarketHoliday
from app.engine.transfer import suggest_transfers
from app.engine.types import WarehouseCtx
from app.services.planning_context import available_stock


def _error(code: str, message: str) -> DomainError:
    return DomainError(code, message)


def _roles(actor: object) -> tuple[str, ...]:
    return tuple(getattr(actor, "roles", ()))


def _user_id(actor: object) -> int:
    value = getattr(actor, "id", None)
    if not isinstance(value, int):
        raise _error("FORBIDDEN", "Authenticated user required.")
    return value


def _employee_id(actor: object) -> int:
    value = getattr(actor, "employee_id", None)
    if not isinstance(value, int):
        raise _error("FORBIDDEN", "An active employee assignment is required.")
    return value


async def _market(session: AsyncSession, actor: object) -> Market:
    code = getattr(actor, "market", None)
    if not code:
        raise _error("FORBIDDEN", "A market-scoped account is required.")
    market = await session.scalar(select(Market).where(Market.code == code))
    if market is None:
        raise _error("FORBIDDEN", "A market-scoped account is required.")
    return market


def _today(market: Market) -> date:
    return clock.now().astimezone(ZoneInfo(market.timezone)).date()


def _can_dispatch(actor: object) -> None:
    if "dispatcher" not in _roles(actor):
        raise _error("FORBIDDEN", "Dispatcher permission required.")


async def _order(session: AsyncSession, actor: object, order_id: int) -> tuple[CustomerOrder, Market]:
    _can_dispatch(actor)
    market = await _market(session, actor)
    order = await session.scalar(
        select(CustomerOrder).where(
            CustomerOrder.id == order_id, CustomerOrder.market_id == market.id
        )
    )
    if order is None:
        raise _error("NOT_FOUND", "Order not found.")
    return order, market


async def _transfer(
    session: AsyncSession, actor: object, transfer_id: int, *, lock: bool
) -> tuple[StockTransfer, Market]:
    market = await _market(session, actor)
    stmt = (
        select(StockTransfer)
        .join(Location, Location.id == StockTransfer.from_warehouse_id)
        .where(StockTransfer.id == transfer_id, Location.market_id == market.id)
    )
    if lock:
        stmt = stmt.with_for_update(of=StockTransfer)
    transfer = await session.scalar(stmt)
    if transfer is None:
        raise _error("NOT_FOUND", "Transfer not found.")
    dest = await session.scalar(
        select(Location).where(
            Location.id == transfer.to_warehouse_id, Location.market_id == market.id
        )
    )
    if dest is None:
        raise _error("NOT_FOUND", "Transfer not found.")
    return transfer, market


async def _manager(session: AsyncSession, actor: object, warehouse_id: int, market: Market) -> None:
    if "warehouse" not in _roles(actor):
        raise _error("FORBIDDEN", "Warehouse permission required.")
    if warehouse_id not in tuple(getattr(actor, "location_ids", ())):
        raise _error("FORBIDDEN", "Warehouse manager permission required.")
    today = _today(market)
    manager = await session.scalar(
        select(LocationManager.id)
        .where(
            LocationManager.location_id == warehouse_id,
            LocationManager.employee_id == _employee_id(actor),
            LocationManager.can_approve.is_(True),
            LocationManager.valid_from <= today,
            (LocationManager.valid_to.is_(None) | (LocationManager.valid_to >= today)),
        )
        .limit(1)
    )
    if manager is None:
        raise _error("FORBIDDEN", "An active manager with approval permission is required.")


def _digest(endpoint: str, body: dict[str, object]) -> str:
    raw = json.dumps(
        {"endpoint": endpoint, "body": body}, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _claim(
    session: AsyncSession, actor: object, endpoint: str, key: str, body: dict[str, object]
) -> tuple[IdempotencyKey, dict[str, object] | None]:
    # No client-supplied key may bypass a prior endpoint/body binding.
    if not 1 <= len(key) <= 200:
        raise _error("VALIDATION_ERROR", "Idempotency-Key is required.")
    digest = _digest(endpoint, body)
    await session.execute(
        insert(IdempotencyKey)
        .values(key=key, user_id=_user_id(actor), endpoint=endpoint, request_hash=digest)
        .on_conflict_do_nothing(index_elements=["key", "user_id"])
    )
    record = await session.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.key == key, IdempotencyKey.user_id == _user_id(actor))
        .with_for_update()
    )
    if record is None or record.endpoint != endpoint or record.request_hash != digest:
        raise _error("IDEMPOTENCY_CONFLICT", "Idempotency key belongs to another request.")
    if record.response_body is not None and record.response_status == 200:
        return record, dict(record.response_body)
    if record.response_status is not None:
        raise _error("IDEMPOTENCY_CONFLICT", "Earlier request cannot be replayed.")
    return record, None


def _save(record: IdempotencyKey, data: dict[str, object]) -> dict[str, object]:
    record.response_status = 200
    record.response_body = data
    return data


def _out(transfer: StockTransfer) -> dict[str, object]:
    return {
        "id": transfer.id,
        "order_id": transfer.order_id,
        "from_warehouse_id": transfer.from_warehouse_id,
        "to_warehouse_id": transfer.to_warehouse_id,
        "status": transfer.status,
        "lead_days": transfer.lead_days,
        "expected_arrival_date": (
            transfer.expected_arrival_date.isoformat() if transfer.expected_arrival_date else None
        ),
    }


def _working_day_arrival(start: date, days: int, working_days: set[int], holidays: set[date]) -> date:
    if days < 1 or not working_days:
        raise _error("VALIDATION_ERROR", "Missing valid transfer calendar configuration.")
    result = start
    for _ in range(days):
        while True:
            result += timedelta(days=1)
            if result.isoweekday() in working_days and result not in holidays:
                break
    return result


async def _arrival(session: AsyncSession, market: Market, lead_days: int) -> date:
    days = market.config.get("working_days", [1, 2, 3, 4, 5])
    if not isinstance(days, list) or any(type(d) is not int or d not in range(1, 8) for d in days):
        raise _error("PLAN_NOT_APPROVABLE", "Market working-day calendar unavailable.")
    today = _today(market)
    holidays = set(
        (await session.execute(select(MarketHoliday.holiday_date).where(
            MarketHoliday.market_id == market.id,
            MarketHoliday.holiday_date.between(today, today + timedelta(days=365)),
        ))).scalars().all()
    )
    return _working_day_arrival(today, lead_days, set(days), holidays)


async def suggestions(session: AsyncSession, actor: object, order_id: int) -> dict[str, object]:
    """Read-only: return at most three rule-based candidates, without guessing a route."""
    order, market = await _order(session, actor, order_id)
    if order.status != "NO_FEASIBLE_DATE":
        return {"items": []}
    last = await session.scalar(
        select(PlanningRun).where(PlanningRun.order_id == order.id)
        .order_by(PlanningRun.run_no.desc()).limit(1)
    )
    if last is None or last.failed_check != "stock":
        return {"items": []}
    lines = (await session.scalars(select(OrderLine).where(OrderLine.order_id == order.id))).all()
    if not lines or any(l.global_product_id is None or l.qty_base is None for l in lines):
        raise _error("PLAN_NOT_APPROVABLE", "Unverified order quantities; no transfer can be suggested.")
    need: dict[int, Decimal] = defaultdict(Decimal)
    for line in lines:
        assert line.global_product_id is not None and line.qty_base is not None
        need[line.global_product_id] += line.qty_base
    warehouses = (await session.scalars(
        select(Location).where(
            Location.market_id == market.id,
            Location.type == "warehouse",
            Location.is_active.is_(True),
        ).order_by(Location.id)
    )).all()
    if len(warehouses) < 2:
        return {"items": []}
    wh_ids = [w.id for w in warehouses]
    ids = sorted(need)
    snapshots = (await session.scalars(
        select(StockSnapshot).where(
            StockSnapshot.warehouse_id.in_(wh_ids),
            StockSnapshot.global_product_id.in_(ids),
        )
    )).all()
    # A missing/stale pair is unknown, not zero stock or an eligible source.
    cfg = market.config or {}
    stale_min = cfg.get("stale_stock_min", 15)
    if type(stale_min) is not int or stale_min <= 0:
        raise _error("PLAN_NOT_APPROVABLE", "Stock freshness configuration missing.")
    verified = {(s.warehouse_id, s.global_product_id) for s in snapshots
                if s.as_of >= clock.now() - timedelta(minutes=stale_min)}
    if any((w, p) not in verified for w in wh_ids for p in ids):
        raise _error("PLAN_NOT_APPROVABLE", "Verified market stock snapshots are incomplete or stale.")
    stock = await available_stock(session, wh_ids, ids, now=clock.now(), exclude_order_id=order.id)
    if any(all(stock[w][p] >= q for p, q in need.items()) for w in wh_ids):
        return {"items": []}  # a warehouse can already fulfil the complete order
    default_lead = cfg.get("transfer_lead_days_default", 1)
    if type(default_lead) is not int or default_lead < 1:
        raise _error("PLAN_NOT_APPROVABLE", "Transfer lead-time configuration unavailable.")
    paths = (await session.scalars(select(RouteMatrix).where(
        RouteMatrix.warehouse_id.in_(wh_ids)
    ))).all()
    routes = {(v.warehouse_id, v.to_lat, v.to_lon): v for v in paths}
    allow_fallback = (cfg.get("routing") or {}).get("allow_fallback", False)
    candidates: list[dict[str, object]] = []
    for dest in warehouses:
        shortage = {p: q - stock[dest.id][p] for p, q in need.items() if q > stock[dest.id][p]}
        if not shortage or dest.lat is None or dest.lon is None:
            continue
        distances: dict[tuple[int, int], Decimal] = {}
        sources: list[WarehouseCtx] = []
        for source in warehouses:
            if source.id == dest.id:
                continue
            if not all(stock[source.id][p] >= q for p, q in shortage.items()):
                continue
            path = routes.get((source.id, dest.lat, dest.lon))
            if path is None or (path.provider != "ors" and not allow_fallback):
                continue
            distances[(source.id, dest.id)] = path.distance_km
            sources.append(WarehouseCtx(
                id=source.id, name=source.name, cutoff=source.loading_cutoff_time or __import__("datetime").time(0),
                efficiency=source.efficiency_factor, stock_available=stock[source.id],
                inbound=(), capacity={}, vehicles=(), drivers=(), route=None,
            ))
        if not sources:
            continue
        target = WarehouseCtx(
            id=dest.id, name=dest.name, cutoff=dest.loading_cutoff_time or __import__("datetime").time(0),
            efficiency=dest.efficiency_factor, stock_available=stock[dest.id],
            inbound=(), capacity={}, vehicles=(), drivers=(), route=None,
        )
        for choice in suggest_transfers(target, shortage, sources, {}, distances, default_lead):
            candidates.append({
                "from_warehouse_id": choice.from_warehouse_id,
                "to_warehouse_id": choice.to_warehouse_id,
                "lead_days": choice.lead_days,
                "distance_km": str(choice.distance_km),
                "route_provenance": routes[(choice.from_warehouse_id, dest.lat, dest.lon)].provider,
                "lines": [{"global_product_id": p, "qty": str(q)} for p, q in choice.lines],
            })
    candidates.sort(key=lambda c: (c["lead_days"], Decimal(str(c["distance_km"])),
                                   c["from_warehouse_id"], c["to_warehouse_id"]))
    return {"items": candidates[:3]}


async def approve(
    session: AsyncSession, actor: object, order_id: int,
    payload: dict[str, object], idempotency_key: str
) -> dict[str, object]:
    """Approve exactly one freshly recomputed candidate, not arbitrary client stock."""
    order, market = await _order(session, actor, order_id)
    record, replay = await _claim(session, actor, f"POST /orders/{order_id}/transfers", idempotency_key, payload)
    if replay is not None:
        return replay
    # Serialize competing approvals for this order before reading current available stock.
    await session.execute(select(CustomerOrder.id).where(CustomerOrder.id == order.id).with_for_update())
    available = (await suggestions(session, actor, order_id))["items"]
    fields = ("from_warehouse_id", "to_warehouse_id", "lead_days", "lines")
    wanted = {k: payload.get(k) for k in fields}
    match = next((c for c in available if
                  c["from_warehouse_id"] == wanted["from_warehouse_id"]
                  and c["to_warehouse_id"] == wanted["to_warehouse_id"]
                  and c["lead_days"] == wanted["lead_days"]
                  and sorted((int(l["global_product_id"]), Decimal(str(l["qty"])))
                             for l in c["lines"]) ==
                      sorted((int(l["global_product_id"]), Decimal(str(l["qty"])))
                             for l in wanted["lines"] if isinstance(l, dict))
                  ), None) if isinstance(wanted["lines"], list) else None
    if match is None:
        raise _error("PLAN_NOT_APPROVABLE", "Transfer is not an eligible current suggestion.")
    lead = int(match["lead_days"])
    arrival = await _arrival(session, market, lead)
    transfer = StockTransfer(
        order_id=order.id, from_warehouse_id=int(match["from_warehouse_id"]),
        to_warehouse_id=int(match["to_warehouse_id"]), status="approved",
        lead_days=lead, expected_arrival_date=arrival,
        suggestion={"source": "rule_based", "route_provenance": match["route_provenance"],
                    "distance_km": match["distance_km"], "order_version": order.version},
        approved_by=_employee_id(actor), approved_at=clock.now(),
    )
    session.add(transfer)
    await session.flush()
    for line in match["lines"]:
        session.add(StockTransferLine(
            transfer_id=transfer.id, global_product_id=int(line["global_product_id"]),
            qty=Decimal(str(line["qty"])),
        ))
    await session.flush()
    await record_decision(session, Action.TRANSFER_APPROVED, "stock_transfer", str(transfer.id),
                          order_id=order.id, after=_out(transfer),
                          actor_user_id=_user_id(actor), actor_employee_id=_employee_id(actor),
                          actor_role="dispatcher")
    return _save(record, _out(transfer))


async def list_transfers(
    session: AsyncSession, actor: object, *,
    status: str | None = None, warehouse_id: int | None = None, page: int = 1, page_size: int = 50
) -> dict[str, object]:
    roles = _roles(actor)
    if "dispatcher" not in roles and "warehouse" not in roles:
        raise _error("FORBIDDEN", "Transfer access requires dispatcher or warehouse role.")
    market = await _market(session, actor)
    src = Location
    statement = select(StockTransfer).join(src, src.id == StockTransfer.from_warehouse_id).where(
        src.market_id == market.id,
    )
    if "dispatcher" not in roles:
        allowed = tuple(getattr(actor, "location_ids", ()))
        if not allowed:
            return {"items": [], "page": page, "page_size": page_size, "total": 0}
        if warehouse_id is not None and warehouse_id not in allowed:
            raise _error("NOT_FOUND", "Warehouse not found.")
        statement = statement.where(
            (StockTransfer.from_warehouse_id.in_(allowed)) |
            (StockTransfer.to_warehouse_id.in_(allowed))
        )
    if status is not None:
        if status not in ("suggested", "approved", "source_confirmed", "received", "cancelled"):
            raise _error("VALIDATION_ERROR", "Unknown transfer status.")
        statement = statement.where(StockTransfer.status == status)
    if warehouse_id is not None:
        statement = statement.where(
            (StockTransfer.from_warehouse_id == warehouse_id) |
            (StockTransfer.to_warehouse_id == warehouse_id)
        )
    total = int((await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )) or 0)
    rows = (await session.scalars(
        statement.order_by(StockTransfer.id.desc()).limit(page_size).offset((page - 1) * page_size)
    )).all()
    return {"items": [_out(row) for row in rows], "page": page, "page_size": page_size, "total": total}


async def confirm_source(
    session: AsyncSession, actor: object, transfer_id: int, idempotency_key: str
) -> dict[str, object]:
    transfer, market = await _transfer(session, actor, transfer_id, lock=False)
    await _manager(session, actor, transfer.from_warehouse_id, market)
    record, replay = await _claim(
        session, actor, f"POST /transfers/{transfer_id}/confirm-source", idempotency_key, {}
    )
    if replay is not None:
        return replay
    transfer, _ = await _transfer(session, actor, transfer_id, lock=True)
    if transfer.status != "approved" or transfer.expected_arrival_date is None:
        raise _error("ILLEGAL_TRANSITION", "Source confirmation requires an approved transfer.")
    lines = (await session.scalars(select(StockTransferLine)
              .where(StockTransferLine.transfer_id == transfer.id).order_by(StockTransferLine.global_product_id))).all()
    if not lines:
        raise _error("PLAN_NOT_APPROVABLE", "Transfer has no verified lines.")
    # Lock the stock resources in deterministic order to avoid confirming beyond available supply.
    for line in lines:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {
            "k": f"stock:{transfer.from_warehouse_id}:{line.global_product_id}"
        })
    stock = await available_stock(session, [transfer.from_warehouse_id],
                                  [line.global_product_id for line in lines],
                                  now=clock.now(), exclude_order_id=None)
    for line in lines:
        if stock[transfer.from_warehouse_id][line.global_product_id] < line.qty:
            raise _error("RESOURCE_CONFLICT", "Source warehouse no longer has sufficient stock.")
    for line in lines:
        session.add(InboundShipment(
            inbound_ref=f"TRANSFER-{transfer.id}", warehouse_id=transfer.to_warehouse_id,
            global_product_id=line.global_product_id, qty=line.qty,
            eta_date=transfer.expected_arrival_date, confirmed=True, received=False,
            source="transfer", transfer_id=transfer.id,
        ))
    transfer.status = "source_confirmed"
    transfer.source_confirmed_by = _employee_id(actor)
    transfer.source_confirmed_at = clock.now()
    await session.flush()
    await record_decision(session, Action.TRANSFER_CONFIRMED, "stock_transfer", str(transfer.id),
                          order_id=transfer.order_id, after=_out(transfer),
                          actor_user_id=_user_id(actor), actor_employee_id=_employee_id(actor),
                          actor_role="warehouse")
    return _save(record, _out(transfer))


async def receive(
    session: AsyncSession, actor: object, transfer_id: int, idempotency_key: str
) -> dict[str, object]:
    transfer, market = await _transfer(session, actor, transfer_id, lock=False)
    await _manager(session, actor, transfer.to_warehouse_id, market)
    record, replay = await _claim(
        session, actor, f"POST /transfers/{transfer_id}/receive", idempotency_key, {}
    )
    if replay is not None:
        return replay
    transfer, _ = await _transfer(session, actor, transfer_id, lock=True)
    if transfer.status != "source_confirmed":
        raise _error("ILLEGAL_TRANSITION", "Receiving requires a source-confirmed transfer.")
    lines = (await session.scalars(
        select(StockTransferLine).where(StockTransferLine.transfer_id == transfer.id)
    )).all()
    inbound = (await session.scalars(
        select(InboundShipment).where(
            InboundShipment.transfer_id == transfer.id, InboundShipment.source == "transfer",
            InboundShipment.confirmed.is_(True), InboundShipment.received.is_(False),
        ).with_for_update()
    )).all()
    if not lines or {(i.global_product_id, i.qty) for i in inbound} != {
        (l.global_product_id, l.qty) for l in lines
    }:
        raise _error("RESOURCE_CONFLICT", "Transfer inbound rows are missing or inconsistent.")
    for row in inbound:
        row.received = True
    transfer.status = "received"
    transfer.received_at = clock.now()
    await session.flush()
    # Approved codes include CONFIRMED but no separate receipt action; the status
    # transition is explicit in the audit payload; a dedicated code needs owner approval.
    await record_decision(session, Action.TRANSFER_CONFIRMED, "stock_transfer", str(transfer.id),
                          order_id=transfer.order_id,
                          snapshot={"stage": "warehouse_received"}, after=_out(transfer),
                          actor_user_id=_user_id(actor), actor_employee_id=_employee_id(actor),
                          actor_role="warehouse")
    return _save(record, _out(transfer))


async def cancel(
    session: AsyncSession, actor: object, transfer_id: int,
    reason_text: str, idempotency_key: str
) -> dict[str, object]:
    _can_dispatch(actor)
    transfer, _ = await _transfer(session, actor, transfer_id, lock=False)
    if not reason_text.strip():
        raise _error("REASON_REQUIRED", "Cancelling a transfer requires a reason.")
    record, replay = await _claim(
        session, actor, f"POST /transfers/{transfer_id}/cancel",
        idempotency_key, {"reason_text": reason_text}
    )
    if replay is not None:
        return replay
    transfer, _ = await _transfer(session, actor, transfer_id, lock=True)
    if transfer.status not in ("suggested", "approved"):
        raise _error("ILLEGAL_TRANSITION", "Confirmed or received transfers cannot be cancelled here.")
    before = _out(transfer)
    transfer.status = "cancelled"
    await session.flush()
    # No TRANSFER_CANCELLED action exists in the approved audit vocabulary. Do not
    # invent one; reuse the existing transfer decision action with explicit stage.
    await record_decision(session, Action.TRANSFER_APPROVED, "stock_transfer", str(transfer.id),
                          order_id=transfer.order_id, reason_text=reason_text,
                          snapshot={"stage": "cancelled"}, before=before, after=_out(transfer),
                          actor_user_id=_user_id(actor), actor_employee_id=_employee_id(actor),
                          actor_role="dispatcher")
    return _save(record, _out(transfer))
