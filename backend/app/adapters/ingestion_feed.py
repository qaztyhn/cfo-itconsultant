"""Typed, per-row rejection boundary over the approved read-only source feeds (T07)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from pydantic import AwareDatetime, TypeAdapter, ValidationError

from app.adapters.base import StockSnapshotDTO
from app.adapters.driver_wire import SourceDriverAvailability, SourceDriverEligibility
from app.adapters.order_wire import SourceCancellation, SourceOrder
from app.adapters.reference_wire import SourceCustomer, SourceFleet, SourceInbound, SourceProduct
from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError
from app.adapters.stock_batches import DeclaredUnit

type WireValue = (
    SourceOrder
    | SourceCancellation
    | SourceCustomer
    | SourceProduct
    | SourceInbound
    | SourceFleet
    | SourceDriverAvailability
    | SourceDriverEligibility
)

FEEDS: dict[str, tuple[str, type[WireValue], tuple[str, ...], dict[str, str]]] = {
    "orders": ("orders", SourceOrder, ("id",), {"status": "SUBMITTED_FOR_PLANNING"}),
    "orders:cancelled": ("orders", SourceCancellation, ("id",), {"status": "CANCELLED"}),
    "customers": ("customers", SourceCustomer, ("id",), {}),
    "products": ("products", SourceProduct, ("sku",), {}),
    "inbound": ("inbound", SourceInbound, ("inbound_ref", "warehouse_code", "sku"), {}),
    "driver-availability": ("fleet/driver-availability", SourceDriverAvailability, ("source_ref",), {}),
    "driver-eligibility": ("fleet/driver-eligibility", SourceDriverEligibility, ("source_ref",), {}),
    "fleet": ("fleet/calendar", SourceFleet, ("vehicle_code", "from", "to"), {}),
}


@dataclass(frozen=True)
class StockFeedValue:
    snapshot: StockSnapshotDTO
    declared: dict[str, DeclaredUnit]
    latest_catalog_time: datetime | None


type SourceValue = WireValue | StockFeedValue


@dataclass(frozen=True)
class FeedRecord:
    value: SourceValue | None
    updated_at: datetime | None
    external_key: str | None
    reject_code: str | None = None
    weight: int = 1


async def read_feed(
    adapter: RestMarketAdapter, entity: str, since: datetime | None
) -> AsyncIterator[FeedRecord]:
    if entity == "stock":
        snapshot = await adapter.fetch_stock()
        declared: dict[str, DeclaredUnit] = {}
        latest: datetime | None = None
        async for record in read_feed(adapter, "products", None):
            if not isinstance(record.value, SourceProduct) or record.updated_at is None:
                raise SourceReadError("Source stock unit catalogue is incomplete")
            product = record.value
            declared[product.sku] = DeclaredUnit(product.sale_unit, product.units_to_base)
            latest = max(latest, record.updated_at) if latest else record.updated_at
        if await adapter.fetch_stock() != snapshot:
            raise SourceReadError("Source stock batch changed during unit verification")
        yield FeedRecord(
            StockFeedValue(snapshot, declared, latest),
            snapshot.as_of,
            str(snapshot.batch_id),
            weight=len(snapshot.items),
        )
        return
    endpoint, model, keys, filters = FEEDS[entity]
    async for row in adapter.raw_pages(endpoint, since, key_fields=keys, filters=filters):
        try:
            stamp = TypeAdapter(AwareDatetime).validate_python(row.get("updated_at"))
        except ValueError:
            stamp = None
        key = row.get(keys[0])
        external_key = key if isinstance(key, str) and len(key) <= 200 else None
        try:
            value = model.model_validate(row)
        except ValidationError as error:
            fields = {str(part) for item in error.errors() for part in item["loc"]}
            reason = (
                "BAD_QTY"
                if fields & {"qty", "unit_price", "units_to_base"}
                else (
                    "MISSING_COORDS"
                    if fields & {"lat", "lon"}
                    else (
                        "BAD_DATE"
                        if stamp is None or fields & {"date_from", "date_to", "eta_date", "from", "to"}
                        else "INVALID_SOURCE_ROW"
                    )
                )
            )
            if fields & {"verified_at", "verified_by"}:
                reason = "DRIVER_NOT_VERIFIED"
            yield FeedRecord(None, stamp, external_key, reason)
        else:
            yield FeedRecord(value, stamp, external_key)
