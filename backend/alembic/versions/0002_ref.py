"""0002_ref

Schema ref: market, holiday, location, handling_group, special_flag, rule, product_global, product_se,
view v_product_local, mapping_task, vehicle, vehicle_availability, customer, app_user (kpi_scopes),
compliance_record (05 mục 3). KHÔNG có bảng thiết bị (v1.1).

Cột chung created_at/updated_at (05 mục 1, ASM-001) có ở mọi bảng; không thêm trùng khi DDL đã có
(ref.market). Trigger set_updated_at gắn ở 0007. Khóa ngoài tới hr.employee thêm ở 0003.

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

from alembic import op

revision = "0002"
down_revision = "0001"

# 05 mục 1: cột chung của mọi bảng nghiệp vụ (ASM-001: mọi bảng CFO trong 05).
TS = "created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"

UPGRADE: tuple[str, ...] = (
    """CREATE TABLE ref.market (
  id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code char(2) NOT NULL UNIQUE,
  name text NOT NULL,
  timezone text NOT NULL,
  locale text NOT NULL DEFAULT 'en',
  currency char(3) NOT NULL,
  gps_enabled boolean NOT NULL DEFAULT false,
  shadow_mode boolean NOT NULL DEFAULT false,
  source_base_url text,
  source_api_key_ref text,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
)""",
    f"""CREATE TABLE ref.market_holiday (
  market_id smallint NOT NULL REFERENCES ref.market(id),
  holiday_date date NOT NULL, name text NOT NULL,
  {TS},
  PRIMARY KEY (market_id, holiday_date)
)""",
    f"""CREATE TABLE ref.location (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  type ref.location_type NOT NULL,
  code text NOT NULL, name text NOT NULL, address text,
  lat numeric(8,5), lon numeric(8,5),
  loading_cutoff_time time,
  efficiency_factor numeric(4,2) NOT NULL DEFAULT 1.00,
  owner_employee_id bigint,
  is_active boolean NOT NULL DEFAULT true,
  {TS},
  UNIQUE (market_id, code),
  CONSTRAINT ck_wh_cutoff CHECK (type <> 'warehouse' OR loading_cutoff_time IS NOT NULL),
  CONSTRAINT ck_geo CHECK (type NOT IN ('warehouse','store') OR (lat IS NOT NULL AND lon IS NOT NULL))
)""",
    f"""CREATE TABLE ref.handling_group (
  id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code text NOT NULL UNIQUE,
  name text NOT NULL, description text,
  prep_unit ref.prep_unit NOT NULL,
  fixed_hours numeric(6,3) NOT NULL DEFAULT 0,
  labour_hours_per_unit numeric(6,3) NOT NULL,
  min_crew smallint NOT NULL DEFAULT 1,
  vehicle_requirement text[] NOT NULL DEFAULT '{{}}',
  {TS}
)""",
    f"""CREATE TABLE ref.special_flag (
  code text PRIMARY KEY,
  name text NOT NULL, multiplier numeric(4,2) NOT NULL CHECK (multiplier >= 1),
  {TS}
)""",
    f"""CREATE TABLE ref.handling_group_rule (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  priority smallint NOT NULL DEFAULT 100,
  category_like text NOT NULL,
  min_weight_kg numeric(10,3), max_weight_kg numeric(10,3),
  handling_group_id smallint NOT NULL REFERENCES ref.handling_group(id),
  flags text[] NOT NULL DEFAULT '{{}}',
  {TS}
)""",
    f"""CREATE TABLE ref.product_global (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code text NOT NULL UNIQUE,
  name text NOT NULL, category text NOT NULL,
  gtin text UNIQUE,
  base_unit text NOT NULL,
  weight_kg numeric(10,3) NOT NULL CHECK (weight_kg > 0),
  volume_m3 numeric(10,4) NOT NULL CHECK (volume_m3 > 0),
  handling_group_id smallint NOT NULL REFERENCES ref.handling_group(id),
  base_units_per_prep_unit numeric(12,4),
  flags text[] NOT NULL DEFAULT '{{}}',
  created_by bigint,
  {TS}
)""",
    f"""CREATE TABLE ref.product_se (
  local_sku text PRIMARY KEY,
  name text NOT NULL, category text NOT NULL, gtin text,
  sale_unit text NOT NULL,
  units_to_base numeric(12,4) NOT NULL DEFAULT 1 CHECK (units_to_base > 0),
  unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0), currency char(3) NOT NULL DEFAULT 'SEK',
  weight_kg numeric(10,3), volume_m3 numeric(10,4),
  global_product_id bigint REFERENCES ref.product_global(id),
  mapping_status ref.mapping_status NOT NULL DEFAULT 'pending',
  mapped_by bigint, mapped_at timestamptz,
  source_updated_at timestamptz, synced_at timestamptz NOT NULL DEFAULT now(),
  {TS},
  CONSTRAINT ck_se_confirmed CHECK (mapping_status <> 'confirmed'
        OR (global_product_id IS NOT NULL AND mapped_by IS NOT NULL))
)""",
    "CREATE INDEX ix_product_se_name_trgm ON ref.product_se USING gin (name gin_trgm_ops)",
    "CREATE INDEX ix_product_se_gtin ON ref.product_se (gtin)",
    """CREATE VIEW ref.v_product_local AS
  SELECT 'SE'::char(2) AS market_code, local_sku, name, category, gtin, sale_unit, units_to_base,
         unit_price, currency, global_product_id, mapping_status FROM ref.product_se""",
    f"""CREATE TABLE ref.mapping_task (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  local_sku text NOT NULL,
  status ref.task_status NOT NULL DEFAULT 'open',
  candidates jsonb NOT NULL DEFAULT '[]',
  blocked_order_count int NOT NULL DEFAULT 0,
  assigned_to bigint, resolved_by bigint, resolved_at timestamptz,
  {TS},
  UNIQUE (market_id, local_sku)
)""",
    f"""CREATE TABLE ref.vehicle (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  home_warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  code text NOT NULL UNIQUE, plate text NOT NULL, name text NOT NULL,
  capacity_kg numeric(10,3) NOT NULL CHECK (capacity_kg > 0),
  capacity_m3 numeric(10,4) NOT NULL CHECK (capacity_m3 > 0),
  capabilities text[] NOT NULL DEFAULT '{{}}',
  required_licence ref.licence_class NOT NULL,
  allowed_group_ids smallint[] NOT NULL DEFAULT '{{}}',
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('available','maintenance','retired')),
  {TS}
)""",
    f"""CREATE TABLE ref.vehicle_availability (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  during tstzrange NOT NULL,
  kind text NOT NULL CHECK (kind IN ('maintenance','unavailable','external_booking')),
  note text, source text NOT NULL DEFAULT 'fleet_calendar',
  {TS},
  CONSTRAINT ex_vehicle_avail EXCLUDE USING gist (vehicle_id WITH =, during WITH &&)
)""",
    f"""CREATE TABLE ref.customer (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,
  type ref.customer_type NOT NULL,
  name text NOT NULL, email text, phone text,
  preferred_channel ref.notify_channel NOT NULL DEFAULT 'email',
  default_receiving_hours jsonb,
  is_anonymised boolean NOT NULL DEFAULT false,
  {TS},
  UNIQUE (market_id, external_ref)
)""",
    f"""CREATE TABLE ref.app_user (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint UNIQUE,
  email text NOT NULL UNIQUE, password_hash text NOT NULL,
  roles ref.user_role[] NOT NULL,
  kpi_scopes text[] NOT NULL DEFAULT '{{}}'
    CHECK (kpi_scopes <@ ARRAY['revenue_all','ops']),
  is_active boolean NOT NULL DEFAULT true, last_login_at timestamptz,
  {TS}
)""",
    f"""CREATE TABLE ref.compliance_record (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  type text NOT NULL CHECK (type IN ('DPIA','EMPLOYEE_CONSULTATION','GPS_NOTICE')),
  status text NOT NULL CHECK (status IN ('missing','in_progress','approved')),
  approved_on date, reference text, note text,
  {TS}
)""",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE ref.compliance_record",
    "DROP TABLE ref.app_user",
    "DROP TABLE ref.customer",
    "DROP TABLE ref.vehicle_availability",
    "DROP TABLE ref.vehicle",
    "DROP TABLE ref.mapping_task",
    "DROP VIEW ref.v_product_local",
    "DROP TABLE ref.product_se",
    "DROP TABLE ref.product_global",
    "DROP TABLE ref.handling_group_rule",
    "DROP TABLE ref.special_flag",
    "DROP TABLE ref.handling_group",
    "DROP TABLE ref.location",
    "DROP TABLE ref.market_holiday",
    "DROP TABLE ref.market",
)


def upgrade() -> None:
    """Tạo bảng ref theo 05 mục 3 (mỗi lệnh riêng: asyncpg không nhận nhiều lệnh một lần)."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Gỡ đúng thứ tự ngược lại."""
    for statement in DOWNGRADE:
        op.execute(statement)
