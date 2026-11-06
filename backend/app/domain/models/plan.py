"""Model SQLAlchemy cho schema `plan` (docs/05).

Bảng: planning_run, fulfilment_plan, plan_vehicle, stock_reservation, prep_reservation,
vehicle_reservation, route_matrix.
Không đổi tên bảng/cột (09 mục 6).

- v1.2: một phương án có nhiều xe (`plan_vehicle`); `fulfilment_plan` không có vehicle_id/driver_employee_id.
- `planning_run.kind = 'replan_suggestion'` không tạo giữ chỗ (09 bất biến 21).
- Hàng/giờ công chỉ khóa khi DUYỆT (advisory lock); xe/tài xế có EXCLUDE ở DB (09 bất biến 11).
Owner: Dev 1 (luồng A) — M1.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSTZRANGE, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import TSTZ, Base, TimestampMixin, bigint_pk
from app.domain.models.types import PLAN_STATUS, RES_STATUS

SCHEMA = {"schema": "plan"}
EMPTY_JSON = text("'{}'")


class PlanningRun(TimestampMixin, Base):
    __tablename__ = "planning_run"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id"))
    order_version: Mapped[int] = mapped_column(Integer)
    run_no: Mapped[int] = mapped_column(Integer)
    triggered_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ref.app_user.id"))
    kind: Mapped[str] = mapped_column(Text, server_default=text("'initial'"))
    trigger: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=EMPTY_JSON)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[str] = mapped_column(Text)
    failed_check: Mapped[str | None] = mapped_column(Text)
    earliest_feasible_date: Mapped[date | None] = mapped_column(Date)
    planning_reserve_min: Mapped[int | None] = mapped_column(Integer)
    reserve_class: Mapped[str | None] = mapped_column(Text)
    hold_expires_at: Mapped[datetime | None] = mapped_column(TSTZ)
    hold_extensions: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class FulfilmentPlan(TimestampMixin, Base):
    __tablename__ = "fulfilment_plan"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.planning_run.id"))
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id"))
    rank: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(PLAN_STATUS, server_default=text("'proposed'"))
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    vehicle_count: Mapped[int] = mapped_column(SmallInteger)
    total_capacity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_capacity_m3: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    target_date: Mapped[date] = mapped_column(Date)
    goods_ready_at: Mapped[datetime] = mapped_column(TSTZ)
    loading_start_at: Mapped[datetime] = mapped_column(TSTZ)
    depart_at: Mapped[datetime] = mapped_column(TSTZ)
    eta_at: Mapped[datetime] = mapped_column(TSTZ)
    trip_end_at: Mapped[datetime] = mapped_column(TSTZ)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    drive_min: Mapped[int] = mapped_column(Integer)
    prep_hours: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    capacity_fill: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    complexity_points: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    planning_reserve_min: Mapped[int] = mapped_column(Integer)
    route_provenance: Mapped[str] = mapped_column(Text)
    workload: Mapped[Any] = mapped_column(JSONB)
    checks: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    explanation: Mapped[str] = mapped_column(Text)
    manual_reason_code: Mapped[str | None] = mapped_column(Text)
    manual_reason_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ref.app_user.id"))


class PlanVehicle(TimestampMixin, Base):
    __tablename__ = "plan_vehicle"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.fulfilment_plan.id"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.vehicle.id"))
    driver_employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr.employee.id"))
    load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    load_m3: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    load_lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    loading_start_at: Mapped[datetime] = mapped_column(TSTZ)
    depart_at: Mapped[datetime] = mapped_column(TSTZ)
    eta_at: Mapped[datetime] = mapped_column(TSTZ)
    trip_end_at: Mapped[datetime] = mapped_column(TSTZ)


class StockReservation(TimestampMixin, Base):
    __tablename__ = "stock_reservation"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.planning_run.id"))
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id"))
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    global_product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.product_global.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    status: Mapped[str] = mapped_column(RES_STATUS, server_default=text("'held'"))


class PrepReservation(TimestampMixin, Base):
    __tablename__ = "prep_reservation"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.planning_run.id"))
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id"))
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    work_date: Mapped[date] = mapped_column(Date)
    resource: Mapped[str] = mapped_column(Text, server_default=text("'labour'"))
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    status: Mapped[str] = mapped_column(RES_STATUS, server_default=text("'held'"))


class VehicleReservation(TimestampMixin, Base):
    """Xe/tài xế: EXCLUDE (order_id WITH <>) ở DB — cùng đơn được trùng, khác đơn thì không."""

    __tablename__ = "vehicle_reservation"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.planning_run.id"))
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.fulfilment_plan.id"))
    plan_vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.plan_vehicle.id"))
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id"))
    vehicle_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.vehicle.id"))
    driver_employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr.employee.id"))
    during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    status: Mapped[str] = mapped_column(RES_STATUS, server_default=text("'held'"))


class RouteMatrix(TimestampMixin, Base):
    """Tính trước; engine chỉ đọc (không gọi API trong engine — 09 mục 8)."""

    __tablename__ = "route_matrix"
    __table_args__ = SCHEMA

    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"), primary_key=True)
    to_lat: Mapped[Decimal] = mapped_column(Numeric(8, 5), primary_key=True)
    to_lon: Mapped[Decimal] = mapped_column(Numeric(8, 5), primary_key=True)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    duration_min: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
