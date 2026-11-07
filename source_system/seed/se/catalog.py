"""Independent source catalogue fixtures (08 section 5.2, ASM-009).

Kept deployable without importing the CFO application. A cross-catalogue test
compares every source field with the CFO reference seed to detect divergence.
These values are reference fixtures, not quantitative scenario-order outcomes.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

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


@dataclass(frozen=True)
class CatalogProduct:
    sku: str
    name: str
    category: str
    gtin: str
    sale_unit: str
    units_to_base: Decimal
    unit_price: Decimal
    weight_kg: Decimal
    volume_m3: Decimal


def catalog_products() -> Iterator[CatalogProduct]:
    for group_no, (group, count) in enumerate(GROUP_COUNTS.items()):
        for index in range(1, count + 1):
            sku, name = EXAMPLES.get(
                (group, index), (f"SE-DEMO-{group}-{index:03d}", f"Demo {group} item {index}")
            )
            digits = f"200000{group_no:01d}{index:05d}"
            checksum = (-sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))) % 10
            unit = {"N3": "bag", "N4": "m3", "N5": "piece"}.get(group, "piece")
            weight = Decimal(25) if group == "N3" else Decimal(10)
            if sku == "448812":
                weight = Decimal("23.8")
            elif sku in ("88412", "SE-TIL-GRT-05"):
                weight = Decimal(5)
            yield CatalogProduct(
                sku,
                name,
                group,
                digits + str(checksum),
                unit,
                Decimal(1),
                Decimal(100 + index),
                weight,
                Decimal("0.1"),
            )
