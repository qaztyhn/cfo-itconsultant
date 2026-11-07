# Changelog (hợp đồng `05` / `06`)

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
