"""T26 synthetic R3 inputs and historical reporting rows for a clean demo."""

import asyncio
import json
import os
import sys
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import AdapterRegistry
from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.domain.enums import OrderStatus
from app.domain.models.hr import (
    DispatcherStaff,
    DriverAvailability,
    DriverVehicleEligibility,
    Employee,
    WarehouseDayCapacity,
)
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan, PlanningRun
from app.domain.models.ref import AppUser, Customer, Location, Market, ProductGlobal, ProductSE
from app.domain.transitions import transition
from app.providers.route_cache import ensure_route
from app.providers.routing_ors import OrsRoutingProvider

VERSION = "t26-r3-v1"


async def report_order(
    session: AsyncSession,
    market: Market,
    locations: dict[str, Location],
    customer: Customer,
    dispatcher: AppUser,
    spec: list[str | None],
    zone: ZoneInfo,
) -> None:
    suffix, status, amount, store, warehouse = spec
    assert suffix and status and amount and store
    day = clock.now().astimezone(zone).date()
    arrival = datetime.combine(day, time(8), zone)
    order = CustomerOrder(
        market_id=market.id,
        external_ref=f"SE-2026-{suffix}",
        order_no=f"SE-2026-9{suffix[1:]}",
        customer_id=customer.id,
        contact_name="Synthetic report fixture",
        delivery_address="Synthetic report site",
        delivery_lat=locations["STO"].lat,
        delivery_lon=locations["STO"].lon,
        date_mode="exact",
        date_from=day,
        date_to=day,
        order_date=arrival - timedelta(days=1),
        submitted_at=arrival - timedelta(days=1),
        origin_store_id=locations[store].id,
        status=status if warehouse else "PLANNED",
        currency="SEK",
        total_amount=Decimal(amount),
        committed_date=day if warehouse else None,
        approved_at=arrival - timedelta(days=1) if warehouse else None,
        delivered_at=arrival if status == "DELIVERED" else None,
        promise_start=arrival if warehouse else None,
        promise_end=arrival + timedelta(hours=2) if warehouse else None,
    )
    session.add(order)
    await session.flush()
    if warehouse is None:
        reason = "T26 synthetic cancellation before approval"
        cancelled = await transition(session, order.id, OrderStatus.CANCELLED, "dispatcher", reason)
        assert cancelled.closed is not None
        await record_decision(
            session,
            Action.ORDER_CANCELLED,
            "order",
            str(order.id),
            order_id=order.id,
            reason_text=reason,
            before=cancelled.closed.before | {"status": "PLANNED"},
            after={"status": "CANCELLED"},
            actor_user_id=dispatcher.id,
            actor_employee_id=dispatcher.employee_id,
            actor_role="dispatcher",
        )
        return
    # Historical read-model fixture. Active orders still require real ApprovalService/ACK.
    run = PlanningRun(
        order_id=order.id, order_version=1, run_no=1, input_snapshot={"fixture": VERSION}, result="feasible"
    )
    session.add(run)
    await session.flush()
    plan = FulfilmentPlan(
        run_id=run.id,
        order_id=order.id,
        rank=1,
        status="approved",
        warehouse_id=locations[warehouse].id,
        vehicle_count=1,
        total_capacity_kg=6000,
        total_capacity_m3=40,
        target_date=day,
        goods_ready_at=arrival - timedelta(hours=1),
        loading_start_at=arrival - timedelta(minutes=45),
        depart_at=arrival - timedelta(minutes=30),
        eta_at=arrival,
        trip_end_at=arrival + timedelta(minutes=30),
        distance_km=20,
        drive_min=60,
        prep_hours=1,
        capacity_fill=Decimal("0.2"),
        score=1,
        score_breakdown={},
        planning_reserve_min=90,
        route_provenance="fallback",
        workload={},
        checks={},
        explanation="T26 synthetic reporting baseline",
    )
    session.add(plan)
    await session.flush()
    order.approved_plan_id = plan.id


async def seed(path: Path) -> dict[str, object]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    settings = get_settings()
    database = make_url(settings.database_url)
    if (
        settings.app_env != "test"
        or os.getenv("DEMO_DISPOSABLE") != "1"
        or fixture["version"] != VERSION
        or settings.app_now != fixture["app_now"]
        or database.host not in ("postgres", "127.0.0.1")
        or database.database != "cfo"
    ):
        raise ValueError("T26 disposable context required")
    clock.init_from_settings(settings.app_now)
    zone = ZoneInfo(fixture["timezone"])
    first = clock.now().astimezone(zone).date()
    days = [first + timedelta(days=offset) for offset in range(4)]
    try:
        async with get_sessionmaker()() as session, session.begin():
            market = (await session.scalars(select(Market).where(Market.code == fixture["market"]))).one()
            orders = await session.scalar(select(func.count(CustomerOrder.id)))
            if orders != 0 or market.timezone != zone.key:
                raise ValueError("T26 requires empty CFO orders and correct market timezone")
            locations = {
                row.code: row
                for row in (
                    await session.scalars(select(Location).where(Location.market_id == market.id))
                ).all()
            }
            for location in locations.values():
                if location.type == "warehouse":
                    location.is_active = location.code in fixture["warehouses"]
                elif location.type == "store":
                    location.is_active = location.code in fixture["stores"]
            employees = {
                row.employee_no: row.id
                for row in (
                    await session.scalars(select(Employee).where(Employee.market_id == market.id))
                ).all()
            }
            for code in fixture["warehouses"]:
                for day in days:
                    session.add(
                        WarehouseDayCapacity(
                            warehouse_id=locations[code].id,
                            work_date=day,
                            shift_code="AM",
                            start_time=time(6),
                            end_time=time(14),
                            headcount=7,
                            productive_hours=Decimal("7.00"),
                            confirmed_by=employees[f"DEMO-{code}-W00"],
                            confirmed_at=clock.now(),
                            change_reason=VERSION,
                        )
                    )
            dispatchers = ("DEMO-DISPATCHER", "DEMO-DISPATCHER-2", "DEMO-DISPATCHER-3")
            for employee_no in dispatchers:
                employee_id = employees[employee_no]
                member = await session.get(DispatcherStaff, employee_id)
                if member is None:
                    session.add(DispatcherStaff(employee_id=employee_id, in_rotation=True))
                else:
                    member.in_rotation = True
            for sku, volume in fixture["volume_m3_per_base"].items():
                product = (
                    await session.scalars(select(ProductGlobal).where(ProductGlobal.code == sku))
                ).one()
                local_product = await session.get(ProductSE, sku)
                if local_product is None:
                    raise ValueError(f"Missing demo SKU {sku}")
                product.volume_m3 = local_product.volume_m3 = Decimal(volume)
            customer = (
                await session.scalars(
                    select(Customer).where(
                        Customer.market_id == market.id, Customer.external_ref == "DEMO-C002"
                    )
                )
            ).one()
            dispatcher = (
                await session.scalars(select(AppUser).where(AppUser.email == "dispatcher@cfo.demo"))
            ).one()
            for spec in fixture["report_orders"]:
                await report_order(session, market, locations, customer, dispatcher, spec, zone)

            adapter = AdapterRegistry()
            adapter.configure(
                market.code,
                market.source_base_url,
                market.source_api_key_ref,
                market_timezone=market.timezone,
            )
            route_provider = OrsRoutingProvider("")
            source_cases = [fixture["main_external_ref"], *fixture["source_cases"]]
            for ref in source_cases:
                source = await adapter.get(market.code).fetch_order_for_sync(ref)
                if source is None or source.status != "SUBMITTED_FOR_PLANNING":
                    raise ValueError(f"Expected submitted Source case {ref}")
                for code in fixture["warehouses"]:
                    await ensure_route(
                        session,
                        locations[code].id,
                        Decimal(str(source.lat)),
                        Decimal(str(source.lon)),
                        route_provider,
                        now=clock.now(),
                    )
            main = await session.scalar(
                select(CustomerOrder.id).where(CustomerOrder.external_ref == fixture["main_external_ref"])
            )
            if main is not None:
                raise ValueError("Main order was already synced into CFO")
            driver_counts = []
            for model in (DriverAvailability, DriverVehicleEligibility):
                driver_counts.append(
                    await session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.source == "synthetic_demo", model.source_ref.startswith(f"{VERSION}:"))
                    )
                )
            if driver_counts != [
                fixture["driver_feed"]["days"] * len(fixture["driver_vehicle_pairs"]),
                len(fixture["driver_vehicle_pairs"]),
            ]:
                raise ValueError("T26 requires the full driver feed ingested from Source")
            return {
                "version": VERSION,
                "app_now": settings.app_now,
                "timezone": zone.key,
                "source_submitted_refs": sorted(source_cases),
                "main_present_in_cfo": False,
                "warehouses": {code: locations[code].id for code in fixture["warehouses"]},
                "stores": {code: locations[code].id for code in fixture["stores"]},
                "dispatchers": {number: employees[number] for number in dispatchers},
                "day_capacity_rows": len(days) * len(fixture["warehouses"]),
                "driver_availability_rows": driver_counts[0],
                "vehicle_eligibility_rows": driver_counts[1],
                "report_rows": len(fixture["report_orders"]),
            }
    finally:
        clock.set_now(None)
        await get_engine().dispose()


if __name__ == "__main__":
    try:
        result = asyncio.run(seed(Path(sys.argv[1])))
    except Exception:
        raise SystemExit(
            "BLOCKED: T26 CFO seed failed; verify a clean demo, T09 and the Source feed."
        ) from None
    print(json.dumps(result, sort_keys=True))
