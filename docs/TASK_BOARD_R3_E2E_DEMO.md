# CFO — Task board Round 3, đảm bảo luồng end-to-end cho demo

> Ngày: 2026-11-18. Đối chiếu code `main` tại `b990399` + quyết định DEC-R3 (nhánh `claude/serene-goodall-rdm4re`).
> File điều phối, không phải phê duyệt mới. Trạng thái "có sẵn" = có code, **chưa** chạy end-to-end thật.

## 1. Luồng demo cần chạy được (15 phút)

| # | Bước demo | Ai | Hiện trạng code | Task cần |
|---|---|---|---|---|
| 1 | Khách đặt đơn ở quầy, Sales tạo đơn trong POS giả lập | Sales | Có sẵn (`source_system/pos_ui`) | E0 kiểm |
| 2 | Sales **Sync now** + **Check feasibility** trong CFO | Sales | Có sẵn (`SalesSyncCheck`, route sync-now, plan) | E0 kiểm |
| 3 | Engine trả 3 phương án; Sales chọn rank 1–3 | Sales | Chỉ cho rank-1 (`approval_service.py:426`) | **T19** |
| 4 | Duyệt → `APPROVED`, khóa tài nguyên, gán Dispatcher | Sales/Dispatcher | **Bị chặn cứng**: ngoài môi trường test, duyệt luôn lỗi "WMS reservation acknowledgment … not configured" (`approval_service.py:506–518`); gate tài xế cần bằng chứng 56 ngày | **E1**, **T12**, T15 |
| 5 | Khách nhận email CONFIRMED (Mailpit) | Hệ thống | **Không gửi**: scheduler chỉ chạy job ingest; outbox, hết hạn hold, quá hạn không được lên lịch; `/internal/tick` còn stub | **E2**, T21 |
| 6 | Đơn khác: Dispatcher mở hàng đợi → Plan review → duyệt | Dispatcher | `OrderQueue`, `PlanReview` có sẵn; `PlanReviewList` là khung rỗng | **E4** |
| 7 | Kho: START_PREP → GOODS_READY → LOADED từng xe | Warehouse | Backend có; **màn Prep Queue chỉ đọc, không có nút** (PR #186 còn draft) | **E3**, T05 |
| 8 | Tài xế: Dispatched → cập nhật vị trí → Delivered kèm vị trí | Driver | `TodaysTrips` có Dispatched/POD; chưa có vị trí | T06, **T13, T14, T16** |
| 9 | Dispatcher thấy "Vị trí gần nhất · Giờ cập nhật · ETA", rủi ro, soạn và gửi DELAY | Dispatcher | Chưa có dòng vị trí; màn DELAY draft cần kiểm | **T17**, T08, **E5** |
| 10 | Khách nhận DISPATCHED, DELIVERED (hoặc DELAY) | Hệ thống | Phụ thuộc E2 | E2, T21 |
| 11 | CS tra cứu trạng thái + ETA | CS | Có sẵn (`OrderLookup`) | T03, E0 kiểm |
| 12 | Màn KPI 5 chỉ số, tách theo đường duyệt | Owner/Lead | Có màn 10 KPI | T22 |
| 13 | **Round 3:** đổi CRM D365 → Salesforce bằng cấu hình, kết quả không đổi | Dispatcher/IT | Chưa có | **T23** |
| 14 | Ngoại lệ: một chuyến FAILED → cảnh báo, Dispatcher xử lý | Driver/Dispatcher | Đang tự lập lại kế hoạch (phải bỏ) | **T07**, (T18 tùy chọn) |

**Nhãn:** 🔴 bắt buộc cho demo · 🟡 nên có (bước demo bị yếu nếu thiếu) · ⚪ chỉ trình bày trên slide.

**DoD chung:** test cả đường được phép và bị cấm; task chạm DB có test PostgreSQL thật; `tools/harness.py` xanh, lệnh nào
không chạy ghi **NOT VERIFIED**; không log PII hay tọa độ; PR ghi `Assumptions: reviewed`. Cỡ: S ≈ 0,5–1 ngày · M ≈ 2–3 · L ≈ 4–5.

---

## Đợt 0 — Đo hiện trạng (làm đầu tiên, 1 ngày)

### E0 · Chạy thử luồng trên `main` 🔴 — Dev 2 + Dev 3 · S
- **Việc:** theo `docs/DEMO_SETUP.md`: `docker compose up`, migrate, seed, rồi đi tay bước 1–11 bằng tài khoản demo. Ghi từng bước PASS/FAIL/BLOCKED kèm log/ảnh.
- **Đầu ra:** bảng kết quả 14 bước; danh sách lỗi mới (nếu có) thành task `E0-xx`. Bảng này quyết định khối lượng thật còn lại.
- **Phụ thuộc:** không. Cần máy có Docker.

---

## Đợt 1 — Gỡ chặn luồng chính 🔴 (song song, ưu tiên cao nhất)

### E1 · Duyệt được trong demo với ACK WMS mô phỏng — Dev 1 · M
- **Việc:** theo DEC-R3-11 (WMS real write tắt; ACK mô phỏng chỉ ở staging/demo, gắn nhãn *simulated*): thêm chế độ cấu hình `WMS_RESERVATION_MODE=simulated` chỉ chấp nhận khi `APP_ENV ≠ production`. Ở chế độ này, `approval_service` ghi intent + ACK mô phỏng (adapter disposable đã có) rồi cho duyệt; `production` vẫn fail closed như hiện tại.
- **Đầu ra:** test PostgreSQL: demo + simulated → `APPROVED`, ledger ghi `simulated=true`; production → `PLAN_NOT_APPROVABLE`; không đổi khóa/audit hiện có.

### E2 · Lên lịch các job chạy nền + `/internal/tick` — Dev 2 · S–M
- **Việc:** `jobs/scheduler.py` hiện chỉ có job ingest. Thêm: `outbox` (gửi email), `hold_expiry`, `risk_check` (quá hạn 30 phút, T08), `retention` (xóa tọa độ, T13). Viết `/internal/tick` (đang stub) chạy cùng các job, dùng key riêng, để demo bấm tay.
- **Đầu ra:** test mỗi job được đăng ký với chu kỳ theo cấu hình; gọi tick → email trong outbox chuyển `sent` sang Mailpit.

### T12 · Dữ liệu tài xế đã xác minh (thay bằng chứng 56 ngày) — Dev 2 (nạp) + Dev 1 (gate) · M · cần T09
- **Việc:** nguồn giả lập `/fleet/driver-availability`, `/fleet/driver-eligibility`; adapter upsert; `official_driver_context` dùng khung khả dụng, `max_driving_min`, quyền lái. Dữ liệu demo `synthetic_demo`.
- **Đầu ra:** gate tài xế pass với seed demo; test các ca bị loại. **Gỡ chặn bước 4.**
- *Cách tạm nếu T09 chậm:* bật `demo_d7_reader` đã merge (#206) cho demo, gỡ khi T12 xong.

### E3 · Nút mốc kho trên Prep Queue — Dev 3 · M
- **Việc:** lấy lại phần UI của PR #186 (draft) hoặc viết mới: nút START_PREP (nhập số người), GOODS_READY, LOADED theo từng xe, báo thiếu hàng/vỡ; bỏ PAUSE/RESUME (T05). Gửi `POST /orders/{id}/events` với `Idempotency-Key`.
- **Đầu ra:** test UI theo thứ tự mốc; lỗi 409 sai thứ tự hiển thị rõ. Đóng/thay PR #186.

### E4 · Màn danh sách Plan review — Dev 3 · S
- **Việc:** `PlanReviewList.tsx` đang là khung rỗng; hiện các planning run đang giữ chỗ (đơn, kho, hạn hold) và mở `PlanReview/:runId`.
- **Đầu ra:** test danh sách + điều hướng.

### E5 · Kiểm và hoàn thiện màn DELAY draft cho Dispatcher — Dev 3 · S
- **Việc:** kiểm luồng bản nháp DELAY trong màn Exceptions/thông báo: xem → sửa ETA/lý do mẫu → Send hoặc Discard (API `notifications/{id}/send|discard` đã có). Bổ sung phần thiếu.
- **Đầu ra:** test UI send/discard; không có ô nhập nội dung tự do.

### T19 · Sales duyệt trong phạm vi (rank 1–3 mọi kho) — Dev 1 (API) + Dev 3 (UI) · M
- **Việc:** nới `approval_service.py:379–434`; rank 2–3 bắt buộc lý do; Sales được chạy lại planner và ghi thỏa thuận ngày cho đơn cửa hàng mình; không tick lịch sát; Sales làm kế hoạch tay/replan sau FAILED/gửi DELAY → 403. `SalesSyncCheck` hiện 3 phương án để chọn.
- **Đầu ra:** test được phép/bị cấm theo `06` §19.1; Sales cửa hàng khác → 404.

### T07 · FAILED và sự cố xe chỉ cảnh báo — Dev 1 · M
- **Việc:** bỏ `suggest_replan` (`execution_service.py:594`, `:610`); đơn FAILED khi mọi chuyến kết thúc và có chuyến thất bại; alert `DELIVERY_FAILED`; `VEHICLE_ISSUE` chỉ alert `EXCEPTION`.
- **Đầu ra:** test 4 ca; không có planning run tự sinh.

---

## Đợt 2 — Thay đổi Round 3 xuất hiện trong demo

### T09 · Migration R3 gộp 🔴 — Dev 1 · M — *chặn T12, T13, T14, T15, T21, T22*
- **Việc:** một forward migration cho toàn bộ `05` §13 + cập nhật model. Ngày đầu chốt hàm `record_point(session, trip_id, point, source) -> RemainingRoute` cho T13/T14.
- **Đầu ra:** migrate lên/xuống sạch trên DB trống và DB có seed cũ.

### T13 · Nhận vị trí (backend) 🔴 — Dev 2 · M · cần T09
- **Việc:** `gps_service` nhận một điểm/lần; tính km/phút còn lại qua `RoutingProvider`; `GET /gps/live` trả một dòng/chuyến cho Dispatcher được gán; bỏ route lịch sử; xóa tọa độ khi đơn `DELIVERED`/`CANCELLED` (FAILED ≤ 7 ngày).
- **Đầu ra:** test quyền xem; xóa đúng lúc.

### T14 · Vị trí bắt buộc khi giao xong, báo sự cố, ETA từ vị trí 🔴 — Dev 1 · M · cần T09
- **Việc:** `DELIVERED`/`FAILED` thiếu vị trí → 422; `DRIVER_INCIDENT` + alert; engine `forecast` dùng vị trí; viết `GET /orders/{id}/eta-forecasts` (stub).
- **Đầu ra:** unit test forecast; tọa độ không vào payload/audit/email.

### T15 · Gán Dispatcher luân phiên + bàn giao 🔴 — Dev 1 · S–M · cần T09
- **Việc:** gán khi duyệt (cùng một Dispatcher cho mọi chuyến của đơn); `POST /trips/{id}/handover`.
- **Đầu ra:** test vòng luân phiên, duyệt đồng thời, bàn giao.

### T16 · Trang tài xế: Cập nhật vị trí, Báo sự cố, giao xong kèm vị trí 🔴 — Dev 3 · M · MSW
- **Việc:** nút lấy vị trí một lần; 4 lý do sự cố; nút Giao xong/Thất bại khóa khi chưa có vị trí.
- **Đầu ra:** test gồm ca từ chối quyền định vị.

### T06 · Trang tài xế bỏ offline/thu vị trí tự động 🟡 — Dev 3 · S
- **Việc:** xóa `offlineQueue.ts`, `offlineEvents.ts`, chu kỳ 30 phút; retry dùng lại cùng key.

### T17 · Dòng "Vị trí gần nhất · Giờ cập nhật · ETA" 🔴 — Dev 3 · S · MSW
- **Việc:** danh sách chuyến được gán cho mình; màu rủi ro, sự cố; nút Bàn giao. Thay màn `TrackingList`.

### T08 · Cảnh báo quá hạn 30 phút 🟡 — Dev 2 · S
- **Việc:** viết `jobs/risk_check.py` (stub): quá ETA hoặc mốc kho 30 phút không có sự kiện → `OVERDUE`. Chạy qua E2.

### T21 · Chỉ email + cờ DISPATCHED 🔴 — Dev 2 · S · cần T09
- **Việc:** 5 loại email qua outbox; DISPATCHED một lần/đơn; bỏ SMS (gộp T02).
- **Đầu ra:** mỗi loại đúng một lần trong Mailpit; DELAY không tự gửi.

### T23 · `CustomerContactPort` + mock D365/Salesforce 🔴 — Dev 2 · M
- **Việc:** cổng + 2 provider (`/crm/d365/contacts`, `/crm/salesforce/contacts`, khác cấu trúc trường); chọn bằng cấu hình; email lấy liên hệ qua cổng. Thêm cách đổi provider dễ bấm khi demo (lệnh CLI hoặc biến môi trường + restart).
- **Đầu ra:** test đổi provider → cùng `PlanningResult`, cùng nội dung email. **Trọng tâm câu chuyện Round 3.**

### T22 · 5 KPI tách theo đường duyệt 🟡 — Dev 1 (API) + Dev 3 (UI) · M · cần T09
- **Việc:** thu `METRICS` về 5, thêm `by_path`, `order_to_commit_min`, `counter_commit_rate`.

### T04 · Ẩn màn ngoài phạm vi 🟡 — Dev 3 · S
- **Việc:** gỡ khỏi menu: Revenue, Transfers, Attendance, Users, Vehicles, Employees, MarketConfig, NotificationInbox, CS Contacts. Giữ file.

### T03 · Bỏ contact log CS 🟡 — Dev 1 + Dev 3 · S
### T05 · Bỏ PAUSE/RESUME, `prep_time = GOODS_READY − START_PREP` 🟡 — Dev 1 · S (làm cùng E3)

---

## Đợt 3 — Chỉ trình bày trên slide ⚪ (làm nếu còn thời gian)

| Task | Lý do để sau |
|---|---|
| T10, T11 · Công suất kho theo ngày/ca | Seed lịch ca hiện tại vẫn cho engine chạy; trình bày thay đổi trên slide |
| T18 · Lập lại phần chưa giao | Demo dừng ở cảnh báo FAILED là đủ chứng minh "con người quyết định" |
| T24 · Thị trường Đan Mạch | Thay bằng slide kiến trúc adapter |
| T25 · AI gợi ý nhóm xử lý | Slide lộ trình AI |
| T02 · Bỏ SMS riêng | Gộp vào T21 |

---

## Đợt 4 — Dữ liệu, kiểm thử, diễn tập 🔴

### T26 · Seed demo Round 3 — Dev 2 · M · cần T09, T12, T15
- **Việc:** 2 kho GBG + STO, 10 cửa hàng; chuyển 4 kịch bản Malmö (000123, 000137, 000129, 000131); đơn kịch bản journey (20 pallet xi măng + 15 pallet gạch, 2 xe); đơn để Sales chọn rank 2; đơn để tài xế báo sự cố/FAILED; danh sách Dispatcher luân phiên; khách có External ID cho cả hai mock CRM.
- **Đầu ra:** seed sạch, lặp lại được; mỗi kịch bản có mã tham chiếu.

### T27 · E2E 14 bước demo — Dev 3/QA · M · cuối
- **Việc:** Playwright cho đúng 14 bước ở mục 1 (gộp các kịch bản `08` §6.3 liên quan).
- **Đầu ra:** mỗi bước PASS/FAIL/BLOCKED kèm trace/ảnh thật.

### T28 · Runbook demo + lệnh reset + video dự phòng — Dev 2 · S
- **Việc:** từng lệnh dựng môi trường từ máy trắng; lệnh reset về trạng thái đầu demo (< 2 phút); quay video luồng chính phòng khi mất mạng.

### E6 · Kịch bản demo 15 phút + 2 lần diễn tập — Người trình bày + cả nhóm · S
- **Việc:** thứ tự bấm, tài khoản từng vai trò, câu nói tương ứng từng bước, phân vai; diễn tập 2 lần có bấm giờ trên môi trường T28.
- **Đầu ra:** checklist demo + thời gian từng phần.

---

## Track trình bày (song song, không phải code)

| Task | Nội dung | Người |
|---|---|---|
| P1 · Slide Round 3 | Thay đổi so với R1/R2, cắt giảm, 46/20/4, thang cắt, CRM A/B, rủi ro, KPI | Người trình bày |
| P2 · Bảng chi phí quy ra tiền | Neo 1 đơn vị ≈ 1,4 nghìn €, license chia đôi, chi phí chạy song song | Người trình bày |
| P3 · Câu hỏi phản biện dự kiến | GPS/DPIA, Sales ngang Dispatcher, dự phòng 6%, CRM vượt ngân sách | Cả nhóm |

---

## Phụ thuộc và đường găng

```
E0 (đo hiện trạng) ─► sinh E0-xx nếu có lỗi
Đợt 1 song song:  E1  E2  E3  E4  E5  T19  T07  (T12 chờ T09, có cách tạm)
T09 ─► T12 T13 T14 T15 T21 T22
MSW:  T16 T17 (không chờ backend)
T23 độc lập từ ngày đầu
T09 + T12 + T15 ─► T26 ─► T27 ─► T28 ─► E6 diễn tập
Đường găng: T09 → T13/T14 → T26 → T27 → E6
```

## Phân người (chỉ task 🔴 và 🟡)

| Dev | Task | Ghi chú |
|---|---|---|
| Dev 1 — Backend lõi | E1, T19 (API), T07, T09, T12 (gate), T14, T15, T22 (API), T03 (API), T05 | Nặng nhất; đề xuất chuyển T22 (API) sang Dev 2 |
| Dev 2 — Tích hợp, hạ tầng | E0, E2, T12 (nạp), T13, T08, T21, T23, T26, T28 | |
| Dev 3 — Frontend | E0, E3, E4, E5, T19 (UI), T16, T06, T17, T22 (UI), T04, T03 (UI), T27 | |
| Người trình bày | P1, P2, P3, E6 | |

**Số task cho demo:** 21 bắt buộc (🔴) + 6 nên có (🟡). Lỗi phát sinh từ E0 chưa tính.
