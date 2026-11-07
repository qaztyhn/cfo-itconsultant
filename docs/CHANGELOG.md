# Changelog (hợp đồng `05` / `06`)

> Mỗi thay đổi `05`/`06` đi cùng migration/code và test trong cùng PR (`09` mục 6, `AGENTS.md`).
> Mục có trạng thái **chờ duyệt** chưa được merge cho tới khi nhóm phê duyệt trên PR.

## [Sales confirmation B — Product decision] — 2026-11-07 — docs-only, chưa triển khai

- Giữ POS/WMS/ERP, database riêng và read-only adapter; Sales yêu cầu CFO đọc đơn ngay qua `sync-now`, polling 5 phút dự phòng.
- Sales xác nhận trực tiếp trên màn CFO riêng chỉ khi plan rank 1 đủ 5 gate, reserve safe, một xe, không ngoại lệ, đúng cửa hàng; ApprovalService vẫn kiểm tra lại và khóa nguồn lực khi commit.
- FIFO hiển thị (`submitted_at,id`), không ép FIFO thực thi; bảo vệ committed của đơn cũ, cạnh tranh với đơn cũ chưa duyệt → Dispatcher.
- Bổ sung hợp đồng mục tiêu và acceptance criteria; không có code/migration/test thực thi trong PR docs này. PR #37 cần đối chiếu trước khi merge.

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
