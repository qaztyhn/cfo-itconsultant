# Changelog (hợp đồng `05` / `06`)

## [Approved decision register] — 2026-11-07 — docs-only

- Tập trung quyết định đã duyệt ở `docs/ASSUMPTIONS.md`: ASM-001/002/003/005/006/007; Sales confirmation, Q12/Q13/Q14 và giờ làm/nghỉ của kho/tài xế trong MVP Bắc Âu.
- **ASM-004 giữ trạng thái chưa duyệt**; các proposal kỹ thuật vẫn cần PR contract/migration/test riêng. Không dùng mã ASM đã cấp trùng với ASM-008 trong PR #55; quyết định sản phẩm dùng `DEC-xxx`.
- `AGENTS.md` và `09_AI_Coding_Rules.md`: bắt buộc Dev/agent cập nhật sổ khi owner chốt giả định mới, kiểm tra trước khi mở PR, dẫn nguồn và phân biệt phê duyệt với triển khai.
- Chỉ có thay đổi docs, không có migration/code/test trong PR này.


## [ASM-002, ASM-003, ASM-006, ASM-007/Q11 — quyết định chủ dự án] — 2026-11-07 — docs-only

- ASM-002: chấp thuận seed tham chiếu (market, N1–N6, position, transitions) riêng dữ liệu demo; GPS mặc định tắt ở migration, tài khoản/mật khẩu demo không nằm trong migration.
- ASM-003: chấp thuận giới hạn đăng nhập MVP 5 lượt/60 giây/IP và HTTP 429; logout 204; email không phân biệt hoa thường; khóa user ngay khi nghỉ việc. Hệ thống nhiều instance cần rate limiter chung trong lần mở rộng.
- ASM-006: chấp thuận bảo đảm quản lý thay thế trước chuyển công tác/nghỉ việc, khóa account người nghỉ, giữ owner gán riêng, audit mọi thay đổi nhân sự/quản lý/owner; chỉnh hồi tố phải có quyền và lý do. Không chấp thuận bỏ `decision_log`; action code chưa có cần PR hợp đồng.
- ASM-007/Q11: Warehouse Manager lập và xác nhận lịch phân ca **từng người/ngày/ca**. `expected_staff` chỉ để so sánh; không chia tự động, không dồn người dư vào ca cuối. Job chỉ sinh điểm danh planned từ lịch do quản lý xác nhận; warehouse ghi thực tế; thay đổi lịch/điểm danh có audit, hồi tố cần lý do.
- Mục tiêu docs, chưa có code/migration/test xác minh. Cần thiết kế bảng lịch ca chính thức mới, API và UI. PR #37 còn Q11=B phải cập nhật/rebase trước merge.

## [ASM-005 — quyết định phân luồng SKU] — 2026-11-07 — docs-only, chưa triển khai

- Khởi đầu khoảng 100 SKU mapping confirmed do IT quản lý, mở rộng danh mục từng giai đoạn.
- Chỉ đơn có **100% SKU confirmed** mới đi CFO. Đơn thiếu SKU tiếp tục quy trình cũ, không bị CFO chặn chờ mapping/không lập plan/hold.
- Mapping về sau không tự động chuyển các đơn đã đi quy trình cũ sang CFO. Bắt buộc ngăn xử lý trùng bằng xác minh luồng thực hiện tại đầu vào; CFO vẫn read-only với POS/WMS/ERP.
- API response, trạng thái theo dõi luồng cũ và bất biến tránh double fulfilment cần được Dev đề xuất trước triển khai. Không tự phục hồi trạng thái `HANDLED_EXTERNALLY` đã bỏ ở v1.2; không có migration/code trong PR này.


> Mỗi thay đổi `05`/`06` đi cùng migration/code và test trong cùng PR (`09` mục 6, `AGENTS.md`).
> Mục có trạng thái **chờ duyệt** chưa được merge cho tới khi nhóm phê duyệt trên PR.

## [05 — migration 0009] — 2026-11-07 — DDL theo Q12/Q12b/Q14 đã duyệt (PR qaztyhn/cfo-itconsultant#53), chờ review PR migration

### Thêm
- `hr.employee_shift_schedule`: lịch ca chính thức của nhân viên kho và tài xế (giờ theo template hoặc giờ riêng, ca qua nửa đêm, giờ nghỉ, trạng thái `scheduled/cancelled`, người lập, lý do); `ux_shift_one_per_day` (Q12a).
- `hr.driver_duty_log`: kỳ làm việc/lái của tài xế (`duty_start/end`, `driving_min`, `source`, `trip_id`) — nguồn kiểm nghỉ 11 giờ và giờ lái (Q12b).
- `ops.order_routing`: quyết định luồng `cfo`/`legacy` một lần theo `(market_id, external_ref)`; `ck_routing_reason` (cfo ⇔ all_confirmed); `unresolved` không lưu được (Q14).
- `ref.vehicle.max_permissible_mass_kg`, `ref.vehicle.regulation_561_scope` (`in_scope|out_of_scope|unknown`, mặc định `unknown` → engine fail closed).
- Trigger `set_updated_at` cho ba bảng mới (ASM-001).

### Ảnh hưởng
- Không đổi bảng/cột cũ khác. Service/API dùng các bảng này (lịch ca, phân luồng, dựng ngữ cảnh engine) ở PR tiếp theo; Dev 2 seed lịch demo và phạm vi xe.

## [Q12–Q14 — lựa chọn nghiệp vụ đã duyệt] — 2026-11-07 — docs, DDL/API/engine chờ PR triển khai (PR qaztyhn/cfo-itconsultant#53)

- Q12: lịch ca chính thức một bảng cho nhân viên kho **và tài xế**; 1 ca/người/ngày; quản lý chính/phó `can_approve` cập nhật; sửa quá khứ cần lý do; thiếu lịch → `schedule_verified=false`, công suất 0; giờ riêng, ca qua nửa đêm, giờ nghỉ, nghỉ giữa ca `driver_min_rest_hours` (MarketConfig mới, mặc định 11).
- Yêu cầu mới của chủ dự án: phương án chỉ hợp lệ khi lên hàng trong ca kho chính thức có người và khoảng làm việc của từng tài xế nằm trọn trong ca thực tế; không mặc định 24/7. Engine: `WarehouseCtx.loading_windows`, `DriverCtx.shifts`, ghép tài xế bipartite, ràng buộc nhóm/năng lực theo dòng trên từng xe; mã `NO_WAREHOUSE_SHIFT`, `OUTSIDE_DRIVER_SHIFT` (`04` mục 6.7, `06` mục 13.0b).
- Q12b (chính sách Bắc Âu cho MVP, duyệt hướng 07/11/2026, không phải xác nhận pháp lý):
  - nghỉ hằng ngày 11 giờ; tắt nghỉ rút gọn 9 giờ;
  - tách thời gian lái (561/2006: 9 giờ/ngày, nghỉ 45 phút sau 4 giờ 30, giới hạn tuần/hai tuần) khỏi tổng giờ làm `driver_max_hours_day`;
  - phạm vi theo market/xe/loại vận hành (`ref.vehicle.regulation_561_scope`);
  - fail closed khi thiếu lịch sử hoặc phạm vi;
  - mã mới `DRIVER_REST_INSUFFICIENT`, `DRIVING_TIME_EXCEEDED`, `DRIVING_BREAK_REQUIRED`, `DRIVER_HISTORY_MISSING`, `VEHICLE_SCOPE_UNKNOWN`.
- Q13: mã audit `LOCATION_MANAGER_CHANGED`, `LOCATION_OWNER_CHANGED`, `EMPLOYEE_TERMINATED`, chỉnh hồi tố `EMPLOYEE_ASSIGNMENT_CHANGED`/`retroactive`.
- Q14: `ops.order_routing` (cfo/legacy, không đổi), trạng thái `unresolved` riêng, Sales kiểm CFO trước điều phối tay, `routing-ack` (`legacy_acknowledged`/`manual_started`), polling không tự tạo hold; nêu rõ bảng nội bộ không bảo đảm chặn điều phối tay (`06` mục 5.0.2).
## [06 v1.4] — 2026-11-07 — **đã duyệt** (Q5–Q10, PR qaztyhn/cfo-itconsultant#37; chủ dự án trả lời trong phiên làm việc 2026-11-07; Q11 thay bằng ASM-007, PR qaztyhn/cfo-itconsultant#50)

Quyết định: Q5 = A, Q6 = A, Q8 = A (điều chỉnh theo ASM-005), Q9 = A, Q10 = A. **Q11 = B bị thay thế** bởi ASM-007: lịch phân ca từng người do Warehouse Manager lập; không chia theo `expected_staff`, không dồn người dư vào ca cuối. Q7 được chốt lại theo nguyên tắc "ưu tiên đơn đặt trước, linh hoạt chèn đơn giao sớm, nhưng mọi đơn phải đúng hạn đã cam kết", khớp `docs/DECISION_SALES_CONFIRMATION.md` mục 5.

### Thêm
- `06` mục 5.2: phạm vi đơn theo vai trò (warehouse qua kế hoạch chưa superseded hoặc chuyến từ kho mình; sales theo cửa hàng gốc; driver theo chuyến mình; viewer `403`; ngoài phạm vi `404`).
- `06` mục 5.3: bảng trường của `GET /orders/{id}` theo vai trò; trường bị cấm thì bỏ khỏi phản hồi; không có GPS.
- `06` mục 5.4: phần tử `GET /orders`; **sắp mặc định `submitted_at ASC, id ASC`** (thay cho `promise_end` trong đề xuất ban đầu); bucket của `/orders/counts`. `BLOCKED_UNMAPPED_SKU` là legacy: không thuộc `needs_plan`/`all`/hàng đợi Dispatcher (ASM-005).
- `06` mục 5.5: timeline; CS không thấy quyết định nội bộ, lần chạy kế hoạch, điểm số, GPS.
- `06` mục 12.2: schema đọc `/mapping/tasks*`, `/products/local`; phản hồi confirm/reject. Theo ASM-005 (PR qaztyhn/cfo-itconsultant#49): confirm **không** mở khóa/chuyển trạng thái đơn, phản hồi không có `ready_order_ids`/`still_blocked_order_ids`; chi tiết task không liệt kê đơn khách; `blocked_order_count` là trường legacy, sắp mặc định theo `id` thay vì số đơn bị chặn.
- `06` mục 13.2: schema điểm danh và công suất. Roster và `attendance_gen` theo lịch chính thức của Warehouse Manager (ASM-007, mục 13.0a); khi chưa có bảng lịch thì job không tạo dòng, không suy từ `expected_staff`.

### Ảnh hưởng
- Mã: route M2-C (mapping), M2-D (orders, counts), M2-E (timeline), M3 (điểm danh, công suất). PR code căn chỉnh ASM-005/007 bỏ mở khóa đơn khi confirm và bỏ chia ca theo `expected_staff`. Không đổi `05`; bảng lịch ca chính thức cần PR migration riêng.
- Thứ tự thực thi không theo FIFO cứng: bảo vệ đơn cũ bằng `committed` (đã duyệt); đơn cũ chưa duyệt tranh nguồn lực thì Sales chuyển Dispatcher (`06` mục 6.3a, `09` bất biến 26–27).

## [Sales confirmation B — Product decision] — 2026-11-07 — docs-only, chưa triển khai

- Giữ POS/WMS/ERP, database riêng và read-only adapter; Sales yêu cầu CFO đọc đơn ngay qua `sync-now`, polling 5 phút dự phòng.
- Sales xác nhận trực tiếp trên màn CFO riêng chỉ khi plan rank 1 đủ 5 gate, reserve safe, một xe, không ngoại lệ, đúng cửa hàng; ApprovalService vẫn kiểm tra lại và khóa nguồn lực khi commit.
- FIFO hiển thị (`submitted_at,id`), không ép FIFO thực thi; bảo vệ committed của đơn cũ, cạnh tranh với đơn cũ chưa duyệt → Dispatcher.
- Bổ sung hợp đồng mục tiêu và acceptance criteria; không có code/migration/test thực thi trong PR docs này. PR #37 cần đối chiếu trước khi merge.

## [06 v1.3] — 2026-11-07 — **đã duyệt** (PR qaztyhn/cfo-itconsultant#12, comment của owner 2026-11-07)

### Thêm
- `06` mục 13.1: API đọc `/locations`, `/employees`, `/vehicles` (và `/{id}`): schema phản hồi, lọc, sắp xếp,
  phân trang, lỗi 401/403/404/422.
- Phạm vi: admin, dispatcher theo market; warehouse theo địa điểm có phân công hiệu lực; vai trò khác `403` (Q3 = A).
- Kiểm theo **ngày hiệu lực** cho phân công (`start_date`/`end_date`) và quản lý địa điểm (`valid_from`/`valid_to`),
  hôm nay theo múi giờ market (điều chỉnh Q1).
- Hiển thị trường nhân viên theo vai trò, tối thiểu hóa dữ liệu: dispatcher thấy thêm `driver_staff` (bằng lái),
  warehouse thấy thêm `warehouse_staff.role`, `counts_in_capacity`; thông tin liên hệ và hợp đồng chỉ admin (Q4 = C
  có điều chỉnh). Trường không hiển thị được bỏ khỏi phản hồi; liệt kê trường nullable (điều chỉnh Q1).

### Đổi
- `06` mục 13: quyền đọc `/vehicles` theo ma trận mục 3 — dispatcher (market), warehouse (xe thuộc kho mình) (Q2 = A);
  mô tả vai trò của `/employees`, `/locations` trỏ tới mục 13.1.

### Ảnh hưởng
- Backend: `app/api/v1/hr.py`, `app/services/hr_read_service.py`, phạm vi/phân trang dùng chung; test PostgreSQL
  quyền, phạm vi, ngày hiệu lực, hiển thị trường.
- Frontend (Dev 3): màn A9/A10 dùng schema mục 13.1; vai trò không phải admin nhận ít trường hơn.
- Không đổi bảng, cột, enum hay endpoint khác.

## [06 v1.2.1] — 2026-11-06 — **chờ nhóm duyệt** (PR qaztyhn/cfo-itconsultant#8)

### Thêm
- `06` mục 1.1: nhóm **mã lỗi kỹ thuật** ngoài danh sách mã nghiệp vụ:
  - `INTERNAL_ERROR` (HTTP 500) — lỗi không bắt; thông báo cố định, không stack trace, không thông điệp gốc.
  - `NOT_FOUND` (HTTP 404) — đã có trong khung mã (`app/core/errors.py`) và bảng HTTP 404, nhưng thiếu trong
    danh sách mã của `06`.
- Quy tắc ánh xạ lỗi framework: 422 / 4xx kỹ thuật khác → `VALIDATION_ERROR` (không trả lại giá trị đầu vào);
  `GET /health` lỗi phụ thuộc → `503` với thân health.
- `X-Correlation-ID` không phải UUID → server thay bằng UUID mới (cột `audit.decision_log.correlation_id` là `uuid`).

### Lý do
`06` mục 1.1 bắt buộc mọi lỗi có `code`, nhưng chưa có mã cho lỗi máy chủ (ASM-004). Không đổi tên/xóa mã nào.

### Ảnh hưởng
- Backend: `app/core/errors.py`, `app/core/correlation.py`, `app/audit/recorder.py`; test `tests/unit/test_core_errors.py`,
  `tests/unit/test_core_correlation.py`, `tests/integration/test_recorder_health.py`.
- Frontend (Dev 3): hiển thị lỗi chung theo `correlation_id`; có thể gặp `INTERNAL_ERROR`, `NOT_FOUND`.
- Nếu nhóm **không** duyệt: chọn mã khác cho 500 trước khi merge PR #8 (code hiện dùng `INTERNAL_ERROR`).
