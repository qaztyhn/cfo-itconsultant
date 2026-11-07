"""0007_audit_views_triggers

audit.decision_log, improvement_log (theo trip_stop, actual_labour_hours, group_hours_per_unit),
kpi_baseline, v_revenue_daily, v_revenue_pending, chỉ mục doanh thu; trigger set_updated_at,
forbid_mutation, check_transition; chỉ mục bắt buộc 05 mục 9 (05 mục 8–9).

- set_updated_at (ASM-001): gắn cho MỌI bảng có cột updated_at trong 6 schema CFO (tính lúc chạy migration).
- forbid_mutation: decision_log và milestone_event chỉ thêm (09 bất biến 13; US-LOG-01 AC2).
- audit.v_kpi_daily KHÔNG tạo ở đây: 05 chỉ định nghĩa chỉ số, chưa có DDL; thuộc M8 (10 mục 2).
- Chỉ mục 05 mục 9 không có tên trong tài liệu → đặt theo quy ước `ix_` (05 mục 1).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0007"
down_revision = "0006"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"
CFO_SCHEMAS = "ARRAY['ref','hr','stg','ops','plan','audit']"

# Gắn/gỡ trigger set_updated_at trên mọi bảng có cột updated_at (chạy SAU khi tạo bảng audit).
_FOR_EACH_UPDATED_AT_TABLE = f"""
DO $$
DECLARE t record;
BEGIN
  FOR t IN
    SELECT c.table_schema, c.table_name
    FROM information_schema.columns c
    JOIN information_schema.tables tb
      ON tb.table_schema = c.table_schema AND tb.table_name = c.table_name AND tb.table_type = 'BASE TABLE'
    WHERE c.column_name = 'updated_at' AND c.table_schema = ANY({CFO_SCHEMAS})
  LOOP
    EXECUTE format(%s, t.table_schema, t.table_name);
  END LOOP;
END $$"""

ATTACH_SET_UPDATED_AT = _FOR_EACH_UPDATED_AT_TABLE % (
    "'CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON %I.%I "
    "FOR EACH ROW EXECUTE FUNCTION audit.set_updated_at()'"
)
DETACH_SET_UPDATED_AT = _FOR_EACH_UPDATED_AT_TABLE % "'DROP TRIGGER IF EXISTS trg_set_updated_at ON %I.%I'"

# 05 mục 9 — chỉ mục bắt buộc.
INDEXES: tuple[tuple[str, str], ...] = (
    ("ops.ix_order_status_committed", "ON ops.customer_order (status, committed_date)"),
    ("ops.ix_order_market_status", "ON ops.customer_order (market_id, status)"),
    ("ops.ix_order_line_order", "ON ops.order_line (order_id)"),
    ("ops.ix_event_order_occurred", "ON ops.milestone_event (order_id, occurred_at)"),
    ("ops.ix_eta_order_version", "ON ops.eta_forecast (order_id, version DESC)"),
    ("ops.ix_notification_status_scheduled", "ON ops.notification (status, scheduled_for)"),
    ("ops.ix_alert_market_resolved", "ON ops.alert (market_id, resolved_at)"),
    ("ops.ix_position_trip_recorded", "ON ops.vehicle_position (trip_id, recorded_at DESC)"),
    (
        "ops.ix_inbound_atp",
        "ON ops.inbound_shipment (warehouse_id, global_product_id, eta_date) "
        "WHERE confirmed AND NOT received",
    ),
    ("hr.ix_attendance_date_status", "ON hr.attendance (work_date, status)"),
    ("hr.ix_assignment_active_location", "ON hr.employee_assignment (location_id) WHERE end_date IS NULL"),
    ("plan.ix_plan_order_status", "ON plan.fulfilment_plan (order_id, status)"),
    (
        "plan.ix_vehicle_res_active",
        "ON plan.vehicle_reservation USING gist (vehicle_id, during) WHERE status IN ('held','committed')",
    ),
)

UPGRADE: tuple[str, ...] = (
    f"""CREATE TABLE audit.decision_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(), correlation_id uuid NOT NULL,
  actor_user_id bigint REFERENCES ref.app_user(id), actor_employee_id bigint, actor_role text,
  action text NOT NULL, entity text NOT NULL, entity_id text,
  order_id bigint, plan_id bigint,
  reason_code text, reason_text text,
  snapshot jsonb, before jsonb, after jsonb,
  {TS}
)""",
    "CREATE INDEX ix_decision_order ON audit.decision_log (order_id, ts)",
    "CREATE INDEX ix_decision_action ON audit.decision_log (action, ts)",
    f"""CREATE TABLE audit.improvement_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  trip_stop_id bigint UNIQUE REFERENCES ops.trip_stop(id),
  actual_labour_hours numeric(8,3),
  labour_segments jsonb,
  group_hours_per_unit jsonb,
  warehouse_id bigint NOT NULL, handling_groups text[] NOT NULL,
  prep_planned_min int, prep_actual_min int, prep_error_min int,
  eta_first timestamptz, eta_last timestamptz, delivered_at timestamptz, eta_error_min int,
  delay_reason text, was_manual boolean NOT NULL DEFAULT false,
  accepted_unchanged boolean, order_mix jsonb, closed_at timestamptz NOT NULL DEFAULT now(),
  {TS}
)""",
    f"""CREATE TABLE audit.kpi_baseline (
  market_id smallint NOT NULL REFERENCES ref.market(id), metric text NOT NULL,
  value numeric NOT NULL, unit text NOT NULL, source text NOT NULL, measured_on date NOT NULL,
  {TS},
  PRIMARY KEY (market_id, metric)
)""",
    """CREATE VIEW audit.v_revenue_daily AS
SELECT m.id AS market_id, (o.delivered_at AT TIME ZONE m.timezone)::date AS day,
       o.origin_store_id AS store_id, p.warehouse_id, o.currency,
       count(*) AS orders_delivered, sum(o.total_amount) AS revenue_recognised
FROM ops.customer_order o
JOIN ref.market m ON m.id = o.market_id
JOIN plan.fulfilment_plan p ON p.id = o.approved_plan_id
WHERE o.status = 'DELIVERED'
GROUP BY m.id, m.timezone, (o.delivered_at AT TIME ZONE m.timezone)::date,
         o.origin_store_id, p.warehouse_id, o.currency""",
    """CREATE VIEW audit.v_revenue_pending AS
SELECT o.market_id, o.committed_date AS day, o.origin_store_id AS store_id,
       p.warehouse_id, o.currency,
       count(*) AS orders_pending, sum(o.total_amount) AS revenue_booked
FROM ops.customer_order o JOIN plan.fulfilment_plan p ON p.id = o.approved_plan_id
WHERE o.status IN ('APPROVED','PREPARING','GOODS_READY','LOADED','DISPATCHED')
GROUP BY o.market_id, o.committed_date, o.origin_store_id, p.warehouse_id, o.currency""",
    "CREATE INDEX ix_order_status_delivered ON ops.customer_order (status, delivered_at)",
    "CREATE INDEX ix_order_store_status ON ops.customer_order (origin_store_id, status)",
    *(f"CREATE INDEX {name.split('.')[1]} {spec}" for name, spec in INDEXES),
    """CREATE FUNCTION audit.set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at := now(); RETURN NEW; END $$ LANGUAGE plpgsql""",
    ATTACH_SET_UPDATED_AT,
    """CREATE FUNCTION audit.forbid_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'append-only table'; END $$ LANGUAGE plpgsql""",
    "CREATE TRIGGER trg_decision_immutable BEFORE UPDATE OR DELETE ON audit.decision_log "
    "FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation()",
    "CREATE TRIGGER trg_event_immutable BEFORE UPDATE OR DELETE ON ops.milestone_event "
    "FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation()",
    """CREATE FUNCTION ops.check_transition() RETURNS trigger AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status AND NOT EXISTS (
     SELECT 1 FROM ops.order_transition WHERE from_status = OLD.status AND to_status = NEW.status)
  THEN RAISE EXCEPTION 'illegal order transition % -> %', OLD.status, NEW.status; END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql""",
    "CREATE TRIGGER trg_check_transition BEFORE UPDATE OF status ON ops.customer_order "
    "FOR EACH ROW EXECUTE FUNCTION ops.check_transition()",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TRIGGER trg_check_transition ON ops.customer_order",
    "DROP FUNCTION ops.check_transition()",
    "DROP TRIGGER trg_event_immutable ON ops.milestone_event",
    "DROP TRIGGER trg_decision_immutable ON audit.decision_log",
    "DROP FUNCTION audit.forbid_mutation()",
    DETACH_SET_UPDATED_AT,
    "DROP FUNCTION audit.set_updated_at()",
    *(f"DROP INDEX {name}" for name, _ in reversed(INDEXES)),
    "DROP INDEX ops.ix_order_store_status",
    "DROP INDEX ops.ix_order_status_delivered",
    "DROP VIEW audit.v_revenue_pending",
    "DROP VIEW audit.v_revenue_daily",
    "DROP TABLE audit.kpi_baseline",
    "DROP TABLE audit.improvement_log",
    "DROP TABLE audit.decision_log",
)


def upgrade() -> None:
    """Tạo bảng audit, view doanh thu, chỉ mục và trigger theo 05 mục 8–9."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại."""
    for statement in DOWNGRADE:
        op.execute(statement)
