"""T07 polling applies versions only to explicitly routed CFO orders (DEC-ROUTING-002).

First CFO acceptance/creation belongs to authorized Sync & check, not this polling worker.
Approved data/commitments stay unchanged; fresh-source suggestion uses a trusted T14 handoff.
"""

from datetime import time
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.order_wire import SourceCancellation, SourceOrder
from app.domain.models.ops import CustomerOrder, OrderLine, OrderRouting
from app.domain.models.plan import (
    FulfilmentPlan,
    PlanningRun,
    PrepReservation,
    StockReservation,
    VehicleReservation,
)
from app.domain.models.ref import Customer, Location, Market
from app.services.alert_service import raise_alert
from app.services.ingest_references import exact, product_mapping
from app.services.ingest_types import ReplanSource, RowOutcome, RowRejected

PRE_DISPATCH = {"APPROVED", "PREPARING", "GOODS_READY", "LOADED"}
PROTECTED = PRE_DISPATCH | {"DISPATCHED", "DELIVERED", "FAILED", "CANCELLED"}


async def _valid_suggestion(
    session: AsyncSession, order: CustomerOrder, source: SourceOrder, run: PlanningRun | None
) -> bool:
    if (
        run is None
        or run.order_id != order.id
        or run.order_version != order.version
        or run.kind != "replan_suggestion"
        or run.hold_expires_at is not None
        or run.params.get("source_version") != source.version
    ):
        return False
    for model in (StockReservation, PrepReservation, VehicleReservation):
        if await session.scalar(select(model.id).where(model.run_id == run.id).limit(1)) is not None:
            return False
    return (
        await session.scalar(
            select(FulfilmentPlan.id)
            .where(FulfilmentPlan.run_id == run.id, FulfilmentPlan.status != "proposed")
            .limit(1)
        )
        is None
    )


async def _suggest(
    session: AsyncSession, order: CustomerOrder, source: SourceOrder, handler: ReplanSource | None
) -> RowOutcome:
    previous = await session.scalar(
        select(PlanningRun).where(
            PlanningRun.order_id == order.id,
            PlanningRun.order_version == order.version,
            PlanningRun.kind == "replan_suggestion",
            PlanningRun.params["source_version"].as_string() == str(source.version),
        )
    )
    if previous is not None and await _valid_suggestion(session, order, source, previous):
        return RowOutcome()
    if handler is None:
        return RowOutcome("REPLAN_DEPENDENCY_UNAVAILABLE")
    # T14 owns five-gate context, old commitments added back, audit and suggestion alert.
    # An inner savepoint prevents a failed handoff losing the source-change warning.
    try:
        async with session.begin_nested():
            baseline = {col.name: getattr(order, col.name) for col in CustomerOrder.__table__.columns}
            old_lines = (
                await session.execute(
                    select(OrderLine.__table__).where(OrderLine.order_id == order.id).order_by(OrderLine.id)
                )
            ).all()
            run_id = await handler(session, order, source)
            await session.flush()
            await session.refresh(order)
            run = await session.get(PlanningRun, run_id) if run_id is not None else None
            new_lines = (
                await session.execute(
                    select(OrderLine.__table__).where(OrderLine.order_id == order.id).order_by(OrderLine.id)
                )
            ).all()
            if (
                not await _valid_suggestion(session, order, source, run)
                or old_lines != new_lines
                or baseline != {col.name: getattr(order, col.name) for col in CustomerOrder.__table__.columns}
            ):
                raise RowRejected("INVALID_REPLAN_HANDOFF")
    except Exception:
        return RowOutcome("REPLAN_DEPENDENCY_UNAVAILABLE")
    return RowOutcome()


async def apply(
    session: AsyncSession,
    market: Market,
    source: SourceOrder | SourceCancellation,
    *,
    replan: ReplanSource | None = None,
) -> RowOutcome:
    routing = await session.get(OrderRouting, (market.id, source.id), with_for_update=True)
    if routing is None:
        return RowOutcome("ROUTING_UNRESOLVED")
    if routing.route == "legacy":
        return RowOutcome()  # Mapping changes never move a legacy order into CFO.
    order = await session.scalar(
        select(CustomerOrder)
        .where(CustomerOrder.market_id == market.id, CustomerOrder.external_ref == source.id)
        .with_for_update()
    )
    if order is None:
        return RowOutcome("CFO_ORDER_NOT_INITIALIZED")
    if source.version <= order.source_version:
        return RowOutcome()
    if order.status in PROTECTED:
        await raise_alert(
            session,
            market_id=market.id,
            type_="ORDER_CHANGED_AFTER_APPROVAL",
            level="warning",
            message="A newer source version requires dispatcher review; approved delivery data is unchanged.",
            dedupe_key=f"SOURCE_CHANGE:{order.id}:{source.version}",
            target_roles=("dispatcher",),
            order_id=order.id,
        )
        if isinstance(source, SourceOrder) and order.status in PRE_DISPATCH:
            return await _suggest(session, order, source, replan)
        return RowOutcome()  # Source cancellation/post-dispatch is alert-only, never a new delivery.
    if isinstance(source, SourceCancellation):
        # No system SUBMITTED/PLANNED -> CANCELLED transition is approved. Do not impersonate Dispatcher.
        return RowOutcome("CANCEL_TRANSITION_REQUIRES_REVIEW")
    if order.status != "SUBMITTED":
        return RowOutcome("ORDER_STATE_LOCKED")
    customer_id = await session.scalar(
        select(Customer.id).where(
            Customer.market_id == market.id,
            Customer.external_ref == source.customer_id,
            Customer.is_anonymised.is_(False),
        )
    )
    store = await session.scalar(
        select(Location.id).where(
            Location.market_id == market.id,
            Location.code == source.store_code,
            Location.type == "store",
            Location.is_active.is_(True),
        )
    )
    if customer_id is None:
        raise RowRejected("UNKNOWN_CUSTOMER")
    if store is None or (order.origin_store_id is not None and store != order.origin_store_id):
        raise RowRejected("UNKNOWN_STORE")
    # Changing Sales attribution also needs the scoped Sync & check handoff; never guess employee identity.
    if source.sales_code is not None:
        from app.domain.models.hr import Employee

        sales = await session.scalar(
            select(Employee.employee_no).where(
                Employee.id == order.sales_employee_id, Employee.market_id == market.id
            )
        )
        if sales != source.sales_code:
            raise RowRejected("UNKNOWN_SALES_EMPLOYEE")
    if len({line.sku for line in source.lines}) != len(source.lines):
        raise RowRejected("DUPLICATE_SOURCE_SKU")  # 05 also uniquely keys (order_id,local_sku).
    lines: list[OrderLine] = []
    for line in source.lines:
        if line.line_no > 32767:
            raise RowRejected("INVALID_SOURCE_ROW")
        product_id, factor = await product_mapping(session, market.id, line.sku)
        qty = exact(line.qty, 12, 3, positive=True)
        price = exact(line.unit_price, 12, 2)
        total = exact((qty * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), 14, 2)
        lines.append(
            OrderLine(
                order_id=order.id,
                line_no=line.line_no,
                local_sku=line.sku,
                global_product_id=product_id,
                qty_sale=qty,
                qty_base=exact(qty * factor, 12, 3, positive=True),
                unit_price=price,
                line_total=total,
            )
        )
    amount = exact(sum((line.line_total for line in lines), Decimal(0)), 14, 2)
    await session.execute(delete(OrderLine).where(OrderLine.order_id == order.id))
    session.add_all(lines)
    order.customer_id, order.origin_store_id = customer_id, store
    order.contact_name, order.contact_phone, order.contact_email = (
        source.contact.name,
        source.contact.phone,
        source.contact.email,
    )
    order.delivery_address = source.address
    order.delivery_lat, order.delivery_lon = Decimal(str(source.lat)), Decimal(str(source.lon))
    order.receiving_restrictions, order.special_requirements = (
        source.receiving_restrictions,
        source.special_requirements,
    )
    end = source.date_to or source.date_from
    assert end is not None  # SourceOrder validates exact/range/latest shape.
    order.date_mode, order.date_from, order.date_to = source.date_mode, source.date_from, end
    order.window_start = time.fromisoformat(source.window_start) if source.window_start else None
    order.window_end = time.fromisoformat(source.window_end) if source.window_end else None
    order.total_amount = amount
    order.source_version, order.version = source.version, order.version + 1
    return RowOutcome(changed=True)
