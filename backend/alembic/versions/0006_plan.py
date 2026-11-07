"""0006_plan

Schema plan: planning_run (kind, trigger), fulfilment_plan (vehicle_count, ux_one_approved_plan),
plan_vehicle (v1.2), stock/prep/vehicle_reservation (EXCLUDE order_id WITH <>), route_matrix (05 mục 7),
kèm khóa ngoài fk_trip_plan_vehicle và fk_order_plan.

v1.2: fulfilment_plan không có vehicle_id/driver_employee_id (chi tiết xe ở plan_vehicle); planning_run.result
không có 'manual'. Cột chung created_at/updated_at (ASM-001); trigger set_updated_at ở 0007.

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0006"
down_revision = "0005"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"

UPGRADE: tuple[str, ...] = (
    f"""CREATE TABLE plan.planning_run (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id), order_version int NOT NULL,
  run_no int NOT NULL, triggered_by bigint REFERENCES ref.app_user(id),
  kind text NOT NULL DEFAULT 'initial' CHECK (kind IN ('initial','rerun','replan_suggestion')),
  trigger text CHECK (trigger IN ('source_change','plan_invalidated','vehicle_issue','delivery_failed')),
  params jsonb NOT NULL DEFAULT '{{}}',
  input_snapshot jsonb NOT NULL,
  result text NOT NULL CHECK (result IN ('feasible','infeasible')),
  failed_check text CHECK (failed_check IN ('stock','preparation','truck','site_date','safety')),
  earliest_feasible_date date,
  planning_reserve_min int, reserve_class text CHECK (reserve_class IN ('safe','tight','infeasible')),
  hold_expires_at timestamptz, hold_extensions smallint NOT NULL DEFAULT 0 CHECK (hold_extensions <= 2),
  duration_ms int,
  {TS},
  UNIQUE (order_id, run_no)
)""",
    f"""CREATE TABLE plan.fulfilment_plan (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  rank smallint NOT NULL, status plan.plan_status NOT NULL DEFAULT 'proposed',
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  vehicle_count smallint NOT NULL CHECK (vehicle_count >= 1),
  total_capacity_kg numeric(10,2) NOT NULL, total_capacity_m3 numeric(8,2) NOT NULL,
  target_date date NOT NULL,
  goods_ready_at timestamptz NOT NULL, loading_start_at timestamptz NOT NULL,
  depart_at timestamptz NOT NULL,
  eta_at timestamptz NOT NULL,
  trip_end_at timestamptz NOT NULL,
  distance_km numeric(8,2) NOT NULL, drive_min int NOT NULL,
  prep_hours numeric(8,3) NOT NULL, capacity_fill numeric(5,4) NOT NULL,
  score numeric(6,4) NOT NULL,
  score_breakdown jsonb NOT NULL, complexity_points smallint NOT NULL DEFAULT 0,
  planning_reserve_min int NOT NULL,
  route_provenance text NOT NULL CHECK (route_provenance IN ('ors','fallback','manual')),
  workload jsonb NOT NULL,
  checks jsonb NOT NULL,
  reason_codes text[] NOT NULL DEFAULT '{{}}', explanation text NOT NULL,
  manual_reason_code text CHECK (manual_reason_code IN
     ('customer_request','system_plan_unsuitable','data_error','special_vehicle','other')),
  manual_reason_text text, created_by bigint REFERENCES ref.app_user(id),
  {TS},
  CONSTRAINT ck_manual CHECK ((status IN ('manual') AND manual_reason_code IS NOT NULL)
    OR status <> 'manual'),
  UNIQUE (run_id, rank)
)""",
    "CREATE UNIQUE INDEX ux_one_approved_plan ON plan.fulfilment_plan (order_id) "
    "WHERE status IN ('approved','manual')",
    f"""CREATE TABLE plan.plan_vehicle (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  plan_id bigint NOT NULL REFERENCES plan.fulfilment_plan(id), seq smallint NOT NULL,
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
  load_kg numeric(10,2) NOT NULL, load_m3 numeric(8,3) NOT NULL,
  load_lines jsonb NOT NULL,
  loading_start_at timestamptz NOT NULL, depart_at timestamptz NOT NULL,
  eta_at timestamptz NOT NULL, trip_end_at timestamptz NOT NULL,
  {TS},
  UNIQUE (plan_id, seq), UNIQUE (plan_id, vehicle_id)
)""",
    "ALTER TABLE ops.delivery_trip ADD CONSTRAINT fk_trip_plan_vehicle "
    "FOREIGN KEY (plan_vehicle_id) REFERENCES plan.plan_vehicle(id)",
    "ALTER TABLE ops.customer_order ADD CONSTRAINT fk_order_plan "
    "FOREIGN KEY (approved_plan_id) REFERENCES plan.fulfilment_plan(id)",
    f"""CREATE TABLE plan.stock_reservation (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  qty numeric(12,3) NOT NULL CHECK (qty > 0), status plan.res_status NOT NULL DEFAULT 'held',
  {TS}
)""",
    "CREATE UNIQUE INDEX ux_stock_res ON plan.stock_reservation (order_id, warehouse_id, global_product_id) "
    "WHERE status IN ('held','committed')",
    f"""CREATE TABLE plan.prep_reservation (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id), work_date date NOT NULL,
  resource text NOT NULL DEFAULT 'labour' CHECK (resource = 'labour'),
  hours numeric(8,3) NOT NULL CHECK (hours > 0), status plan.res_status NOT NULL DEFAULT 'held',
  {TS}
)""",
    "CREATE UNIQUE INDEX ux_prep_res ON plan.prep_reservation (order_id, warehouse_id, work_date, resource) "
    "WHERE status IN ('held','committed')",
    f"""CREATE TABLE plan.vehicle_reservation (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id),
  plan_id bigint NOT NULL REFERENCES plan.fulfilment_plan(id),
  plan_vehicle_id bigint NOT NULL REFERENCES plan.plan_vehicle(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
  during tstzrange NOT NULL, status plan.res_status NOT NULL DEFAULT 'held',
  {TS},
  CONSTRAINT ex_vehicle_res EXCLUDE USING gist (vehicle_id WITH =, during WITH &&, order_id WITH <>)
     WHERE (status IN ('held','committed')),
  CONSTRAINT ex_driver_res EXCLUDE USING gist (driver_employee_id WITH =, during WITH &&, order_id WITH <>)
     WHERE (status IN ('held','committed'))
)""",
    f"""CREATE TABLE plan.route_matrix (
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  to_lat numeric(8,5) NOT NULL, to_lon numeric(8,5) NOT NULL,
  distance_km numeric(8,2) NOT NULL, duration_min int NOT NULL,
  provider text NOT NULL CHECK (provider IN ('ors','fallback')),
  computed_at timestamptz NOT NULL DEFAULT now(),
  {TS},
  PRIMARY KEY (warehouse_id, to_lat, to_lon)
)""",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE plan.route_matrix",
    "DROP TABLE plan.vehicle_reservation",
    "DROP TABLE plan.prep_reservation",
    "DROP TABLE plan.stock_reservation",
    "ALTER TABLE ops.customer_order DROP CONSTRAINT fk_order_plan",
    "ALTER TABLE ops.delivery_trip DROP CONSTRAINT fk_trip_plan_vehicle",
    "DROP TABLE plan.plan_vehicle",
    "DROP TABLE plan.fulfilment_plan",
    "DROP TABLE plan.planning_run",
)


def upgrade() -> None:
    """Tạo bảng plan theo 05 mục 7."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại."""
    for statement in DOWNGRADE:
        op.execute(statement)
