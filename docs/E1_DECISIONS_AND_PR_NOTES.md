# E1 — Ghi chú quyết định và trạng thái (nhánh feat/e1-approve-wms-simulated)

## Trạng thái
- PR #224: Draft. Không merge.
- Mục tiêu E1 (Dispatcher duyệt SE-2026-000249 → APPROVED, có trip_ids, audit, bằng chứng batch sau ACK): CHƯA đạt.

## Đã làm (đã kiểm chứng bằng lệnh)
- Allowlist hai mốc demo cô lập: 04/11/2026 và 01/12/2026 (phương án C). Vẫn yêu cầu APP_ENV=test, DEMO_DISPOSABLE=1, WMS_RESERVATION_MODE=simulated.
- as_of của snapshot WMS giả lập lấy theo APP_NOW.
- Kết quả: ruff và black pass trên 3 file; unit 12 passed; integration test_wms_intent 8 passed.

## Điểm chặn còn lại
1. Route POST /plans/{id}/approve truyền session=db nên nhánh giữ hàng WMS mô phỏng trong approval_service.approve() không chạy. Đề xuất đưa bước giữ hàng vào đúng vị trí sau five-gate recheck, trước commit APPROVED.
2. Batch sau ACK không vào CFO vì hai nguyên nhân: (a) ingest_stock.apply() dedupe theo source_batch_id và bỏ qua batch trùng số (batch 2 của #222 trùng batch 2 của lượt giữ đầu tiên, vì bộ đếm batch của WMS giả lập là toàn cục); (b) mark_refreshed() không được gọi ở đâu nên refreshed_batch_id không được đặt.
3. Chưa có bù trừ (release) khi WMS đã ACK nhưng duyệt CFO thất bại sau đó.

## Quyết định cần owner xác nhận (CHƯA có)
Q1. Sales có được giữ hàng WMS (qua _reserve_before_approval) cho đơn cửa hàng mình (DEC-R3-10) hay chỉ Dispatcher? Hiện code chỉ cho dispatcher.
Q2. Thứ tự: giữ hàng trước hay sau five-gate recheck? Đề xuất: sau recheck, trước commit APPROVED, kèm bù trừ release nếu duyệt thất bại sau ACK.
Q3. Xác nhận phương án C (hai mốc demo) và đề xuất ghi vào docs/ASSUMPTIONS.md với ID ASM mới (chưa được owner duyệt).

## Ghi chú vận hành
- Mật khẩu role cfo của container cfo-itconsultant-postgres đã được đặt lại từ POSTGRES_PASSWORD trong .env cục bộ. Không đưa mật khẩu vào commit hay tài liệu.
- Tránh dùng COMPOSE_PROJECT_NAME=cfo-demo-e0 trong .env của repo này khi làm việc với stack chính.