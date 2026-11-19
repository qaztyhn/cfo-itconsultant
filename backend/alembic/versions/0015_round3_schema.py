"""0015: Round 3 storage contracts (DEC-R3, docs/05 section 13)."""

from alembic import op

revision = "0015"
down_revision = "0014"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"
NEW_TABLES = (
    "hr.warehouse_day_capacity",
    "hr.driver_availability",
    "hr.driver_vehicle_eligibility",
)


def upgrade() -> None:
    op.execute("ALTER TYPE ops.event_type ADD VALUE IF NOT EXISTS 'DRIVER_INCIDENT'")
    op.execute("ALTER TABLE ops.vehicle_position DROP CONSTRAINT IF EXISTS vehicle_position_source_check")
    op.execute("""ALTER TABLE ops.vehicle_position ADD CONSTRAINT vehicle_position_source_check
        CHECK (source IN ('device','simulator','driver_tap','driver_incident','driver_completion'))""")
    op.execute("ALTER TABLE ops.vehicle_position ADD COLUMN remaining_km numeric(7,1)")
    op.execute("ALTER TABLE ops.vehicle_position ADD COLUMN remaining_min int")
    op.execute("""ALTER TABLE ops.vehicle_position ADD COLUMN route_source text
        CHECK (route_source IN ('ors','haversine_estimate'))""")
    op.execute("ALTER TABLE ops.proof_of_delivery ADD COLUMN site_distance_m int")
    op.execute("""ALTER TABLE ops.delivery_trip ADD COLUMN assigned_dispatcher_employee_id bigint
        REFERENCES hr.employee(id)""")
    op.execute("ALTER TABLE hr.dispatcher_staff ADD COLUMN in_rotation boolean NOT NULL DEFAULT true")
    op.execute("""ALTER TABLE ops.notification ADD CONSTRAINT ck_notification_email_only_r3
        CHECK (channel = 'email') NOT VALID""")
    op.execute("""ALTER TABLE ops.notification ADD COLUMN skipped_reason text
        CHECK (skipped_reason IS NULL OR skipped_reason IN
            ('SKIPPED_NO_CHANNEL','SKIPPED_FLAG_DISABLED'))""")
    op.execute("ALTER TABLE plan.planning_run DROP CONSTRAINT IF EXISTS planning_run_kind_check")
    op.execute("""ALTER TABLE plan.planning_run ADD CONSTRAINT planning_run_kind_check
        CHECK (kind IN ('initial','rerun','replan_suggestion','remaining_replan'))""")
    op.execute("ALTER TABLE plan.planning_run ADD COLUMN remaining_lines jsonb")
    op.execute(f"""CREATE TABLE hr.warehouse_day_capacity (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        warehouse_id bigint NOT NULL REFERENCES ref.location(id),
        work_date date NOT NULL,
        shift_code text NOT NULL CHECK (shift_code ~ '^[A-Z0-9_]{{1,16}}$'),
        start_time time NOT NULL, end_time time NOT NULL CHECK (end_time <> start_time),
        headcount smallint NOT NULL CHECK (headcount BETWEEN 0 AND 500),
        productive_hours numeric(4,2) NOT NULL CHECK (productive_hours > 0 AND productive_hours <= 12),
        confirmed_by bigint NOT NULL REFERENCES hr.employee(id),
        confirmed_at timestamptz NOT NULL DEFAULT now(),
        change_reason text, superseded_at timestamptz,
        superseded_by bigint REFERENCES hr.warehouse_day_capacity(id),
        {TS}
    )""")
    op.execute("""CREATE UNIQUE INDEX ux_wdc_active ON hr.warehouse_day_capacity
        (warehouse_id, work_date, shift_code) WHERE superseded_at IS NULL""")
    op.execute(f"""CREATE TABLE hr.driver_availability (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
        work_date date NOT NULL,
        available_from timestamptz NOT NULL,
        available_to timestamptz NOT NULL CHECK (available_to > available_from),
        max_driving_min int NOT NULL CHECK (max_driving_min BETWEEN 0 AND 900),
        verified_by text NOT NULL, verified_at timestamptz NOT NULL,
        source text NOT NULL CHECK (source IN ('fleet_api','fleet_csv','synthetic_demo')),
        source_ref text NOT NULL, superseded_at timestamptz,
        UNIQUE (source, source_ref),
        {TS}
    )""")
    op.execute("""CREATE UNIQUE INDEX ux_driver_avail_active ON hr.driver_availability
        (driver_employee_id, work_date) WHERE superseded_at IS NULL""")
    op.execute(f"""CREATE TABLE hr.driver_vehicle_eligibility (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
        vehicle_id bigint REFERENCES ref.vehicle(id),
        licence_class ref.licence_class,
        verified_until date NOT NULL, verified_by text NOT NULL,
        verified_at timestamptz NOT NULL,
        source text NOT NULL CHECK (source IN ('fleet_api','fleet_csv','synthetic_demo')),
        source_ref text NOT NULL, revoked_at timestamptz,
        CHECK ((vehicle_id IS NULL) <> (licence_class IS NULL)),
        UNIQUE (source, source_ref),
        {TS}
    )""")
    for table in NEW_TABLES:
        op.execute(f"""CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION audit.set_updated_at()""")
    op.execute("""ALTER TABLE audit.improvement_log ADD COLUMN approval_path text
        CHECK (approval_path IS NULL OR approval_path IN ('sales','dispatcher'))""")
    op.execute("ALTER TABLE audit.improvement_log ADD COLUMN order_to_commit_min int")


def downgrade() -> None:
    # PostgreSQL enum labels are intentionally retained: removing one requires a type rebuild.
    op.execute("ALTER TABLE audit.improvement_log DROP COLUMN order_to_commit_min")
    op.execute("ALTER TABLE audit.improvement_log DROP COLUMN approval_path")
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute("ALTER TABLE plan.planning_run DROP COLUMN remaining_lines")
    op.execute("ALTER TABLE plan.planning_run DROP CONSTRAINT planning_run_kind_check")
    op.execute("""ALTER TABLE plan.planning_run ADD CONSTRAINT planning_run_kind_check
        CHECK (kind IN ('initial','rerun','replan_suggestion'))""")
    op.execute("ALTER TABLE ops.notification DROP COLUMN skipped_reason")
    op.execute("ALTER TABLE ops.notification DROP CONSTRAINT ck_notification_email_only_r3")
    op.execute("ALTER TABLE hr.dispatcher_staff DROP COLUMN in_rotation")
    op.execute("ALTER TABLE ops.delivery_trip DROP COLUMN assigned_dispatcher_employee_id")
    op.execute("ALTER TABLE ops.proof_of_delivery DROP COLUMN site_distance_m")
    op.execute("ALTER TABLE ops.vehicle_position DROP COLUMN route_source")
    op.execute("ALTER TABLE ops.vehicle_position DROP COLUMN remaining_min")
    op.execute("ALTER TABLE ops.vehicle_position DROP COLUMN remaining_km")
    op.execute("ALTER TABLE ops.vehicle_position DROP CONSTRAINT vehicle_position_source_check")
    op.execute("""ALTER TABLE ops.vehicle_position ADD CONSTRAINT vehicle_position_source_check
        CHECK (source IN ('device','simulator'))""")
