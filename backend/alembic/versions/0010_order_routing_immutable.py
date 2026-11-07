"""0010_order_routing_immutable

Q14 (06 mục 5.0.2, 05 mục 6): quyết định phân luồng đã ghi trong ops.order_routing là BẤT BIẾN.
- Trigger ops.guard_order_routing (BEFORE UPDATE OR DELETE):
  * không đổi khóa (market_id, external_ref) và quyết định: route, reason_code, unmapped_skus, decided_at,
    decided_source_version, decided_by_user_id;
  * không DELETE (xóa rồi ghi lại = đổi quyết định);
  * chỉ cho cập nhật riêng trường xác nhận bàn giao acknowledged_by_user_id / acknowledged_at, và chỉ
    GHI MỘT LẦN (từ NULL sang giá trị); đã xác nhận thì không sửa/xóa.
- ck_routing_ack: hai trường xác nhận cùng NULL hoặc cùng có giá trị.
Tách khỏi 0009 để DB đã chạy 0009 cũng nhận được ràng buộc. Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0010"
down_revision = "0009"

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE ops.order_routing ADD CONSTRAINT ck_routing_ack "
    "CHECK ((acknowledged_by_user_id IS NULL) = (acknowledged_at IS NULL))",
    """CREATE FUNCTION ops.guard_order_routing() RETURNS trigger AS $$
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
END $$ LANGUAGE plpgsql""",
    "CREATE TRIGGER trg_guard_order_routing BEFORE UPDATE OR DELETE ON ops.order_routing "
    "FOR EACH ROW EXECUTE FUNCTION ops.guard_order_routing()",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TRIGGER trg_guard_order_routing ON ops.order_routing",
    "DROP FUNCTION ops.guard_order_routing()",
    "ALTER TABLE ops.order_routing DROP CONSTRAINT ck_routing_ack",
)


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
