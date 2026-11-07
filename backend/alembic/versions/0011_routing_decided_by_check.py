"""0011_routing_decided_by_check

DEC-ROUTING-002 (chủ dự án chốt 07/11/2026): polling chỉ đồng bộ dữ liệu nguồn, KHÔNG ghi quyết định phân
luồng. Quyết định cfo/legacy chỉ được lưu khi Sales chạy "Sync & check routing" hoặc Dispatcher kiểm tra được
ủy quyền.
- decided_by_user_id NOT NULL; decided_by_role ∈ {sales, dispatcher} NOT NULL (không có quyết định
  của hệ thống).
- reason_text; reason_code = 'manual_started' (Sales đã điều phối tay trước khi kiểm, chưa có quyết định) bắt
  buộc lý do không rỗng (ck_routing_manual_reason).
- Trigger guard (0010) mở rộng: decided_by_role, reason_text cũng bất biến.
Migration THẤT BẠI nếu bảng đã có dòng (chưa có decided_by_role; fail closed, không bịa người/vai trò quyết
định). Trên main chưa có code nào ghi bảng này.
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0011"
down_revision = "0010"

_GUARD = """CREATE OR REPLACE FUNCTION ops.guard_order_routing() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'order_routing decision is immutable (delete)'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.market_id IS DISTINCT FROM OLD.market_id
     OR NEW.external_ref IS DISTINCT FROM OLD.external_ref
     OR NEW.route IS DISTINCT FROM OLD.route
     OR NEW.reason_code IS DISTINCT FROM OLD.reason_code
     OR NEW.unmapped_skus IS DISTINCT FROM OLD.unmapped_skus
     OR NEW.decided_at IS DISTINCT FROM OLD.decided_at
     OR NEW.decided_source_version IS DISTINCT FROM OLD.decided_source_version
     OR NEW.decided_by_user_id IS DISTINCT FROM OLD.decided_by_user_id
     {extra}
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'order_routing decision is immutable' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.acknowledged_at IS NOT NULL
     AND (NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at
          OR NEW.acknowledged_by_user_id IS DISTINCT FROM OLD.acknowledged_by_user_id) THEN
    RAISE EXCEPTION 'order_routing acknowledgement is write-once'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql"""

_EXTRA = """OR NEW.decided_by_role IS DISTINCT FROM OLD.decided_by_role
     OR NEW.reason_text IS DISTINCT FROM OLD.reason_text"""

UPGRADE: tuple[str, ...] = (
    """DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM ops.order_routing) THEN
    RAISE EXCEPTION 'ops.order_routing must be empty before 0011 (decided_by_role cannot be inferred)';
  END IF;
END $$""",
    "ALTER TABLE ops.order_routing ADD COLUMN decided_by_role text "
    "CHECK (decided_by_role IN ('sales','dispatcher'))",
    "ALTER TABLE ops.order_routing ADD COLUMN reason_text text",
    "ALTER TABLE ops.order_routing ALTER COLUMN decided_by_user_id SET NOT NULL, "
    "ALTER COLUMN decided_by_role SET NOT NULL",
    "ALTER TABLE ops.order_routing ADD CONSTRAINT ck_routing_manual_reason CHECK ("
    "reason_code <> 'manual_started' OR (reason_text IS NOT NULL AND btrim(reason_text) <> ''))",
    _GUARD.replace("{extra}", _EXTRA),
)

DOWNGRADE: tuple[str, ...] = (
    _GUARD.replace("{extra}\n", ""),
    "ALTER TABLE ops.order_routing DROP CONSTRAINT ck_routing_manual_reason",
    "ALTER TABLE ops.order_routing ALTER COLUMN decided_by_user_id DROP NOT NULL",
    "ALTER TABLE ops.order_routing DROP COLUMN reason_text, DROP COLUMN decided_by_role",
)


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
