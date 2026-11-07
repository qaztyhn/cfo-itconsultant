"""Model SQLAlchemy cho schema `hr` (docs/05).

Bảng: position, employee, employee_assignment, location_manager, warehouse_staff, sales_staff,
dispatcher_staff, driver_staff, cs_staff, shift_template, attendance, absence.
Không đổi tên bảng/cột (09 mục 6). Tên/email/điện thoại nhân viên không ghi log.
Owner: Dev 1 (luồng A) — M1.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Numeric, SmallInteger, Text, Time, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import TSTZ, Base, TimestampMixin, bigint_pk
from app.domain.models.types import (
    ABSENCE_TYPE,
    ATTENDANCE_STATUS,
    EMPLOYEE_STATUS,
    EMPLOYMENT_TYPE,
    LICENCE_CLASS,
    MANAGER_LEVEL,
    SALES_ROLE,
    USER_ROLE,
    WAREHOUSE_ROLE,
)

EMPTY_ARRAY = text("'{}'")
SCHEMA = {"schema": "hr"}


def _employee_fk() -> ForeignKey:
    return ForeignKey("hr.employee.id")


class Position(TimestampMixin, Base):
    __tablename__ = "position"
    __table_args__ = SCHEMA

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    grp: Mapped[str] = mapped_column(Text)
    default_roles: Mapped[list[str]] = mapped_column(ARRAY(USER_ROLE), server_default=EMPTY_ARRAY)
    default_kpi_scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)


class Employee(TimestampMixin, Base):
    __tablename__ = "employee"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"))
    employee_no: Mapped[str] = mapped_column(Text)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    work_email: Mapped[str | None] = mapped_column(Text)
    work_phone: Mapped[str | None] = mapped_column(Text)
    position_code: Mapped[str] = mapped_column(Text, ForeignKey("hr.position.code"))
    employment_type: Mapped[str] = mapped_column(EMPLOYMENT_TYPE, server_default=text("'full_time'"))
    weekly_hours: Mapped[Decimal] = mapped_column(Numeric(4, 1), server_default=text("40"))
    hire_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(EMPLOYEE_STATUS, server_default=text("'active'"))
    reports_to_employee_id: Mapped[int | None] = mapped_column(BigInteger, _employee_fk())
    is_anonymised: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class EmployeeAssignment(TimestampMixin, Base):
    """Một phân công hiệu lực/người: ux_one_active_assignment ở DB (09 bất biến 19)."""

    __tablename__ = "employee_assignment"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk())
    location_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class LocationManager(TimestampMixin, Base):
    """Một quản lý chính hiệu lực/nơi: ux_one_primary_manager ở DB (09 bất biến 19)."""

    __tablename__ = "location_manager"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    location_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk())
    level: Mapped[str] = mapped_column(MANAGER_LEVEL)
    can_approve: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class WarehouseStaff(TimestampMixin, Base):
    __tablename__ = "warehouse_staff"
    __table_args__ = SCHEMA

    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk(), primary_key=True)
    role: Mapped[str] = mapped_column(WAREHOUSE_ROLE)
    counts_in_capacity: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class SalesStaff(TimestampMixin, Base):
    __tablename__ = "sales_staff"
    __table_args__ = SCHEMA

    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk(), primary_key=True)
    role: Mapped[str] = mapped_column(SALES_ROLE)


class DispatcherStaff(TimestampMixin, Base):
    __tablename__ = "dispatcher_staff"
    __table_args__ = SCHEMA

    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk(), primary_key=True)
    can_send_delay_notice: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class DriverStaff(TimestampMixin, Base):
    __tablename__ = "driver_staff"
    __table_args__ = SCHEMA

    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk(), primary_key=True)
    home_warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    licence_class: Mapped[str] = mapped_column(LICENCE_CLASS)
    licence_expires_on: Mapped[date] = mapped_column(Date)
    adr: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class CsStaff(TimestampMixin, Base):
    __tablename__ = "cs_staff"
    __table_args__ = SCHEMA

    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk(), primary_key=True)
    team: Mapped[str | None] = mapped_column(Text)


class ShiftTemplate(TimestampMixin, Base):
    __tablename__ = "shift_template"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ref.location.id"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    useful_hours_per_staff: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    expected_staff: Mapped[int] = mapped_column(SmallInteger)


class Attendance(TimestampMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk())
    work_date: Mapped[date] = mapped_column(Date)
    shift_template_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("hr.shift_template.id"))
    status: Mapped[str] = mapped_column(ATTENDANCE_STATUS, server_default=text("'planned'"))
    recorded_by: Mapped[int | None] = mapped_column(BigInteger, _employee_fk())
    recorded_at: Mapped[datetime | None] = mapped_column(TSTZ)


class Absence(TimestampMixin, Base):
    __tablename__ = "absence"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    employee_id: Mapped[int] = mapped_column(BigInteger, _employee_fk())
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(ABSENCE_TYPE)
    approved: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    approved_by: Mapped[int | None] = mapped_column(BigInteger, _employee_fk())
