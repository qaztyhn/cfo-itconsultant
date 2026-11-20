"""T27 disposable-only GPS_NOTICE fixture for synthetic Driver Chrome acceptance.

This is NOT privacy/legal approval for real workers. No production access, no
customer data, no physical WMS stock modification, and no GPS history inserted.
"""

import argparse
import asyncio
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.domain.models.hr import DriverAvailability, EmployeeShiftSchedule
from app.domain.models.ops import CustomerOrder, DeliveryTrip, TripStop
from app.domain.models.ref import ComplianceRecord, Market

EXTERNAL_REF = "SE-2026-000249"
REFERENCE = "SYNTHETIC-T27-STEP8-NOT-LEGAL-SIGNOFF"


async def prepare(order_id: int, trip_id: int, plan_id: int) -> None:
    settings = get_settings()
    app_now = settings.app_now
    if (
        settings.app_env != "test"
        or os.environ.get("DEMO_DISPOSABLE") != "1"
        or os.environ.get("COMPOSE_PROJECT_NAME") != "cfo-demo-e004"
        or os.environ.get("DEMO_D7_FIXTURE_DIR") != "/srv/e0_04_d7/step8_dec02"
        or not app_now
    ):
        raise ValueError("T27 synthetic notice requires isolated E0-04 execution stack")
    instant = datetime.fromisoformat(app_now)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("A timezone-aware frozen API clock is required")
    local = instant.astimezone(ZoneInfo("Europe/Stockholm"))
    if (
        local.date() != date(2026, 12, 2)
        or not (6 <= local.hour < 14)
        or local.utcoffset().total_seconds() != 3600
    ):
        raise ValueError("GPS simulator may only be enabled in the reviewed synthetic driver shift")
    clock.init_from_settings(app_now)
    try:
        async with get_sessionmaker()() as session, session.begin():
            order = await session.get(CustomerOrder, order_id)
            trip = await session.get(DeliveryTrip, trip_id)
            market = await session.scalar(select(Market).where(Market.code == "SE").with_for_update())
            if (
                order is None
                or trip is None
                or market is None
                or order.external_ref != EXTERNAL_REF
                or order.market_id != market.id
                or order.approved_plan_id != plan_id
                or order.status != "LOADED"
                or trip.status != "loading"
                or not await session.scalar(
                    select(TripStop.id).where(
                        TripStop.trip_id == trip_id,
                        TripStop.order_id == order_id,
                        TripStop.status == "pending",
                    )
                )
            ):
                raise ValueError("T27 GPS fixture requires the exact LOADED approved Source order/trip")
            shift = await session.scalar(
                select(EmployeeShiftSchedule.id)
                .where(
                    EmployeeShiftSchedule.employee_id == trip.driver_employee_id,
                    EmployeeShiftSchedule.warehouse_id == trip.warehouse_id,
                    EmployeeShiftSchedule.work_date == local.date(),
                    EmployeeShiftSchedule.status == "scheduled",
                )
                .limit(1)
            )
            availability = await session.scalar(
                select(DriverAvailability.id)
                .where(
                    DriverAvailability.driver_employee_id == trip.driver_employee_id,
                    DriverAvailability.work_date == local.date(),
                    DriverAvailability.source == "synthetic_demo",
                    DriverAvailability.verified_by.is_not(None),
                    DriverAvailability.verified_at <= instant,
                    DriverAvailability.available_from <= instant,
                    DriverAvailability.available_to > instant,
                    DriverAvailability.superseded_at.is_(None),
                )
                .limit(1)
            )
            if shift is None or availability is None:
                raise ValueError("T12 official shift and synthetic Fleet availability must both be verified")
            if (
                await session.scalar(
                    select(ComplianceRecord.id)
                    .where(
                        ComplianceRecord.market_id == market.id,
                        ComplianceRecord.type == "GPS_NOTICE",
                        ComplianceRecord.status == "approved",
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ValueError("T27 requires fresh private synthetic GPS notice state")
            session.add(
                ComplianceRecord(
                    market_id=market.id,
                    type="GPS_NOTICE",
                    status="approved",
                    approved_on=local.date(),
                    reference=REFERENCE,
                    note="Synthetic-only fixture; no real worker GPS or legal signoff",
                )
            )
            market.gps_enabled = True
        print("T27 synthetic GPS opt-in fixture ready; verified T12 shift/Fleet; no real legal signoff")
    finally:
        clock.set_now(None)
        await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", type=int, required=True)
    parser.add_argument("--trip-id", type=int, required=True)
    parser.add_argument("--plan-id", type=int, required=True)
    args = parser.parse_args()
    if min(args.order_id, args.trip_id, args.plan_id) < 1:
        parser.error("Positive authoritative IDs required")
    asyncio.run(prepare(args.order_id, args.trip_id, args.plan_id))


if __name__ == "__main__":
    main()
