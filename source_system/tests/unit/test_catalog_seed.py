from collections import Counter
from decimal import Decimal

from seed.se.catalog import catalog_products


def test_US_SRC_01_AC1_catalogue_has_documented_skus_units_and_valid_unique_gtins() -> None:
    products = tuple(catalog_products())
    assert products == tuple(catalog_products())
    assert len({p.sku for p in products}) == len(products) == 100
    assert Counter(p.category for p in products) == {
        "N1": 25,
        "N2": 20,
        "N3": 20,
        "N4": 8,
        "N5": 15,
        "N6": 12,
    }
    assert len({p.gtin for p in products}) == 100
    for product in products:
        assert len(product.gtin) == 13 and product.gtin.isascii() and product.gtin.isdigit()
        assert sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(product.gtin)) % 10 == 0
        assert product.units_to_base > 0 and product.unit_price > 0
    indexed = {p.sku: p for p in products}
    assert indexed["448812"].weight_kg == Decimal("23.8")
    assert indexed["88412"].weight_kg == Decimal(5)
    assert "449130" in indexed
    assert indexed["SE-CEM-MOR-25"].sale_unit == "bag"
    assert all(p.sale_unit == "m3" for p in products if p.category == "N4")
