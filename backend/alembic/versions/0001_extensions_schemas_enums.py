"""0001_extensions_schemas_enums

Extension pgcrypto/btree_gist/pg_trgm, 6 schema, mọi enum (05 mục 2; v1.2: không có
MANUAL_PLANNING/HANDLED_EXTERNALLY; event PREP_PAUSED/PREP_RESUMED).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

revision = "0001"
down_revision = None


def upgrade() -> None:
    """Tạo đối tượng DB theo 05. TODO(#M0-migrations)."""
    raise NotImplementedError


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại. TODO(#M0-migrations)."""
    raise NotImplementedError
