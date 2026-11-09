"""Transactional, explicit Source -> CFO routing acceptance (DEC-ROUTING-002).

Called ONLY with a freshly fetched, validated SourceOrder from Dev 2's authenticated
market adapter. This service never reads/writes POS or WMS, polls, plans, or approves.
The HTTP/adapter boundary remains Dev 2-owned. Caller owns the DB transaction.
"""

import hashlib
import json
from datetime import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.order_wire import SourceOrder
from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.hr import Employee
from app.domain.models.ops import CustomerOrder, IdempotencyKey, OrderLine, OrderRouting
from app.domain.models.ref import Customer, Location, Market
from app.services import ingest_orders
from app.services.ingest_references import exact
from app.services.ingest_types import RowRejected

_ENDPOINT = "POST /integration/orders/sync-now"
_MAPPING = text("""
SELECT p.local_sku, p.global_product_id, p.mapping_status, p.units_to_base
FROM ref.v_product_local p JOIN ref.market m ON m.code = p.market_code
WHERE m.id = :market AND p.local_sku = ANY(:skus)
""")


class RoutingActor(Protocol):
    id: int
    employee_id: int | None
    roles: tuple[str, ...]
    market: str
    location_ids: tuple[int, ...]


def _role(actor: RoutingActor) -> str:
    if "sales" in actor.roles:
        return "sales"
    if "dispatcher" in actor.roles:
        return "dispatcher"
    raise DomainError("FORBIDDEN", "Only authorised Sales or Dispatcher can check routing.")


def _hash(external_ref: str) -> str:
    raw = json.dumps({"external_ref": external_ref}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


async def _claim(
    session: AsyncSession, actor: RoutingActor, external_ref: str, key: str
) -> tuple[IdempotencyKey, dict[str, object] | None]:
    if not isinstance(key, str) or not 1 <= len(key) <= 200:
        raise DomainError("VALIDATION_ERROR", "Idempotency-Key is required.")
    digest = _hash(external_ref)
    await session.execute(
        insert(IdempotencyKey)
        .values(key=key, user_id=actor.id, endpoint=_ENDPOINT, request_hash=digest)
        .on_conflict_do_nothing(index_elements=["key", "user_id"])
    )
    saved = await session.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.key == key, IdempotencyKey.user_id == actor.id)
        .with_for_update()
    )
    if saved is None or saved.endpoint != _ENDPOINT or saved.request_hash != digest:
        raise DomainError("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts with another request.")
    if saved.response_status == 200 and saved.response_body is not None:
        return saved, dict(saved.response_body)
    if saved.response_status is not None:
        raise DomainError("IDEMPOTENCY_CONFLICT", "The prior request cannot be replayed.")
    return saved, None


def _result(
    source: SourceOrder,
    route: str,
    order_id: int | None,
    *,
    already_decided: bool,
    sync_status: str,
    source_version: int | None = None,
) -> dict[str, object]:
    return {
        "order_id": order_id,
        "external_ref": source.id,
        "source_version": source.version if source_version is None else source_version,
        "routing_status": route,
        "sync_status": sync_status,
        "already_decided": already_decided,
    }


async def accept_source_order(
    session: AsyncSession,
    actor: RoutingActor,
    source: SourceOrder,
    idempotency_key: str,
) -> dict[str, object]:
    """Atomically route and initialise a submitted Source order, never a pending legacy order.

    Source freshness and API authentication MUST be established by Dev 2 before this call.
    The function serializes all routing attempts per (market, external_ref). Caller must
    commit or roll back this transaction, including the routing audit and order.
    """
    role = _role(actor)
    market = await session.scalar(select(Market).where(Market.code == actor.market))
    if market is None:
        raise DomainError("NOT_FOUND", "Market is not available.")
    # A caller must never route data returned by a different market adapter.
    if source.status != "SUBMITTED_FOR_PLANNING":
        raise DomainError("NOT_FOUND", "Submitted source order is not available.")
    store = await session.scalar(
        select(Location).where(
            Location.market_id == market.id,
            Location.code == source.store_code,
            Location.type == "store",
            Location.is_active.is_(True),
        )
    )
    if store is None or (role == "sales" and store.id not in actor.location_ids):
        raise DomainError("NOT_FOUND", "Submitted source order is not available.")

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"source-route:{market.id}:{source.id}"},
    )
    claimed, replay = await _claim(session, actor, source.id, idempotency_key)
    if replay is not None:
        return replay

    routing = await session.get(OrderRouting, (market.id, source.id), with_for_update=True)
    existing = await session.scalar(
        select(CustomerOrder)
        .where(
            CustomerOrder.market_id == market.id,
            CustomerOrder.external_ref == source.id,
        )
        .with_for_update()
    )
    if routing is not None:
        if source.version < routing.decided_source_version:
            raise DomainError(
                "RESOURCE_CONFLICT",
                "Source version predates the immutable routing decision.",
            )
        if routing.route == "legacy":
            if existing is not None:
                raise DomainError("RESOURCE_CONFLICT", "Legacy route has an unexpected CFO order.")
            answer = _result(
                source,
                "legacy",
                None,
                already_decided=True,
                sync_status="already_current",
            )
        else:
            if existing is None:
                raise DomainError(
                    "RESOURCE_CONFLICT",
                    "CFO routing exists but order is not initialised.",
                )
            if source.version > existing.source_version:
                outcome = await ingest_orders.apply(session, market, source)
                if outcome.reject_code is not None:
                    raise DomainError("RESOURCE_CONFLICT", "Newer Source version needs review.")
            if existing.source_version < source.version:
                # Protected orders are alert-only; never claim that changed Source data was applied.
                answer = _result(
                    source,
                    "cfo",
                    existing.id,
                    already_decided=True,
                    sync_status="unresolved",
                    source_version=existing.source_version,
                )
            else:
                answer = _result(
                    source,
                    "cfo",
                    existing.id,
                    already_decided=True,
                    sync_status="already_current",
                    source_version=existing.source_version,
                )
        if answer["sync_status"] != "unresolved":
            claimed.response_status, claimed.response_body = 200, answer
        return answer
    if existing is not None:
        raise DomainError("RESOURCE_CONFLICT", "Order exists without a routing decision.")

    if len({ln.sku for ln in source.lines}) != len(source.lines) or any(
        ln.line_no > 32767 for ln in source.lines
    ):
        raise DomainError("VALIDATION_ERROR", "Source order lines have invalid identities.")
    skus = [ln.sku for ln in source.lines]
    rows = (await session.execute(_MAPPING, {"market": market.id, "skus": skus})).all()
    mapping = {r.local_sku: r for r in rows}
    # Missing reference data is *unresolved*, not a permanent legacy decision.
    if any(sku not in mapping for sku in skus):
        return _result(source, "unresolved", None, already_decided=False, sync_status="unresolved")
    unmapped = sorted(sku for sku in skus if mapping[sku].mapping_status != "confirmed")
    if not unmapped and any(
        mapping[sku].global_product_id is None
        or mapping[sku].units_to_base is None
        or not mapping[sku].units_to_base.is_finite()
        or mapping[sku].units_to_base <= 0
        for sku in skus
    ):
        return _result(source, "unresolved", None, already_decided=False, sync_status="unresolved")

    customer_id: int | None = None
    sales_employee_id: int | None = None
    if not unmapped:
        customer_id = await session.scalar(
            select(Customer.id).where(
                Customer.market_id == market.id,
                Customer.external_ref == source.customer_id,
                Customer.is_anonymised.is_(False),
            )
        )
        if source.sales_code:
            sales_employee_id = await session.scalar(
                select(Employee.id).where(
                    Employee.market_id == market.id,
                    Employee.employee_no == source.sales_code,
                    Employee.status == "active",
                )
            )
        if customer_id is None or (source.sales_code and sales_employee_id is None):
            return _result(
                source,
                "unresolved",
                None,
                already_decided=False,
                sync_status="unresolved",
            )

    now = clock.now()
    route = "legacy" if unmapped else "cfo"
    session.add(
        OrderRouting(
            market_id=market.id,
            external_ref=source.id,
            route=route,
            reason_code="unmapped_sku" if unmapped else "all_confirmed",
            unmapped_skus=unmapped,
            decided_at=now,
            decided_source_version=source.version,
            decided_by_user_id=actor.id,
            decided_by_role=role,
        )
    )
    order_id: int | None = None
    if route == "cfo":
        try:
            lines = []
            for ln in source.lines:
                factor = mapping[ln.sku].units_to_base
                qty = exact(ln.qty, 12, 3, positive=True)
                price = exact(ln.unit_price, 12, 2)
                amount = exact(
                    (qty * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    14,
                    2,
                )
                lines.append((ln, qty, price, exact(qty * factor, 12, 3, positive=True), amount))
            total = exact(sum((item[4] for item in lines), Decimal("0")), 14, 2)
        except RowRejected as exc:
            raise DomainError("VALIDATION_ERROR", "Invalid Source quantity or units.") from exc
        date_to = source.date_to or source.date_from
        if date_to is None:
            raise DomainError("VALIDATION_ERROR", "Invalid Source delivery date.")
        order = CustomerOrder(
            order_no=f"pending:{market.id}:{source.id}",
            market_id=market.id,
            external_ref=source.id,
            source_version=source.version,
            version=1,
            customer_id=customer_id,
            contact_name=source.contact.name,
            contact_phone=source.contact.phone,
            contact_email=source.contact.email,
            delivery_address=source.address,
            delivery_lat=Decimal(str(source.lat)),
            delivery_lon=Decimal(str(source.lon)),
            receiving_restrictions=source.receiving_restrictions,
            special_requirements=source.special_requirements,
            date_mode=source.date_mode,
            date_from=source.date_from,
            date_to=date_to,
            window_start=(time.fromisoformat(source.window_start) if source.window_start else None),
            window_end=(time.fromisoformat(source.window_end) if source.window_end else None),
            # Source D1 has updated_at but no original submitted_at; this is the best
            # available Source event timestamp, NOT certified original POS FIFO evidence.
            order_date=source.updated_at,
            submitted_at=source.updated_at,
            sales_employee_id=sales_employee_id,
            origin_store_id=store.id,
            currency=market.currency,
            total_amount=total,
        )
        session.add(order)
        await session.flush()
        order.order_no = f"{market.code}-{source.updated_at.year}-{order.id:06d}"
        session.add_all(
            [
                OrderLine(
                    order_id=order.id,
                    line_no=ln.line_no,
                    local_sku=ln.sku,
                    global_product_id=mapping[ln.sku].global_product_id,
                    qty_sale=qty,
                    qty_base=qty_base,
                    unit_price=price,
                    line_total=amount,
                )
                for ln, qty, price, qty_base, amount in lines
            ]
        )
        order_id = order.id
    await record_decision(
        session,
        Action.ROUTING_DECIDED,
        "order_routing",
        source.id,
        order_id=order_id,
        actor_user_id=actor.id,
        actor_employee_id=actor.employee_id,
        actor_role=role,
        after={
            "route": route,
            "source_version": source.version,
            "unmapped_sku_count": len(unmapped),
        },
    )
    answer = _result(source, route, order_id, already_decided=False, sync_status="synced")
    claimed.response_status, claimed.response_body = 200, answer
    return answer
