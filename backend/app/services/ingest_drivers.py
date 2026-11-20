"""Persist verified driver records and monotonic tombstones under the driver row lock."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.driver_wire import SourceDriverAvailability, SourceDriverEligibility
from app.core.config import get_settings
from app.domain.models.hr import DriverAvailability, DriverStaff, DriverVehicleEligibility, Employee
from app.domain.models.ref import Location, Market, Vehicle
from app.services.ingest_types import RowOutcome, RowRejected

DRIVER_FEEDS = ("driver-availability", "driver-eligibility")


async def apply(
    session: AsyncSession,
    market: Market,
    item: SourceDriverAvailability | SourceDriverEligibility,
    now: datetime,
) -> RowOutcome:
    if item.market is not None and item.market != market.code.strip():
        raise RowRejected("WRONG_MARKET")
    if item.verified_at > item.updated_at or item.verified_at > now:
        raise RowRejected("DRIVER_NOT_VERIFIED")
    if item.source == "synthetic_demo" and get_settings().app_env == "production":
        raise RowRejected("DRIVER_NOT_VERIFIED")
    driver_id = await session.scalar(
        select(DriverStaff.employee_id)
        .join(Employee, Employee.id == DriverStaff.employee_id)
        .where(Employee.market_id == market.id, Employee.employee_no == item.employee_no)
        .with_for_update(of=DriverStaff)
    )
    if driver_id is None:
        raise RowRejected("UNKNOWN_DRIVER")
    if isinstance(item, SourceDriverAvailability):
        return await _availability(session, driver_id, item, ZoneInfo(market.timezone))
    return await _eligibility(session, market.id, driver_id, item)


async def _availability(
    session: AsyncSession, driver_id: int, item: SourceDriverAvailability, zone: ZoneInfo
) -> RowOutcome:
    if (
        item.available_from >= item.available_to
        or item.available_from.astimezone(zone).date() != item.work_date
    ):
        raise RowRejected("BAD_DATE")
    row = await session.scalar(
        select(DriverAvailability).where(
            DriverAvailability.source == item.source, DriverAvailability.source_ref == item.source_ref
        )
    )
    if row is not None:
        if row.driver_employee_id != driver_id or row.work_date != item.work_date:
            raise RowRejected("INVALID_SOURCE_ROW")
        if row.superseded_at is not None or item.verified_at < row.verified_at:
            return RowOutcome()
        if item.superseded:
            row.superseded_at = item.updated_at
            return RowOutcome(changed=True)
        return RowOutcome(
            changed=_refresh(
                row,
                verified_at=item.verified_at,
                verified_by=item.verified_by,
                available_from=item.available_from,
                available_to=item.available_to,
                max_driving_min=item.max_driving_min,
            )
        )

    retired = item.updated_at if item.superseded else None
    latest = await session.scalar(
        select(DriverAvailability)
        .where(
            DriverAvailability.driver_employee_id == driver_id,
            DriverAvailability.work_date == item.work_date,
        )
        .order_by(
            DriverAvailability.verified_at.desc(),
            DriverAvailability.superseded_at.desc().nulls_first(),
            DriverAvailability.id.desc(),
        )
        .limit(1)
    )
    if latest is not None:
        # Use the Source feed order for equally verified active records. A known
        # or older revision cannot reactivate availability after a tombstone.
        older = item.verified_at < latest.verified_at or (
            item.verified_at == latest.verified_at
            and latest.superseded_at is not None
            and item.updated_at < latest.superseded_at
        )
        if older:
            retired = max(latest.verified_at, item.updated_at)
        elif latest.superseded_at is None and (not item.superseded or item.verified_at > latest.verified_at):
            latest.superseded_at = item.updated_at
            await session.flush()  # release the partial unique index before inserting its successor
    session.add(
        DriverAvailability(
            driver_employee_id=driver_id,
            work_date=item.work_date,
            source=item.source,
            source_ref=item.source_ref,
            verified_by=item.verified_by,
            verified_at=item.verified_at,
            available_from=item.available_from,
            available_to=item.available_to,
            max_driving_min=item.max_driving_min,
            superseded_at=retired,
        )
    )
    return RowOutcome(changed=True)


async def _eligibility(
    session: AsyncSession, market_id: int, driver_id: int, item: SourceDriverEligibility
) -> RowOutcome:
    if (item.vehicle_code is None) == (item.licence_class is None):
        raise RowRejected("INVALID_SOURCE_ROW")
    vehicle_id = None
    if item.vehicle_code is not None:
        vehicle_id = await session.scalar(
            select(Vehicle.id)
            .join(Location, Location.id == Vehicle.home_warehouse_id)
            .where(Location.market_id == market_id, Vehicle.code == item.vehicle_code)
        )
        if vehicle_id is None:
            raise RowRejected("UNKNOWN_VEHICLE")
    row = await session.scalar(
        select(DriverVehicleEligibility).where(
            DriverVehicleEligibility.source == item.source,
            DriverVehicleEligibility.source_ref == item.source_ref,
        )
    )
    if row is not None:
        if (row.driver_employee_id, row.vehicle_id, row.licence_class) != (
            driver_id,
            vehicle_id,
            item.licence_class,
        ):
            raise RowRejected("INVALID_SOURCE_ROW")
        if row.revoked_at is not None or item.verified_at < row.verified_at:
            return RowOutcome()
        if item.revoked:
            row.revoked_at = item.updated_at
            return RowOutcome(changed=True)
        return RowOutcome(
            changed=_refresh(
                row,
                verified_at=item.verified_at,
                verified_by=item.verified_by,
                verified_until=item.verified_until,
            )
        )
    session.add(
        DriverVehicleEligibility(
            driver_employee_id=driver_id,
            vehicle_id=vehicle_id,
            licence_class=item.licence_class,
            verified_until=item.verified_until,
            verified_by=item.verified_by,
            verified_at=item.verified_at,
            source=item.source,
            source_ref=item.source_ref,
            revoked_at=item.updated_at if item.revoked else None,
        )
    )
    return RowOutcome(changed=True)


def _refresh(
    row: DriverAvailability | DriverVehicleEligibility, *, verified_at: datetime, **fields: object
) -> bool:
    # A source_ref's evidence version is immutable. Reverification can update the same
    # identity with a newer verified_at; older overlap/retry pages cannot undo it.
    if verified_at <= row.verified_at:
        if verified_at == row.verified_at and any(getattr(row, k) != v for k, v in fields.items()):
            raise RowRejected("INVALID_SOURCE_ROW")
        return False
    row.verified_at = verified_at
    for name, value in fields.items():
        setattr(row, name, value)
    return True
