"""0009_schedule_routing_driver_rules

Q12 / Q12b / Q14 (đã duyệt 07/11/2026, PR #53):
- hr.employee_shift_schedule: lịch ca chính thức của nhân viên kho và tài xế, 1 ca/người/ngày;
- hr.driver_duty_log: kỳ làm việc/lái để kiểm nghỉ 11 giờ và giờ lái;
- ops.order_routing: quyết định luồng cfo/legacy không đổi;
- ref.vehicle.max_permissible_mass_kg + regulation_561_scope (mặc định 'unknown' → engine fail closed).
Cột chung created_at/updated_at (ASM-001) và trigger set_updated_at.

Nguồn sự thật: docs/05_Database_Design.md. Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0009"
down_revision = "0008"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"
NEW_TABLES = (("hr", "employee_shift_schedule"), ("hr", "driver_duty_log"), ("ops", "order_routing"))

UPGRADE: tuple[str, ...] = (
    """ALTER TABLE ref.vehicle
  ADD COLUMN max_permissible_mass_kg numeric(10,2) CHECK (max_permissible_mass_kg > 0),
  ADD COLUMN regulation_561_scope text NOT NULL DEFAULT 'unknown'
    CHECK (regulation_561_scope IN ('in_scope','out_of_scope','unknown'))""",
    f"""CREATE TABLE hr.employee_shift_schedule (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  work_date date NOT NULL,
  shift_template_id bigint REFERENCES hr.shift_template(id),
  start_time time, end_time time,
  break_start time, break_end time,
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','cancelled')),
  assigned_by bigint NOT NULL REFERENCES hr.employee(id), assigned_at timestamptz NOT NULL,
  cancelled_by bigint REFERENCES hr.employee(id), cancelled_at timestamptz,
  reason_text text,
  {TS},
  CONSTRAINT ck_shift_source CHECK (shift_template_id IS NOT NULL OR start_time IS NOT NULL),
  CONSTRAINT ck_shift_times CHECK ((start_time IS NULL) = (end_time IS NULL)),
  CONSTRAINT ck_shift_break CHECK ((break_start IS NULL) = (break_end IS NULL)),
  CONSTRAINT ck_shift_cancelled CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
)""",
    "CREATE UNIQUE INDEX ux_shift_one_per_day ON hr.employee_shift_schedule (employee_id, work_date) "
    "WHERE status = 'scheduled'",
    "CREATE INDEX ix_shift_schedule_wh_date ON hr.employee_shift_schedule (warehouse_id, work_date)",
    f"""CREATE TABLE hr.driver_duty_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  duty_start timestamptz NOT NULL, duty_end timestamptz NOT NULL,
  driving_min int NOT NULL DEFAULT 0 CHECK (driving_min >= 0),
  source text NOT NULL CHECK (source IN ('trip','shift','manual_record')),
  trip_id bigint REFERENCES ops.delivery_trip(id),
  recorded_by bigint REFERENCES hr.employee(id),
  {TS},
  CONSTRAINT ck_duty_interval CHECK (duty_end > duty_start)
)""",
    "CREATE INDEX ix_driver_duty_log_emp ON hr.driver_duty_log (employee_id, duty_start)",
    f"""CREATE TABLE ops.order_routing (
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,
  route text NOT NULL CHECK (route IN ('cfo','legacy')),
  reason_code text NOT NULL CHECK (reason_code IN ('all_confirmed','unmapped_sku','manual_started')),
  unmapped_skus text[] NOT NULL DEFAULT '{{}}',
  decided_at timestamptz NOT NULL, decided_source_version int NOT NULL,
  decided_by_user_id bigint REFERENCES ref.app_user(id),
  acknowledged_by_user_id bigint REFERENCES ref.app_user(id), acknowledged_at timestamptz,
  {TS},
  PRIMARY KEY (market_id, external_ref),
  CONSTRAINT ck_routing_reason CHECK ((route = 'cfo') = (reason_code = 'all_confirmed'))
)""",
    *(
        f"CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON {schema}.{table} "
        "FOR EACH ROW EXECUTE FUNCTION audit.set_updated_at()"
        for schema, table in NEW_TABLES
    ),
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE ops.order_routing",
    "DROP TABLE hr.driver_duty_log",
    "DROP TABLE hr.employee_shift_schedule",
    "ALTER TABLE ref.vehicle DROP COLUMN regulation_561_scope, DROP COLUMN max_permissible_mass_kg",
)


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
