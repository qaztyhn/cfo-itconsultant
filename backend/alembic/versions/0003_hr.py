"""0003_hr

Schema hr: position (default_kpi_scopes), employee, assignment (ux_one_active_assignment),
location_manager (ux_one_primary_manager), 5 bảng con, shift_template, attendance, absence (05 mục 4).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    """Tạo đối tượng DB theo 05. TODO(#M0-migrations)."""
    raise NotImplementedError


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại. TODO(#M0-migrations)."""
    raise NotImplementedError
