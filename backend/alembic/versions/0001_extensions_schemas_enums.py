"""0001_extensions_schemas_enums

Extension pgcrypto/btree_gist/pg_trgm, 6 schema, mọi enum (05 mục 2; v1.2: không có
MANUAL_PLANNING/HANDLED_EXTERNALLY; event PREP_PAUSED/PREP_RESUMED).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0001"
down_revision = None

EXTENSIONS = ("pgcrypto", "btree_gist", "pg_trgm")
SCHEMAS = ("ref", "hr", "stg", "ops", "plan", "audit")

# (schema.tên, nhãn) — sao chép NGUYÊN VĂN 05 mục 2, giữ đúng thứ tự nhãn.
ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # ref
    ("ref.location_type", ("warehouse", "store", "dispatch_center", "head_office")),
    ("ref.user_role", ("admin", "dispatcher", "warehouse", "sales", "driver", "customer_service", "viewer")),
    ("ref.mapping_status", ("pending", "suggested", "confirmed", "rejected")),
    ("ref.licence_class", ("B", "C", "CE")),
    ("ref.prep_unit", ("line", "pallet", "m3", "bundle", "package")),
    ("ref.customer_type", ("business", "consumer")),
    ("ref.notify_channel", ("email", "sms_sim")),
    ("ref.task_status", ("open", "in_progress", "done")),
    # hr
    ("hr.employment_type", ("full_time", "part_time", "temp", "contractor")),
    ("hr.employee_status", ("active", "on_leave", "terminated")),
    ("hr.warehouse_role", ("manager", "deputy", "supervisor", "operator", "forklift_operator")),
    ("hr.sales_role", ("retail", "trade", "store_manager")),
    ("hr.attendance_status", ("planned", "present", "absent", "leave")),
    ("hr.absence_type", ("leave", "sick", "training")),
    ("hr.manager_level", ("primary", "deputy")),
    # ops
    ("ops.date_mode", ("exact", "range", "latest")),
    (
        "ops.order_status",
        (
            "SUBMITTED",
            "BLOCKED_UNMAPPED_SKU",
            "PLANNED",
            "NO_FEASIBLE_DATE",
            "APPROVED",
            "PREPARING",
            "GOODS_READY",
            "LOADED",
            "DISPATCHED",
            "DELIVERED",
            "FAILED",
            "CANCELLED",
        ),
    ),
    (
        "ops.event_type",
        (
            "START_PREP",
            "PREP_PAUSED",
            "PREP_RESUMED",
            "GOODS_READY",
            "LOADED",
            "DISPATCHED",
            "DELIVERED",
            "FAILED",
            "SHORTAGE",
            "BREAKAGE",
            "VEHICLE_ISSUE",
            "SHIFT_CHANGE",
        ),
    ),
    ("ops.risk_status", ("ON_TRACK", "AT_RISK", "PREDICTED_LATE", "OVERDUE")),
    ("ops.risk_color", ("green", "yellow", "orange", "red")),
    ("ops.notif_template", ("CONFIRMED", "DISPATCHED", "DELIVERED", "FAILED", "DELAY")),
    ("ops.notif_status", ("draft", "queued", "sent", "failed", "suppressed")),
    ("ops.transfer_status", ("suggested", "approved", "source_confirmed", "received", "cancelled")),
    ("ops.negotiation_outcome", ("agreed", "declined", "unreachable")),
    ("ops.trip_status", ("planned", "loading", "on_road", "completed", "cancelled")),
    # plan
    ("plan.plan_status", ("proposed", "expired", "approved", "superseded", "rejected", "manual")),
    ("plan.res_status", ("held", "committed", "released", "expired", "consumed")),
)


def upgrade() -> None:
    """Tạo extension, schema và enum theo 05 mục 2."""
    for ext in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for name, labels in ENUMS:
        values = ", ".join(f"'{label}'" for label in labels)
        op.execute(f"CREATE TYPE {name} AS ENUM ({values})")


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại (enum → schema → extension)."""
    for name, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema}")
    for ext in reversed(EXTENSIONS):
        op.execute(f"DROP EXTENSION IF EXISTS {ext}")
