"""0003_hr

Schema hr: position (default_kpi_scopes), employee, assignment (ux_one_active_assignment),
location_manager (ux_one_primary_manager), 5 bảng con, shift_template, attendance, absence (05 mục 4),
kèm các khóa ngoài chéo từ ref tới hr.employee.

Cột chung created_at/updated_at (05 mục 1, ASM-001) có ở mọi bảng. Trigger set_updated_at gắn ở 0007.

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0003"
down_revision = "0002"

TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"

UPGRADE: tuple[str, ...] = (
    f"""CREATE TABLE hr.position (
  code text PRIMARY KEY, name text NOT NULL,
  grp text NOT NULL CHECK (grp IN ('warehouse','store','transport','central')),
  default_roles ref.user_role[] NOT NULL DEFAULT '{{}}',
  default_kpi_scopes text[] NOT NULL DEFAULT '{{}}',
  {TS}
)""",
    f"""CREATE TABLE hr.employee (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  employee_no text NOT NULL, first_name text NOT NULL, last_name text NOT NULL,
  work_email text UNIQUE, work_phone text,
  position_code text NOT NULL REFERENCES hr.position(code),
  employment_type hr.employment_type NOT NULL DEFAULT 'full_time',
  weekly_hours numeric(4,1) NOT NULL DEFAULT 40,
  hire_date date NOT NULL, end_date date,
  status hr.employee_status NOT NULL DEFAULT 'active',
  reports_to_employee_id bigint REFERENCES hr.employee(id),
  is_anonymised boolean NOT NULL DEFAULT false,
  {TS},
  UNIQUE (market_id, employee_no)
)""",
    "ALTER TABLE ref.app_user ADD CONSTRAINT fk_user_emp "
    "FOREIGN KEY (employee_id) REFERENCES hr.employee(id)",
    "ALTER TABLE ref.location ADD CONSTRAINT fk_loc_owner "
    "FOREIGN KEY (owner_employee_id) REFERENCES hr.employee(id)",
    "ALTER TABLE ref.product_se ADD CONSTRAINT fk_pse_mapper "
    "FOREIGN KEY (mapped_by) REFERENCES hr.employee(id)",
    "ALTER TABLE ref.product_global ADD CONSTRAINT fk_pg_creator "
    "FOREIGN KEY (created_by) REFERENCES hr.employee(id)",
    f"""CREATE TABLE hr.employee_assignment (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  location_id bigint NOT NULL REFERENCES ref.location(id),
  start_date date NOT NULL, end_date date,
  {TS},
  CHECK (end_date IS NULL OR end_date >= start_date)
)""",
    "CREATE UNIQUE INDEX ux_one_active_assignment ON hr.employee_assignment (employee_id) "
    "WHERE end_date IS NULL",
    f"""CREATE TABLE hr.location_manager (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  location_id bigint NOT NULL REFERENCES ref.location(id),
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  level hr.manager_level NOT NULL,
  can_approve boolean NOT NULL DEFAULT true,
  valid_from date NOT NULL, valid_to date,
  {TS}
)""",
    "CREATE UNIQUE INDEX ux_one_primary_manager ON hr.location_manager (location_id) "
    "WHERE level = 'primary' AND valid_to IS NULL",
    f"""CREATE TABLE hr.warehouse_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  role hr.warehouse_role NOT NULL,
  counts_in_capacity boolean NOT NULL DEFAULT true,
  {TS}
)""",
    f"""CREATE TABLE hr.sales_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  role hr.sales_role NOT NULL,
  {TS}
)""",
    f"""CREATE TABLE hr.dispatcher_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  can_send_delay_notice boolean NOT NULL DEFAULT true,
  {TS}
)""",
    f"""CREATE TABLE hr.driver_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  home_warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  licence_class ref.licence_class NOT NULL, licence_expires_on date NOT NULL,
  adr boolean NOT NULL DEFAULT false,
  {TS}
)""",
    f"""CREATE TABLE hr.cs_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id), team text,
  {TS}
)""",
    f"""CREATE TABLE hr.shift_template (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  weekday smallint NOT NULL CHECK (weekday BETWEEN 1 AND 7),
  start_time time NOT NULL, end_time time NOT NULL,
  useful_hours_per_staff numeric(4,2) NOT NULL,
  expected_staff smallint NOT NULL,
  {TS},
  UNIQUE (warehouse_id, weekday, start_time)
)""",
    f"""CREATE TABLE hr.attendance (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  work_date date NOT NULL,
  shift_template_id bigint REFERENCES hr.shift_template(id),
  status hr.attendance_status NOT NULL DEFAULT 'planned',
  recorded_by bigint REFERENCES hr.employee(id), recorded_at timestamptz,
  {TS},
  UNIQUE (employee_id, work_date)
)""",
    f"""CREATE TABLE hr.absence (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  start_date date NOT NULL, end_date date NOT NULL, type hr.absence_type NOT NULL,
  approved boolean NOT NULL DEFAULT false, approved_by bigint REFERENCES hr.employee(id),
  {TS},
  CHECK (end_date >= start_date)
)""",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE hr.absence",
    "DROP TABLE hr.attendance",
    "DROP TABLE hr.shift_template",
    "DROP TABLE hr.cs_staff",
    "DROP TABLE hr.driver_staff",
    "DROP TABLE hr.dispatcher_staff",
    "DROP TABLE hr.sales_staff",
    "DROP TABLE hr.warehouse_staff",
    "DROP TABLE hr.location_manager",
    "DROP TABLE hr.employee_assignment",
    "ALTER TABLE ref.product_global DROP CONSTRAINT fk_pg_creator",
    "ALTER TABLE ref.product_se DROP CONSTRAINT fk_pse_mapper",
    "ALTER TABLE ref.location DROP CONSTRAINT fk_loc_owner",
    "ALTER TABLE ref.app_user DROP CONSTRAINT fk_user_emp",
    "DROP TABLE hr.employee",
    "DROP TABLE hr.position",
)


def upgrade() -> None:
    """Tạo bảng hr và khóa ngoài chéo theo 05 mục 4."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại."""
    for statement in DOWNGRADE:
        op.execute(statement)
