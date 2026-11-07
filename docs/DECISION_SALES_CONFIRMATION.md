# CFO — Quyết định sản phẩm: Sales xác nhận giao hàng trong CFO (Cách B)

**Ngày chốt:** 2026-11-07. **Trạng thái:** đặc tả mục tiêu đã được chủ dự án chấp thuận, **chưa triển khai mã**. Tài liệu này cùng các cập nhật 01–10 là cơ sở triển khai, không mô tả khả năng đang chạy.

## 1. Giữ nguyên hệ thống nguồn

POS/WMS/ERP sẵn có và cơ sở dữ liệu của chúng **không bị thay thế hoặc thay đổi**. Sales tạo, validate và submit đơn tại POS như hiện tại. CFO tiếp tục dùng `MarketAdapter` với API **GET** để nạp dữ liệu; không ghi ngược POS/WMS/ERP, không chia sẻ một database. Sales làm việc trên **giao diện CFO riêng** sau khi nhập đơn ở POS.

## 2. Luồng xác nhận tại quầy

1. Sales submit đơn `SUBMITTED_FOR_PLANNING` tại POS cũ.
2. Sales mở **My store orders → Sync & confirm delivery** trong CFO, nhập mã đơn POS (`external_ref`) và bấm **Sync now**. CFO xác minh role, market, cửa hàng, đọc từ API nguồn, kiểm version và upsert đơn vào DB CFO. Dùng cùng DTO/ingestion/checkpoint/reject/idempotency với job định kỳ. Polling mỗi 5 phút tiếp tục là cơ chế dự phòng, **không phải thời gian chờ bắt buộc**.
3. Sales bấm **Check feasibility**. CFO chạy engine và giữ chỗ 15 phút theo cơ chế hiện có. Hiển thị **Khả thi — chưa xác nhận**, phương án xếp hạng 1, kho/ETA/khung giờ, thời hạn giữ chỗ; không lộ điểm nội bộ hay GPS.
4. Khi khách đồng ý, Sales bấm **Confirm** nếu backend đánh dấu đủ điều kiện; CFO dùng **chính ApprovalService hiện tại** để xác minh lại nguồn lực, khóa và commit trong một transaction, chuyển `APPROVED`, ghi `decision_log` với người thực hiện và phát `CONFIRMED` theo quy tắc hiện tại. Chỉ sau commit thành công mới được hứa lịch giao với khách.
5. Nếu không khả thi/hết hạn/chưa đủ an toàn thì **Retry/Recheck hoặc chuyển Dispatcher**. Không có cơ chế override cho Sales.

## 3. Quyền Sales được duyệt (đồng thời phải thỏa toàn bộ)

- Sales thuộc cửa hàng gốc (`origin_store_id` trong `location_ids` hiện hành và đúng market).
- Đơn đã vào CFO, phiên bản nguồn chưa đổi, trạng thái `PLANNED`; phương án do hệ thống tạo **rank 1**, **1 xe**, `reserve_class=safe`, cả năm gate đều pass, hold còn hạn; không có SKU chưa ánh xạ hay dữ liệu nguồn quá cũ.
- Không thay ngày khách yêu cầu, không transfer/manual/replan, không đổi tiêu chí, không chọn plan 2/3, không ngoại lệ đòi thương lượng, không gửi DELAY, không xem GPS.
- Phải kiểm tra lại tồn kho, nhân công **theo từng ngày**, lịch xe/tài xế, tất cả đơn `committed` trước đó. Việc `held` tồn kho và giờ công **được phép vượt**, do đó không coi hold là cam kết nguồn lực chắc chắn. Nếu có đơn **đặt trước, chưa duyệt** đang tranh nguồn lực mà chưa chứng minh đủ công suất cho cả hai đúng hạn, **không cho Sales tự duyệt**, chuyển Dispatcher.
- Các lỗi xung đột từ chối commit; hai Sales duyệt cạnh tranh một xe/SKU/công suất phải được xử lý an toàn bằng khóa khi duyệt và `Idempotency-Key`.
- Dispatcher giữ toàn bộ quyền duyệt, chọn phương án khác, xử lý ngày giao, ngoại lệ, kế hoạch tay, lập lại. Không có auto-approval.

## 4. API mục tiêu (chưa triển khai)

**POST `/api/v1/integration/orders/sync-now`**: role sales; `Idempotency-Key`, body `{"external_ref":"POS-SE-88120"}`. CFO gọi adapter **đọc** đơn qua API nguồn hiện có, lọc theo market/store và trả `200 {"order_id":4021,"external_ref":"POS-SE-88120","sync_status":"synced","source_version":1}`; lần gọi lại `sync_status="already_current"`. Không thuộc cửa hàng hoặc không có đơn submit: 404; sai role: 403; nguồn lỗi: 503; xung đột: 409.

**POST `/api/v1/orders/{id}/plan`**: Sales được gọi **chỉ body mặc định `{}`**, đúng cửa hàng mình, không thay tiêu chí. Response `GET /planning-runs/{id}`/plan cho Sales phải rút gọn với `sales_approvable` và `sales_block_reason` cùng rank-1/ETA/hold; server chặn truy cập plan ngoài phạm vi.

**POST `/api/v1/plans/{id}/approve`**: giữ endpoint và dùng lại ApprovalService; Sales chỉ được duyệt các phương án đủ điều kiện ở mục 3. Nếu không hợp lệ → `409 PLAN_NOT_APPROVABLE`; hold hết → `409 HOLD_EXPIRED`; nguồn lực đổi → `409 RESOURCE_CONFLICT`. Không có API bypass.

**Tính khả thi khi tích hợp POS thật:** Hợp đồng nguồn hiện có cung cấp `GET /orders?updated_since=&status=SUBMITTED_FOR_PLANNING&page=&page_size=`. CFO có thể tìm `external_ref` qua truy vấn phân trang hạn chế. Nếu POS không cung cấp dữ liệu vừa submit ngay hoặc adapter không thể truy xuất đủ nhanh, UI phải hiển thị Retry/Wait, **không cam kết thời gian vài giây cho mọi POS**. Không bắt buộc webhook hoặc thay đổi POS.

## 5. Ưu tiên đơn hàng

- Danh sách: đơn nộp trước hiện trước theo `submitted_at ASC, id ASC`; cho phép sort thêm theo ngày giao yêu cầu và `promise_end`.
- Lập lịch: đơn nộp sau nhưng giao sớm có thể được chuẩn bị/giao trước nếu không làm trễ đơn cũ. Các đơn **đã duyệt** phải được bảo vệ bằng `committed` tồn kho/công suất/xe theo lịch.
- Với đơn cũ **chưa duyệt**, CFO không giả vờ có cơ chế bảo vệ tuyệt đối: nếu có nguy cơ tranh tài nguyên, việc Sales xác nhận đơn sau phải chuyển Dispatcher. Không tự tạo thuật toán tối ưu toàn cục mới hoặc giữ trước cố định 7 ngày.

## 6. Phân công và xác minh

- **Dev 1:** API planning cho Sales, guard bảo mật/nguồn lực, `ApprovalService` chung, audit, xử lý cạnh tranh đơn cũ, kiểm tra DB cần migration hay không.
- **Dev 2:** sync-now qua adapter/read-only ingestion, chống trùng polling, source tests, reliability/rate limit.
- **Dev 3:** màn `Sync & confirm delivery` trong CFO; My store orders; rank-1/hold/Confirm/Retry/Escalate và trạng thái dễ hiểu; không sửa POS.
- **Kiểm thử:** đúng cửa hàng, khác cửa hàng 404, role cấm 403, trùng sync, data stale, SKU unmapped, hold expired, multi-vehicle, rank2, low reserve, tranh xe/SKU/giờ công giữa 2 Sales, bảo vệ đơn cũ, lỗi nguồn và không xác nhận trước khi commit.
- **DB:** không sửa `docs/05_Database_Design.md` trong quyết định docs vì chưa xác minh cần cột/bảng mới; Dev 1 phải kiểm tra model/constraints và trình PR migration riêng nếu cần.
- **PR mở:** PR #37 (Q5–Q11) phải được rebase và cập nhật cách sort/permissions theo quyết định này trước khi merge.
