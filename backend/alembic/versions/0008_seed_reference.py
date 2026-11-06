"""0008_seed_reference

Seed tham chiếu: market SE + MarketConfig mặc định, handling_group N1–N6 (05 mục 11), special_flag,
position, order_transition (v1.2: NO_FEASIBLE_DATE → APPROVED khi lập tay;
PREPARING/GOODS_READY/LOADED/FAILED → APPROVED khi duyệt gợi ý lập lại), position.default_kpi_scopes.

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    """Tạo đối tượng DB theo 05. TODO(#M0-migrations)."""
    raise NotImplementedError


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại. TODO(#M0-migrations)."""
    raise NotImplementedError
