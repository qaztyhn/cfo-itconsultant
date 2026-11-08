"""Source tables from docs/05 section 10 and line fields from docs/06 section 16.

The logical schema is translated to SOURCE_SCHEMA for each instance. POS
validation, ingestion and scenario seeds are separate M1 work.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema="source")
    type_annotation_map = {
        str: Text,
        Decimal: Numeric,
        datetime: DateTime(timezone=True),
    }


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Customer(Timestamps, Base):
    __tablename__ = "src_customer"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str | None]
    phone: Mapped[str | None]
    type: Mapped[str]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Address(Timestamps, Base):
    __tablename__ = "src_address"

    id: Mapped[str] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("source.src_customer.id"))
    address: Mapped[str]
    lat: Mapped[Decimal | None]
    lon: Mapped[Decimal | None]
    receiving_hours: Mapped[dict[str, list[list[str]]] | None] = mapped_column(JSONB)


class ReceivingCalendar(Timestamps, Base):
    __tablename__ = "src_receiving_calendar"
    __table_args__ = (CheckConstraint("id = 'instance'", name="ck_receiving_calendar_singleton"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    timezone: Mapped[str]
    valid_from: Mapped[date]
    valid_to: Mapped[date]
    working_days: Mapped[list[int]] = mapped_column(JSONB)
    holidays: Mapped[list[str]] = mapped_column(JSONB)


class Store(Timestamps, Base):
    __tablename__ = "src_store"
    code: Mapped[str] = mapped_column(primary_key=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Sales(Timestamps, Base):
    __tablename__ = "src_sales"
    code: Mapped[str] = mapped_column(primary_key=True)
    store_code: Mapped[str] = mapped_column(ForeignKey("source.src_store.code"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class Product(Timestamps, Base):
    __tablename__ = "src_product"

    sku: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str | None]
    gtin: Mapped[str | None]
    sale_unit: Mapped[str]
    units_to_base: Mapped[Decimal]
    unit_price: Mapped[Decimal]
    weight_kg: Mapped[Decimal]
    volume_m3: Mapped[Decimal]


class Stock(Timestamps, Base):
    __tablename__ = "src_stock"

    warehouse_code: Mapped[str] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("source.src_product.sku"), primary_key=True)
    on_hand: Mapped[Decimal]
    reserved: Mapped[Decimal]
    as_of: Mapped[datetime]
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("source.src_stock_snapshot_batch.id"))
    physical_stock_pool_id: Mapped[str | None]


class StockBatch(Timestamps, Base):
    __tablename__ = "src_stock_snapshot_batch"
    __table_args__ = (
        CheckConstraint("row_count >= 0", name="ck_stock_batch_count"),
        UniqueConstraint("source_instance", "as_of", name="ux_stock_batch_capture"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_instance: Mapped[str]
    as_of: Mapped[datetime]
    published_at: Mapped[datetime | None]
    complete: Mapped[bool] = mapped_column(server_default=text("false"))
    row_count: Mapped[int] = mapped_column(server_default=text("0"))
    content_hash: Mapped[str]


class Inbound(Timestamps, Base):
    __tablename__ = "src_inbound"

    inbound_ref: Mapped[str] = mapped_column(primary_key=True)
    warehouse_code: Mapped[str] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("source.src_product.sku"), primary_key=True)
    qty: Mapped[Decimal]
    eta_date: Mapped[date]
    confirmed: Mapped[bool]
    received: Mapped[bool]


class VehicleCalendar(Timestamps, Base):
    __tablename__ = "src_vehicle_calendar"

    vehicle_code: Mapped[str] = mapped_column(primary_key=True)
    from_ts: Mapped[datetime] = mapped_column(primary_key=True)
    to_ts: Mapped[datetime] = mapped_column(primary_key=True)
    kind: Mapped[str]


class Order(Timestamps, Base):
    __tablename__ = "src_order"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'VALIDATED', 'SUBMITTED_FOR_PLANNING', 'CANCELLED')",
            name="ck_src_order_status",
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[int]
    customer_id: Mapped[str] = mapped_column(ForeignKey("source.src_customer.id"))
    address_id: Mapped[str] = mapped_column(ForeignKey("source.src_address.id"))
    date_mode: Mapped[str]
    date_from: Mapped[date | None]
    date_to: Mapped[date | None]
    window_start: Mapped[time | None]
    window_end: Mapped[time | None]
    sales_code: Mapped[str | None]
    store_code: Mapped[str | None]
    status: Mapped[str]
    # SRC-Q1 (DEC-SRC-001): snapshots taken when the order is written, never overwritten by later changes to
    # the customer/address records. Nullable at the DB level so the additive upgrade keeps existing rows.
    address: Mapped[str | None]
    lat: Mapped[Decimal | None]
    lon: Mapped[Decimal | None]
    contact_name: Mapped[str | None]
    contact_phone: Mapped[str | None]
    contact_email: Mapped[str | None]
    receiving_restrictions: Mapped[str | None]
    special_requirements: Mapped[str | None]
    cancel_reason: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    cancelled_at: Mapped[datetime | None]


class OrderLine(Timestamps, Base):
    __tablename__ = "src_order_line"
    __table_args__ = (UniqueConstraint("order_id", "line_no", name="ux_src_order_line_number"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("source.src_order.id"))
    line_no: Mapped[int]
    sku: Mapped[str] = mapped_column(ForeignKey("source.src_product.sku"))
    qty: Mapped[Decimal]
    unit_price: Mapped[Decimal]


class CreateRequest(Timestamps, Base):
    __tablename__ = "src_create_request"
    key: Mapped[str] = mapped_column(primary_key=True)
    request_hash: Mapped[str]
    order_id: Mapped[str] = mapped_column(ForeignKey("source.src_order.id"))
