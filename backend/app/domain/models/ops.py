"""Model SQLAlchemy cho schema `ops` (docs/05).

Bảng: stock_snapshot, inbound_shipment, stock_transfer, stock_transfer_line, customer_order, order_line,
order_transition, date_negotiation, delivery_trip, trip_stop, milestone_event, proof_of_delivery,
eta_forecast, alert, notification, customer_contact_log, vehicle_position, idempotency_key.
Không đổi tên bảng/cột (09 mục 6).

- `customer_order.status` chỉ đổi qua `domain.transitions.transition()` (09 bất biến 12).
- `milestone_event` chỉ thêm (trigger chặn UPDATE/DELETE); POD theo `trip_stop_id`,
  không UPDATE POD cũ (bất biến 22).
- contact_*/delivery_address/recipient_name là PII của khách: không ghi log (bất biến 16).
- GPS (`vehicle_position`) chỉ dispatcher đọc, kiểm ở API (bất biến 4).
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import TSTZ, Base, TimestampMixin, bigint_pk
from app.domain.models.types import (
    DATE_MODE,
    EVENT_TYPE,
    NEGOTIATION_OUTCOME,
    NOTIF_STATUS,
    NOTIF_TEMPLATE,
    NOTIFY_CHANNEL,
    ORDER_STATUS,
    RISK_COLOR,
    RISK_STATUS,
    TRANSFER_STATUS,
    TRIP_STATUS,
    USER_ROLE,
)

SCHEMA = {"schema": "ops"}
EMPTY_JSON = text("'{}'")


def _fk(target: str, name: str | None = None) -> ForeignKey:
    return ForeignKey(target, name=name)


class StockSnapshot(TimestampMixin, Base):
    """Ảnh chụp ghi đè mỗi lần đồng bộ; KHÔNG `FOR UPDATE` trên bảng này (09 mục 5)."""

    __tablename__ = "stock_snapshot"
    __table_args__ = SCHEMA

    warehouse_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.location.id"), primary_key=True)
    global_product_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.product_global.id"), primary_key=True)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    wms_reserved: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default=text("0"))
    as_of: Mapped[datetime] = mapped_column(TSTZ)
    run_id: Mapped[int | None] = mapped_column(BigInteger, _fk("stg.sync_run.id"))


class InboundShipment(TimestampMixin, Base):
    __tablename__ = "inbound_shipment"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    inbound_ref: Mapped[str] = mapped_column(Text)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.location.id"))
    global_product_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.product_global.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    eta_date: Mapped[date] = mapped_column(Date)
    confirmed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    received: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source: Mapped[str] = mapped_column(Text, server_default=text("'erp'"))
    transfer_id: Mapped[int | None] = mapped_column(
        BigInteger, _fk("ops.stock_transfer.id", "fk_inb_transfer")
    )
    run_id: Mapped[int | None] = mapped_column(BigInteger, _fk("stg.sync_run.id"))


class StockTransfer(TimestampMixin, Base):
    __tablename__ = "stock_transfer"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int | None] = mapped_column(BigInteger)  # 05: không có khóa ngoài
    from_warehouse_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.location.id"))
    to_warehouse_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.location.id"))
    status: Mapped[str] = mapped_column(TRANSFER_STATUS, server_default=text("'suggested'"))
    lead_days: Mapped[int] = mapped_column(SmallInteger)
    expected_arrival_date: Mapped[date | None] = mapped_column(Date)
    suggestion: Mapped[dict[str, Any]] = mapped_column(JSONB)
    approved_by: Mapped[int | None] = mapped_column(BigInteger, _fk("hr.employee.id"))
    approved_at: Mapped[datetime | None] = mapped_column(TSTZ)
    source_confirmed_by: Mapped[int | None] = mapped_column(BigInteger, _fk("hr.employee.id"))
    source_confirmed_at: Mapped[datetime | None] = mapped_column(TSTZ)
    received_at: Mapped[datetime | None] = mapped_column(TSTZ)


class StockTransferLine(TimestampMixin, Base):
    __tablename__ = "stock_transfer_line"
    __table_args__ = SCHEMA

    transfer_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.stock_transfer.id"), primary_key=True)
    global_product_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.product_global.id"), primary_key=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class CustomerOrder(TimestampMixin, Base):
    __tablename__ = "customer_order"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_no: Mapped[str] = mapped_column(Text)
    market_id: Mapped[int] = mapped_column(SmallInteger, _fk("ref.market.id"))
    external_ref: Mapped[str] = mapped_column(Text)
    source_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    customer_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.customer.id"))
    contact_name: Mapped[str] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    delivery_address: Mapped[str] = mapped_column(Text)
    delivery_lat: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    delivery_lon: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    receiving_restrictions: Mapped[str | None] = mapped_column(Text)
    special_requirements: Mapped[str | None] = mapped_column(Text)
    date_mode: Mapped[str] = mapped_column(DATE_MODE)
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    window_start: Mapped[time | None] = mapped_column(Time)
    window_end: Mapped[time | None] = mapped_column(Time)
    order_date: Mapped[datetime] = mapped_column(TSTZ)
    sales_employee_id: Mapped[int | None] = mapped_column(BigInteger, _fk("hr.employee.id"))
    origin_store_id: Mapped[int | None] = mapped_column(BigInteger, _fk("ref.location.id"))
    status: Mapped[str] = mapped_column(ORDER_STATUS, server_default=text("'SUBMITTED'"))
    block_reason: Mapped[str | None] = mapped_column(Text)
    committed_date: Mapped[date | None] = mapped_column(Date)
    promise_start: Mapped[datetime | None] = mapped_column(TSTZ)
    promise_end: Mapped[datetime | None] = mapped_column(TSTZ)
    # Phụ thuộc vòng với plan.fulfilment_plan.order_id → use_alter (khóa ngoài thêm sau, như 0006).
    approved_plan_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plan.fulfilment_plan.id", name="fk_order_plan", use_alter=True)
    )
    currency: Mapped[str] = mapped_column(CHAR(3))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default=text("0"))
    submitted_at: Mapped[datetime] = mapped_column(TSTZ)
    planned_at: Mapped[datetime | None] = mapped_column(TSTZ)
    approved_at: Mapped[datetime | None] = mapped_column(TSTZ)
    delivered_at: Mapped[datetime | None] = mapped_column(TSTZ)
    closed_at: Mapped[datetime | None] = mapped_column(TSTZ)


class OrderLine(TimestampMixin, Base):
    __tablename__ = "order_line"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(SmallInteger)
    local_sku: Mapped[str] = mapped_column(Text)
    global_product_id: Mapped[int | None] = mapped_column(BigInteger, _fk("ref.product_global.id"))
    qty_sale: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    qty_base: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class OrderTransition(TimestampMixin, Base):
    """Bảng tra chuyển trạng thái (seed 0008); allowed_roles rỗng = hệ thống (ASM-002)."""

    __tablename__ = "order_transition"
    __table_args__ = SCHEMA

    from_status: Mapped[str] = mapped_column(ORDER_STATUS, primary_key=True)
    to_status: Mapped[str] = mapped_column(ORDER_STATUS, primary_key=True)
    requires_reason: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    allowed_roles: Mapped[list[str]] = mapped_column(ARRAY(USER_ROLE))


class DateNegotiation(TimestampMixin, Base):
    __tablename__ = "date_negotiation"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    proposed_date: Mapped[date] = mapped_column(Date)
    outcome: Mapped[str] = mapped_column(NEGOTIATION_OUTCOME)
    channel: Mapped[str] = mapped_column(Text)
    contacted_at: Mapped[datetime] = mapped_column(TSTZ)
    recorded_by: Mapped[int] = mapped_column(BigInteger, _fk("hr.employee.id"))
    note: Mapped[str | None] = mapped_column(Text)
    remind_at: Mapped[datetime | None] = mapped_column(TSTZ)


class DeliveryTrip(TimestampMixin, Base):
    __tablename__ = "delivery_trip"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    plan_vehicle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plan.plan_vehicle.id", name="fk_trip_plan_vehicle", use_alter=True)
    )
    warehouse_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.location.id"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.vehicle.id"))
    driver_employee_id: Mapped[int] = mapped_column(BigInteger, _fk("hr.employee.id"))
    status: Mapped[str] = mapped_column(TRIP_STATUS, server_default=text("'planned'"))
    depart_planned_at: Mapped[datetime] = mapped_column(TSTZ)
    depart_actual_at: Mapped[datetime | None] = mapped_column(TSTZ)
    ended_at: Mapped[datetime | None] = mapped_column(TSTZ)


class TripStop(TimestampMixin, Base):
    __tablename__ = "trip_stop"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    trip_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.delivery_trip.id"))
    seq: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    order_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    eta_planned_at: Mapped[datetime] = mapped_column(TSTZ)
    arrived_at: Mapped[datetime | None] = mapped_column(TSTZ)
    completed_at: Mapped[datetime | None] = mapped_column(TSTZ)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))


class MilestoneEvent(TimestampMixin, Base):
    """Chỉ thêm (trigger trg_event_immutable)."""

    __tablename__ = "milestone_event"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    plan_id: Mapped[int | None] = mapped_column(BigInteger)  # 05: không có khóa ngoài
    trip_id: Mapped[int | None] = mapped_column(BigInteger, _fk("ops.delivery_trip.id"))
    event_type: Mapped[str] = mapped_column(EVENT_TYPE)
    occurred_at: Mapped[datetime] = mapped_column(TSTZ)
    received_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
    actor_user_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.app_user.id"))
    actor_employee_id: Mapped[int | None] = mapped_column(BigInteger, _fk("hr.employee.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=EMPTY_JSON)
    idempotency_key: Mapped[str] = mapped_column(Text)


class ProofOfDelivery(TimestampMixin, Base):
    """Một bản ghi cho mỗi lần giao (trip_stop); không UPDATE POD cũ (09 bất biến 22)."""

    __tablename__ = "proof_of_delivery"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    trip_stop_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.trip_stop.id"))
    order_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    result: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(TSTZ)
    recipient_name: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)


class EtaForecast(TimestampMixin, Base):
    __tablename__ = "eta_forecast"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    version: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
    trigger: Mapped[str] = mapped_column(Text)
    planned_eta: Mapped[datetime] = mapped_column(TSTZ)
    forecast_eta: Mapped[datetime] = mapped_column(TSTZ)
    commitment_deadline: Mapped[datetime] = mapped_column(TSTZ)
    reserve_total_min: Mapped[int] = mapped_column(Integer)
    slack_min: Mapped[int] = mapped_column(Integer)
    consumption_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    consecutive_negative: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    risk_status: Mapped[str] = mapped_column(RISK_STATUS)
    risk_color: Mapped[str] = mapped_column(RISK_COLOR)


class Alert(TimestampMixin, Base):
    __tablename__ = "alert"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int | None] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    market_id: Mapped[int] = mapped_column(SmallInteger, _fk("ref.market.id"))
    level: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    target_roles: Mapped[list[str]] = mapped_column(ARRAY(USER_ROLE))
    dedupe_key: Mapped[str] = mapped_column(Text)
    acknowledged_by: Mapped[int | None] = mapped_column(BigInteger, _fk("hr.employee.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(TSTZ)
    resolved_at: Mapped[datetime | None] = mapped_column(TSTZ)


class Notification(TimestampMixin, Base):
    __tablename__ = "notification"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    template: Mapped[str] = mapped_column(NOTIF_TEMPLATE)
    channel: Mapped[str] = mapped_column(NOTIFY_CHANNEL)
    recipient: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    eta_window: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(NOTIF_STATUS, server_default=text("'queued'"))
    scheduled_for: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(TSTZ)
    created_by_employee_id: Mapped[int | None] = mapped_column(BigInteger, _fk("hr.employee.id"))
    suppressed_reason: Mapped[str | None] = mapped_column(Text)
    plan_id: Mapped[int | None] = mapped_column(BigInteger)  # 05: không có khóa ngoài
    dedupe_key: Mapped[str] = mapped_column(Text)


class CustomerContactLog(TimestampMixin, Base):
    __tablename__ = "customer_contact_log"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int | None] = mapped_column(BigInteger, _fk("ops.customer_order.id"))
    customer_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.customer.id"))
    employee_id: Mapped[int] = mapped_column(BigInteger, _fk("hr.employee.id"))
    channel: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    contacted_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))


class VehiclePosition(TimestampMixin, Base):
    """GPS: chỉ dispatcher đọc (09 bất biến 4); xóa sau retention_days."""

    __tablename__ = "vehicle_position"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    trip_id: Mapped[int] = mapped_column(BigInteger, _fk("ops.delivery_trip.id"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.vehicle.id"))
    lat: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    lon: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    recorded_at: Mapped[datetime] = mapped_column(TSTZ)
    received_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
    source: Mapped[str] = mapped_column(Text)


class IdempotencyKey(TimestampMixin, Base):
    __tablename__ = "idempotency_key"
    __table_args__ = SCHEMA

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.app_user.id"), primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class OrderRouting(TimestampMixin, Base):
    """Quyết định luồng cfo/legacy của đơn nguồn (Q14, 0009); không đổi; 'unresolved' không lưu."""

    __tablename__ = "order_routing"
    __table_args__ = SCHEMA

    market_id: Mapped[int] = mapped_column(SmallInteger, _fk("ref.market.id"), primary_key=True)
    external_ref: Mapped[str] = mapped_column(Text, primary_key=True)
    route: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(Text)
    unmapped_skus: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    decided_at: Mapped[datetime] = mapped_column(TSTZ)
    decided_source_version: Mapped[int] = mapped_column(Integer)
    decided_by_user_id: Mapped[int] = mapped_column(BigInteger, _fk("ref.app_user.id"))  # 0011
    decided_by_role: Mapped[str] = mapped_column(Text)  # 0011: sales | dispatcher (không có "system")
    reason_text: Mapped[str | None] = mapped_column(Text)  # 0011: bắt buộc khi reason_code = manual_started
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(BigInteger, _fk("ref.app_user.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(TSTZ)
