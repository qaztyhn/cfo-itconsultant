"""Kiểu enum PostgreSQL (05 mục 2) cho model. `create_type=False`: kiểu do migration 0001 tạo.

Nhãn lấy từ `app.domain.enums` khi có (một nguồn cho mã Python); còn lại ghi nguyên văn 05.
Test drift so nhãn từng enum với `pg_enum` của DB.
"""

from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM

from app.domain import enums as E


def _enum(schema: str, name: str, values: type[StrEnum] | tuple[str, ...]) -> ENUM:
    labels = tuple(m.value for m in values) if isinstance(values, type) else values
    return ENUM(*labels, name=name, schema=schema, create_type=False)


# ref
LOCATION_TYPE = _enum("ref", "location_type", ("warehouse", "store", "dispatch_center", "head_office"))
USER_ROLE = _enum("ref", "user_role", E.UserRole)
MAPPING_STATUS = _enum("ref", "mapping_status", ("pending", "suggested", "confirmed", "rejected"))
LICENCE_CLASS = _enum("ref", "licence_class", ("B", "C", "CE"))
PREP_UNIT = _enum("ref", "prep_unit", E.PrepUnit)
CUSTOMER_TYPE = _enum("ref", "customer_type", ("business", "consumer"))
NOTIFY_CHANNEL = _enum("ref", "notify_channel", ("email", "sms_sim"))
TASK_STATUS = _enum("ref", "task_status", ("open", "in_progress", "done"))

# hr
EMPLOYMENT_TYPE = _enum("hr", "employment_type", ("full_time", "part_time", "temp", "contractor"))
EMPLOYEE_STATUS = _enum("hr", "employee_status", ("active", "on_leave", "terminated"))
WAREHOUSE_ROLE = _enum(
    "hr", "warehouse_role", ("manager", "deputy", "supervisor", "operator", "forklift_operator")
)
SALES_ROLE = _enum("hr", "sales_role", ("retail", "trade", "store_manager"))
ATTENDANCE_STATUS = _enum("hr", "attendance_status", ("planned", "present", "absent", "leave"))
ABSENCE_TYPE = _enum("hr", "absence_type", ("leave", "sick", "training"))
MANAGER_LEVEL = _enum("hr", "manager_level", ("primary", "deputy"))
