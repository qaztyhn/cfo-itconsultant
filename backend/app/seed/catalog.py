"""Synthetic catalogue reference subset, 08 section 5.2; no orders or business outcomes."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.hr import Employee
from app.domain.models.ref import HandlingGroup, Market, ProductGlobal, ProductSE

GROUP_COUNTS = {"N1": 25, "N2": 20, "N3": 20, "N4": 8, "N5": 15, "N6": 12}
EXAMPLES = {
    ("N1", 1): ("SE-PNT-INT-10", "Interior wall paint 10 L"),
    ("N2", 1): ("SE-BRD-GYP-13", "Gypsum board 13 x 900 x 2500"),
    ("N2", 2): ("SE-TIL-POR-60", "Porcelain tile 60x60 grey"),
    ("N2", 20): ("448812", "Gipsskiva GN13 900x2700"),
    ("N3", 1): ("SE-CEM-MOR-25", "Cement mortar 25 kg"),
    ("N3", 2): ("SE-TIL-ADH-25", "Tile adhesive C2TE 25 kg"),
    ("N3", 3): ("SE-TIL-GRT-05", "Tile grout 5 kg"),
    ("N3", 20): ("88412", "Fogbruk gra 5 kg"),
    ("N5", 1): ("SE-TMB-C24-4895", "C24 timber 45x95 4.8 m"),
    ("N5", 15): ("449130", "Trall 28x120 impregnerad 4.2 m"),
}
PENDING = {"448812", "88412", "449130"}


async def seed_catalog(session: AsyncSession, *, now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError("Catalogue seed timestamp must be timezone-aware")
    mapper = (
        await session.scalars(
            select(Employee.id)
            .join(Market, Market.id == Employee.market_id)
            .where(Employee.employee_no == "DEMO-ADMIN", Market.code == "SE")
        )
    ).one()
    groups = {g.code: g.id for g in (await session.scalars(select(HandlingGroup))).all()}
    for group, count in GROUP_COUNTS.items():
        for index in range(1, count + 1):
            sku, name = EXAMPLES.get(
                (group, index),
                (f"SE-DEMO-{group}-{index:03d}", f"Demo {group} item {index}"),
            )
            if await session.get(ProductSE, sku) is not None:
                continue
            unit = {"N3": "bag", "N4": "m3", "N5": "piece"}.get(group, "piece")
            # Private synthetic range; GTIN check digit, no real product identities.
            digits = f"200000{list(GROUP_COUNTS).index(group):01d}{index:05d}"
            checksum = (-sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))) % 10
            gtin = digits + str(checksum)
            weight = Decimal("25") if group == "N3" else Decimal("10")
            if sku == "448812":
                weight = Decimal("23.8")
            elif sku in ("88412", "SE-TIL-GRT-05"):
                weight = Decimal(5)
            global_id = None
            if sku not in PENDING:
                product = (
                    await session.scalars(select(ProductGlobal).where(ProductGlobal.code == sku))
                ).one_or_none()
                if product is None:
                    product = ProductGlobal(
                        code=sku,
                        name=name,
                        category=group,
                        gtin=gtin,
                        base_unit=unit,
                        weight_kg=weight,
                        volume_m3=Decimal("0.1"),
                        handling_group_id=groups[group],
                        base_units_per_prep_unit=(Decimal(40) if group in ("N2", "N3") else None),
                        flags=["HAZARDOUS"] if sku == "SE-PNT-INT-10" else [],
                        created_by=mapper,
                    )
                    session.add(product)
                    await session.flush()
                global_id = product.id
            session.add(
                ProductSE(
                    local_sku=sku,
                    name=name,
                    category=group,
                    gtin=gtin,
                    sale_unit=unit,
                    units_to_base=Decimal(1),
                    unit_price=Decimal(100 + index),
                    weight_kg=weight,
                    volume_m3=Decimal("0.1"),
                    global_product_id=global_id,
                    mapping_status="pending" if sku in PENDING else "confirmed",
                    mapped_by=None if sku in PENDING else mapper,
                    mapped_at=None if sku in PENDING else now,
                    source_updated_at=now,
                    synced_at=now,
                )
            )
