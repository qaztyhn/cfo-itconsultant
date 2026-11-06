"""0005_ops

Schema ops: stock_snapshot, inbound, transfer, customer_order, order_line, order_transition,
date_negotiation, delivery_trip (plan_vehicle_id), trip_stop (UNIQUE trip_id+order_id, bỏ
ux_stop_active_order), milestone_event (trip_id), proof_of_delivery theo trip_stop_id, eta_forecast, alert
(ux_alert_open_dedupe), notification (plan_id), contact_log, vehicle_position, idempotency_key (05 mục 6).

Cột chung created_at/updated_at (05 mục 1, ASM-001) có ở mọi bảng; idempotency_key đã có created_at nên
chỉ thêm updated_at. Mốc nghiệp vụ (occurred_at, completed_at, computed_at, contacted_at, recorded_at…)
giữ nguyên. Khóa ngoài tới plan.* (approved_plan_id, plan_vehicle_id) thêm ở 0006; trigger ở 0007;
chỉ mục bắt buộc của 05 mục 9 ở 0007.

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0005"
down_revision = "0004"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"

UPGRADE: tuple[str, ...] = (
    f"""CREATE TABLE ops.stock_snapshot (
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  on_hand numeric(12,3) NOT NULL CHECK (on_hand >= 0),
  wms_reserved numeric(12,3) NOT NULL DEFAULT 0 CHECK (wms_reserved >= 0),
  as_of timestamptz NOT NULL, run_id bigint REFERENCES stg.sync_run(id),
  {TS},
  PRIMARY KEY (warehouse_id, global_product_id)
)""",
    f"""CREATE TABLE ops.inbound_shipment (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  inbound_ref text NOT NULL, warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  qty numeric(12,3) NOT NULL CHECK (qty > 0), eta_date date NOT NULL,
  confirmed boolean NOT NULL DEFAULT false,
  received boolean NOT NULL DEFAULT false,
  source text NOT NULL DEFAULT 'erp' CHECK (source IN ('erp','transfer')),
  transfer_id bigint, run_id bigint REFERENCES stg.sync_run(id),
  {TS},
  UNIQUE (inbound_ref, global_product_id)
)""",
    f"""CREATE TABLE ops.stock_transfer (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint, from_warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  to_warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  status ops.transfer_status NOT NULL DEFAULT 'suggested',
  lead_days smallint NOT NULL, expected_arrival_date date,
  suggestion jsonb NOT NULL,
  approved_by bigint REFERENCES hr.employee(id), approved_at timestamptz,
  source_confirmed_by bigint REFERENCES hr.employee(id), source_confirmed_at timestamptz,
  received_at timestamptz,
  {TS},
  CHECK (from_warehouse_id <> to_warehouse_id)
)""",
    f"""CREATE TABLE ops.stock_transfer_line (
  transfer_id bigint NOT NULL REFERENCES ops.stock_transfer(id),
  global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  qty numeric(12,3) NOT NULL CHECK (qty > 0),
  {TS},
  PRIMARY KEY (transfer_id, global_product_id)
)""",
    "ALTER TABLE ops.inbound_shipment ADD CONSTRAINT fk_inb_transfer "
    "FOREIGN KEY (transfer_id) REFERENCES ops.stock_transfer(id)",
    f"""CREATE TABLE ops.customer_order (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_no text NOT NULL UNIQUE,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,
  source_version int NOT NULL DEFAULT 1,
  version int NOT NULL DEFAULT 1,
  customer_id bigint NOT NULL REFERENCES ref.customer(id),
  contact_name text NOT NULL, contact_phone text, contact_email text,
  delivery_address text NOT NULL, delivery_lat numeric(8,5) NOT NULL, delivery_lon numeric(8,5) NOT NULL,
  receiving_restrictions text, special_requirements text,
  date_mode ops.date_mode NOT NULL,
  date_from date, date_to date NOT NULL,
  window_start time, window_end time,
  order_date timestamptz NOT NULL,
  sales_employee_id bigint REFERENCES hr.employee(id),
  origin_store_id bigint REFERENCES ref.location(id),
  status ops.order_status NOT NULL DEFAULT 'SUBMITTED',
  block_reason text,
  committed_date date, promise_start timestamptz, promise_end timestamptz,
  approved_plan_id bigint,
  currency char(3) NOT NULL, total_amount numeric(14,2) NOT NULL DEFAULT 0,
  submitted_at timestamptz NOT NULL, planned_at timestamptz, approved_at timestamptz,
  delivered_at timestamptz, closed_at timestamptz,
  {TS},
  UNIQUE (market_id, external_ref),
  CONSTRAINT ck_dates CHECK (
    (date_mode = 'exact'  AND date_from = date_to) OR
    (date_mode = 'range'  AND date_from < date_to) OR
    (date_mode = 'latest' AND date_from IS NULL)),
  CONSTRAINT ck_window CHECK ((window_start IS NULL) = (window_end IS NULL)
    AND (window_start IS NULL OR window_start < window_end))
)""",
    f"""CREATE TABLE ops.order_line (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id) ON DELETE CASCADE,
  line_no smallint NOT NULL, local_sku text NOT NULL,
  global_product_id bigint REFERENCES ref.product_global(id),
  qty_sale numeric(12,3) NOT NULL CHECK (qty_sale > 0),
  qty_base numeric(12,3),
  unit_price numeric(12,2) NOT NULL, line_total numeric(14,2) NOT NULL,
  {TS},
  UNIQUE (order_id, line_no), UNIQUE (order_id, local_sku)
)""",
    f"""CREATE TABLE ops.order_transition (
  from_status ops.order_status NOT NULL, to_status ops.order_status NOT NULL,
  requires_reason boolean NOT NULL DEFAULT false, allowed_roles ref.user_role[] NOT NULL,
  {TS},
  PRIMARY KEY (from_status, to_status)
)""",
    f"""CREATE TABLE ops.date_negotiation (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  proposed_date date NOT NULL, outcome ops.negotiation_outcome NOT NULL,
  channel text NOT NULL CHECK (channel IN ('phone','email','in_person')),
  contacted_at timestamptz NOT NULL, recorded_by bigint NOT NULL REFERENCES hr.employee(id),
  note text, remind_at timestamptz,
  {TS}
)""",
    f"""CREATE TABLE ops.delivery_trip (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  plan_vehicle_id bigint,
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
  status ops.trip_status NOT NULL DEFAULT 'planned',
  depart_planned_at timestamptz NOT NULL, depart_actual_at timestamptz, ended_at timestamptz,
  {TS}
)""",
    f"""CREATE TABLE ops.trip_stop (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trip_id bigint NOT NULL REFERENCES ops.delivery_trip(id),
  seq smallint NOT NULL DEFAULT 1, order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  eta_planned_at timestamptz NOT NULL, arrived_at timestamptz, completed_at timestamptz,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','delivered','failed','cancelled')),
  {TS},
  UNIQUE (trip_id, seq), UNIQUE (trip_id, order_id)
)""",
    f"""CREATE TABLE ops.milestone_event (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  plan_id bigint, trip_id bigint REFERENCES ops.delivery_trip(id),
  event_type ops.event_type NOT NULL,
  occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  actor_user_id bigint NOT NULL REFERENCES ref.app_user(id),
  actor_employee_id bigint REFERENCES hr.employee(id),
  payload jsonb NOT NULL DEFAULT '{{}}',
  idempotency_key text NOT NULL UNIQUE,
  {TS}
)""",
    f"""CREATE TABLE ops.proof_of_delivery (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trip_stop_id bigint NOT NULL UNIQUE REFERENCES ops.trip_stop(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  result text NOT NULL CHECK (result IN ('delivered','failed')),
  completed_at timestamptz NOT NULL, recipient_name text, note text,
  failure_reason text CHECK (failure_reason IN
    ('customer_absent','site_inaccessible','refused','wrong_address','vehicle_breakdown','goods_damaged','other')),
  {TS},
  CHECK ((result = 'failed') = (failure_reason IS NOT NULL))
)""",
    "CREATE INDEX ix_pod_order ON ops.proof_of_delivery (order_id, completed_at)",
    "CREATE UNIQUE INDEX ux_pod_one_delivered ON ops.proof_of_delivery (order_id) WHERE result = 'delivered'",
    f"""CREATE TABLE ops.eta_forecast (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  version int NOT NULL, computed_at timestamptz NOT NULL DEFAULT now(),
  trigger text NOT NULL,
  planned_eta timestamptz NOT NULL, forecast_eta timestamptz NOT NULL,
  commitment_deadline timestamptz NOT NULL,
  reserve_total_min int NOT NULL, slack_min int NOT NULL, consumption_pct numeric(6,2) NOT NULL,
  consecutive_negative smallint NOT NULL DEFAULT 0,
  risk_status ops.risk_status NOT NULL, risk_color ops.risk_color NOT NULL,
  {TS},
  UNIQUE (order_id, version)
)""",
    f"""CREATE TABLE ops.alert (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint REFERENCES ops.customer_order(id), market_id smallint NOT NULL REFERENCES ref.market(id),
  level text NOT NULL CHECK (level IN ('info','warning','critical')),
  type text NOT NULL,
  message text NOT NULL, target_roles ref.user_role[] NOT NULL,
  dedupe_key text NOT NULL,
  acknowledged_by bigint REFERENCES hr.employee(id), acknowledged_at timestamptz, resolved_at timestamptz,
  {TS}
)""",
    "CREATE UNIQUE INDEX ux_alert_open_dedupe ON ops.alert (dedupe_key) WHERE resolved_at IS NULL",
    f"""CREATE TABLE ops.notification (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  template ops.notif_template NOT NULL, channel ref.notify_channel NOT NULL,
  recipient text NOT NULL, subject text, body text NOT NULL,
  eta_window jsonb,
  status ops.notif_status NOT NULL DEFAULT 'queued',
  scheduled_for timestamptz NOT NULL DEFAULT now(),
  attempts smallint NOT NULL DEFAULT 0, last_error text, sent_at timestamptz,
  created_by_employee_id bigint REFERENCES hr.employee(id),
  suppressed_reason text,
  plan_id bigint,
  dedupe_key text NOT NULL UNIQUE,
  {TS}
)""",
    f"""CREATE TABLE ops.customer_contact_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint REFERENCES ops.customer_order(id), customer_id bigint NOT NULL REFERENCES ref.customer(id),
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  channel text NOT NULL CHECK (channel IN ('phone','email','chat')),
  reason_code text NOT NULL CHECK (reason_code IN
    ('where_is_my_order','change_request','complaint','delay_inquiry','other')),
  note text, contacted_at timestamptz NOT NULL DEFAULT now(),
  {TS}
)""",
    f"""CREATE TABLE ops.vehicle_position (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trip_id bigint NOT NULL REFERENCES ops.delivery_trip(id),
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  lat numeric(8,5) NOT NULL, lon numeric(8,5) NOT NULL, accuracy_m numeric(8,1),
  recorded_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
  source text NOT NULL CHECK (source IN ('device','simulator')),
  {TS}
)""",
    """CREATE TABLE ops.idempotency_key (
  key text NOT NULL, user_id bigint NOT NULL REFERENCES ref.app_user(id),
  endpoint text NOT NULL, request_hash text NOT NULL, response_status int, response_body jsonb,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (key, user_id)
)""",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE ops.idempotency_key",
    "DROP TABLE ops.vehicle_position",
    "DROP TABLE ops.customer_contact_log",
    "DROP TABLE ops.notification",
    "DROP TABLE ops.alert",
    "DROP TABLE ops.eta_forecast",
    "DROP TABLE ops.proof_of_delivery",
    "DROP TABLE ops.milestone_event",
    "DROP TABLE ops.trip_stop",
    "DROP TABLE ops.delivery_trip",
    "DROP TABLE ops.date_negotiation",
    "DROP TABLE ops.order_transition",
    "DROP TABLE ops.order_line",
    "DROP TABLE ops.customer_order",
    "ALTER TABLE ops.inbound_shipment DROP CONSTRAINT fk_inb_transfer",
    "DROP TABLE ops.stock_transfer_line",
    "DROP TABLE ops.stock_transfer",
    "DROP TABLE ops.inbound_shipment",
    "DROP TABLE ops.stock_snapshot",
)


def upgrade() -> None:
    """Tạo bảng ops theo 05 mục 6."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại."""
    for statement in DOWNGRADE:
        op.execute(statement)
