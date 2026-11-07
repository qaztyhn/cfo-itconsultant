# Hợp đồng — lịch ca chính thức (kho + tài xế), mã audit nhân sự, phân luồng đơn (Q12–Q14)

> **Trạng thái:** ngày 2026-11-07, chủ dự án **đã duyệt các lựa chọn nghiệp vụ** trong comment trên PR qaztyhn/cfo-itconsultant#53:
> Q12a–d = A, Q13 = các mã đề xuất, Q14 = A cùng quy trình vận hành. Chủ dự án bổ sung **yêu cầu bắt buộc** về giờ làm
> thực tế của nhân viên kho và tài xế. **Migration, API và engine cuối cùng vẫn phải review** ở PR triển khai.
>
> Tác giả: Dev 1.
> Đã đưa vào: `04` (mục 6.7), `05` (mục 4, 6), `06` (mục 5.0.2, 13.0b), `CHANGELOG`.
> Nguồn: qaztyhn/cfo-itconsultant#49 (ASM-005), qaztyhn/cfo-itconsultant#50 (ASM-006/007), review của
> qaztyhn/cfo-itconsultant#54.

## Quyết định đã duyệt

| # | Quyết định |
|---|---|
| Q12a | Tối đa **1 ca chính thức/nhân viên/ngày** (MVP) |
| Q12b | Người lập/sửa lịch: quản lý **chính hoặc phó** của kho đó, đang hiệu lực và có `can_approve = true`. `expected_staff` chỉ để so sánh, không phải quota |
| Q12c | Quản lý được phép sửa lịch quá khứ, nhưng **bắt buộc lý do** và có lịch sử audit |
| Q12d | Thiếu lịch chính thức → `schedule_verified = false`, công suất 0 |
| Q13 | `LOCATION_MANAGER_CHANGED`, `LOCATION_OWNER_CHANGED`, `EMPLOYEE_TERMINATED`. Chỉnh hồi tố phân công dùng `EMPLOYEE_ASSIGNMENT_CHANGED`, `reason_code = retroactive`, lý do bắt buộc |
| Q14 | Mỗi đơn nguồn có một quyết định luồng `cfo` / `legacy`, đã lưu thì **không đổi**. Đơn legacy không có plan/hold/approve trong CFO; IT mapping về sau không chuyển nó vào CFO. Sales phải kiểm đơn trong CFO **trước khi** điều phối tay. Fail closed khi dữ liệu nguồn hoặc quyền sở hữu luồng chưa chắc chắn |
| **Mới** | Phương án giao chỉ hợp lệ khi thỏa cả hai: (1) lên hàng/chuẩn bị nằm trong **ca chính thức có người** của kho; (2) **toàn bộ khoảng làm việc** của từng tài xế nằm trong **ca thực tế** của tài xế đó, gồm lên hàng, chờ, chạy, dỡ và quay về, có tôn trọng giờ nghỉ và lịch đã nhận. Không mặc định 24/7; không biết ca thì không có phương án duyệt được |

## Q12 — Lịch phân ca chính thức cho nhân viên kho **và tài xế**

**Nguồn dữ liệu và người cập nhật**
- **Một bảng chung** `hr.employee_shift_schedule` cho mọi nhân viên của kho. Tài xế thuộc kho gốc `driver_staff.home_warehouse_id`.
  Dùng chung để có một cơ chế quyền, một lịch sử và một quy tắc 1 ca/ngày.
- **Người cập nhật:** Warehouse Manager của kho (Q12b), cho cả nhân viên kho và tài xế của kho. Dispatcher và admin chỉ đọc.
  Không job hay engine nào tự tạo hoặc sửa lịch.

**Giờ ca, giờ nghỉ, nghỉ giữa ca**
- Giờ ca lấy theo `shift_template`, hoặc **giờ riêng** `start_time` / `end_time` (thường dùng cho tài xế).
- `end_time < start_time` nghĩa là ca **qua nửa đêm**, kết thúc vào ngày hôm sau. `work_date` là ngày bắt đầu ca, theo múi giờ market.
- **Giờ nghỉ** `break_start` / `break_end` là tùy chọn. Engine coi đây là khoảng không làm việc: chuyến không được chồng lên giờ nghỉ.
- **Nghỉ giữa hai ca:** khi lưu lịch, service từ chối nếu khoảng nghỉ giữa hai ca liên tiếp của một tài xế nhỏ hơn
  `driver_min_rest_hours`. Đây là MarketConfig mới, mặc định 11.

**DDL (`05` mục 4) — chờ PR migration**
```sql
CREATE TABLE hr.employee_shift_schedule (
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
  CHECK (shift_template_id IS NOT NULL OR start_time IS NOT NULL),
  CHECK ((start_time IS NULL) = (end_time IS NULL)),
  CHECK ((break_start IS NULL) = (break_end IS NULL)),
  CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
);
CREATE UNIQUE INDEX ux_shift_one_per_day ON hr.employee_shift_schedule (employee_id, work_date)
  WHERE status = 'scheduled';
```
- Bảng có thêm các cột chung theo ASM-001.
- Đổi ca = hủy dòng cũ rồi thêm dòng mới, ghi `SHIFT_CHANGED` (trước/sau, actor) trong cùng transaction. Không xóa dòng.

**API (`06` mục 13.0b)**
- `GET /warehouses/{id}/shift-schedule?from=&to=&kind=staff|driver|all`
  - Quyền đọc: warehouse (kho mình), dispatcher, admin. Tối đa 31 ngày.
  - Trả `expected_staff` (chỉ để so sánh), `scheduled_count`, và từng người với `start_at`, `end_at`, `break`.
- `PUT /warehouses/{id}/shift-schedule`
  - Quyền ghi: Q12b. Sai vai trò → `403`; kho khác → `404`.
  - Thân request: `entries[{employee_id, date, shift_template_id|null, start_time?, end_time?, break_start?, break_end?}]`, `reason_text?`.
  - Áp dụng toàn bộ hoặc không gì cả.
  - `422` kèm `details.field` khi: người không thuộc kho, người đã nghỉ, trùng ca trong ngày, chồng ca, thiếu nghỉ giữa ca, template sai kho hoặc sai thứ.
  - Sửa ngày đã qua mà thiếu lý do → `422 REASON_REQUIRED`.
- `attendance_gen` chép các dòng `scheduled` trong 14 ngày tới thành `planned`.
- API công suất trả thêm `schedule_verified`.

**Đầu vào engine và quy tắc (`04` mục 6.7)**
- `WarehouseCtx.loading_windows`: các ca kho chính thức có ít nhất một người tính công suất.
  Rỗng → `NO_WAREHOUSE_SHIFT` (check preparation).
- `DriverCtx.shifts`: các ca thực tế của tài xế, đã trừ giờ nghỉ, có thể qua nửa đêm.
  Rỗng → tài xế không dùng được.
- Mỗi xe lên hàng trọn trong một `loading_window`, với `loading_start ≤ cutoff` của ngày đó.
  Không được thì dời sang cửa sổ của ngày làm việc kế. Không bao giờ lên hàng trước `goods_ready_at`.
- **Khoảng làm việc của tài xế** = `[loading_start, trip_end]` của xe, tính cả thời gian chờ xuất phát. Khoảng này phải
  nằm trọn trong một ca của tài xế, không chồng lịch đã nhận, và tổng giờ trong ngày ≤ `driver_max_hours_day`.
- Giao vào ngày sau: lên hàng trong cửa sổ của **ngày giao**; xe và tài xế không chờ qua đêm.
- **Mã mới:**
  - `NO_WAREHOUSE_SHIFT` (preparation);
  - `OUTSIDE_DRIVER_SHIFT` (safety): có tài xế đủ bằng nhưng không ai có ca phủ trọn chuyến;
  - `NO_DRIVER` thêm `detail.reason` = `no_schedule` | `licence` | `busy`.
- **Ghép tài xế–xe:** ghép đúng bằng bipartite/backtracking. Tồn tại cách ghép hợp lệ thì không được báo `NO_DRIVER`.

## Q13 — Mã audit nhân sự

| Mã | Khi nào |
|---|---|
| `LOCATION_MANAGER_CHANGED` | `PUT /locations/{id}/managers` (quản lý chính/phó cũ → mới) |
| `LOCATION_OWNER_CHANGED` | `PATCH /locations/{id}/owner`, hoặc owner tự đổi theo quản lý chính (`reason_code = follows_primary`) |
| `EMPLOYEE_TERMINATED` | `POST /employees/{id}/terminate` |
| `EMPLOYEE_ASSIGNMENT_CHANGED` | chuyển công tác; chỉnh hồi tố (`retroactive`, lý do bắt buộc, chỉ admin, không tạo phân công chồng ngày) |
| `SHIFT_CHANGED` | mỗi lần lưu lịch (Q12) |

## Q14 — Phân luồng đơn và quy trình Sales

**Quy trình**
1. Sales nhập và submit đơn trên POS.
2. **Trước mọi điều phối tay**, Sales mở CFO → **Sync & check routing**.
3. CFO trả một trong ba trạng thái:

| `routing_status` | Điều kiện | Sales làm gì |
|---|---|---|
| `cfo` | Đọc đủ đơn, 100% SKU đã confirmed | CFO lập kế hoạch/điều phối theo cổng duyệt; **không** điều phối tay |
| `legacy` | Đọc đủ đơn, có SKU chưa confirmed | Toàn bộ đơn theo quy trình tay; CFO không plan/hold/approve; mapping về sau không kéo đơn vào CFO |
| `unresolved` | Nguồn hoặc CFO không sẵn sàng, dữ liệu thiếu, hoặc version đang đổi | **Không** coi là legacy; không lưu quyết định; thử lại hoặc báo theo quy trình; không xác nhận giao |

4. **Xác nhận bàn giao** (chống làm trùng):
   - `legacy` → Sales bấm "Tôi xử lý theo quy trình cũ", CFO ghi audit `ROUTING_LEGACY_ACKNOWLEDGED`.
   - Đơn đã được điều phối tay trước khi kiểm CFO → Sales chọn "Đã điều phối tay". CFO lưu `legacy` với
     `reason_code = manual_started`, kể cả khi đủ SKU.

**DDL (`05` mục 6) — chờ PR migration**
```sql
CREATE TABLE ops.order_routing (
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,
  route text NOT NULL CHECK (route IN ('cfo','legacy')),
  reason_code text NOT NULL CHECK (reason_code IN ('all_confirmed','unmapped_sku','manual_started')),
  unmapped_skus text[] NOT NULL DEFAULT '{}',
  decided_at timestamptz NOT NULL, decided_source_version int NOT NULL,
  decided_by_user_id bigint REFERENCES ref.app_user(id),
  acknowledged_by_user_id bigint REFERENCES ref.app_user(id), acknowledged_at timestamptz,
  PRIMARY KEY (market_id, external_ref)
);
```

**Cách quyết định luồng**
- Mỗi quyết định chạy trong một transaction: lấy advisory lock `routing:<market>:<external_ref>`, rồi `INSERT … ON CONFLICT DO NOTHING`.
  Bên thua đọc lại quyết định đã lưu.
- `customer_order` chỉ được tạo khi `route = 'cfo'`.
- `order_service`, `planning_service`, `approval_service` đều kiểm `route = 'cfo'` trước khi plan/hold/approve.
- Polling được phép quyết định `cfo`/`legacy`, nhưng **không tự tạo hold** trước khi Sales kiểm.
- Dữ liệu cũ: đơn đang `BLOCKED_UNMAPPED_SKU` được chuyển thành `legacy / unmapped_sku`.

**Giới hạn:** bảng định tuyến nội bộ **không bảo đảm** chặn được điều phối tay, vì CFO chỉ đọc POS. Chống làm trùng dựa vào:
1. quy tắc "kiểm CFO trước";
2. xác nhận bàn giao có audit;
3. lựa chọn `manual_started`;
4. cảnh báo khi version đơn đổi.

Nếu sau này POS cung cấp owner luồng thì có thể bổ sung kiểm tra tự động.

**API (`06` mục 5.0.2)**
- `sync-now` trả `routing_status` kèm `order_id?`, `unmapped_skus?`, `retry_after_s?`. Trạng thái `unresolved` trả `200`; lỗi kỹ thuật của nguồn vẫn là `503`.
- `POST /integration/orders/{external_ref}/routing-ack` (Sales, đúng cửa hàng): `{choice: legacy_acknowledged | manual_started, reason_text?}`.
  `manual_started` bắt buộc lý do và chỉ hợp lệ khi đơn chưa có hold/approve trong CFO.

## Phối hợp
- **Dev 1:** migration `0009`, schedule service + API, guard `route = 'cfo'`, các mã audit, engine (lịch kho/tài xế, ghép tài xế).
- **Dev 2:** ghi `order_routing` trong ingestion/sync-now; polling không tạo hold; seed lịch demo cho kho và tài xế.
- **Dev 3:** màn lập lịch có tài xế; màn Sync & check routing với ba trạng thái và các nút bàn giao.
