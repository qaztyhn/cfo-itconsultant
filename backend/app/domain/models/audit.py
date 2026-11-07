"""Model SQLAlchemy cho schema `audit` (docs/05).

Bảng: decision_log, improvement_log, kpi_baseline.
Không đổi tên bảng/cột (09 mục 6).

- `decision_log` CHỈ THÊM: ghi qua `app.audit.recorder.record_decision()` trong transaction nghiệp vụ;
  trigger `trg_decision_immutable` chặn UPDATE/DELETE (09 bất biến 13, 14). Model chỉ để đọc
  (GET /audit/decisions, M8).
- `audit.v_kpi_daily` chưa có DDL trong 05 → không ánh xạ (M8).
Owner: Dev 1 (luồng A) — M1.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import TSTZ, Base, TimestampMixin, bigint_pk

SCHEMA = {"schema": "audit"}


class DecisionLog(TimestampMixin, Base):
    __tablename__ = "decision_log"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    ts: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
    correlation_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True))
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ref.app_user.id"))
    actor_employee_id: Mapped[int | None] = mapped_column(BigInteger)  # 05: không có khóa ngoài
    actor_role: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[int | None] = mapped_column(BigInteger)
    plan_id: Mapped[int | None] = mapped_column(BigInteger)
    reason_code: Mapped[str | None] = mapped_column(Text)
    reason_text: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ImprovementLog(TimestampMixin, Base):
    """Một dòng cho mỗi lần giao đã đóng (theo trip_stop, v1.1)."""

    __tablename__ = "improvement_log"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id"))
    trip_stop_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ops.trip_stop.id"))
    actual_labour_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    labour_segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    group_hours_per_unit: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    warehouse_id: Mapped[int] = mapped_column(BigInteger)
    handling_groups: Mapped[list[str]] = mapped_column(ARRAY(Text))
    prep_planned_min: Mapped[int | None] = mapped_column(Integer)
    prep_actual_min: Mapped[int | None] = mapped_column(Integer)
    prep_error_min: Mapped[int | None] = mapped_column(Integer)
    eta_first: Mapped[datetime | None] = mapped_column(TSTZ)
    eta_last: Mapped[datetime | None] = mapped_column(TSTZ)
    delivered_at: Mapped[datetime | None] = mapped_column(TSTZ)
    eta_error_min: Mapped[int | None] = mapped_column(Integer)
    delay_reason: Mapped[str | None] = mapped_column(Text)
    was_manual: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    accepted_unchanged: Mapped[bool | None] = mapped_column(Boolean)
    order_mix: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    closed_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))


class KpiBaseline(TimestampMixin, Base):
    __tablename__ = "kpi_baseline"
    __table_args__ = SCHEMA

    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"), primary_key=True)
    metric: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    measured_on: Mapped[date] = mapped_column(Date)
