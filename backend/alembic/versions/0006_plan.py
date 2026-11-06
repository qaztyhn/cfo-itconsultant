"""0006_plan

Schema plan: planning_run (kind, trigger), fulfilment_plan (vehicle_count, ux_one_approved_plan),
plan_vehicle (v1.2), stock/prep/vehicle_reservation (EXCLUDE order_id WITH <>), route_matrix (05 mục 7).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    """Tạo đối tượng DB theo 05. TODO(#M0-migrations)."""
    raise NotImplementedError


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại. TODO(#M0-migrations)."""
    raise NotImplementedError
