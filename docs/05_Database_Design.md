# 05 — Database Design (CFO MVP)

> Tài liệu giao cho agent code. DDL dưới đây là **nguồn sự thật** của mô hình dữ liệu: agent sinh migration Alembic từ đây, không tự đổi tên bảng/cột/enum. Mọi con số cấu hình nằm trong `ref.market.config` (xem tài liệu 04).
> Nhãn: **[C]** đã chốt trong trao đổi, **[S]** slide, **[T]** bản thiết kế, **[A]** giả định chỉnh được.
>
> Lịch sử: **v1.1** — Thay đổi so với 1.0: (1) bỏ quản lý thiết bị kho khỏi MVP (bảng `equipment_type`, `location_equipment`, `equipment_adjustment`, các cột thiết bị ở `handling_group` và `warehouse_staff`); năng lực đặc biệt (cẩu, ben) vẫn là thuộc tính của **xe**; (2) POD và `improvement_log` gắn với **từng lần giao** (`trip_stop_id`) thay vì `order_id`; (3) thêm trạng thái đơn `HANDLED_EXTERNALLY` cho đơn cần nhiều xe/xe ngoài đội; (4) quy tắc đóng kế hoạch cũ khi lập lại/hủy/giao thất bại; (5) quy tắc khóa chống giữ chỗ vượt tồn kho và công suất; (6) `alert.dedupe_key` chỉ duy nhất khi cảnh báo đang mở; `notification.dedupe_key` gồm cả kế hoạch; (7) cờ `app_user.can_view_revenue` và định nghĩa doanh thu.
>
> **Phiên bản 1.2 (06/11/2026).** (1) Một đơn có thể đi **nhiều xe** cùng kho, cùng ngày, đến gần như cùng lúc: bảng mới `plan.plan_vehicle`, `fulfilment_plan` bỏ `vehicle_id`/`driver_employee_id`, mỗi xe một `delivery_trip`; (2) bỏ trạng thái `MANUAL_PLANNING` và `HANDLED_EXTERNALLY`, bỏ `needs_manual`/`manual_reason`/`external_handoff`; (3) `planning_run.kind` gồm `replan_suggestion` (hệ thống tự gợi ý phương án mới, không giữ chỗ); (4) giữ chỗ lúc lập kế hoạch **không khóa**, chỉ khóa và chặn khi duyệt; (5) sự kiện `PREP_PAUSED`/`PREP_RESUMED`, giờ nhân công thực tế theo từng đoạn; (6) doanh thu: bỏ `can_view_revenue`, thêm `kpi_scopes`, hai view doanh thu; (7) giờ công tính theo đơn vị cơ sở nhỏ nhất.

## 1. Tổng quan

- **PostgreSQL 16**, extension: `pgcrypto`, `btree_gist`, `pg_trgm`.
- **Hai nhóm database:**
  1. **CFO DB** (tài liệu này): 6 schema `ref` (dữ liệu chủ), `hr` (nhân sự), `stg` (nhập liệu), `ops` (vận hành), `plan` (kế hoạch và giữ chỗ), `audit` (nhật ký và KPI).
  2. **Hệ thống nguồn giả lập từng nước** (mục 9): schema `src_<cc>` (ví dụ `src_se`), hợp đồng giống nhau cho mọi nước. Local: DB riêng trong container `source-se`. Staging cloud: schema riêng trong cùng database Supabase.
- **Khóa chính:** `bigint GENERATED ALWAYS AS IDENTITY` cho mọi bảng (trừ bảng khóa ghép). Khóa ngoài đầy đủ.
- **Cột chung** có ở mọi bảng nghiệp vụ (không lặp lại trong DDL cho gọn): `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL DEFAULT now()` (trigger `set_updated_at`).
- **Thời gian:** `timestamptz` (UTC); ngày nghiệp vụ (`date`) hiểu theo `ref.market.timezone`. **Tiền:** `numeric(14,2)`, tiền tệ theo market. **Khối lượng:** kg `numeric(10,3)`. **Thể tích:** m³ `numeric(10,4)`. **Giờ công:** giờ `numeric(8,3)`.
- **Quy tắc đặt tên:** bảng số ít, snake_case; enum đặt trong schema chứa nó; khóa ngoài `<bảng>_id`; ràng buộc `ck_`, `ux_`, `ix_`, `ex_` + tên.
- **Bất biến:** `audit.decision_log`, `ops.milestone_event` chỉ thêm (trigger chặn UPDATE/DELETE). Dữ liệu cá nhân không hard-delete: dùng `status`, ẩn danh sau thời gian lưu giữ.

## 2. Khởi tạo, schema, enum

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS ref;   CREATE SCHEMA IF NOT EXISTS hr;
CREATE SCHEMA IF NOT EXISTS stg;   CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS plan;  CREATE SCHEMA IF NOT EXISTS audit;

-- ref
CREATE TYPE ref.location_type  AS ENUM ('warehouse','store','dispatch_center','head_office');
CREATE TYPE ref.user_role      AS ENUM ('admin','dispatcher','warehouse','sales','driver','customer_service','viewer');
CREATE TYPE ref.mapping_status AS ENUM ('pending','suggested','confirmed','rejected');
CREATE TYPE ref.licence_class  AS ENUM ('B','C','CE');
CREATE TYPE ref.prep_unit      AS ENUM ('line','pallet','m3','bundle','package');
CREATE TYPE ref.customer_type  AS ENUM ('business','consumer');
CREATE TYPE ref.notify_channel AS ENUM ('email','sms_sim');
CREATE TYPE ref.task_status    AS ENUM ('open','in_progress','done');

-- hr
CREATE TYPE hr.employment_type  AS ENUM ('full_time','part_time','temp','contractor');
CREATE TYPE hr.employee_status  AS ENUM ('active','on_leave','terminated');
CREATE TYPE hr.warehouse_role   AS ENUM ('manager','deputy','supervisor','operator','forklift_operator');
CREATE TYPE hr.sales_role       AS ENUM ('retail','trade','store_manager');
CREATE TYPE hr.attendance_status AS ENUM ('planned','present','absent','leave');
CREATE TYPE hr.absence_type     AS ENUM ('leave','sick','training');
CREATE TYPE hr.manager_level    AS ENUM ('primary','deputy');

-- ops
CREATE TYPE ops.date_mode AS ENUM ('exact','range','latest');
CREATE TYPE ops.order_status AS ENUM (
  'SUBMITTED','BLOCKED_UNMAPPED_SKU','PLANNED','NO_FEASIBLE_DATE',
  'APPROVED','PREPARING','GOODS_READY','LOADED','DISPATCHED','DELIVERED','FAILED','CANCELLED');
  -- v1.2: không còn MANUAL_PLANNING (đơn nhiều xe tự lập kế hoạch) và HANDLED_EXTERNALLY
CREATE TYPE ops.event_type AS ENUM (
  'START_PREP','PREP_PAUSED','PREP_RESUMED','GOODS_READY','LOADED','DISPATCHED','DELIVERED','FAILED',
  'SHORTAGE','BREAKAGE','VEHICLE_ISSUE','SHIFT_CHANGE');
CREATE TYPE ops.risk_status AS ENUM ('ON_TRACK','AT_RISK','PREDICTED_LATE','OVERDUE');
CREATE TYPE ops.risk_color  AS ENUM ('green','yellow','orange','red');
CREATE TYPE ops.notif_template AS ENUM ('CONFIRMED','DISPATCHED','DELIVERED','FAILED','DELAY');
CREATE TYPE ops.notif_status   AS ENUM ('draft','queued','sent','failed','suppressed');
CREATE TYPE ops.transfer_status AS ENUM ('suggested','approved','source_confirmed','received','cancelled');
CREATE TYPE ops.negotiation_outcome AS ENUM ('agreed','declined','unreachable');
CREATE TYPE ops.trip_status AS ENUM ('planned','loading','on_road','completed','cancelled');

-- plan
CREATE TYPE plan.plan_status AS ENUM ('proposed','expired','approved','superseded','rejected','manual');
CREATE TYPE plan.res_status  AS ENUM ('held','committed','released','expired','consumed');
```

## 3. Schema `ref` — dữ liệu chủ

```sql
CREATE TABLE ref.market (
  id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code char(2) NOT NULL UNIQUE,                 -- SE, DK, NO, FI
  name text NOT NULL,
  timezone text NOT NULL,                       -- 'Europe/Stockholm'
  locale text NOT NULL DEFAULT 'en',
  currency char(3) NOT NULL,                    -- 'SEK'
  gps_enabled boolean NOT NULL DEFAULT false,   -- [C] cờ GPS theo nước
  shadow_mode boolean NOT NULL DEFAULT false,   -- [S] chạy bóng: không gửi thông báo cho khách
  source_base_url text,                         -- hệ thống nguồn của nước này
  source_api_key_ref text,                      -- tên biến môi trường chứa khóa
  config jsonb NOT NULL DEFAULT '{}'::jsonb,    -- MarketConfig (tài liệu 04, mục 8)
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ref.market_holiday (
  market_id smallint NOT NULL REFERENCES ref.market(id),
  holiday_date date NOT NULL, name text NOT NULL,
  PRIMARY KEY (market_id, holiday_date)
);

CREATE TABLE ref.location (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  type ref.location_type NOT NULL,
  code text NOT NULL, name text NOT NULL, address text,
  lat numeric(8,5), lon numeric(8,5),
  loading_cutoff_time time,                     -- chỉ kho: quá giờ này thì lên hàng ca sau [S]
  efficiency_factor numeric(4,2) NOT NULL DEFAULT 1.00,  -- [C] chưa có UI, mặc định 1,0
  owner_employee_id bigint,                     -- FK thêm sau (hr.employee) [C]
  is_active boolean NOT NULL DEFAULT true,
  UNIQUE (market_id, code),
  CONSTRAINT ck_wh_cutoff CHECK (type <> 'warehouse' OR loading_cutoff_time IS NOT NULL),
  CONSTRAINT ck_geo CHECK (type NOT IN ('warehouse','store') OR (lat IS NOT NULL AND lon IS NOT NULL))
);

-- v1.1: KHÔNG có bảng thiết bị kho trong MVP (theo slide: equipment-level scheduling ngoài MVP).
-- Giả định [A]: mọi kho có đủ thiết bị cho N1–N6; định mức giờ công đã bao gồm thời gian dùng thiết bị.
-- Năng lực đặc biệt khi giao (cẩu, ben) là thuộc tính của xe: ref.vehicle.capabilities + handling_group.vehicle_requirement.

-- N1–N6 + định mức giờ công DÙNG CHUNG mọi kho [C]; IT quản lý
CREATE TABLE ref.handling_group (
  id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code text NOT NULL UNIQUE,                    -- 'N1'..'N6'
  name text NOT NULL, description text,
  prep_unit ref.prep_unit NOT NULL,
  fixed_hours numeric(6,3) NOT NULL DEFAULT 0,          -- cố định mỗi DÒNG hàng
  labour_hours_per_unit numeric(6,3) NOT NULL,          -- giờ công / đơn vị chuẩn bị
  min_crew smallint NOT NULL DEFAULT 1,                 -- chỉ hiển thị, chưa ép buộc
  vehicle_requirement text[] NOT NULL DEFAULT '{}'      -- ví dụ {'dump'} cho N4
);
CREATE TABLE ref.special_flag (
  code text PRIMARY KEY,                        -- FRAGILE, SPECIAL_STORAGE, HAZARDOUS, FAR_OR_OUTDOOR
  name text NOT NULL, multiplier numeric(4,2) NOT NULL CHECK (multiplier >= 1)
);
CREATE TABLE ref.handling_group_rule (          -- bảng quy tắc cứng gán nhóm, IT sửa [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  priority smallint NOT NULL DEFAULT 100,
  category_like text NOT NULL,                  -- ví dụ 'Cement%'
  min_weight_kg numeric(10,3), max_weight_kg numeric(10,3),
  handling_group_id smallint NOT NULL REFERENCES ref.handling_group(id),
  flags text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE ref.product_global (               -- sản phẩm chung, chỉ IT tạo/sửa [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code text NOT NULL UNIQUE,                    -- mã toàn cầu (canonical_id)
  name text NOT NULL, category text NOT NULL,
  gtin text UNIQUE,
  base_unit text NOT NULL,                      -- đơn vị cơ sở, ví dụ 'bag','sheet','m'
  weight_kg numeric(10,3) NOT NULL CHECK (weight_kg > 0),   -- trên 1 đơn vị cơ sở
  volume_m3 numeric(10,4) NOT NULL CHECK (volume_m3 > 0),
  handling_group_id smallint NOT NULL REFERENCES ref.handling_group(id),
  base_units_per_prep_unit numeric(12,4),       -- ví dụ 40 bao = 1 pallet; NULL nếu prep_unit = 'line'
  flags text[] NOT NULL DEFAULT '{}',
  created_by bigint
);

-- Mỗi nước một bảng sản phẩm riêng [C]. Mẫu cho Thụy Điển; tools/add_market.py sinh bảng cho nước mới.
CREATE TABLE ref.product_se (
  local_sku text PRIMARY KEY,
  name text NOT NULL, category text NOT NULL, gtin text,
  sale_unit text NOT NULL,
  units_to_base numeric(12,4) NOT NULL DEFAULT 1 CHECK (units_to_base > 0),
  unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0), currency char(3) NOT NULL DEFAULT 'SEK',
  weight_kg numeric(10,3), volume_m3 numeric(10,4),           -- tham khảo từ nguồn
  global_product_id bigint REFERENCES ref.product_global(id),
  mapping_status ref.mapping_status NOT NULL DEFAULT 'pending',
  mapped_by bigint, mapped_at timestamptz,
  source_updated_at timestamptz, synced_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_se_confirmed CHECK (mapping_status <> 'confirmed'
        OR (global_product_id IS NOT NULL AND mapped_by IS NOT NULL))
);
CREATE INDEX ix_product_se_name_trgm ON ref.product_se USING gin (name gin_trgm_ops);
CREATE INDEX ix_product_se_gtin ON ref.product_se (gtin);

-- View hợp nhất để engine/mapping đọc. tools/add_market.py tái tạo view khi thêm nước.
CREATE VIEW ref.v_product_local AS
  SELECT 'SE'::char(2) AS market_code, local_sku, name, category, gtin, sale_unit, units_to_base,
         unit_price, currency, global_product_id, mapping_status FROM ref.product_se;

CREATE TABLE ref.mapping_task (                 -- hàng đợi cho IT [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  local_sku text NOT NULL,
  status ref.task_status NOT NULL DEFAULT 'open',
  candidates jsonb NOT NULL DEFAULT '[]',       -- [{global_product_id, reason:'gtin'|'name_sim', score}]
  blocked_order_count int NOT NULL DEFAULT 0,
  assigned_to bigint, resolved_by bigint, resolved_at timestamptz,
  UNIQUE (market_id, local_sku)
);

CREATE TABLE ref.vehicle (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  home_warehouse_id bigint NOT NULL REFERENCES ref.location(id),   -- xe thuộc kho [C]
  code text NOT NULL UNIQUE, plate text NOT NULL, name text NOT NULL,
  capacity_kg numeric(10,3) NOT NULL CHECK (capacity_kg > 0),
  capacity_m3 numeric(10,4) NOT NULL CHECK (capacity_m3 > 0),
  capabilities text[] NOT NULL DEFAULT '{}',    -- 'crane','tail_lift','dump','long_bed'
  required_licence ref.licence_class NOT NULL,
  allowed_group_ids smallint[] NOT NULL DEFAULT '{}',   -- nhóm N chở được; rỗng = tất cả
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('available','maintenance','retired')),
  max_permissible_mass_kg numeric(10,2) CHECK (max_permissible_mass_kg > 0),   -- Q12b (0009)
  regulation_561_scope text NOT NULL DEFAULT 'unknown'                          -- Q12b: unknown → fail closed
    CHECK (regulation_561_scope IN ('in_scope','out_of_scope','unknown'))
);
CREATE TABLE ref.vehicle_availability (         -- bận/rảnh theo khoảng thời gian
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  during tstzrange NOT NULL, kind text NOT NULL CHECK (kind IN ('maintenance','unavailable','external_booking')),
  note text, source text NOT NULL DEFAULT 'fleet_calendar',
  CONSTRAINT ex_vehicle_avail EXCLUDE USING gist (vehicle_id WITH =, during WITH &&)
);

CREATE TABLE ref.customer (                     -- đồng bộ từ hệ thống nguồn [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,
  type ref.customer_type NOT NULL,
  name text NOT NULL, email text, phone text,
  preferred_channel ref.notify_channel NOT NULL DEFAULT 'email',
  default_receiving_hours jsonb,                -- {"mon":["07:00","16:00"], ...} hoặc NULL
  is_anonymised boolean NOT NULL DEFAULT false,
  UNIQUE (market_id, external_ref)
);

CREATE TABLE ref.app_user (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint UNIQUE,                    -- FK thêm sau; NULL = tài khoản hệ thống
  email text NOT NULL UNIQUE, password_hash text NOT NULL,
  roles ref.user_role[] NOT NULL,
  kpi_scopes text[] NOT NULL DEFAULT '{}'
    CHECK (kpi_scopes <@ ARRAY['revenue_all','ops']),  -- v1.2: revenue_all (Business owner), ops (KPI vận hành); sao chép từ position.default_kpi_scopes khi tạo
  is_active boolean NOT NULL DEFAULT true, last_login_at timestamptz
);

CREATE TABLE ref.compliance_record (            -- DPIA, tham vấn nhân viên, thông báo GPS [S][C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  type text NOT NULL CHECK (type IN ('DPIA','EMPLOYEE_CONSULTATION','GPS_NOTICE')),
  status text NOT NULL CHECK (status IN ('missing','in_progress','approved')),
  approved_on date, reference text, note text
);
```

## 4. Schema `hr` — nhân sự **[C]**

Một bảng `employee` + **5 bảng con**: `warehouse_staff`, `sales_staff`, `dispatcher_staff`, `driver_staff`, `cs_staff`. Admin chỉ là quyền (`app_user.roles`), giao cho nhân viên IT. Business owner và Project Lead là nhân viên không có bảng con, chỉ có quyền `viewer`; hai người phân biệt bằng `ref.app_user.kpi_scopes` (Business owner `{revenue_all}`, Project Lead `{ops}`). Không thêm vai trò mới. Công nhân kho không có tài khoản. Mỗi người **chỉ có một phân công đang hiệu lực** (một nơi tại một thời điểm).

```sql
CREATE TABLE hr.position (
  code text PRIMARY KEY, name text NOT NULL,
  grp text NOT NULL CHECK (grp IN ('warehouse','store','transport','central')),
  default_roles ref.user_role[] NOT NULL DEFAULT '{}',
  default_kpi_scopes text[] NOT NULL DEFAULT '{}'      -- v1.2: BUSINESS_OWNER {revenue_all}; PROJECT_LEAD, DISPATCHER, WAREHOUSE_MANAGER, WAREHOUSE_DEPUTY {ops}
);
-- Seed: WAREHOUSE_MANAGER, WAREHOUSE_DEPUTY, WAREHOUSE_SUPERVISOR, WAREHOUSE_OPERATOR, FORKLIFT_OPERATOR,
--       DRIVER, DISPATCHER, STORE_MANAGER, SALES_RETAIL, SALES_TRADE, CUSTOMER_SERVICE,
--       IT_INTEGRATION (admin), BUSINESS_OWNER (viewer), PROJECT_LEAD (viewer)

CREATE TABLE hr.employee (
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
  UNIQUE (market_id, employee_no)
);
ALTER TABLE ref.app_user ADD CONSTRAINT fk_user_emp FOREIGN KEY (employee_id) REFERENCES hr.employee(id);
ALTER TABLE ref.location ADD CONSTRAINT fk_loc_owner FOREIGN KEY (owner_employee_id) REFERENCES hr.employee(id);
ALTER TABLE ref.product_se ADD CONSTRAINT fk_pse_mapper FOREIGN KEY (mapped_by) REFERENCES hr.employee(id);
ALTER TABLE ref.product_global ADD CONSTRAINT fk_pg_creator FOREIGN KEY (created_by) REFERENCES hr.employee(id);

CREATE TABLE hr.employee_assignment (           -- phân công công tác; một phân công hiệu lực/người
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  location_id bigint NOT NULL REFERENCES ref.location(id),
  start_date date NOT NULL, end_date date,
  CHECK (end_date IS NULL OR end_date >= start_date)
);
CREATE UNIQUE INDEX ux_one_active_assignment ON hr.employee_assignment (employee_id) WHERE end_date IS NULL;

CREATE TABLE hr.location_manager (              -- quản lý kho/cửa hàng
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  location_id bigint NOT NULL REFERENCES ref.location(id),
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  level hr.manager_level NOT NULL,
  can_approve boolean NOT NULL DEFAULT true,    -- quyền xác nhận chuyển kho, sửa ca, đóng ngoại lệ
  valid_from date NOT NULL, valid_to date
);
CREATE UNIQUE INDEX ux_one_primary_manager ON hr.location_manager (location_id)
  WHERE level = 'primary' AND valid_to IS NULL;

CREATE TABLE hr.warehouse_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  role hr.warehouse_role NOT NULL,
  counts_in_capacity boolean NOT NULL DEFAULT true          -- manager/supervisor mặc định false
);
CREATE TABLE hr.sales_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  role hr.sales_role NOT NULL
);
CREATE TABLE hr.dispatcher_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  can_send_delay_notice boolean NOT NULL DEFAULT true
);
CREATE TABLE hr.driver_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id),
  home_warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  licence_class ref.licence_class NOT NULL, licence_expires_on date NOT NULL, adr boolean NOT NULL DEFAULT false
);
CREATE TABLE hr.cs_staff (
  employee_id bigint PRIMARY KEY REFERENCES hr.employee(id), team text
);

CREATE TABLE hr.shift_template (                -- ca mẫu của kho
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  weekday smallint NOT NULL CHECK (weekday BETWEEN 1 AND 7),
  start_time time NOT NULL, end_time time NOT NULL,
  useful_hours_per_staff numeric(4,2) NOT NULL,  -- giờ hữu ích/người/ca (đã trừ nghỉ) [A] 7.0
  expected_staff smallint NOT NULL,
  UNIQUE (warehouse_id, weekday, start_time)
);
-- Q12 / Q12b (đã duyệt 07/11/2026, migration 0009): lịch ca chính thức cho nhân viên kho VÀ tài xế, do Warehouse
-- Manager (quản lý chính/phó can_approve của kho) lập. expected_staff chỉ để so sánh, không tự chia/dồn ca.
-- Đổi ca = hủy dòng cũ + thêm dòng mới (không UPDATE giờ, không DELETE), ghi SHIFT_CHANGED cùng transaction.
CREATE TABLE hr.employee_shift_schedule (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  work_date date NOT NULL,                        -- ngày bắt đầu ca (múi giờ market)
  shift_template_id bigint REFERENCES hr.shift_template(id),
  start_time time, end_time time,                 -- giờ riêng; end < start = ca qua nửa đêm
  break_start time, break_end time,
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','cancelled')),
  assigned_by bigint NOT NULL REFERENCES hr.employee(id), assigned_at timestamptz NOT NULL,
  cancelled_by bigint REFERENCES hr.employee(id), cancelled_at timestamptz,
  reason_text text,                               -- bắt buộc khi sửa ngày đã qua (service)
  CONSTRAINT ck_shift_source CHECK (shift_template_id IS NOT NULL OR start_time IS NOT NULL),
  CONSTRAINT ck_shift_times CHECK ((start_time IS NULL) = (end_time IS NULL)),
  CONSTRAINT ck_shift_break CHECK ((break_start IS NULL) = (break_end IS NULL)),
  CONSTRAINT ck_shift_cancelled CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
);
CREATE UNIQUE INDEX ux_shift_one_per_day ON hr.employee_shift_schedule (employee_id, work_date)
  WHERE status = 'scheduled';                     -- Q12a: tối đa 1 ca chính thức/người/ngày
CREATE INDEX ix_shift_schedule_wh_date ON hr.employee_shift_schedule (warehouse_id, work_date);

-- Q12b (migration 0009): kỳ làm việc/lái đã xảy ra hoặc đã cam kết của tài xế — nguồn kiểm nghỉ 11 giờ và giờ lái.
CREATE TABLE hr.driver_duty_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  duty_start timestamptz NOT NULL, duty_end timestamptz NOT NULL,
  driving_min int NOT NULL DEFAULT 0 CHECK (driving_min >= 0),
  source text NOT NULL CHECK (source IN ('trip','shift','manual_record')),
  trip_id bigint REFERENCES ops.delivery_trip(id),
  recorded_by bigint REFERENCES hr.employee(id),
  CONSTRAINT ck_duty_interval CHECK (duty_end > duty_start)
);
CREATE INDEX ix_driver_duty_log_emp ON hr.driver_duty_log (employee_id, duty_start);

CREATE TABLE hr.attendance (                    -- điểm danh từng người (kho + tài xế) [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  work_date date NOT NULL,
  shift_template_id bigint REFERENCES hr.shift_template(id),
  status hr.attendance_status NOT NULL DEFAULT 'planned',
  recorded_by bigint REFERENCES hr.employee(id), recorded_at timestamptz,
  UNIQUE (employee_id, work_date)
);
CREATE TABLE hr.absence (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  start_date date NOT NULL, end_date date NOT NULL, type hr.absence_type NOT NULL,
  approved boolean NOT NULL DEFAULT false, approved_by bigint REFERENCES hr.employee(id),
  CHECK (end_date >= start_date)
);
```

**ASM-006/007 được chủ dự án chốt:** đổi phân công/quản lý/owner, nghỉ việc, thay lịch ca và sửa điểm danh phải có audit actor + before/after; thay đổi hồi tố bắt buộc lý do, giới hạn quyền. Lịch phân ca chính thức do Warehouse Manager quản lý, điểm danh chỉ ghi hiện diện thực tế. Bộ máy không tự chọn ca dựa vào `expected_staff`. Quy định này là **thiết kế mục tiêu** và phải được xác minh ở migration/API trước khi code.

**Quy tắc dữ liệu nhân sự:** (1) nhân viên `active` phải có đúng một phân công đang hiệu lực (kiểm ở service); (2) mỗi kho/cửa hàng có đúng một quản lý chính đang hiệu lực (ràng buộc DB ở trên) và quản lý đó phải có phân công tại chính nơi đó (kiểm ở service); (3) `owner_employee_id` mặc định là quản lý chính, gán lại được; (4) nhân viên `terminated`: khóa `app_user.is_active`, giữ lịch sử, ẩn danh sau `data_retention_days`; (5) công suất kho dùng `counts_in_capacity = true` và điểm danh `present` (hoặc `planned` cho ngày tương lai, trừ nghỉ phép đã duyệt).

## 5. Schema `stg` — nhập liệu từ hệ thống nguồn

```sql
CREATE TABLE stg.sync_run (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  market_id smallint NOT NULL REFERENCES ref.market(id),
  entity text NOT NULL CHECK (entity IN ('orders','customers','products','stock','inbound','fleet')),
  kind text NOT NULL DEFAULT 'api' CHECK (kind IN ('api','csv')),
  checkpoint_from timestamptz, checkpoint_to timestamptz,
  file_name text, file_sha256 text,               -- chỉ khi kind = 'csv' (adapter dự phòng)
  started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','partial','failed')),
  rows_in int NOT NULL DEFAULT 0, rows_ok int NOT NULL DEFAULT 0, rows_rejected int NOT NULL DEFAULT 0,
  data_as_of timestamptz,                         -- thời điểm dữ liệu nguồn (độ tươi)
  error text
);
CREATE UNIQUE INDEX ux_sync_file ON stg.sync_run (market_id, entity, file_sha256)
  WHERE file_sha256 IS NOT NULL AND status IN ('ok','partial');
CREATE TABLE stg.sync_reject (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES stg.sync_run(id),
  external_key text, reason_code text NOT NULL,   -- BAD_QTY, UNKNOWN_WAREHOUSE, BAD_DATE, MISSING_COORDS, ...
  reason text, raw jsonb
);
CREATE TABLE stg.sync_checkpoint (               -- mốc updated_since cho từng thực thể [T]
  market_id smallint NOT NULL REFERENCES ref.market(id),
  entity text NOT NULL, last_updated_since timestamptz NOT NULL,
  PRIMARY KEY (market_id, entity)
);
```

Quy tắc: **khóa tự nhiên** (market, external_ref) để upsert; chạy lại không nhân đôi; dòng lỗi vào `sync_reject`, không làm hỏng cả lượt; chỉ cập nhật `sync_checkpoint` khi lượt chạy thành công; kéo `updated_since = checkpoint − 2 phút` để không sót bản ghi thay đổi sát mốc.

## 6. Schema `ops` — vận hành

```sql
CREATE TABLE ops.stock_snapshot (                -- ảnh chụp ghi đè mỗi lần đồng bộ, không cộng dồn
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  on_hand numeric(12,3) NOT NULL CHECK (on_hand >= 0),
  wms_reserved numeric(12,3) NOT NULL DEFAULT 0 CHECK (wms_reserved >= 0),   -- giữ cho kênh khác
  as_of timestamptz NOT NULL, run_id bigint REFERENCES stg.sync_run(id),
  PRIMARY KEY (warehouse_id, global_product_id)
);
CREATE TABLE ops.inbound_shipment (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  inbound_ref text NOT NULL, warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  qty numeric(12,3) NOT NULL CHECK (qty > 0), eta_date date NOT NULL,
  confirmed boolean NOT NULL DEFAULT false,      -- chưa xác nhận thì KHÔNG tính vào ATP [S]
  received boolean NOT NULL DEFAULT false,       -- đã về thì bỏ khỏi ATP (tránh tính hai lần)
  source text NOT NULL DEFAULT 'erp' CHECK (source IN ('erp','transfer')),
  transfer_id bigint, run_id bigint REFERENCES stg.sync_run(id),
  UNIQUE (inbound_ref, global_product_id)
);

CREATE TABLE ops.stock_transfer (                -- gợi ý bằng quy tắc, dispatcher duyệt, kho nguồn xác nhận [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint, from_warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  to_warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  status ops.transfer_status NOT NULL DEFAULT 'suggested',
  lead_days smallint NOT NULL, expected_arrival_date date,
  suggestion jsonb NOT NULL,                     -- lý do quy tắc: đủ hàng, lead time, khoảng cách
  approved_by bigint REFERENCES hr.employee(id), approved_at timestamptz,
  source_confirmed_by bigint REFERENCES hr.employee(id), source_confirmed_at timestamptz,
  received_at timestamptz,
  CHECK (from_warehouse_id <> to_warehouse_id)
);
CREATE TABLE ops.stock_transfer_line (
  transfer_id bigint NOT NULL REFERENCES ops.stock_transfer(id),
  global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  qty numeric(12,3) NOT NULL CHECK (qty > 0), PRIMARY KEY (transfer_id, global_product_id)
);
ALTER TABLE ops.inbound_shipment ADD CONSTRAINT fk_inb_transfer FOREIGN KEY (transfer_id) REFERENCES ops.stock_transfer(id);

CREATE TABLE ops.customer_order (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_no text NOT NULL UNIQUE,                 -- 'SE-2026-000123' (sinh khi nhập CFO)
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,                    -- mã đơn ở hệ thống nguồn
  source_version int NOT NULL DEFAULT 1,         -- phiên bản đơn ở nguồn
  version int NOT NULL DEFAULT 1,                -- tăng khi dữ liệu kế hoạch của đơn đổi (ngày, hàng, địa chỉ)
  customer_id bigint NOT NULL REFERENCES ref.customer(id),
  contact_name text NOT NULL, contact_phone text, contact_email text,   -- bản chụp [C]
  delivery_address text NOT NULL, delivery_lat numeric(8,5) NOT NULL, delivery_lon numeric(8,5) NOT NULL,
  receiving_restrictions text, special_requirements text,
  date_mode ops.date_mode NOT NULL,              -- 3 dạng yêu cầu ngày [C]
  date_from date, date_to date NOT NULL,         -- exact: from=to; range: from<to; latest: from NULL
  window_start time, window_end time,            -- khung giờ nhận hàng khách yêu cầu (tùy chọn) [C]
  order_date timestamptz NOT NULL,
  sales_employee_id bigint REFERENCES hr.employee(id),
  origin_store_id bigint REFERENCES ref.location(id),
  status ops.order_status NOT NULL DEFAULT 'SUBMITTED',
  block_reason text,
  committed_date date, promise_start timestamptz, promise_end timestamptz,   -- ngày cam kết ≠ ngày yêu cầu [T]
  approved_plan_id bigint,                       -- FK thêm sau
  currency char(3) NOT NULL, total_amount numeric(14,2) NOT NULL DEFAULT 0,   -- total_amount = Σ line_total (đơn giá chụp lúc đặt × số lượng); không đổi sau khi giao
  submitted_at timestamptz NOT NULL, planned_at timestamptz, approved_at timestamptz,
  delivered_at timestamptz, closed_at timestamptz,
  UNIQUE (market_id, external_ref),
  CONSTRAINT ck_dates CHECK (
    (date_mode = 'exact'  AND date_from = date_to) OR
    (date_mode = 'range'  AND date_from < date_to) OR
    (date_mode = 'latest' AND date_from IS NULL)),
  CONSTRAINT ck_window CHECK ((window_start IS NULL) = (window_end IS NULL) AND (window_start IS NULL OR window_start < window_end))
);
CREATE TABLE ops.order_line (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id) ON DELETE CASCADE,
  line_no smallint NOT NULL, local_sku text NOT NULL,
  global_product_id bigint REFERENCES ref.product_global(id),   -- NULL tới khi ánh xạ xong
  qty_sale numeric(12,3) NOT NULL CHECK (qty_sale > 0),
  qty_base numeric(12,3),                         -- = qty_sale × units_to_base; tính khi ánh xạ xong
  unit_price numeric(12,2) NOT NULL, line_total numeric(14,2) NOT NULL,
  UNIQUE (order_id, line_no), UNIQUE (order_id, local_sku)
);

CREATE TABLE ops.order_transition (              -- bảng tra chuyển trạng thái hợp lệ
  from_status ops.order_status NOT NULL, to_status ops.order_status NOT NULL,
  requires_reason boolean NOT NULL DEFAULT false, allowed_roles ref.user_role[] NOT NULL,
  PRIMARY KEY (from_status, to_status)
);
-- Q14 (đã duyệt phương án A 07/11/2026, migration 0009): quyết định luồng cfo/legacy, không đổi sau khi lưu.
-- 'unresolved' KHÔNG được lưu. customer_order chỉ tạo khi route = 'cfo'. Không bảo đảm chặn điều phối tay ngoài CFO.
CREATE TABLE ops.order_routing (
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,
  route text NOT NULL CHECK (route IN ('cfo','legacy')),
  reason_code text NOT NULL CHECK (reason_code IN ('all_confirmed','unmapped_sku','manual_started')),
  unmapped_skus text[] NOT NULL DEFAULT '{}',
  decided_at timestamptz NOT NULL, decided_source_version int NOT NULL,
  decided_by_user_id bigint NOT NULL REFERENCES ref.app_user(id),            -- 0011: không có quyết định hệ thống
  decided_by_role text NOT NULL CHECK (decided_by_role IN ('sales','dispatcher')),   -- 0011 (DEC-ROUTING-002)
  reason_text text,                                                          -- 0011: bắt buộc khi manual_started
  acknowledged_by_user_id bigint REFERENCES ref.app_user(id), acknowledged_at timestamptz,
  PRIMARY KEY (market_id, external_ref),
  CONSTRAINT ck_routing_reason CHECK ((route = 'cfo') = (reason_code = 'all_confirmed')),
  CONSTRAINT ck_routing_ack CHECK ((acknowledged_by_user_id IS NULL) = (acknowledged_at IS NULL)),  -- 0010
  CONSTRAINT ck_routing_manual_reason CHECK (                                                       -- 0011
    reason_code <> 'manual_started' OR (reason_text IS NOT NULL AND btrim(reason_text) <> ''))
);
-- 0011 / DEC-ROUTING-002: polling chỉ đồng bộ dữ liệu nguồn, KHÔNG ghi bảng này. Chỉ Sales "Sync & check routing" hoặc
-- Dispatcher kiểm tra được ủy quyền mới ghi, trên dữ liệu nguồn mới nhất và trạng thái mapping lúc đó. Đã ghi `cfo` mà
-- Sales báo đã điều phối tay → KHÔNG đổi luồng; ghi ROUTING_MANUAL_CONFLICT_ESCALATED + alert ROUTING_MANUAL_CONFLICT
-- cho Dispatcher.
-- 0010: trigger ops.trg_guard_order_routing (BEFORE UPDATE OR DELETE) — quyết định BẤT BIẾN: không đổi khóa, route,
-- reason_code, unmapped_skus, decided_*; không DELETE; chỉ ghi MỘT LẦN cặp acknowledged_by_user_id/acknowledged_at.
CREATE TABLE ops.date_negotiation (              -- chỉ đổi ngày khi khách đồng ý [S][C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  proposed_date date NOT NULL, outcome ops.negotiation_outcome NOT NULL,
  channel text NOT NULL CHECK (channel IN ('phone','email','in_person')),
  contacted_at timestamptz NOT NULL, recorded_by bigint NOT NULL REFERENCES hr.employee(id),
  note text, remind_at timestamptz                 -- 'unreachable' => nhắc lại sau 24 giờ
);

CREATE TABLE ops.delivery_trip (                 -- MVP: một chuyến = một xe = một điểm dừng (không ghép đơn);
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,   -- v1.2: đơn nhiều xe có nhiều chuyến, mỗi xe một chuyến
  plan_vehicle_id bigint,                        -- FK tới plan.plan_vehicle (thêm sau)
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
  status ops.trip_status NOT NULL DEFAULT 'planned',
  depart_planned_at timestamptz NOT NULL, depart_actual_at timestamptz, ended_at timestamptz
);
CREATE TABLE ops.trip_stop (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trip_id bigint NOT NULL REFERENCES ops.delivery_trip(id),
  seq smallint NOT NULL DEFAULT 1, order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  eta_planned_at timestamptz NOT NULL, arrived_at timestamptz, completed_at timestamptz,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','delivered','failed','cancelled')),
  UNIQUE (trip_id, seq), UNIQUE (trip_id, order_id)
);
-- v1.2: bỏ ux_stop_active_order (một đơn nhiều xe có nhiều trip_stop pending cùng lúc).
-- Trạng thái đơn tổng hợp từ các chuyến: LOADED khi MỌI xe đã lên hàng; DISPATCHED khi xe ĐẦU TIÊN xuất phát;
-- DELIVERED khi MỌI trip_stop delivered; FAILED khi mọi chuyến đã kết thúc và có ít nhất một stop failed
-- (ghi phần đã giao vào payload; dispatcher xếp lại phần còn thiếu).

CREATE TABLE ops.milestone_event (               -- bất biến; nhân viên chỉ nhập sự thật, không có bước duyệt [S]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  plan_id bigint, trip_id bigint REFERENCES ops.delivery_trip(id),   -- v1.2: LOADED/DISPATCHED/DELIVERED/FAILED theo từng xe
  event_type ops.event_type NOT NULL,
  occurred_at timestamptz NOT NULL,              -- giờ thật ở hiện trường (có thể sớm hơn received_at khi offline)
  received_at timestamptz NOT NULL DEFAULT now(),
  actor_user_id bigint NOT NULL REFERENCES ref.app_user(id),
  actor_employee_id bigint REFERENCES hr.employee(id),      -- bản chụp lúc ghi
  payload jsonb NOT NULL DEFAULT '{}',           -- shortage/breakage: sku, qty, note; vehicle_issue: note;
                                                 -- START_PREP, PREP_RESUMED: {crew_size} (bắt buộc, số người làm đoạn này)
                                                 -- PREP_PAUSED: {note?}; GOODS_READY: {crew_size?} (sửa nếu đổi giữa chừng)
  idempotency_key text NOT NULL UNIQUE
);
CREATE TABLE ops.proof_of_delivery (           -- v1.1: MỘT bản ghi cho MỖI LẦN GIAO (trip_stop), không phải mỗi đơn
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trip_stop_id bigint NOT NULL UNIQUE REFERENCES ops.trip_stop(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),   -- để tra cứu nhanh; một đơn có thể có nhiều POD (thất bại rồi giao lại)
  result text NOT NULL CHECK (result IN ('delivered','failed')),
  completed_at timestamptz NOT NULL, recipient_name text, note text,
  failure_reason text CHECK (failure_reason IN
    ('customer_absent','site_inaccessible','refused','wrong_address','vehicle_breakdown','goods_damaged','other')),
  CHECK ((result = 'failed') = (failure_reason IS NOT NULL))
);
CREATE INDEX ix_pod_order ON ops.proof_of_delivery (order_id, completed_at);
CREATE UNIQUE INDEX ux_pod_one_delivered ON ops.proof_of_delivery (order_id) WHERE result = 'delivered';
CREATE TABLE ops.eta_forecast (                  -- mỗi lần tính lại một dòng (phiên bản ETA)
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  version int NOT NULL, computed_at timestamptz NOT NULL DEFAULT now(),
  trigger text NOT NULL,                         -- event:<type> | gps | source_change | overdue_milestone | morning_check | approval
  planned_eta timestamptz NOT NULL, forecast_eta timestamptz NOT NULL,
  commitment_deadline timestamptz NOT NULL,      -- = promise_end
  reserve_total_min int NOT NULL, slack_min int NOT NULL, consumption_pct numeric(6,2) NOT NULL,
  consecutive_negative smallint NOT NULL DEFAULT 0,
  risk_status ops.risk_status NOT NULL, risk_color ops.risk_color NOT NULL,
  UNIQUE (order_id, version)
);
CREATE TABLE ops.alert (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint REFERENCES ops.customer_order(id), market_id smallint NOT NULL REFERENCES ref.market(id),
  level text NOT NULL CHECK (level IN ('info','warning','critical')),
  type text NOT NULL,                            -- RISK_ORANGE, PREDICTED_LATE, OVERDUE, GPS_LOST, STALE_DATA, EXCEPTION,
                                                 -- MAPPING_BLOCK, SYNC_FAILED, ORDER_CHANGED_AFTER_APPROVAL, HOLD_EXPIRING,
                                                 -- PLAN_INVALIDATED, REPLAN_SUGGESTED (v1.2: details.run_id của phương án gợi ý)
                                                 -- ROUTING_MANUAL_CONFLICT (DEC-ROUTING-002: đơn cfo bị báo đã điều phối tay)
  message text NOT NULL, target_roles ref.user_role[] NOT NULL,
  dedupe_key text NOT NULL,                      -- v1.1: chỉ duy nhất khi cảnh báo còn mở (xem chỉ mục dưới)
  acknowledged_by bigint REFERENCES hr.employee(id), acknowledged_at timestamptz, resolved_at timestamptz
);
CREATE UNIQUE INDEX ux_alert_open_dedupe ON ops.alert (dedupe_key) WHERE resolved_at IS NULL;
CREATE TABLE ops.notification (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  template ops.notif_template NOT NULL, channel ref.notify_channel NOT NULL,
  recipient text NOT NULL, subject text, body text NOT NULL,
  eta_window jsonb,                              -- {start,end} đã thông báo, để so lệch ≥ 30 phút
  status ops.notif_status NOT NULL DEFAULT 'queued',
  scheduled_for timestamptz NOT NULL DEFAULT now(),   -- giờ yên lặng 21:00–07:00 (trừ DELAY)
  attempts smallint NOT NULL DEFAULT 0, last_error text, sent_at timestamptz,
  created_by_employee_id bigint REFERENCES hr.employee(id),  -- DELAY: dispatcher bấm gửi [C]
  suppressed_reason text,
  plan_id bigint,                                -- v1.1: kế hoạch liên quan (CONFIRMED/DISPATCHED/DELIVERED/FAILED)
  dedupe_key text NOT NULL UNIQUE                -- v1.1: '<order_id>:<template>:<plan_id|trip_stop_id>:<status>' để lập lại kế hoạch
                                                 -- vẫn gửi được CONFIRMED mới; DELAY: thêm phiên bản ETA
);
CREATE TABLE ops.customer_contact_log (          -- CS ghi nhật ký liên hệ [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint REFERENCES ops.customer_order(id), customer_id bigint NOT NULL REFERENCES ref.customer(id),
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  channel text NOT NULL CHECK (channel IN ('phone','email','chat')),
  reason_code text NOT NULL CHECK (reason_code IN ('where_is_my_order','change_request','complaint','delay_inquiry','other')),
  note text, contacted_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ops.vehicle_position (              -- GPS [C]; chỉ dispatcher xem; xóa 30 ngày sau chuyến
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  trip_id bigint NOT NULL REFERENCES ops.delivery_trip(id),
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id),
  lat numeric(8,5) NOT NULL, lon numeric(8,5) NOT NULL, accuracy_m numeric(8,1),
  recorded_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
  source text NOT NULL CHECK (source IN ('device','simulator'))
);
CREATE TABLE ops.idempotency_key (
  key text NOT NULL, user_id bigint NOT NULL REFERENCES ref.app_user(id),
  endpoint text NOT NULL, request_hash text NOT NULL, response_status int, response_body jsonb,
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (key, user_id)
);
```

### Seed bảng chuyển trạng thái `ops.order_transition`

| Từ | Đến | Cần lý do | Vai trò |
|---|---|---|---|
| (tạo mới) | SUBMITTED | | system |
| SUBMITTED | PLANNED / BLOCKED_UNMAPPED_SKU / NO_FEASIBLE_DATE | | system |
| BLOCKED_UNMAPPED_SKU | SUBMITTED | | system (khi ánh xạ xong) |
| PLANNED | APPROVED | kế hoạch tay hoặc chọn khác: có | dispatcher |
| NO_FEASIBLE_DATE | APPROVED | có (kế hoạch tay) | dispatcher (v1.2) |
| PLANNED | SUBMITTED (chạy lại) | có | dispatcher |
| NO_FEASIBLE_DATE | SUBMITTED | có (cần bản ghi `agreed`) | dispatcher |
| NO_FEASIBLE_DATE, PLANNED | CANCELLED | có | dispatcher |
| APPROVED | PREPARING / SUBMITTED (lập lại) | lập lại: có | warehouse / dispatcher |
| PREPARING, GOODS_READY, LOADED, FAILED | APPROVED (duyệt phương án gợi ý lập lại) | có | dispatcher (v1.2) |
| PREPARING | GOODS_READY | | warehouse |
| GOODS_READY | LOADED | | warehouse |
| LOADED | DISPATCHED | | driver |
| DISPATCHED | DELIVERED / FAILED | FAILED: có | driver |
| FAILED | SUBMITTED (xếp lại) | có | dispatcher |
| APPROVED, PREPARING, GOODS_READY, LOADED | CANCELLED | có | dispatcher |

Trigger `ops.trg_check_transition` (BEFORE UPDATE OF status ON `ops.customer_order`) từ chối chuyển không có trong bảng.

**Đóng kế hoạch cũ (bắt buộc, cùng một transaction với việc đổi trạng thái đơn).** Áp dụng cho `APPROVED → SUBMITTED` (lập lại), `FAILED → SUBMITTED` (xếp lại), `APPROVED/PREPARING/GOODS_READY/LOADED → CANCELLED`, `PLANNED → SUBMITTED` (chạy lại) và **khi duyệt phương án gợi ý lập lại** (v1.2, đơn đang `APPROVED`…`LOADED` hoặc `FAILED`; đơn về `APPROVED` với kế hoạch mới):
1. Kế hoạch đang `approved`/`manual` của đơn → `superseded` (kế hoạch tay vẫn nhận ra nhờ `manual_reason_code`); kế hoạch `proposed` → `superseded`.
2. Mọi giữ chỗ `held`/`committed` của đơn (`stock_reservation`, `prep_reservation`, `vehicle_reservation`) → `released`. Riêng sau `FAILED`, giữ chỗ hàng đã `consumed` khi xuất kho thì giữ nguyên `consumed`.
3. Mọi `trip_stop` còn `pending` → `cancelled`; mọi `delivery_trip` chưa `completed` → `cancelled` (đơn nhiều xe có nhiều chuyến).
4. `customer_order.approved_plan_id`, `committed_date`, `promise_start`, `promise_end` → `NULL` (giá trị cũ nằm trong `decision_log.before`).
5. Ghi `decision_log` (`ORDER_REPLAN` / `ORDER_CANCELLED` / `CRITERIA_CHANGED_RERUN`) kèm `before/after`.
Nhờ bước 1, chỉ mục `ux_one_approved_plan` không chặn việc duyệt kế hoạch mới. Lần duyệt mới tạo thông báo `CONFIRMED` mới (dedupe theo `plan_id`), nên khách nhận ngày mới qua luồng thông báo thường.

**Gợi ý lập lại tự động (v1.2).** Khi một đơn đã duyệt gặp một trong bốn tín hiệu — (a) nguồn sửa đơn sau khi duyệt, (b) tồn kho đổi làm kế hoạch không còn hợp lệ, (c) `VEHICLE_ISSUE`, (d) giao `FAILED` — hệ thống tạo `planning_run(kind='replan_suggestion', trigger=…)`. Engine chạy **coi như kế hoạch hiện tại của chính đơn này không tồn tại** (giữ chỗ hàng, giờ công, xe, tài xế của nó được cộng lại vào phần khả dụng) để không tính sai nhân công, công suất, tồn kho. Lần chạy này **không tạo giữ chỗ** (tránh trùng chỉ mục với giữ chỗ `committed` của chính đơn). Hệ thống tạo alert `REPLAN_SUGGESTED` cho dispatcher. Dispatcher: **duyệt** (đóng kế hoạch cũ theo 5 bước trên rồi khóa, kiểm tra lại và commit kế hoạch mới trong cùng transaction; `409 RESOURCE_CONFLICT` nếu tài nguyên đã bị chiếm), **giữ kế hoạch cũ** (lý do), hoặc lập lại thủ công. Không bao giờ tự duyệt. Đơn đã `DISPATCHED` chỉ nhận alert.

## 7. Schema `plan` — kế hoạch và giữ chỗ

```sql
CREATE TABLE plan.planning_run (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES ops.customer_order(id), order_version int NOT NULL,
  run_no int NOT NULL, triggered_by bigint REFERENCES ref.app_user(id),
  kind text NOT NULL DEFAULT 'initial' CHECK (kind IN ('initial','rerun','replan_suggestion')),   -- v1.2
  trigger text CHECK (trigger IN ('source_change','plan_invalidated','vehicle_issue','delivery_failed')),
  params jsonb NOT NULL DEFAULT '{}',            -- trọng số, kho/xe bị loại, ngày đích dispatcher chọn
  input_snapshot jsonb NOT NULL,                 -- ảnh chụp đầu vào để tái lập quyết định
  result text NOT NULL CHECK (result IN ('feasible','infeasible')),   -- v1.2: không còn 'manual'
  failed_check text CHECK (failed_check IN ('stock','preparation','truck','site_date','safety')),
  earliest_feasible_date date,
  planning_reserve_min int, reserve_class text CHECK (reserve_class IN ('safe','tight','infeasible')),
  hold_expires_at timestamptz, hold_extensions smallint NOT NULL DEFAULT 0 CHECK (hold_extensions <= 2),
  duration_ms int, UNIQUE (order_id, run_no)
);
CREATE TABLE plan.fulfilment_plan (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id), order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  rank smallint NOT NULL, status plan.plan_status NOT NULL DEFAULT 'proposed',
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  vehicle_count smallint NOT NULL CHECK (vehicle_count >= 1),          -- v1.2: số xe; chi tiết ở plan.plan_vehicle
  total_capacity_kg numeric(10,2) NOT NULL, total_capacity_m3 numeric(8,2) NOT NULL,   -- dùng cho hòa điểm "xe nhỏ hơn"
  target_date date NOT NULL,
  goods_ready_at timestamptz NOT NULL, loading_start_at timestamptz NOT NULL,   -- loading_start = xe đầu tiên
  depart_at timestamptz NOT NULL,                -- xe đầu tiên xuất phát
  eta_at timestamptz NOT NULL,                   -- xe CUỐI CÙNG tới (ETA của đơn)
  trip_end_at timestamptz NOT NULL,
  distance_km numeric(8,2) NOT NULL, drive_min int NOT NULL,
  prep_hours numeric(8,3) NOT NULL, capacity_fill numeric(5,4) NOT NULL,   -- 0..1 mức đầy công suất kho [C]
  score numeric(6,4) NOT NULL,                  -- 0,5·km + 0,5·mức đầy (min–max), thấp hơn là tốt hơn [C]
  score_breakdown jsonb NOT NULL, complexity_points smallint NOT NULL DEFAULT 0,
  planning_reserve_min int NOT NULL,
  route_provenance text NOT NULL CHECK (route_provenance IN ('ors','fallback','manual')),
  workload jsonb NOT NULL,                      -- từng dòng: nhóm, đơn vị chuẩn bị, giờ công, cờ
  checks jsonb NOT NULL,                        -- {stock:{pass,code,detail},preparation:{...},truck:{...},site_date:{...},safety:{...}}
  reason_codes text[] NOT NULL DEFAULT '{}', explanation text NOT NULL,
  manual_reason_code text CHECK (manual_reason_code IN
     ('customer_request','system_plan_unsuitable','data_error','special_vehicle','other')),
  manual_reason_text text, created_by bigint REFERENCES ref.app_user(id),
  CONSTRAINT ck_manual CHECK ((status IN ('manual') AND manual_reason_code IS NOT NULL) OR status <> 'manual'),
  UNIQUE (run_id, rank)
);
CREATE UNIQUE INDEX ux_one_approved_plan ON plan.fulfilment_plan (order_id) WHERE status IN ('approved','manual');

CREATE TABLE plan.plan_vehicle (                 -- v1.2: các xe của một phương án (ít xe nhất có thể), cùng kho, cùng ngày
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  plan_id bigint NOT NULL REFERENCES plan.fulfilment_plan(id), seq smallint NOT NULL,
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id), driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
  load_kg numeric(10,2) NOT NULL, load_m3 numeric(8,3) NOT NULL,
  load_lines jsonb NOT NULL,                     -- [{line_no, qty_base}] — một dòng được tách qua nhiều xe theo tải/thể tích
  loading_start_at timestamptz NOT NULL, depart_at timestamptz NOT NULL,
  eta_at timestamptz NOT NULL, trip_end_at timestamptz NOT NULL,
  UNIQUE (plan_id, seq), UNIQUE (plan_id, vehicle_id)
);
ALTER TABLE ops.delivery_trip ADD CONSTRAINT fk_trip_plan_vehicle FOREIGN KEY (plan_vehicle_id) REFERENCES plan.plan_vehicle(id);
ALTER TABLE ops.customer_order ADD CONSTRAINT fk_order_plan FOREIGN KEY (approved_plan_id) REFERENCES plan.fulfilment_plan(id);

-- Giữ chỗ "như vé xe": held (đang được chọn, hết hạn) / committed (đã chọn) / chưa ai chọn (không có dòng) [C]
CREATE TABLE plan.stock_reservation (            -- tính MỘT LẦN cho mỗi (đơn, kho, sản phẩm) dù có 3 phương án [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id), order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id), global_product_id bigint NOT NULL REFERENCES ref.product_global(id),
  qty numeric(12,3) NOT NULL CHECK (qty > 0), status plan.res_status NOT NULL DEFAULT 'held'
);
CREATE UNIQUE INDEX ux_stock_res ON plan.stock_reservation (order_id, warehouse_id, global_product_id)
  WHERE status IN ('held','committed');
CREATE TABLE plan.prep_reservation (             -- giờ công theo ngày, một lần cho (đơn, kho)
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id), order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id), work_date date NOT NULL,
  resource text NOT NULL DEFAULT 'labour' CHECK (resource = 'labour'),   -- v1.1: chỉ giờ công (không còn thiết bị)
  hours numeric(8,3) NOT NULL CHECK (hours > 0), status plan.res_status NOT NULL DEFAULT 'held'
);
CREATE UNIQUE INDEX ux_prep_res ON plan.prep_reservation (order_id, warehouse_id, work_date, resource)
  WHERE status IN ('held','committed');
CREATE TABLE plan.vehicle_reservation (          -- mỗi XE của mỗi phương án giữ xe + tài xế; hai ĐƠN khác nhau không được trùng
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES plan.planning_run(id), plan_id bigint NOT NULL REFERENCES plan.fulfilment_plan(id),
  plan_vehicle_id bigint NOT NULL REFERENCES plan.plan_vehicle(id),
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  vehicle_id bigint NOT NULL REFERENCES ref.vehicle(id), driver_employee_id bigint NOT NULL REFERENCES hr.employee(id),
  during tstzrange NOT NULL, status plan.res_status NOT NULL DEFAULT 'held',
  CONSTRAINT ex_vehicle_res EXCLUDE USING gist (vehicle_id WITH =, during WITH &&, order_id WITH <>)
     WHERE (status IN ('held','committed')),
  CONSTRAINT ex_driver_res EXCLUDE USING gist (driver_employee_id WITH =, during WITH &&, order_id WITH <>)
     WHERE (status IN ('held','committed'))
);
CREATE TABLE plan.route_matrix (                 -- tính trước; engine chỉ ĐỌC bảng này, không gọi API [T]
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  to_lat numeric(8,5) NOT NULL, to_lon numeric(8,5) NOT NULL,
  distance_km numeric(8,2) NOT NULL, duration_min int NOT NULL,
  provider text NOT NULL CHECK (provider IN ('ors','fallback')), computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (warehouse_id, to_lat, to_lon)
);
```

**Quy tắc giữ chỗ:** (1) khi engine đề xuất kế hoạch, tạo `planning_run` với `hold_expires_at = now + 15 phút` và giữ chỗ cả 3 phương án; hàng và giờ công chỉ tính một lần cho mỗi (đơn, kho); (2) gia hạn tối đa 2 lần (+15 phút mỗi lần); (3) job `hold_expiry` chuyển `held` → `expired`, kế hoạch `proposed` → `expired`; (4) khi duyệt: transaction khóa tài nguyên liên quan (bên dưới), kiểm tra lại tồn kho, công suất, xe, tài xế, rồi chuyển phương án được chọn sang `committed` và các giữ chỗ khác sang `released`; (5) tồn kho khả dụng khi tính ATP **trừ cả `held` còn hiệu lực lẫn `committed`** của đơn khác.

**Chống vượt tồn kho và công suất khi nhiều dispatcher thao tác đồng thời (v1.2).** Xe và tài xế đã được ràng buộc EXCLUDE bảo vệ ở DB. Hàng và giờ công **không** có ràng buộc DB (chỉ mục `ux_stock_res`, `ux_prep_res` chỉ chặn trùng trong cùng một đơn). **Quyết định nhóm:** lúc lập kế hoạch **cho phép** giữ chỗ `held` vượt tồn kho/công suất (không khóa, để lập kế hoạch nhanh); **chỉ chặn khi duyệt**:
1. **Khóa logic** bằng `pg_advisory_xact_lock(hashtextextended(key, 0))` với key `stock:<warehouse_id>:<global_product_id>` cho từng sản phẩm và `labour:<warehouse_id>:<work_date>` cho từng ngày chuẩn bị. Không dùng `SELECT … FOR UPDATE` trên `ops.stock_snapshot` vì job đồng bộ ghi đè bảng này mỗi 5 phút.
2. **Thứ tự khóa cố định** để tránh deadlock: kho (id tăng) → sản phẩm (id tăng) → ngày công suất (tăng) → xe → tài xế. Xe/tài xế khóa bằng `SELECT … FOR UPDATE` trên `ref.vehicle` / `hr.driver_staff`.
3. **Chỉ áp dụng khi duyệt** (ApprovalService). Sau khi lấy khóa, đọc lại `on_hand − wms_reserved − Σ committed của đơn khác` và tổng giờ `committed` của ngày (giữ chỗ `held` của đơn khác **không** chặn việc duyệt); nếu không đủ → `409 RESOURCE_CONFLICT`, rollback. Lúc lập kế hoạch, engine vẫn trừ `held` còn hạn + `committed` của đơn khác khi tính ATP/công suất (để gợi ý thực tế), nhưng không khóa và không từ chối ghi giữ chỗ.
4. Hệ quả có chủ đích: hai đơn có thể cùng giữ một lượng hàng; đơn duyệt trước thắng, đơn sau nhận `409` và nút Re-run plan.

## 8. Schema `audit` — nhật ký và KPI

```sql
CREATE TABLE audit.decision_log (               -- nhật ký quyết định [C]; chỉ thêm
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(), correlation_id uuid NOT NULL,
  actor_user_id bigint REFERENCES ref.app_user(id), actor_employee_id bigint, actor_role text,
  action text NOT NULL, entity text NOT NULL, entity_id text,
  order_id bigint, plan_id bigint,
  reason_code text, reason_text text,
  snapshot jsonb, before jsonb, after jsonb
);
CREATE INDEX ix_decision_order ON audit.decision_log (order_id, ts);
CREATE INDEX ix_decision_action ON audit.decision_log (action, ts);
CREATE TABLE audit.improvement_log (            -- kế hoạch so với thực tế, dùng hiệu chỉnh buffer và định mức [S]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,           -- v1.1: một dòng cho mỗi lần giao đã đóng
  order_id bigint NOT NULL REFERENCES ops.customer_order(id),
  trip_stop_id bigint UNIQUE REFERENCES ops.trip_stop(id),
  actual_labour_hours numeric(8,3),              -- v1.2: Σ crew_size × độ dài từng đoạn làm việc (START_PREP/PREP_RESUMED → PREP_PAUSED/GOODS_READY)
  labour_segments jsonb,                         -- [{start, end, crew_size}]
  group_hours_per_unit jsonb,                    -- {"N3": {"units": 20, "unit": "bag", "hours": 0.081, "hours_per_unit": 0.00405}, …}
                                                 -- giờ thực tế chia cho từng nhóm theo tỷ lệ giờ kế hoạch, rồi chia số đơn vị cơ sở → dữ liệu train AI
  warehouse_id bigint NOT NULL, handling_groups text[] NOT NULL,
  prep_planned_min int, prep_actual_min int, prep_error_min int,
  eta_first timestamptz, eta_last timestamptz, delivered_at timestamptz, eta_error_min int,
  delay_reason text, was_manual boolean NOT NULL DEFAULT false,
  accepted_unchanged boolean, order_mix jsonb, closed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit.kpi_baseline (               -- baseline thủ công trước pilot [S]
  market_id smallint NOT NULL REFERENCES ref.market(id), metric text NOT NULL,
  value numeric NOT NULL, unit text NOT NULL, source text NOT NULL, measured_on date NOT NULL,
  PRIMARY KEY (market_id, metric)
);
```

**KPI (view `audit.v_kpi_daily`, ngày tính theo múi giờ của market):**

| Chỉ số | Định nghĩa |
|---|---|
| `planning_time_min` | Trung bình `approved_at − submitted_at` của đơn đã duyệt; so với `kpi_baseline.planning_time` |
| `on_time_rate` | Đơn DELIVERED có `delivered_at ≤ promise_end` và cùng `committed_date` / tổng đơn DELIVERED. **FAILED tính riêng**, không vào mẫu số |
| `labour_hours_per_delivery`, `km_per_delivery` | Trung bình `prep_hours` và `distance_km` của kế hoạch đã duyệt (thay "cost per delivery", không quy ra tiền) [C] |
| `prep_error_min` | Trung bình trị tuyệt đối `prep_actual − prep_planned` (phút làm việc) |
| `eta_error_min` | Trung bình trị tuyệt đối `delivered_at − eta_first` |
| `plan_acceptance_rate` | Số đơn duyệt đúng phương án rank 1, không đổi / số đơn duyệt |
| `failed_delivery_rate` | FAILED / (DELIVERED + FAILED) [C] |
| `capacity_utilisation` | Giờ công đã giữ `committed` / giờ công khả dụng theo ngày, theo kho [C] |
| `manual_plan_count` | Số kế hoạch tay (dữ liệu học cho AI sau này) [C] |

**Quyền xem KPI vận hành:** `admin` và người có `'ops'` trong `kpi_scopes` (dispatcher, quản lý/phó kho, Project Lead). Business owner (`revenue_all`) **không** xem KPI vận hành. CS không xem KPI.

**Doanh thu (v1.2, báo cáo chỉ đọc, không thuộc 8 KPI vận hành).** Doanh thu chỉ gồm **tiền hàng** (đơn giá × số lượng); chưa có phí giao, phí đóng gói, chi phí nhân công, giá vốn, lợi nhuận (chờ quyết định riêng, không tự thêm).

| Chỉ số | Định nghĩa |
|---|---|
| Doanh thu ghi nhận (`recognised`) | Σ `total_amount` của đơn **DELIVERED**, tính vào ngày giao thực tế (`delivered_at`) theo `ref.market.timezone` |
| Đã duyệt chưa giao (`booked`) | Σ `total_amount` của đơn `APPROVED`, `PREPARING`, `GOODS_READY`, `LOADED`, `DISPATCHED`, theo `committed_date` |
| Số đơn đã giao | Số đơn DELIVERED trong kỳ |
| Giá trị đơn trung bình | recognised ÷ số đơn đã giao, làm tròn 2 chữ số |
| Tỷ trọng | Doanh thu một nơi ÷ tổng cùng góc nhìn cùng kỳ, làm tròn 1 chữ số; chỉ Business owner và admin thấy |

Quy tắc: `FAILED`, `CANCELLED`, `SUBMITTED`, `PLANNED`, `NO_FEASIBLE_DATE`, `BLOCKED_UNMAPPED_SKU` không tính; đơn giao thất bại rồi giao lại chỉ tính một lần vào ngày giao thành công; mỗi market một tiền tệ, không gộp; ngày luôn theo múi giờ market, không theo UTC. **Hai góc nhìn không được cộng với nhau:** theo cửa hàng (`origin_store_id`; đơn không có cửa hàng → "Unassigned store") và theo kho (`fulfilment_plan.warehouse_id` của `approved_plan_id`); mỗi truy vấn chỉ GROUP BY một chiều; tổng hai góc nhìn trong cùng kỳ phải bằng nhau (test nhất quán).

```sql
CREATE VIEW audit.v_revenue_daily AS      -- doanh thu ghi nhận
SELECT m.id AS market_id, (o.delivered_at AT TIME ZONE m.timezone)::date AS day,
       o.origin_store_id AS store_id, p.warehouse_id, o.currency,
       count(*) AS orders_delivered, sum(o.total_amount) AS revenue_recognised
FROM ops.customer_order o
JOIN ref.market m ON m.id = o.market_id
JOIN plan.fulfilment_plan p ON p.id = o.approved_plan_id
WHERE o.status = 'DELIVERED'
GROUP BY m.id, m.timezone, (o.delivered_at AT TIME ZONE m.timezone)::date,
         o.origin_store_id, p.warehouse_id, o.currency;

CREATE VIEW audit.v_revenue_pending AS    -- đã duyệt, chưa giao
SELECT o.market_id, o.committed_date AS day, o.origin_store_id AS store_id,
       p.warehouse_id, o.currency,
       count(*) AS orders_pending, sum(o.total_amount) AS revenue_booked
FROM ops.customer_order o JOIN plan.fulfilment_plan p ON p.id = o.approved_plan_id
WHERE o.status IN ('APPROVED','PREPARING','GOODS_READY','LOADED','DISPATCHED')
GROUP BY o.market_id, o.committed_date, o.origin_store_id, p.warehouse_id, o.currency;

CREATE INDEX ix_order_status_delivered ON ops.customer_order (status, delivered_at);
CREATE INDEX ix_order_store_status ON ops.customer_order (origin_store_id, status);
```

**Quyền xem doanh thu (kiểm ở máy chủ, `resolve_revenue_scope(user)`):** `all = true` nếu là `admin` hoặc có `revenue_all` (Business owner: mọi cửa hàng và kho của nước, cả hai góc nhìn); nếu không, danh sách `location_id` có `location.owner_employee_id = user.employee_id` và `is_active` (owner cửa hàng → chỉ góc nhìn store; owner kho → chỉ góc nhìn warehouse). Rỗng và không `all` → `403`. Dispatcher, CS, sales không phải owner, tài xế, Project Lead: không xem. Xuất CSV ghi `decision_log` `REVENUE_EXPORTED`.

## 9. Trigger, hàm, chỉ mục

```sql
-- set_updated_at: trigger BEFORE UPDATE gắn cho mọi bảng có cột updated_at.
CREATE FUNCTION audit.forbid_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'append-only table'; END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_decision_immutable BEFORE UPDATE OR DELETE ON audit.decision_log
  FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation();
CREATE TRIGGER trg_event_immutable BEFORE UPDATE OR DELETE ON ops.milestone_event
  FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation();

CREATE FUNCTION ops.check_transition() RETURNS trigger AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status AND NOT EXISTS (
     SELECT 1 FROM ops.order_transition WHERE from_status = OLD.status AND to_status = NEW.status)
  THEN RAISE EXCEPTION 'illegal order transition % -> %', OLD.status, NEW.status; END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_check_transition BEFORE UPDATE OF status ON ops.customer_order
  FOR EACH ROW EXECUTE FUNCTION ops.check_transition();
```

Chỉ mục bắt buộc: `customer_order(status, committed_date)`, `customer_order(market_id, status)`, `order_line(order_id)`, `milestone_event(order_id, occurred_at)`, `eta_forecast(order_id, version DESC)`, `notification(status, scheduled_for)`, `alert(market_id, resolved_at)`, `vehicle_position(trip_id, recorded_at DESC)`, `inbound_shipment(warehouse_id, global_product_id, eta_date) WHERE confirmed AND NOT received`, `attendance(work_date, status)`, `hr.employee_assignment(location_id) WHERE end_date IS NULL`, `plan.fulfilment_plan(order_id, status)`, `plan.vehicle_reservation USING gist(vehicle_id, during) WHERE status IN ('held','committed')`.

## 10. Hệ thống nguồn giả lập (`src_<cc>`) — bảng tối thiểu

Dùng chung cho mọi nước (cùng mã nguồn, dữ liệu seed riêng). CFO **chỉ đọc**, không ghi ngược.

| Bảng | Cột chính |
|---|---|
| `src_customer` | id, name, email, phone, type, updated_at |
| `src_address` | id, customer_id, address, lat, lon (địa chỉ seed sẵn kèm tọa độ) |
| `src_product` | sku, name, category, gtin, sale_unit, units_to_base, unit_price, weight_kg, volume_m3, updated_at |
| `src_stock` | warehouse_code, sku, on_hand, reserved, as_of |
| `src_inbound` | inbound_ref, warehouse_code, sku, qty, eta_date, confirmed, received |
| `src_vehicle_calendar` | vehicle_code, from_ts, to_ts, kind |
| `src_order`, `src_order_line` | id, version, customer_id, address_id, date_mode, date_from, date_to, window_start, window_end, sales_code, store_code, status (`DRAFT`,`VALIDATED`,`SUBMITTED_FOR_PLANNING`,`CANCELLED`), updated_at |

Quy tắc: đơn chỉ vào CFO khi `status = SUBMITTED_FOR_PLANNING` (sau bước "Sales Validation" của form POS giả lập). Mọi bảng có `updated_at` để CFO kéo theo `updated_since`.

## 11. Thứ tự migration và seed

1. `0001_extensions_schemas_enums` → 2. `0002_ref` → 3. `0003_hr` (và các `ALTER … ADD CONSTRAINT` chéo) → 4. `0004_stg` → 5. `0005_ops` → 6. `0006_plan` → 7. `0007_audit_views_triggers` → 8. `0008_seed_reference` (market SE, handling_group N1–N6, special_flag, position, order_transition, user_role). → 9. `0009_schedule_routing_driver_rules` (lịch ca chính thức, nhật ký làm việc tài xế, phân luồng đơn, phạm vi 561/2006 của xe — Q12/Q12b/Q14) → 10. `0010_order_routing_immutable` (quyết định phân luồng bất biến, xác nhận bàn giao ghi một lần) → 11. `0011_routing_decided_by_check` (quyết định chỉ do Sales check/Dispatcher, lý do bắt buộc cho manual_started).
Seed dữ liệu mẫu (script `seed/generate_data.py`, cố định random seed): xem tài liệu 08 mục "Dữ liệu seed".

**Định mức mẫu cho `ref.handling_group` (ví dụ minh họa, IT thay bằng số thật) [T][A]:**

Định mức do **IT nhập cứng** trong MVP (quy tắc cứng, chưa có số liệu kho thật); sau pilot, dữ liệu `improvement_log.group_hours_per_unit` (**giờ nhân công thực tế trên một đơn vị cơ sở** của từng nhóm, không phụ thuộc số người) là cơ sở để AI hiệu chỉnh ở giai đoạn 2. Tên hiển thị tiếng Anh (`name`) dùng ở UI dạng "N3 · Bagged cement & mortar".

| Mã | `name` (UI) | Mô tả | Đơn vị chuẩn bị | Giờ cố định/dòng | Giờ công/đơn vị | ≈ phút/đơn vị | Người tối thiểu | Yêu cầu xe |
|---|---|---|---|---|---|---|---|---|
| N1 | Small items & accessories | Hàng nhỏ nhặt tay (keo tuýp, ốc vít, dụng cụ, sơn lon) | line | 0 | 0,05 | 3 / dòng | 1 | — |
| N2 | Boards, sheets & tiles | Hàng tấm, thùng xếp chồng (ván, thạch cao, gạch ốp) | pallet | 0,25 | 0,40 | 24 / pallet | 1–2 | — |
| N3 | Bagged cement & mortar | Hàng bao nặng theo pallet (xi măng, vữa, keo dán gạch) | pallet | 0,25 | 0,15 | 9 / pallet | 1 | — |
| N4 | Bulk materials | Vật liệu rời (cát, đá, sỏi) | m3 | 0,50 | 0,10 | 6 / m³ | 1 | `dump` |
| N5 | Long goods | Hàng dài, nặng (gỗ dài, thép cây, ống, xà gồ) | bundle | 0,50 | 0,50 | 30 / bó | 2 | — |
| N6 | Large & fragile items | Hàng lớn, dễ vỡ, giá trị cao (kính, khung cửa, cửa, sứ vệ sinh) | package | 0,25 | 0,60 | 36 / kiện | 2 | — |

Hệ số cờ mẫu: FRAGILE 1,25 · SPECIAL_STORAGE 1,15 · HAZARDOUS 1,30 · FAR_OR_OUTDOOR 1,20 [A]; tích các hệ số tối đa 2,0. Kiểm tra cuối đơn: +0,5 giờ công cố định/đơn.

Quy tắc và hạn chế đã biết [A]:
- **N6 không gắn cờ FRAGILE** (độ khó đã nằm trong định mức N6; gắn thêm sẽ nhân hai lần). `POST /mapping/tasks/{id}/confirm` và `PATCH /products/global/{id}` từ chối `422 VALIDATION_ERROR`.
- **Tính theo đơn vị nhỏ nhất (v1.2):** định mức ghi theo đơn vị chuẩn bị (pallet, bó…) nhưng hệ thống quy về **đơn vị cơ sở** để dễ scale: `giờ/đơn vị cơ sở = labour_hours_per_unit / base_units_per_prep_unit` (N3: 0,15 / 40 bao = 0,00375 giờ/bao; 20 bao = 0,075 giờ). Hàng **không chia nhỏ được** (không có `base_units_per_prep_unit`: một kiện cửa, một bó bán nguyên bó) thì số đơn vị **làm tròn lên** số nguyên; `line` luôn là 1. Ghi vào báo cáo như một quyết định của nhóm.
- Định mức đã bao gồm thời gian dùng thiết bị (xe nâng, máy xúc…) vì MVP không quản lý thiết bị kho.
- Paint & chemicals trong ảnh thiết kế không là nhóm riêng: sơn lon thuộc N1 kèm cờ `HAZARDOUS` hoặc `SPECIAL_STORAGE` khi cần; "Tiles & heavy" gộp vào N2.
