"""0002_ref

Schema ref: market, holiday, location, handling_group, special_flag, rule, product_global, product_se,
view v_product_local, mapping_task, vehicle, vehicle_availability, customer, app_user (kpi_scopes),
compliance_record (05 mục 3). KHÔNG có bảng thiết bị (v1.1).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    """Tạo đối tượng DB theo 05. TODO(#M0-migrations)."""
    raise NotImplementedError


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại. TODO(#M0-migrations)."""
    raise NotImplementedError
