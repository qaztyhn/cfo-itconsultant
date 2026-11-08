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
| **Mới (2)** | Chính sách lái/nghỉ Bắc Âu cho MVP: nghỉ hằng ngày 11 giờ; tắt nghỉ rút gọn 9 giờ; tách thời gian lái khỏi tổng giờ làm; áp 561/2006 theo market/xe/loại vận hành; fail closed (mục Q12b) |
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

## Q12b — Thời gian lái, làm việc và nghỉ của tài xế (chính sách Bắc Âu cho MVP)

(đã duyệt hướng chính sách 07/11/2026 trên PR qaztyhn/cfo-itconsultant#53/#54 — **không phải xác nhận pháp lý**; phạm vi áp dụng từng nước/xe/loại vận hành phải được pháp chế và vận hành xác minh trước triển khai thật)

**Chính sách mặc định** — áp dụng cho SE trước; DK, NO, FI, IS là chính sách riêng theo market, bật khi cần.

1. **Nghỉ hằng ngày 11 giờ liên tục** trước kỳ làm việc tiếp theo.
   - Kiểm trên khoảng làm việc thực tế (ca chính thức + chuyến đã nhận), không theo ngày điểm danh.
   - Nhân viên kho cũng dùng 11 giờ làm mặc định thận trọng của MVP.
2. **Nghỉ rút gọn 9 giờ: TẮT** trong lập kế hoạch tự động.
   - Chỉ bật sau này khi đủ cả các điều kiện: đủ điều kiện theo market/vận hành, đã rà soát pháp lý, có lịch sử đếm đủ (tối đa 3 lần giữa hai kỳ nghỉ tuần khi 561/2006 áp dụng), và phê duyệt có audit.
   - **Không** có nút ghi đè thủ công vượt cổng an toàn/pháp lý.
3. **Trong phạm vi Quy định (EC) 561/2006**, kiểm **thời gian lái** tách khỏi **tổng thời gian làm việc**:
   - Lái tối đa 9 giờ/ngày. Mức 10 giờ (tối đa 2 lần/tuần) cần theo dõi đủ điều kiện; MVP **tắt**, luôn dùng 9 giờ.
   - Sau tối đa 4 giờ 30 lái phải nghỉ ≥ 45 phút, hoặc 15 phút rồi 30 phút (đúng thứ tự).
   - Giới hạn lái tuần (56 giờ), hai tuần (90 giờ) và nghỉ tuần đều cần lịch sử.
   - `driver_max_hours_day` (9) là **tổng giờ làm việc**: lên/dỡ hàng, chờ, chạy, quay về. Đây **không** phải giới hạn 9 giờ lái.
4. **Phạm vi xét theo market, xe và loại vận hành**, không áp chung cho mọi tài xế.
   - Các yếu tố: nội địa / quốc tế / cabotage; khối lượng tối đa cho phép (gồm rơ-moóc); miễn trừ; loại vận hành.
   - Từ 01/07/2026 phạm vi mở rộng cho một số xe trên 2,5 t đến 3,5 t chạy vận tải quốc tế/cabotage thuê. Phải xác minh cho từng nước Bắc Âu, kể cả cách triển khai trong EEA.
5. **Fail closed:** thiếu một trong các dữ liệu sau thì **không** khẳng định tuân thủ và **không** có phương án duyệt được tự động:
   - giờ ca chính thức;
   - lịch sử làm việc/lái/nghỉ trước đó;
   - thông tin phạm vi xe/vận hành;
   - bằng chứng nghỉ bắt buộc.

   UI phải phân biệt "thiếu dữ liệu" với "không có tài xế khả thi".

**Dữ liệu và cấu hình đề xuất** (chờ PR migration/API)

- **`MarketConfig.driver_rules`** (theo market), validate ở `PUT /markets/{code}/config`:

  | Tham số | Mặc định |
  |---|---|
  | `daily_rest_hours` | 11 |
  | `reduced_rest_enabled` | false |
  | `driving_max_min_day` | 540 |
  | `driving_extended_enabled` | false |
  | `driving_break_after_min` | 270 |
  | `driving_break_min` | 45 |
  | `weekly_driving_max_min` | 3360 |
  | `fortnight_driving_max_min` | 5400 |

- **`ref.vehicle`**:
  - `max_permissible_mass_kg`;
  - `regulation_561_scope`: `in_scope` | `out_of_scope` | `unknown`, mặc định `unknown`. `unknown` → fail closed.
- **Lịch sử tài xế:**
  - Nguồn: chuyến đã thực hiện hoặc đã cam kết (`ops.delivery_trip`, `plan.vehicle_reservation` committed) và ca chính thức.
  - Bảng đề xuất `hr.driver_duty_log` (`employee_id`, `duty_start`, `duty_end`, `driving_min`, `source`).
  - Thiếu lịch sử cho khoảng thời gian cần xét → `history_complete = false`.
- **Seed demo (Dev 2):** xe có phạm vi rõ ràng, tài xế có đủ lịch sử 14 ngày, lịch ca do quản lý xác nhận.

**Đầu vào engine** (`04` mục 6.7):
- `DriverCtx.duty_history` (các kỳ làm việc đã có và sắp tới), `driving_min_by_day`, `driving_min_week`, `driving_min_fortnight`, `history_complete`.
- `VehicleCtx.regulation_561`: `True` / `False` / `None` (chưa biết).
- Các tham số `driver_rules` trong `EngineConfig`.

**Quy tắc engine** (hạn chế theo giai đoạn của MVP; mọi lỗi dưới đây là check `safety`, và nếu có tài xế khác hợp lệ thì engine chọn tài xế đó):

- **Nghỉ 11 giờ:** khoảng làm việc của chuyến phải cách mọi kỳ làm việc khác (trước và sau) ≥ 11 giờ, trừ khi nằm trong **cùng** một ca. Vi phạm → `DRIVER_REST_INSUFFICIENT`.
- **Xe trong phạm vi 561:**
  - Thiếu lịch sử → `DRIVER_HISTORY_MISSING`.
  - Thời gian lái của chuyến = lái đi + lái về. Vượt 540 phút/ngày, 3360 phút/tuần hoặc 5400 phút/hai tuần → `DRIVING_TIME_EXCEEDED`.
  - Chặng lái liên tục > 270 phút → `DRIVING_BREAK_REQUIRED`. MVP chưa tự chèn giờ nghỉ vào chuyến; việc này để giai đoạn sau.
- **Xe chưa rõ phạm vi** → `VEHICLE_SCOPE_UNKNOWN`.
- **Tổng giờ làm việc/ngày** ≤ `driver_max_hours_day`.

**Test bắt buộc:**
- ca qua nửa đêm; đổi ngày, ngày lễ;
- về muộn rồi vào ca sớm hôm sau;
- ngưỡng 4h30 lái; giới hạn lái trong ngày;
- trùng chuyến đã nhận;
- hai tài xế khác hạng bằng;
- tài xế đang trong ca nhưng ca không phủ giờ lấy hàng;
- thiếu lịch sử; xe chưa rõ phạm vi.

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
- ~~Polling được phép quyết định `cfo`/`legacy`, nhưng không tự tạo hold trước khi Sales kiểm.~~ **Thay thế bởi DEC-ROUTING-002:** polling chỉ đồng bộ dữ liệu nguồn; quyết định chỉ do Sales check hoặc Dispatcher kiểm tra được ủy quyền.
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
