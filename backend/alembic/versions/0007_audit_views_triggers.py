"""0007_audit_views_triggers

audit.decision_log, improvement_log (theo trip_stop), kpi_baseline, v_kpi_daily; trigger set_updated_at,
forbid_mutation, check_transition (05 mục 8–9).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    """Tạo đối tượng DB theo 05. TODO(#M0-migrations)."""
    raise NotImplementedError


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại. TODO(#M0-migrations)."""
    raise NotImplementedError
