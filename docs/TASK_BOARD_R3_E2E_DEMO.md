# CFO — Task board Round 3 (luồng end-to-end cho demo)

> Ngày: 2026-11-19. Căn cứ: DEC-R3-01 → 10, DEC-R3-15 và docs đã đồng bộ ở nhánh `claude/serene-goodall-rdm4re` (commit mới nhất):
> `02` (US/AC), `05` §13, `06` §19, `07`, `03`, `04`, `10` §0. Đối chiếu code `main` tại `b990399`.
> CRM để sau (DEC-R3-11 → 14 đã hủy). File điều phối, không phải phê duyệt mới.

**Nhãn:** 🔴 bắt buộc cho demo · 🟡 nên có · ⚪ chỉ trình bày.
**DoD chung:** test theo tên `test_US_<EPIC>_<NN>_AC<k>_…`, cả đường được phép và bị cấm; task chạm DB có test PostgreSQL thật;
`tools/harness.py` xanh, lệnh không chạy ghi **NOT VERIFIED**; không log PII/tọa độ; PR ghi `Assumptions: reviewed`.
Cỡ: S ≈ 0,5–1 ngày · M ≈ 2–3 · L ≈ 4–5.

## 1. Luồng demo (14 bước) và task cần

| # | Bước | Vai trò | US/AC | Hiện trạng code | Task |
|---|---|---|---|---|---|
| 1 | Tạo đơn trong POS giả lập | Sales | US-SRC-01..03 | Chưa có POS UI, đã thử tạo và submit đơn qua Source API | E0 |
| 2 | Sync now + Check feasibility | Sales | US-ORD-06, flow 2a | Có | E0 |
| 3 | 3 phương án; Sales chọn rank 1–3 | Sales | US-APR-05 | Chỉ rank-1 | T19 |
| 4 | Duyệt → APPROVED, gán Dispatcher luân phiên | Sales/Dispatcher | US-APR-01, US-GPS-02 AC3 | **Chặn**: duyệt luôn lỗi ngoài môi trường test (WMS ACK); gate tài xế cần proof 56 ngày | E1, T12, T15 |
| 5 | Email CONFIRMED | Hệ thống | US-NOT-01 | **Không gửi**: chỉ job ingest được lên lịch; `/internal/tick` stub | E2, T21 |
| 6 | Dispatcher: hàng đợi → Plan review → duyệt | Dispatcher | US-APR-01 | `PlanReviewList` rỗng | E4 |
| 7 | Kho: Start prep → Goods ready → Loaded từng xe | Warehouse | US-WH-04 | Backend có; **UI không có nút** (PR #186 draft) | E3, T05 |
| 8 | Tài xế: Dispatched → Cập nhật vị trí → Delivered kèm vị trí | Driver | US-EXE-02, US-GPS-01 | Có Dispatched/POD; chưa có vị trí | T06, T13, T14, T16 |
| 9 | Dispatcher: dòng "Vị trí gần nhất · Giờ cập nhật · ETA", rủi ro, DELAY | Dispatcher | US-GPS-02, US-RSK-01/02, US-NOT-02 | Chưa có dòng vị trí; DELAY draft cần kiểm | T17, T08, E5 |
| 10 | Email DISPATCHED, DELIVERED (hoặc DELAY) | Hệ thống | US-NOT-01/02 | Phụ thuộc E2 | E2, T21 |
| 11 | CS tra cứu trạng thái + ETA | CS | US-CS-01 | Có | T03, E0 |
| 12 | KPI 5 chỉ số, tách theo đường | Owner/Lead | US-KPI-01 | Màn 10 KPI | T22 |
| 12b | Đơn hàng & doanh thu: doanh thu, tổng đơn, 5 nhóm trạng thái theo kỳ | Business owner/owner | US-REV-01, US-REV-02 | Màn Revenue có; chưa có nhóm trạng thái | T29, T30 |
| 13 | Ngoại lệ: chuyến FAILED → cảnh báo → Dispatcher xử lý | Driver/Dispatcher | US-EXE-02 AC7, US-EXE-04/05 | Đang tự lập lại kế hoạch | T07, T18 |

---

## Đợt 0 — Đo hiện trạng

### E0 · Chạy thử luồng trên `main` 🔴 — Dev 2 + Dev 3 · S
- **Việc:** theo `docs/DEMO_SETUP.md`: `docker compose up`, migrate, seed; đi tay 13 bước bằng tài khoản demo.
- **Đầu ra:** bảng PASS/FAIL/BLOCKED 14 bước kèm log/ảnh; lỗi mới → task `E0-xx`.

---

## Đợt 1 — Gỡ chặn luồng chính (song song)

### E1 · Duyệt được trong demo với ACK WMS mô phỏng 🔴 — Dev 1 · M
- **Căn cứ:** DEC-WMS-RESERVE-SYNC-20261109 (ACK mô phỏng chỉ staging/demo, nhãn *simulated*). US-APR-01 AC1.
- **Việc:** `WMS_RESERVATION_MODE=simulated` chỉ khi `APP_ENV ≠ production`; `approval_service.py:506–518` ghi intent + ACK mô phỏng (adapter disposable đã có) rồi cho duyệt; production vẫn fail closed.
- **Đầu ra:** test PG: demo → `APPROVED`, ledger `simulated=true`; production → `PLAN_NOT_APPROVABLE`.

### E2 · Lên lịch job nền + `/internal/tick` 🔴 — Dev 2 · S–M
- **Căn cứ:** US-NOT-01, US-NOT-03, US-RES-01 AC4, US-RSK-01 AC2/AC5, US-GPS-03.
- **Việc:** `jobs/scheduler.py` thêm `outbox`, `hold_expiry`, `risk_check` (T08), `retention` (T13); viết `/internal/tick` (stub) với key riêng.
- **Đầu ra:** test đăng ký job; gọi tick → email `sent` trong Mailpit.

### E3 · Nút mốc kho trên Prep Queue 🔴 — Dev 3 · M
- **Căn cứ:** US-WH-04, US-WH-05, `03` §5.6.
- **Việc:** lấy phần UI của PR #186 hoặc viết mới: Start prep (số người), Goods ready, Mark loaded từng xe; 3 thẻ ngoại lệ (Shortage/Breakage/Vehicle issue); không Pause/Resume.
- **Đầu ra:** test UI thứ tự mốc; 409 hiển thị rõ. Đóng/thay PR #186.

### E4 · Màn danh sách Plan review 🔴 — Dev 3 · S
- **Căn cứ:** `03` A1. **Việc:** `PlanReviewList.tsx` hiện các run đang giữ chỗ, mở `PlanReview/:runId`.

### E5 · Màn DELAY draft cho Dispatcher 🔴 — Dev 3 · S
- **Căn cứ:** US-NOT-02, `03` §5.4. **Việc:** xem → sửa khung ETA/lý do mẫu → Send/Discard (API có sẵn); không ô nội dung tự do.

### T19 · Sales duyệt trong phạm vi 🔴 — Dev 1 (API) + Dev 3 (UI) · M
- **Căn cứ:** US-APR-05 AC1–AC8, `06` §19.1–19.2.
- **Việc:** nới `approval_service.py:379–434`; Sales rank 1–3 mọi kho, lý do cho rank 2–3, chạy lại planner, thỏa thuận ngày; bỏ tick lịch sát cho mọi vai trò; Sales gọi manual/override/replan sau thực thi/DELAY → 403. `SalesSyncCheck` hiện 3 phương án để chọn.

### T07 · FAILED và sự cố xe chỉ cảnh báo 🔴 — Dev 1 · M
- **Căn cứ:** US-EXE-02 AC3/AC7, US-WH-05 AC2, US-APR-04 AC1, `06` §19.3.
- **Việc:** bỏ `suggest_replan` (`execution_service.py:594`, `:610`); alert `DELIVERY_FAILED` kèm kết quả từng chuyến; `VEHICLE_ISSUE` → alert `EXCEPTION`.

---

## Đợt 2 — Thay đổi R3 trong luồng demo

### T09 · Migration R3 gộp 🔴 — Dev 1 · M — *chặn T10, T12, T13, T14, T15, T18, T21, T22*
- **Căn cứ:** `05` §13. **Việc:** một forward migration + model; ngày đầu chốt `record_point(session, trip_id, point, source) -> RemainingRoute` cho T13/T14.
- **Đầu ra:** migrate lên/xuống sạch trên DB trống và DB có seed cũ.

### T12 · Tài xế đã xác minh 🔴 — Dev 2 (nạp) + Dev 1 (gate) · M · cần T09
- **Căn cứ:** DEC-R3-07, `05` §13.3, `06` §19.6, `04` §6.7.
- **Việc:** nguồn `/fleet/driver-availability`, `/fleet/driver-eligibility`; adapter upsert; `official_driver_context` dùng khung khả dụng, `max_driving_min`, quyền lái; seed `synthetic_demo`.
- **Đầu ra:** gate pass với seed demo; ca bị loại → `NO_DRIVER (not_verified)`. *Cách tạm:* bật `demo_d7_reader` (#206) tới khi xong.

### T10 · Công suất kho theo ngày/ca 🟡 — Dev 1 · M · cần T09
- **Căn cứ:** US-WH-01, US-WH-02 AC1–AC4, `06` §19.5.
- **Việc:** `official_warehouse_capacity` đọc `warehouse_day_capacity`; API `day-capacity` có audit; gỡ `attendance_gen`.
- *Ghi chú demo:* seed lịch ca cũ vẫn cho engine chạy nếu T10 chưa xong.

### T11 · Form Công suất ngày 🟡 — Dev 3 · S · MSW
- **Căn cứ:** `03` A5.

### T13 · Nhận vị trí (backend) 🔴 — Dev 2 · M · cần T09
- **Căn cứ:** US-GPS-01, US-GPS-02 AC1/AC2, US-GPS-03, `06` §19.3.
- **Việc:** `gps_service` một điểm/lần; `remaining_km/min` qua `RoutingProvider`; `GET /gps/live` một dòng/chuyến cho Dispatcher được gán; bỏ route lịch sử; xóa tọa độ khi đơn kết thúc.

### T14 · Vị trí bắt buộc khi hoàn tất, sự cố, ETA từ vị trí 🔴 — Dev 1 · M · cần T09
- **Căn cứ:** US-EXE-02 AC8, US-EXE-05, US-RSK-01 AC1, `04` §6.3.
- **Việc:** DELIVERED/FAILED thiếu vị trí → 422; `site_distance_m`; `DRIVER_INCIDENT` + alert; engine `forecast` dùng vị trí; viết `GET /orders/{id}/eta-forecasts` (stub).

### T15 · Gán Dispatcher luân phiên + bàn giao 🔴 — Dev 1 · S–M · cần T09
- **Căn cứ:** US-GPS-02 AC3, US-APR-01 AC1.

### T16 · Trang tài xế: Cập nhật vị trí, Báo sự cố, hoàn tất kèm vị trí 🔴 — Dev 3 · M · MSW
- **Căn cứ:** `03` §5.10, US-GPS-01 AC4, US-EXE-05.

### T06 · Trang tài xế bỏ offline 🟡 — Dev 3 · S
- **Căn cứ:** US-EXE-03. **Việc:** xóa `offlineQueue.ts`, `offlineEvents.ts`, thu vị trí theo chu kỳ; retry cùng key.

### T17 · Dòng vị trí gần nhất + Bàn giao 🔴 — Dev 3 · S · MSW
- **Căn cứ:** US-GPS-02, `03` §5.4. **Việc:** thay `TrackingList` bằng danh sách chuyến được gán.

### T08 · Cảnh báo quá hạn 30 phút 🟡 — Dev 2 · S
- **Căn cứ:** US-RSK-01 AC2/AC5. **Việc:** viết `jobs/risk_check.py` (stub); chỉ alert, không tính ETA.

### T21 · Chỉ email + cờ DISPATCHED 🔴 — Dev 2 · S · cần T09
- **Căn cứ:** US-NOT-01 AC3, `06` §19.7. **Việc:** bỏ `sms_sim`; DISPATCHED một lần/đơn; cờ `NOTIFY_DISPATCHED_ENABLED`.

### T18 · Lập lại phần chưa giao, hẹn lại, hủy 🟡 — Dev 1 · L · cần T09
- **Căn cứ:** US-EXE-04 AC1–AC6, `06` §19.4. **Việc:** viết `replan` (`scope=remaining|full`) và `cancel` (stub `orders.py:298–306`).
- *Ghi chú demo:* bước 13 có thể dừng ở cảnh báo FAILED nếu T18 chưa xong.

### T22 · 5 KPI tách theo đường 🟡 — Dev 1 (API) + Dev 3 (UI) · M · cần T09
- **Căn cứ:** US-KPI-01 AC1/AC5/AC6, `06` §19.8, `03` §5.7.

### T05 · Bỏ PAUSE/RESUME 🟡 — Dev 1 · S (làm cùng E3)
- **Căn cứ:** US-WH-04 AC6/AC7.

### T03 · Bỏ contact log CS 🟡 — Dev 1 + Dev 3 · S
- **Căn cứ:** US-CS-02.

### T04 · Gỡ màn bị cắt khỏi menu và router 🔴 — Dev 3 · S
- **Căn cứ:** `03` §3.2, DEC-R3-15. **Việc:** gỡ Transfers (Dispatcher và kho), Users, Vehicles, Employees, Market config, bản đồ Tracking (thay bằng T17), CS Contacts; Attendance & shifts thay bằng Công suất ngày. Giữ file component; URL trực tiếp → trang "Không thuộc phạm vi pilot".
- **Đầu ra:** test menu theo vai trò; build xanh.

### T31 · Không mount API chuyển kho và API ghi quản trị 🟡 — Dev 1 · S
- **Căn cứ:** `06` §19.1, DEC-R3-15. **Việc:** gỡ đăng ký `/transfers/*`, `/orders/{id}/transfer-suggestions`, `POST /employees`, `/users*`, `POST /vehicles`, `/markets/{code}/config`, shift-templates, absences; `NO_FEASIBLE_DATE` không trả gợi ý chuyển kho. API đọc phục vụ lập kế hoạch giữ nguyên.
- **Đầu ra:** test 404 cho từng route; test planning cũ vẫn xanh.

### T29 · API Đơn hàng theo nhóm trạng thái 🔴 — Dev 1 · S–M
- **Căn cứ:** US-REV-02 AC1–AC7, `06` §19.11. **Việc:** `GET /revenue/order-status` (5 nhóm theo `committed_date`; nhóm hủy theo ngày chuyển `CANCELLED`; bỏ đơn chờ duyệt; quyền như `/revenue/*`); thêm `status_group` cho `/revenue/orders`.
- **Đầu ra:** test PG cho phân nhóm, biên kỳ, đơn hủy trước duyệt, đơn chờ duyệt bị loại, quyền (owner nơi khác 404, vai trò khác 403), tổng nhóm = tổng đơn.

### T30 · Màn Đơn hàng & doanh thu 🔴 — Dev 3 · S · MSW
- **Căn cứ:** `03` A16b. **Việc:** mở rộng màn Revenue: thẻ doanh thu + tổng đơn, 5 thẻ nhóm trạng thái, thanh tỷ trọng, bấm thẻ → bảng đơn của nhóm.
- **Đầu ra:** test UI bộ lọc kỳ, góc nhìn, bấm nhóm.

---

## Đợt 3 — Dữ liệu, kiểm thử, diễn tập 🔴

### T26 · Seed demo R3 — Dev 2 · M · cần T09, T12, T15
- Đơn trải đủ 5 nhóm trạng thái trong kỳ demo (có đơn hủy trước duyệt) cho màn Đơn hàng & doanh thu; 2 kho GBG + STO, 10 cửa hàng; chuyển 4 kịch bản Malmö (000123, 000137, 000129, 000131); đơn journey 20 pallet xi măng + 15 pallet gạch (2 xe); đơn cho Sales chọn rank 2; đơn cho sự cố/FAILED; công suất ngày; tài xế đã xác minh; danh sách Dispatcher luân phiên.

### T27 · E2E 14 bước — Dev 3/QA · M · cuối
- Playwright đúng 14 bước ở mục 1 (gồm 12b); PASS/FAIL/BLOCKED kèm trace thật.

### T28 · Runbook + lệnh reset + video dự phòng — Dev 2 · S

### E6 · Kịch bản demo 15 phút + 2 lần diễn tập — Người trình bày + cả nhóm · S

---

## Phụ thuộc

```
E0 ─► sinh E0-xx nếu có lỗi
Đợt 1 song song: E1 E2 E3 E4 E5 T19 T07
T09 ─► T10 T12 T13 T14 T15 T18 T21 T22
MSW (không chờ backend): T11 T16 T17 T30
Độc lập: T29 T31
T09 + T12 + T15 ─► T26 ─► T27 ─► T28 ─► E6
Đường găng: T09 → T13/T14 → T26 → T27 → E6
```

## Phân người (theo `docs/10` §0)

| Dev | Task |
|---|---|
| Dev 1 — Backend lõi | E1, T19 (API), T07, T09, T12 (gate), T14, T15, T29, T31, T10, T18, T22 (API), T05, T03 (API) |
| Dev 2 — Tích hợp, hạ tầng | E0, E2, T12 (nạp), T13, T08, T21, T26, T28 |
| Dev 3 — Frontend | E0, E3, E4, E5, T19 (UI), T16, T06, T17, T30, T04, T11, T22 (UI), T03 (UI), T27 |
| Người trình bày | E6, slide (ngân sách, CRM chỉ trình bày) |

**Tổng:** 23 task 🔴 + 9 task 🟡 (T10, T11, T18 là 🟡 vì demo vẫn chạy được khi chưa có; T04 lên 🔴 vì menu demo phải gọn). Lỗi phát sinh từ E0 chưa tính.

## Câu hỏi mở
1. Dev 1 nặng nhất: có chuyển T10, T29 hoặc T22 (API) sang Dev 2 không? (lệch phân công file trong `docs/10`).
