"""T07 reference upserts; caller owns transaction/savepoints and market/feed lease."""

import re
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.reference_wire import SourceCustomer, SourceFleet, SourceInbound, SourceProduct
from app.domain.models.ops import InboundShipment
from app.domain.models.ref import Customer, Location, Market, Vehicle, VehicleAvailability
from app.services.ingest_types import RowOutcome, RowRejected
from app.services.mapping_service import ensure_task


def exact(value: Decimal, precision: int, scale: int, *, positive: bool = False) -> Decimal:
    if (
        not value.is_finite()
        or value < 0
        or (positive and value == 0)
        or value >= Decimal(10) ** (precision - scale)
        or value != value.quantize(Decimal(10) ** -scale)
    ):
        raise RowRejected("BAD_QTY")
    return value


def product_table(code: str) -> str:
    if not re.fullmatch(r"[A-Z]{2}", code):
        raise RowRejected("INVALID_MARKET")
    return f"ref.product_{code.lower()}"


async def product_mapping(session: AsyncSession, market_id: int, sku: str) -> tuple[int, Decimal]:
    product = (
        await session.execute(
            text("""
        SELECT p.global_product_id, p.units_to_base, p.mapping_status
        FROM ref.v_product_local p JOIN ref.market m ON m.code=p.market_code
        WHERE m.id=:market AND p.local_sku=:sku
    """),
            {"market": market_id, "sku": sku},
        )
    ).one_or_none()
    if product is None:
        raise RowRejected("UNKNOWN_SKU")
    if product.mapping_status != "confirmed" or product.global_product_id is None:
        raise RowRejected("SKU_UNMAPPED")
    if not product.units_to_base.is_finite() or product.units_to_base <= 0:
        raise RowRejected("BAD_QTY")
    return product.global_product_id, product.units_to_base


async def customer(session: AsyncSession, market: Market, value: SourceCustomer) -> RowOutcome:
    if value.type not in {"business", "consumer"} or not value.name.strip():
        raise RowRejected("INVALID_SOURCE_ROW")
    row = await session.scalar(
        select(Customer)
        .where(Customer.market_id == market.id, Customer.external_ref == value.id)
        .with_for_update()
    )
    if row is not None and row.is_anonymised:
        raise RowRejected("CUSTOMER_ANONYMISED")
    data = {"type": value.type, "name": value.name, "email": value.email, "phone": value.phone}
    if row is None:
        session.add(Customer(market_id=market.id, external_ref=value.id, **data))
    else:
        for field, content in data.items():
            setattr(row, field, content)
    return RowOutcome(changed=True)


async def product(session: AsyncSession, market: Market, value: SourceProduct, now: datetime) -> RowOutcome:
    table = product_table(market.code)
    if value.category is None:
        raise RowRejected("INVALID_SOURCE_ROW")  # 05 requires category; never invent a category.
    exact(value.units_to_base, 12, 4, positive=True)
    exact(value.unit_price, 12, 2)
    for amount, scale in ((value.weight_kg, 3), (value.volume_m3, 4)):
        if amount is not None:
            exact(amount, 10, scale)
    current = (
        await session.execute(
            text(
                f"SELECT source_updated_at, mapping_status, units_to_base, sale_unit "
                f"FROM {table} WHERE local_sku=:sku FOR UPDATE"
            ),
            {"sku": value.sku},
        )
    ).one_or_none()
    if current and current.source_updated_at and value.updated_at <= current.source_updated_at:
        return RowOutcome()
    if current and (current.units_to_base != value.units_to_base or current.sale_unit != value.sale_unit):
        raise RowRejected("UNIT_CONVERSION_CHANGED")
    await session.execute(
        text(f"""
        INSERT INTO {table} (local_sku,name,category,gtin,sale_unit,units_to_base,unit_price,currency,
            weight_kg,volume_m3,source_updated_at,synced_at)
        VALUES (:sku,:name,:category,:gtin,:unit,:factor,:price,:currency,:weight,:volume,:updated,:now)
        ON CONFLICT (local_sku) DO UPDATE SET name=EXCLUDED.name,category=EXCLUDED.category,
            gtin=EXCLUDED.gtin,sale_unit=EXCLUDED.sale_unit,units_to_base=EXCLUDED.units_to_base,
            unit_price=EXCLUDED.unit_price,weight_kg=EXCLUDED.weight_kg,volume_m3=EXCLUDED.volume_m3,
            source_updated_at=EXCLUDED.source_updated_at,synced_at=EXCLUDED.synced_at
    """),
        {
            "sku": value.sku,
            "name": value.name,
            "category": value.category,
            "gtin": value.gtin,
            "unit": value.sale_unit,
            "factor": value.units_to_base,
            "price": value.unit_price,
            "currency": market.currency,
            "weight": value.weight_kg,
            "volume": value.volume_m3,
            "updated": value.updated_at,
            "now": now,
        },
    )
    if not current or current.mapping_status != "confirmed":
        await ensure_task(session, market.id, value.sku)
    return RowOutcome(changed=True)


async def inbound(session: AsyncSession, market: Market, value: SourceInbound, run_id: int) -> RowOutcome:
    warehouse = await session.scalar(
        select(Location.id).where(
            Location.market_id == market.id,
            Location.code == value.warehouse_code,
            Location.type == "warehouse",
            Location.is_active.is_(True),
        )
    )
    if warehouse is None:
        raise RowRejected("UNKNOWN_WAREHOUSE")
    product_id, factor = await product_mapping(session, market.id, value.sku)
    aliases = await session.scalar(
        text("""
        SELECT count(*) FROM ref.v_product_local p JOIN ref.market m ON m.code=p.market_code
        WHERE m.id=:market AND p.global_product_id=:product AND p.mapping_status='confirmed'
    """),
        {"market": market.id, "product": product_id},
    )
    if aliases != 1:
        raise RowRejected("SOURCE_KEY_COLLISION")  # Target has no local SKU provenance; never last-row-wins.
    qty = exact(exact(value.qty, 12, 3, positive=True) * factor, 12, 3, positive=True)
    # 05's target identity omits warehouse; refuse collisions rather than moving/merging inventory.
    row = await session.scalar(
        select(InboundShipment)
        .where(
            InboundShipment.inbound_ref == value.inbound_ref, InboundShipment.global_product_id == product_id
        )
        .with_for_update()
    )
    if row is not None and (row.source != "erp" or row.warehouse_id != warehouse):
        raise RowRejected("SOURCE_KEY_COLLISION")
    if row is None:
        row = InboundShipment(
            inbound_ref=value.inbound_ref, warehouse_id=warehouse, global_product_id=product_id, source="erp"
        )
        session.add(row)
        changed = True
    else:
        changed = (row.qty, row.eta_date, row.confirmed, row.received) != (
            qty,
            value.eta_date,
            value.confirmed,
            value.received,
        )
    row.qty, row.eta_date, row.confirmed, row.received, row.run_id = (
        qty,
        value.eta_date,
        value.confirmed,
        value.received,
        run_id,
    )
    return RowOutcome(changed=changed)


async def fleet(session: AsyncSession, market: Market, value: SourceFleet) -> RowOutcome:
    vehicle_id = await session.scalar(
        select(Vehicle.id)
        .join(Location, Location.id == Vehicle.home_warehouse_id)
        .where(Location.market_id == market.id, Vehicle.code == value.vehicle_code)
    )
    if vehicle_id is None:
        raise RowRejected("UNKNOWN_VEHICLE")
    if value.kind not in {"maintenance", "unavailable", "external_booking"}:
        raise RowRejected("INVALID_SOURCE_ROW")
    during = Range(value.start, value.end, bounds="[)")
    row = await session.scalar(
        select(VehicleAvailability)
        .where(
            VehicleAvailability.vehicle_id == vehicle_id,
            VehicleAvailability.source == "fleet_calendar",
            VehicleAvailability.during == during,
        )
        .with_for_update()
    )
    if row is None:
        session.add(
            VehicleAvailability(
                vehicle_id=vehicle_id, during=during, kind=value.kind, source="fleet_calendar"
            )
        )
        changed = True
    else:
        changed = row.kind != value.kind
        row.kind = value.kind
    return RowOutcome(changed=changed)
