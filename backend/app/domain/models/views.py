"""View chỉ đọc (05 mục 3, 8): khai báo bằng MetaData RIÊNG để không lẫn với bảng.

- Không thuộc `Base.metadata` → autogenerate/test drift không coi view là bảng thiếu; không thể `create_all`.
- Chỉ dùng trong SELECT. View do migration tạo (0002, 0007); test so cột với information_schema.
- Doanh thu: hai góc nhìn store/warehouse không cộng với nhau; quyền xem qua `resolve_revenue_scope` (M8).
"""

from sqlalchemy import CHAR, BigInteger, Column, Date, MetaData, Numeric, SmallInteger, Table, Text

from app.domain.models.types import MAPPING_STATUS

VIEW_METADATA = MetaData()

v_product_local = Table(
    "v_product_local",
    VIEW_METADATA,
    Column("market_code", CHAR(2)),
    Column("local_sku", Text),
    Column("name", Text),
    Column("category", Text),
    Column("gtin", Text),
    Column("sale_unit", Text),
    Column("units_to_base", Numeric(12, 4)),
    Column("unit_price", Numeric(12, 2)),
    Column("currency", CHAR(3)),
    Column("global_product_id", BigInteger),
    Column("mapping_status", MAPPING_STATUS),
    schema="ref",
)

v_revenue_daily = Table(
    "v_revenue_daily",
    VIEW_METADATA,
    Column("market_id", SmallInteger),
    Column("day", Date),
    Column("store_id", BigInteger),
    Column("warehouse_id", BigInteger),
    Column("currency", CHAR(3)),
    Column("orders_delivered", BigInteger),
    Column("revenue_recognised", Numeric),
    schema="audit",
)

v_revenue_pending = Table(
    "v_revenue_pending",
    VIEW_METADATA,
    Column("market_id", SmallInteger),
    Column("day", Date),
    Column("store_id", BigInteger),
    Column("warehouse_id", BigInteger),
    Column("currency", CHAR(3)),
    Column("orders_pending", BigInteger),
    Column("revenue_booked", Numeric),
    schema="audit",
)
