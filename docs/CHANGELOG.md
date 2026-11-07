# Changelog (hợp đồng `05` / `06`)

> Mỗi thay đổi `05`/`06` đi cùng migration/code và test trong cùng PR (`09` mục 6, `AGENTS.md`).
> Mục có trạng thái **chờ duyệt** chưa được merge cho tới khi nhóm phê duyệt trên PR.

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
