"""Alembic environment.

Đọc DATABASE_URL từ app.core.config.Settings. Mỗi migration một ý, có upgrade/downgrade
(09 mục 6). Thứ tự: 0001_extensions_schemas_enums → 0002_ref → 0003_hr → 0004_stg →
0005_ops → 0006_plan → 0007_audit_views_triggers → 0008_seed_reference (05 mục 11).

Owner: Dev 1 (luồng A).
"""

# TODO(#M0-migrations): cấu hình async engine và target_metadata = app.domain.models.Base.metadata
