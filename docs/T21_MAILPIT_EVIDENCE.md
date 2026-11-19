# T21 và T27 bước 5 — bằng chứng PostgreSQL và Mailpit

Ngày chạy 2026-11-19. PostgreSQL 16, schema tại Alembic `head`, Mailpit v1.27.8
và dữ liệu tổng hợp trong các môi trường cục bộ tách biệt.

## T21 · DISPATCHED với hai xe

Fixture `SE-M6` có hai xe và một tài xế được phân công cho mỗi xe. Test gọi
API sự kiện thật và chạy outbox E2 qua `/internal/tick` sau khi các giao dịch
đã commit. Ca này dùng proof D7 tổng hợp ở ranh giới đọc lịch sử tài xế.

| Cấu hình | PostgreSQL | Mailpit |
| --- | --- | --- |
| `NOTIFY_DISPATCHED_ENABLED=true` | Hai sự kiện xuất phát. Sau xe thứ nhất và sau xe thứ hai đều có đúng 1 thông báo `DISPATCHED`. Bản ghi chuyển `queued` → `sent`. | 1 email chứa `Order SE-M6: Delivery dispatched.`. Mailpit ID `EjQA7eaK9o3nAkVNqb2Voc`. |
| `NOTIFY_DISPATCHED_ENABLED=false` | Hai sự kiện xuất phát và đơn `DISPATCHED`. Đúng 1 bản ghi `suppressed` với `SKIPPED_FLAG_DISABLED`. Ca kết thúc chuyến lỗi vẫn đưa `FAILED` vào `queued`. | 0 email `DISPATCHED`. |

Retry cùng key và payload trả lại phản hồi cũ. Hai request đồng thời với hai
key đều trả HTTP 200, ghi đủ hai sự kiện và tạo một thông báo. Khi DB đã có
thông báo từ plan trước theo khóa `1:DISPATCHED:2:DISPATCHED`, hai chuyến vẫn
xuất phát và bản ghi cũ được giữ nguyên. Tick lặp lại xử lý 0 thông báo.

Chạy từ `backend/` với `TEST_DATABASE_URL` trỏ tới PostgreSQL dùng cho test,
Mailpit SMTP nghe ở `127.0.0.1:1025` và `E2_MAILPIT_URL=http://127.0.0.1:8025`:

```sh
python -m pytest -q tests/integration/test_dispatched_notification.py
python -m pytest -q tests/integration/test_dispatched_notification.py \
  tests/integration/test_e2_mailpit.py tests/integration/test_execution_api.py \
  tests/integration/test_notify_api.py tests/integration/test_notify_backend.py \
  tests/integration/test_notification_delivery.py tests/integration/test_approval_service.py
```

Bốn ca T21 đạt. Bộ 87 ca PostgreSQL với Mailpit đạt, gồm hồi quy `CONFIRMED`,
`DELIVERED`, `DELAY`, thiếu email và worker E2.

## T27 bước 5

**PASS.** Cùng ID `CONFIRMED` ở `queued` sau Approve và `sent` sau lượt E2.

Lượt dùng chung T21/T27 trên đúng đơn `SE-2026-000249`, tiếp nối
[E0-04](E0_04_DEMO.md), [E1 #224](E1_DEMO.md) và enqueue cùng giao dịch của
[#223](https://github.com/qaztyhn/cfo-itconsultant/pull/223). CFO và Source
chạy cục bộ với PostgreSQL 16, WMS disposable và đồng hồ demo
`2026-12-01T10:05:00+01:00` (`Europe/Stockholm`).

| Điểm đối chiếu | Quan sát trên cùng đơn |
| --- | --- |
| Sales chuẩn bị đơn | Sync now HTTP 200, `order_id=1`, `routing=cfo`. Check feasibility HTTP 200, `run_id=1`, `plan_id=1`. |
| Dispatcher bấm Approve | Playwright Chromium 156, Plan Review → chấp nhận lịch sát biên → `POST /api/v1/plans/1/approve` HTTP 200. Phản hồi `APPROVED`, `CONFIRMED` ID `1` ở `queued`. |
| PostgreSQL trước khi khởi động E2 | `ops.notification.id=1`, `plan_id=1`, `queued`, `attempts=0`, `sent_at=NULL`. Khung cam kết ngày `2026-12-02`, `06:00–08:00 UTC` (`07:00–09:00` Stockholm). |
| PostgreSQL sau lượt E2 | Job nền `notify_outbox:SE` xử lý 1 bản ghi sau commit. Cùng `ops.notification.id=1` ở `sent` với `sent_at` có giá trị, `attempts=1` và đúng 1 audit `NOTIFICATION_SENT`. |
| Mailpit | Đúng 1 email, ID `CNNtnj6v6iar47usKbr5ej`. Subject `Your delivery is confirmed — order SE-2026-000001`. Nội dung có `Order SE-2026-000001: Delivery confirmed.` và khung `2026-12-02T07:00+01:00 – 2026-12-02T09:00+01:00`. |

PostgreSQL đối chiếu `external_ref=SE-2026-000249` với
`order_no=SE-2026-000001` trên cùng `customer_order.id=1`. Mẫu `CONFIRMED`
dùng `order_no` của CFO trong subject và nội dung.
