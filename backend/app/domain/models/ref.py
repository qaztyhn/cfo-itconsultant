"""Model SQLAlchemy cho schema `ref` (docs/05).

Bảng: market, market_holiday, location, handling_group, special_flag, handling_group_rule, product_global,
product_se, mapping_task, vehicle, vehicle_availability, customer, app_user, compliance_record.
Không đổi tên bảng/cột (09 mục 6). View `ref.v_product_local` không ánh xạ (chỉ đọc bằng truy vấn).
Owner: Dev 1 (luồng A) — M1.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSTZRANGE, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import TSTZ, Base, TimestampMixin, bigint_pk, smallint_pk
from app.domain.models.types import (
    CUSTOMER_TYPE,
    LICENCE_CLASS,
    LOCATION_TYPE,
    MAPPING_STATUS,
    NOTIFY_CHANNEL,
    PREP_UNIT,
    TASK_STATUS,
    USER_ROLE,
)

EMPTY_ARRAY = text("'{}'")
SCHEMA = {"schema": "ref"}


class Market(TimestampMixin, Base):
    __tablename__ = "market"
    __table_args__ = SCHEMA

    id: Mapped[int] = smallint_pk()
    code: Mapped[str] = mapped_column(CHAR(2))
    name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, server_default=text("'en'"))
    currency: Mapped[str] = mapped_column(CHAR(3))
    gps_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    shadow_mode: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source_base_url: Mapped[str | None] = mapped_column(Text)
    source_api_key_ref: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class MarketHoliday(TimestampMixin, Base):
    __tablename__ = "market_holiday"
    __table_args__ = SCHEMA

    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"), primary_key=True)
    holiday_date: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(Text)


class Location(TimestampMixin, Base):
    __tablename__ = "location"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"))
    type: Mapped[str] = mapped_column(LOCATION_TYPE)
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    loading_cutoff_time: Mapped[time | None] = mapped_column(Time)
    efficiency_factor: Mapped[Decimal] = mapped_column(Numeric(4, 2), server_default=text("1.00"))
    owner_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hr.employee.id", name="fk_loc_owner")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class HandlingGroup(TimestampMixin, Base):
    __tablename__ = "handling_group"
    __table_args__ = SCHEMA

    id: Mapped[int] = smallint_pk()
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    prep_unit: Mapped[str] = mapped_column(PREP_UNIT)
    fixed_hours: Mapped[Decimal] = mapped_column(Numeric(6, 3), server_default=text("0"))
    labour_hours_per_unit: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    min_crew: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    vehicle_requirement: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)


class SpecialFlag(TimestampMixin, Base):
    __tablename__ = "special_flag"
    __table_args__ = SCHEMA

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2))


class HandlingGroupRule(TimestampMixin, Base):
    __tablename__ = "handling_group_rule"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    priority: Mapped[int] = mapped_column(SmallInteger, server_default=text("100"))
    category_like: Mapped[str] = mapped_column(Text)
    min_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    max_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    handling_group_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.handling_group.id"))
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)


class ProductGlobal(TimestampMixin, Base):
    __tablename__ = "product_global"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(Text)
    base_unit: Mapped[str] = mapped_column(Text)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    volume_m3: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    handling_group_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.handling_group.id"))
    base_units_per_prep_unit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hr.employee.id", name="fk_pg_creator")
    )


class ProductSE(TimestampMixin, Base):
    """Bảng sản phẩm riêng của Thụy Điển (05 mục 3); nước khác do tools/add_market.py sinh."""

    __tablename__ = "product_se"
    __table_args__ = SCHEMA

    local_sku: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(Text)
    sale_unit: Mapped[str] = mapped_column(Text)
    units_to_base: Mapped[Decimal] = mapped_column(Numeric(12, 4), server_default=text("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(CHAR(3), server_default=text("'SEK'"))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    volume_m3: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    global_product_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ref.product_global.id"))
    mapping_status: Mapped[str] = mapped_column(MAPPING_STATUS, server_default=text("'pending'"))
    mapped_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hr.employee.id", name="fk_pse_mapper")
    )
    mapped_at: Mapped[datetime | None] = mapped_column(TSTZ)
    source_updated_at: Mapped[datetime | None] = mapped_column(TSTZ)
    synced_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))


class MappingTask(TimestampMixin, Base):
    __tablename__ = "mapping_task"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"))
    local_sku: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(TASK_STATUS, server_default=text("'open'"))
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'"))
    blocked_order_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    assigned_to: Mapped[int | None] = mapped_column(BigInteger)
    resolved_by: Mapped[int | None] = mapped_column(BigInteger)
    resolved_at: Mapped[datetime | None] = mapped_column(TSTZ)


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicle"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    home_warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    code: Mapped[str] = mapped_column(Text)
    plate: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    capacity_m3: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)
    required_licence: Mapped[str] = mapped_column(LICENCE_CLASS)
    allowed_group_ids: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), server_default=EMPTY_ARRAY)
    status: Mapped[str] = mapped_column(Text, server_default=text("'available'"))
    max_permissible_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # Q12b (0009)
    regulation_561_scope: Mapped[str] = mapped_column(
        Text, server_default=text("'unknown'")
    )  # unknown → fail closed


class VehicleAvailability(TimestampMixin, Base):
    __tablename__ = "vehicle_availability"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.vehicle.id"))
    during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    kind: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, server_default=text("'fleet_calendar'"))


class Customer(TimestampMixin, Base):
    """Khách đồng bộ từ nguồn. name/email/phone là PII: không ghi log (09 bất biến 16)."""

    __tablename__ = "customer"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"))
    external_ref: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(CUSTOMER_TYPE)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    preferred_channel: Mapped[str] = mapped_column(NOTIFY_CHANNEL, server_default=text("'email'"))
    default_receiving_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_anonymised: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class AppUser(TimestampMixin, Base):
    """Tài khoản. password_hash không bao giờ trả ra API hay log (09 bất biến 25)."""

    __tablename__ = "app_user"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hr.employee.id", name="fk_user_emp")
    )
    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(ARRAY(USER_ROLE))
    kpi_scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(TSTZ)


class ComplianceRecord(TimestampMixin, Base):
    __tablename__ = "compliance_record"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"))
    type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    approved_on: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
