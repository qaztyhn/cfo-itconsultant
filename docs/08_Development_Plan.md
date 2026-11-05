# 08 — Development Plan (CFO MVP)

> **Phiên bản 1.1 (06/11/2026):** bỏ thiết bị kho (seed, API, màn, E2E #5 cũ); E2E #5 mới là tranh chấp tồn kho đồng thời; E2E #6 dùng lối xử lý ngoài CFO; E2E #12 kiểm hai POD; thời gian không cố định (lịch 7 ngày chỉ tham khảo).
>
> Kế hoạch xây MVP đầy đủ phạm vi đã chốt (`01_PRD.md`), xếp theo **thứ tự phụ thuộc**, phân công cho nhóm 2–3 người, kèm dữ liệu seed, kịch bản kiểm thử E2E, tiêu chí hoàn thành và triển khai. Mục tiêu thời gian của nhóm: **không cố định, làm đến khi xong, càng nhanh càng tốt**; lịch 7 ngày ở mục 9 chỉ là tham chiếu thứ tự (slide proposal ghi 6 tuần cho dự án thật). Tài liệu tham chiếu: `04` (kiến trúc, engine), `05` (DDL), `06` (API), `03` (UI), `02` (story và AC), `07` (luồng), `09` (quy tắc cho AI coding).

## 1. Nguyên tắc thực hiện

1. **Hợp đồng trước, mã sau.** `05` (DDL) và `06` (API) là nguồn sự thật; agent không đổi tên bảng/cột/endpoint/enum/mã lỗi. Cần đổi thì cập nhật tài liệu trước, ghi vào `docs/CHANGELOG.md`.
2. **Dọc theo lát cắt chạy được.** Mỗi milestone kết thúc bằng một tình huống chạy được từ giao diện tới DB và có test.
3. **Engine là hàm thuần, test trước.** Viết test bảng cho mỗi bước ở `04` mục 6 **trước** hoặc **cùng lúc** với mã.
4. **Seed khớp thiết kế UI.** Dữ liệu seed chủ đích tạo lại các đơn trong ảnh thiết kế (mã SE-2026-000123, 137, 141…) để so ảnh.
5. **Mọi story có AC chạy được thành test** (`test_US_PLN_03_AC2_…`); PR không được gộp nếu AC liên quan chưa pass.
6. **Đồng hồ giả lập.** `core/clock.py` đọc `APP_NOW` (ví dụ `2026-11-04T10:05:00+01:00`) để demo và test lặp lại được; mọi mã nghiệp vụ lấy giờ qua `clock.now()`, không gọi `datetime.now()` trực tiếp.

## 2. Phân công (2–3 người)

| Luồng | Phụ trách | Phạm vi chính |
|---|---|---|
| **A — Backend lõi** | Dev 1 | DB migration, `engine/*`, planning, reservation, approval, forecast/risk, audit |
| **B — Tích hợp, dữ liệu, hạ tầng** | Dev 2 | Hệ thống nguồn giả lập + POS UI, adapters + ingestion, mapping, routing, notify, GPS ingest + simulator, jobs, seed, Docker/CI/deploy |
| **C — Frontend** | Dev 3 | AppShell + design system, mọi màn hình web, driver PWA, client OpenAPI |

Nếu chỉ có 2 người: **B gộp vào A** (ưu tiên nguồn giả lập, seed, ingestion trước), C giữ nguyên. Giao diện giữa các luồng là OpenAPI (`06`) — frontend dựng bằng mock (MSW) cho tới khi endpoint thật xong.

## 3. Thứ tự xây dựng theo phụ thuộc

Mỗi milestone liệt kê việc theo luồng, **Xong khi** (điều kiện thoát) và các story liên quan.

### M0 — Nền móng (không phụ thuộc)
- **A:** khởi tạo `backend/` (FastAPI, SQLAlchemy 2, Alembic, ruff, mypy, pytest); migration `0001…0008` đúng `05` (extension, schema, enum, bảng, ràng buộc, trigger, seed tham chiếu: market SE, handling_group N1–N6, special_flag, position, order_transition); auth JWT + RBAC dependency; middleware `correlation_id`; lỗi chuẩn `06` mục 1.1; `record_decision()`; `clock.py`.
- **B:** `docker-compose.yml` (postgres, mailpit, source-se, cfo-api, cfo-web); `Makefile` (`up`, `migrate`, `seed`, `test`); CI (ruff, mypy, pytest, build web, openapi diff); khung `source_system/` (FastAPI, DB riêng, model `src_*` ở `05` mục 10).
- **C:** khởi tạo Vite + React + TS strict; Tailwind với token màu/phông ở `03` mục 2 và 11; `AppShell`, `Sidebar` theo vai trò, `DemoBanner`, `PageHeader`, `StatusChip`, `RiskChip`, `ReasonModal`, `MaskedText`; màn **Sign in** (00); client OpenAPI sinh từ `/openapi.json`; mock MSW.
- **Xong khi:** `docker compose up` chạy toàn bộ; đăng nhập được bằng tài khoản seed; `GET /health` ok; migration chạy sạch trên DB trống; CI xanh. *Story:* US-EMP-03 (phần đăng nhập), US-LOG-01 AC2.

### M1 — Hệ thống nguồn giả lập và seed (phụ thuộc M0)
- **B:** hợp đồng nguồn `06` mục 16 (orders, customers, products, stock, inbound, fleet/calendar, addresses, validate/submit/cancel); POS UI (màn 5.5) dùng token chung; `seed/generate_data.py` đúng mục 7; `tools/add_market.py`; contract test.
- **A:** model SQLAlchemy cho mọi bảng `ref/hr/ops/plan/audit`; repository cơ bản; `GET /employees`, `/locations`, `/vehicles` (đọc).
- **C:** POS UI form + bảng vật liệu; màn **Order queue** ở dạng tĩnh với mock; `FilterChips`, `JourneyBar`.
- **Xong khi:** `make seed` tạo đúng dữ liệu mục 7 và lặp lại cho kết quả giống nhau; POS tạo → validate → submit một đơn. *Story:* US-SRC-01..03, US-ORD-01.

### M2 — Tích hợp và nhập liệu (phụ thuộc M1)
- **B:** `MarketAdapter`, `RestMarketAdapter`, `CsvMarketAdapter` (dự phòng); `ingest_*` jobs với checkpoint trừ 2 phút, upsert theo khóa tự nhiên, `sync_reject`, `sync_run`; tồn kho ghi đè kèm `as_of`; hàng nhập `received`; `RoutingProvider` (ORS + fallback + cache `route_matrix`); alert `SYNC_FAILED`, `STALE_DATA`; `/internal/tick`; APScheduler.
- **A:** `OrderService.prepare_for_planning` (kiểm ánh xạ SKU, chụp địa chỉ, `order_no`); `mapping_service` + ứng viên bằng quy tắc (`engine/mapping_candidates.py`); `GET /orders`, `/orders/{id}`, `/orders/counts`, `/timeline`.
- **C:** **Order queue** nối API thật; **Data integration** (5.9); **Product mapping** (5.A7).
- **Xong khi:** đơn POS vào CFO trong ≤ 5 phút; nạp lại không nhân đôi; dòng lỗi vào reject; SKU lạ chặn đơn và xuất hiện ở hàng đợi IT; IT xác nhận → đơn tự mở khóa. *Story:* US-INT-01..05, US-PRD-01..03, US-ORD-02/03.

### M3 — Nhân sự, công suất kho (phụ thuộc M0, song song M2)
- **A:** API nhân sự `06` mục 13 (employees, assignments, managers, attendance, shift templates, absences); ràng buộc một phân công hiệu lực, một quản lý chính; `attendance_gen`; `GET /warehouses/{id}/capacity`.
- **B:** seed nhân viên, ca mẫu, ngày lễ (thư viện `holidays`), bằng lái.
- **C:** **Attendance & shifts** (5.A5); **Employees & locations**, **Vehicles & drivers**, **Users** (5.A9–A11).
- **Xong khi:** "All present" ghi một lần; vắng giảm công suất đúng công thức; chuyển công tác đóng phân công cũ. *Story:* US-WH-01/02, US-EMP-01/02/04.

### M4 — Engine lập kế hoạch (phụ thuộc M2, M3) — **đường găng**
- **A:** `engine/workload.py`, `atp.py`, `capacity.py`, `schedule.py`, `delivery.py`, `gate.py`, `scoring.py`, `explain.py`, `planner.py`, `transfer.py` đúng `04` mục 6; bộ test bảng đầy đủ (mục 6.2 của tài liệu này); `PlanningService` nạp ngữ cảnh → engine → lưu `planning_run`, `fulfilment_plan`, giữ chỗ; `POST /orders/{id}/plan`; `GET /planning-runs/{id}` (gồm `rejected_candidates`, `stock_matrix`, `dates_searched`).
- **B:** ma trận lộ trình đủ cho cặp (kho, điểm giao) của mọi đơn seed; dữ liệu seed cho các tình huống kịch bản 1–7.
- **C:** **Plan review** (5.2) và **No feasible date** (5.3) với mock, rồi nối API khi sẵn sàng.
- **Xong khi:** các AC của US-PLN-01..08 và US-ATP-01 pass; một đơn seed ra đúng 3 phương án với score, checks, giải thích; đơn thiếu hàng ra `NO_FEASIBLE_DATE` kèm ngày sớm nhất; unit test engine ≥ 90% dòng. *Story:* US-PLN-01..08, US-ATP-01.

### M5 — Giữ chỗ, duyệt, chuyển kho (phụ thuộc M4)
- **A:** `ReservationService` (hold 15 phút, gia hạn ≤ 2, `hold_expiry`, advisory lock theo (kho, sản phẩm) và (kho, ngày) khi tạo giữ chỗ), `ApprovalService` (transaction, khóa theo `04` mục 7 quy tắc 8, kiểm tra lại, trip/stop, `eta_forecast` v1, thông báo `CONFIRMED`), kế hoạch tay, **xử lý ngoài CFO** (`external-handoff`), lập lại/hủy **đóng kế hoạch cũ** (`superseded`, `released`, trip/stop `cancelled`), thương lượng ngày; `Idempotency-Key`; chuyển kho (`stock_transfer` và API).
- **C:** nút Approve, `DecisionBar`, modal lý do, bộ đếm hold, Extend, tick "accept tight", kế hoạch tay, form "Handled outside CFO"; **Transfers** (5.A4); danh sách Plan review, Exceptions.
- **B:** thử tải đồng thời (hai dispatcher tranh xe, tranh cùng SKU, tranh cùng ngày công suất), seed cho kịch bản 5, 6, 9, 14.
- **Xong khi:** AC của US-RES-01, US-APR-01..04, US-ATP-02/03, US-PLN-07, US-ORD-05 pass; test đồng thời đúng một bên thắng (xe, SKU, ngày công suất); EXCLUDE chặn đơn khác nhưng cho phép cùng đơn; lập lại sau duyệt rồi duyệt lại không bị `ux_one_approved_plan` chặn.

### M6 — Thực thi, driver PWA, GPS (phụ thuộc M5)
- **A:** `ExecutionService` (sự kiện bất biến, thứ tự, idempotency, POD theo từng `trip_stop`), `GET /driver/trips`, `/warehouses/{id}/prep-queue`; chuyển trạng thái qua `transition()`.
- **B:** `gps_service` (nhận lô vị trí, kiểm `gps_enabled`, `on_road`), `tools/gps_simulator.py`, `retention_job`, `gps_lost_check`; `compliance_record`.
- **C:** **Prep queue** (5.6) + báo ngoại lệ; **Driver PWA** (5.10: danh sách, chi tiết, hàng đợi offline IndexedDB, xin quyền vị trí, thông báo riêng tư, Failed + lý do).
- **Xong khi:** đơn đi hết vòng `APPROVED → … → DELIVERED/FAILED` bằng giao diện; FAILED → xếp lại → giao lại tạo POD thứ hai; offline gửi lại không trùng; GPS lên bản đồ dispatcher (simulator); khách/CS nhận `403` với GPS. *Story:* US-WH-04/05, US-EXE-01..04, US-GPS-01..03.

### M7 — Rủi ro, cảnh báo, thông báo (phụ thuộc M6)
- **A:** `engine/forecast.py`, `RiskService` (ETA theo sự kiện/GPS/nguồn/mốc quá hạn/07:00, `eta_forecast`, màu rủi ro, 2 lần liên tiếp), `alert_service`, bản nháp `DELAY`.
- **B:** `notify_service` (outbox, giờ yên lặng, dedupe, thử lại, Mailpit/Brevo, `sms_sim`, `shadow_mode`), `milestone_overdue_check`, `morning_check`, `stale_data_check`.
- **C:** **Tracking & risk** (5.4, gồm Live position), **Notification inbox** (5.8), alerts trên Order queue, A3 Tracking list.
- **Xong khi:** AC US-RSK-01..03, US-NOT-01..03 pass; kịch bản trễ giữa chừng chạy đủ (cam → đỏ → bản nháp → dispatcher gửi); không tính lại ETA khi không có tín hiệu.

### M8 — KPI, nhật ký, quản trị, CS (phụ thuộc M6, M7)
- **A:** `audit.v_kpi_daily` (múi giờ market), `kpi_service`, `/kpi/*` (gồm `/kpi/revenue` với `can_view_revenue`), `improvement_log` nightly, `/audit/decisions`.
- **B:** baseline và chuỗi dữ liệu 48 đơn đã đóng cho "demo week" (khớp thiết kế KPI), `retention` ẩn danh.
- **C:** **KPIs & decision log** (5.7), **Handling groups & norms** (A8), **Market config & GPS** (A12), **CS Order lookup** (A14), **My store orders** (A15).
- **Xong khi:** AC US-KPI-01/02, US-LOG-01, US-ADM-01..03, US-CS-01/02 pass; quyền xem KPI đúng ma trận.

### M9 — Hoàn thiện và triển khai (phụ thuộc M1–M8)
- Chạy toàn bộ kịch bản E2E (mục 6.3); sửa lỗi; so giao diện với ảnh thiết kế; kiểm tra phân quyền cho mọi hàng ma trận `06` mục 3; thử hiệu năng; deploy staging (mục 8); README, hướng dẫn demo, `docs/CHANGELOG.md`.
- **Xong khi:** mục 10 (nghiệm thu) đạt toàn bộ.

## 4. Backlog theo mô-đun (đối chiếu story)

| Mô-đun | Nhiệm vụ chính | Story |
|---|---|---|
| Nguồn giả lập | API chuẩn, POS UI, seed, contract test | US-SRC-01..03 |
| Ingestion | Adapter, checkpoint, upsert, reject, alert | US-INT-01..04 |
| Routing | ORS, fallback, cache, `route_matrix` | US-INT-05 |
| Mapping | Task, ứng viên, confirm/reject, mở khóa đơn | US-PRD-01..05 |
| Orders | Danh sách, chi tiết, timeline, hủy/lập lại | US-ORD-01..05 |
| ATP & transfer | ATP theo thời gian, gợi ý và vòng đời chuyển kho | US-ATP-01..03 |
| Capacity & HR | Điểm danh, ca, phân công, quản lý | US-WH-01/02, US-EMP-01..04 |
| Engine | Workload, schedule, delivery, gate, scoring, explain | US-PLN-01..08 |
| Reservation & approval | Hold, extend, approve, manual, external handoff, replan, khóa đồng thời | US-RES-01, US-APR-01..04, US-ORD-05 |
| Execution | Sự kiện, POD, driver, prep queue | US-WH-04/05, US-EXE-01..04 |
| GPS | Nhận vị trí, bản đồ, mất tín hiệu, xóa | US-GPS-01..03 |
| Risk | Forecast, trạng thái, alert | US-RSK-01..03 |
| Notify | Outbox, mẫu, nháp DELAY, yên lặng | US-NOT-01..03 |
| KPI & audit | View, dashboard, nhật ký | US-KPI-01/02, US-LOG-01 |
| Admin & CS | Config, đồng bộ, GPS flag, tra cứu, liên hệ | US-ADM-01..03, US-CS-01/02 |

## 5. Dữ liệu seed (chi tiết)

Lệnh: `make seed` (`backend/app/seed/generate_data.py`, random seed cố định `20261104`). Đồng hồ demo: `APP_NOW=2026-11-04T10:05:00+01:00` (Thứ Tư 4/11/2026, Europe/Stockholm).

### 5.1 Hạ tầng
- **Market SE:** timezone `Europe/Stockholm`, `currency SEK`, `locale en`, `gps_enabled = true` (demo), `shadow_mode = false`, `config` mặc định ở `04` mục 8. Ngày lễ Thụy Điển từ thư viện `holidays`.
- **3 kho:** Göteborg DC (`GBG`, 57.7089, 11.9746, cut-off 15:00), Stockholm DC (`STO`, 59.3293, 18.0686, cut-off 15:00), Malmö DC (`MLM`, 55.6050, 13.0038, cut-off 15:00).
- **25 cửa hàng** (`ST-001…ST-025`) quanh ba vùng (ví dụ Store Göteborg Väst, Store Uppsala, Store Malmö City…) với toạ độ gần đúng; `type = store`; owner mặc định là quản lý cửa hàng.
- **Trụ sở và điều phối:** 1 `dispatch_center`, 1 `head_office`.
- **Ca mẫu mỗi kho** (T2–T6): Ca 1 06:00–14:00 (6–8 người), Ca 2 14:00–22:00 (4–6 người); `useful_hours_per_staff = 7.0` (ca 8 giờ).
- **Thiết bị kho:** không seed (ngoài MVP v1.1); giả định mọi kho đủ thiết bị. Năng lực cẩu/ben nằm ở xe (mục 5.3).

### 5.2 Sản phẩm (~100 SKU)
Phân bổ đủ N1–N6 để mọi nhóm có dữ liệu: **N1** ~25 SKU (keo tuýp, ốc vít, dụng cụ cầm tay) · **N2** ~20 (ván ép, thạch cao, gạch ốp, tấm) · **N3** ~20 (xi măng, vữa, keo dán gạch bao 25 kg theo pallet) · **N4** ~8 (cát, đá, sỏi, theo m³) · **N5** ~15 (gỗ dài, thép cây, ống, xà gồ) · **N6** ~12 (kính, khung cửa, cửa đi, sứ vệ sinh). Mỗi SKU có tên, loại, GTIN (một số trùng global để test ánh xạ), đơn vị bán, `units_to_base`, cân nặng, thể tích, giá (SEK). **3 SKU chưa ánh xạ** (khớp thiết kế): "Gipsskiva GN13 900×2700" (ERP 448812, 23,8 kg, pallet 40), "Fogbruk grå 5 kg" (POS 88412, chặn đơn SE-2026-000156), "Trall 28×120 impregnerad 4.2 m" (ERP 449130). 97 SKU còn lại đã `confirmed`.
SKU thiết kế dùng làm mẫu: SE-BRD-GYP-13 (Gypsum board 13 × 900 × 2500), SE-CEM-MOR-25 (Cement mortar 25 kg), SE-TMB-C24-4895 (C24 timber 45×95 4,8 m), SE-PNT-INT-10 (Interior wall paint 10 L), SE-TIL-ADH-25 (Tile adhesive C2TE 25 kg), SE-TIL-POR-60 (Porcelain tile 60×60 grey), SE-TIL-GRT-05 (Tile grout 5 kg), SE-CEM-MOR-25.

### 5.3 Xe và tài xế
8–10 xe, mã dạng `<KHO>-<tải>-<số>`: Van 3,5 t (1.200–3.500 kg tùy xe, 10 m³; ví dụ GBG-03-02 chở 3.500 kg), Truck 12 t (6.000 kg, 40 m³; GBG-12-03, STO-12-04, MLM-12-02), Truck 18 t (GBG-18-01, MLM-18-01), Truck 26 t (GBG-26-01), Crane truck (STO-CR-01, 8.000 kg, năng lực `crane`), Tipper (MLM, `dump`, N4). Bằng lái yêu cầu B/C/CE theo xe. **10 tài xế** (tài khoản `driver1…`), hạng bằng đa dạng; **một tài xế có bằng hết hạn** để test `LICENCE_EXPIRED`.

### 5.4 Nhân sự (~150)
Mỗi kho: 1 quản lý (`wm.got@cfo.demo` cho Göteborg), 1 phó, 1–2 trưởng ca, 10–12 công nhân. 10 tài xế. 3 dispatcher (`dispatcher@cfo.demo`). 2 CS (`cs@cfo.demo`). 1 IT (`admin@cfo.demo`). 1 Business owner (`owner@cfo.demo`, `viewer`, `can_view_revenue = true`). 1 Project lead (`lead@cfo.demo`, `viewer`, `can_view_revenue = false`). Mỗi cửa hàng: 1 quản lý + 3 sales (`sales@cfo.demo` là một sales). Công nhân kho **không có `app_user`**. Mật khẩu demo ghi trong `README` (chỉ môi trường demo).

### 5.5 Khách và địa chỉ
~40 khách (≈ 30 doanh nghiệp: Nordbygg Entreprenad AB, Uppsala Takservice AB, Mälardalens Golv AB, Öresund Fastighetsservice AB, Skånska Kakel & Klinker AB, Hallands Snickeri AB, Göta Renovering AB, Nordic Ställning AB, Bygg & Montage Väst AB…; ≈ 10 cá nhân), mỗi khách 1–3 địa chỉ có toạ độ, giờ nhận hàng mặc định (T2–T6 07:00–16:00 hoặc khác).

### 5.6 Đơn kịch bản (khớp ảnh thiết kế)

| Đơn | Khách / điểm | Tình huống seed | Trạng thái |
|---|---|---|---|
| SE-2026-000123 | Nordbygg Entreprenad AB, Kungsbacka | `exact` Tue 10 Nov, nhận 08:00–14:30, 4 dòng, 4.120 kg, 9,6 m³; ba phương án khả thi (GBG xe 12 t, MLM xe 18 t, GBG xe 18 t); 6 ứng viên bị loại (STO ngoài giờ nhận; van 3,5 t quá tải; MLM-12-02 bận; GBG-26-01 vượt 9 giờ…) | `PLANNED` |
| SE-2026-000137 | Skånska Kakel & Klinker AB, Lund | `exact` Mon 9 Nov 07:00–15:00; 3 dòng keo/gạch/vữa; GBG thiếu keo (42 < 160), STO đủ nhưng thiếu công suất, MLM đủ sau hàng nhập IN-SE-88213 (200 bao về 11/11); ngày khả thi sớm nhất Thu 12/11 | `NO_FEASIBLE_DATE` |
| SE-2026-000141 | Uppsala Takservice AB, Uppsala | STO → Uppsala, xe STO-12-04, cửa sổ 10:00–12:30; `START_PREP` 07:10, `GOODS_READY` chưa ghi dù kế hoạch 09:30; ETA dự báo 13:15 | `PREPARING`, Predicted late |
| SE-2026-000138 | Mälardalens Golv AB, Västerås | Cửa sổ 13:00–16:00; chậm lên hàng 25 phút, slack 34 phút | `LOADED`, At risk |
| SE-2026-000129 | Khách cá nhân, Malmö | Cửa sổ 12:00–18:00; ETA 13:10–13:40 | `DISPATCHED` |
| SE-2026-000131 | Öresund Fastighetsservice AB, Helsingborg | Thu 5 Nov 07:00–11:00; MLM | `APPROVED` |
| SE-2026-000144 | Nordic Ställning AB, Södertälje | Fri 6 Nov 06:30–10:00; cần xe cẩu, tổng tải (~11 t giàn giáo) vượt tải xe cẩu duy nhất của STO, nên không xe nào vừa có cẩu vừa đủ tải (`NO_CAPABLE_VEHICLE`); dùng cho kịch bản xử lý ngoài CFO (hãng đối tác có cẩu, khớp nhật ký trong ảnh thiết kế) | `MANUAL_PLANNING` |
| SE-2026-000152 | Hallands Snickeri AB, Varberg | Chỉ có ngày Wed 11 Nov | `SUBMITTED` (000152) |
| SE-2026-000118 | Göta Renovering AB, Borås | Đã giao 09:12 | `DELIVERED` |
| SE-2026-000146/149/150/153/155 | Göteborg DC | Hàng đợi chuẩn bị theo thiết kế: 126 / 210 / 45 / 96 / 70 phút; 000155 chuẩn bị xong sau giờ cắt nên lên hàng Thu 06:00 | `APPROVED`/`PREPARING`/`GOODS_READY` |
| SE-2026-000156 | — | Chứa SKU "Fogbruk grå 5 kg" chưa ánh xạ | `BLOCKED_UNMAPPED_SKU` |

Ngoài ra: ~48 đơn đã đóng trong tuần 3–9/11 cho dashboard KPI (92% đúng hạn, tỷ lệ chấp nhận 81%, sai số chuẩn bị 11 phút, sai số ETA 14 phút, 2 kế hoạch tay, 7 phương án khác được chọn; có `crew_size` ở START_PREP; một đơn FAILED rồi giao lại để có hai POD) và một vài thông báo mẫu cho Notification inbox (CONFIRMED, DISPATCHED, DELIVERED, một bản nháp DELAY, một thông báo suppressed).
Dữ liệu tồn kho, hàng nhập (gồm IN-SE-88213), lịch xe, điểm danh được sinh để các tình huống trên đúng khi chạy engine. **Các con số trong ảnh thiết kế là mục tiêu minh họa**; nếu engine cho kết quả hơi khác (ví dụ điểm số thay cho tiền), chấp nhận miễn đúng quy tắc.

## 6. Chiến lược kiểm thử

### 6.1 Cấp độ
- **Unit (engine):** bảng test cho từng bước; phủ ≥ 90% dòng `engine/`; mypy strict.
- **Integration (API + DB thật):** ingestion, upsert, reject, giữ chỗ, EXCLUDE, approve đồng thời (xe, SKU, ngày công suất), lập lại đóng kế hoạch cũ, POD nhiều lần giao, dedupe thông báo sau lập lại, dedupe cảnh báo chỉ khi đang mở, trigger chuyển trạng thái, RBAC mọi endpoint (gồm `/kpi/revenue` theo `can_view_revenue`).
- **Contract:** `source_system/openapi.yaml` với instance SE và một instance giả; `openapi diff` chặn thay đổi phá vỡ giữa backend và frontend.
- **E2E (Playwright):** kịch bản ở 6.3 chạy trên Docker Compose.
- **Phi chức năng:** thời gian lập kế hoạch một đơn < 2 giây; bảng đơn < 1 giây với 1.000 đơn; kiểm tra truy cập bằng axe.

### 6.2 Bảng test bắt buộc cho engine (mỗi hàng là một test)
Khối lượng việc (ví dụ 10,15 giờ; cờ nhân 1,625; trần 2,0; nhóm `line`); ATP (đủ ngay, đủ sau hàng nhập, hàng nhập chưa xác nhận, giữ chỗ của đơn khác, 14 ngày không đủ); công suất (điểm danh, 90%, ngày lễ, hết công suất trong 14 ngày); lịch (qua nhiều ngày, giờ cắt); xe (tải/thể tích/nhóm/năng lực/bằng/giờ lái/bận); ngày (exact không sớm, range, latest, ngoài cửa sổ, ngày làm việc kế); dự trữ (an toàn/sát/không khả thi); xếp hạng (ví dụ 0,50/0,50/0,26, vùng bỏ qua, một ứng viên, hòa nhiều tầng, mã `LOWEST_SCORE_OF_3`); tiền kiểm (`NEEDS_MULTI_VEHICLE`, `NO_CAPABLE_VEHICLE`); không khả thi (check xa nhất, ngày sớm nhất); chuyển kho (điều kiện, thứ tự); forecast (hấp thụ chậm, mốc quá hạn, GPS, làm tròn 15); rủi ro (29%, 50%, 75%, slack âm một lần và hai lần, overdue, reserve tối thiểu 30 phút).

### 6.3 Kịch bản E2E bắt buộc

| # | Kịch bản | Điểm kiểm |
|---|---|---|
| 1 | Đường lý tưởng: POS → CFO → 3 phương án → Approve → Start prep → Goods ready → Loaded → Dispatched (GPS giả lập) → Delivered | Mọi trạng thái, giữ chỗ → committed, 4 thông báo, KPI cập nhật, decision_log đủ |
| 2 | Thiếu hàng nhưng có hàng nhập xác nhận trước ngày | Phương án khả thi, `STOCK_AFTER_INBOUND`, điểm phức tạp +1 |
| 3 | Thiếu hàng mọi kho (đơn 000137) | `NO_FEASIBLE_DATE`, ngày sớm nhất 12/11, gợi ý chuyển kho; thương lượng `agreed` → chạy lại → khả thi |
| 4 | Quá công suất ngày / quá giờ cắt (đơn 000155) | Goods ready dời, lên hàng ca sau, `PREP_AFTER_CUTOFF` |
| 5 | Hai đơn tranh cùng SKU ở cùng kho (100 bao; cần 80 và 70) | Lập kế hoạch/duyệt đồng thời: tổng giữ chỗ ≤ 100; một đơn thành công, đơn kia loại kho hoặc `409 RESOURCE_CONFLICT` |
| 6 | Đơn vượt xe lớn nhất / cần xe ngoài đội (đơn 000144) | `MANUAL_PLANNING`; lập tay một xe bị `422` kèm gợi ý; dispatcher ghi nhận xử lý ngoài CFO có lý do → `HANDLED_EXTERNALLY`, `EXTERNAL_HANDOFF_RECORDED`, không thông báo tự động, KPI đếm riêng |
| 7 | Cửa sổ nhận hàng không khớp | `OUTSIDE_RECEIVING_HOURS` / dời ngày làm việc kế |
| 8 | Trễ giữa chừng (đơn 000141) | xanh → vàng → cam → PREDICTED_LATE sau hai lần; bản nháp DELAY; dispatcher sửa và gửi; không gửi lại khi lệch < 30 phút |
| 9 | Hai dispatcher duyệt cùng lúc tranh một xe | Một thành công, một `409 RESOURCE_CONFLICT` |
| 10 | Nạp lại cùng dữ liệu; dòng lỗi | Không nhân đôi; reject; `partial` |
| 11 | SKU chưa ánh xạ (đơn 000156) | `BLOCKED_UNMAPPED_SKU` → IT xác nhận → mở khóa → lập kế hoạch tự động |
| 12 | Giao thất bại rồi giao lại | `FAILED` + lý do, thông báo FAILED, replan (kế hoạch cũ `superseded`), duyệt lại (`CONFIRMED` mới), giao thành công; hai POD; tính riêng KPI |
| 13 | GPS | Simulator → bản đồ dispatcher; CS/khách `403`; mất tín hiệu 60 phút → alert; retention 30 ngày |
| 14 | Hold hết hạn / gia hạn | Extend 2 lần, lần 3 bị từ chối; Approve sau hết hạn vẫn kiểm tra lại |
| 15 | Phân quyền | CS không thấy GPS/điểm; sales không duyệt; quản lý kho A không thấy kho B; driver chỉ chuyến mình |
| 16 | Đơn đổi sau khi duyệt | Alert `ORDER_CHANGED_AFTER_APPROVAL`, không ghi đè; Replan (đóng kế hoạch cũ, duyệt lại được)/Keep/Cancel |

## 7. Definition of Done

Một nhiệm vụ chỉ "xong" khi: (1) mã chạy và đúng **AC** của story liên quan; (2) có test (unit/integration/E2E phù hợp) và CI xanh; (3) lint, mypy, format sạch; (4) không đổi hợp đồng `05/06` nếu chưa cập nhật tài liệu và `CHANGELOG`; (5) mọi hành động quyết định gọi `record_decision()`; (6) không có PII trong log; (7) có xử lý lỗi và trạng thái rỗng/tải/lỗi ở UI; (8) quyền được kiểm ở máy chủ; (9) tài liệu liên quan được cập nhật nếu hành vi đổi.

## 8. Triển khai

- **Local:** `docker compose up -d && make migrate seed` → web `http://localhost:5173`, API `:8000/docs`, Mailpit `:8025`, POS `:8100`.
- **Staging (cuối lộ trình, không phải production):**
  1. Supabase: tạo project; chạy migration và seed (CFO DB; schema `src_se` cho hệ thống nguồn); dùng chuỗi kết nối pooler.
  2. Render: dịch vụ `cfo-api` và `source-se` (Dockerfile), biến môi trường `DATABASE_URL`, `ORS_API_KEY`, `JWT_SECRET`, `SMTP_*`, `SOURCE_SE_BASE_URL`, `SOURCE_SE_API_KEY`, `INTERNAL_TICK_KEY`, `APP_ENV=staging`, `APP_NOW` (tùy chọn).
  3. Vercel: dự án `frontend` (biến `VITE_API_URL`), kèm manifest PWA.
  4. UptimeRobot hoặc cron-job.org: gọi `/health` và `/internal/tick` mỗi 5 phút (giữ service thức và thay bộ lập lịch).
  5. Bật `gps_enabled` + biểu ngữ "chưa có DPIA, chỉ demo"; kiểm tra email qua Brevo/Resend (hoặc ghi Mailpit nếu không gửi thật).
- **Giới hạn free-tier cần kiểm tra lại trước khi deploy:** Render ngủ sau ~15 phút; Supabase tạm dừng sau ~1 tuần không hoạt động và dung lượng ~500 MB; Vercel Hobby phi thương mại; quota ORS theo ngày (ma trận tính trước và cache).
- **CI:** `ruff`, `mypy`, `pytest` (với Postgres service), `openapi diff`, build web; chạy E2E trên nhánh chính.

## 9. Lịch tham chiếu 7 ngày (3 người) — chỉ để tham khảo thứ tự, không phải cam kết thời gian

| Ngày | A — Backend lõi | B — Tích hợp/hạ tầng | C — Frontend |
|---|---|---|---|
| 1 | M0: migration, auth, RBAC, audit, clock, lỗi chuẩn | M0: Compose, CI, khung source system | M0: shell, token, Sign in, client OpenAPI, mock |
| 2 | M1/M2: models, orders API, mapping service, workload + ATP (test trước) | M1/M2: source API + POS, seed, adapter + ingestion | Order queue, POS UI, Data integration |
| 3 | M3/M4: HR API, capacity, schedule, delivery, gate (test trước) | M2/M3: routing + matrix, jobs, seed nhân sự, mapping candidates | Attendance, Product mapping, Employees |
| 4 | M4/M5: scoring, planner, planning service, reservation, approval, transfers | Seed kịch bản 1–7, thử đồng thời | Plan review, No feasible date, Transfers, Exceptions |
| 5 | M6/M7: execution, forecast, risk, alerts | GPS ingest + simulator, notify + Mailpit, jobs rủi ro | Prep queue, Driver PWA, Tracking & risk |
| 6 | M8: KPI views, audit API, improvement | Seed KPI/tuần demo, retention, E2E kịch bản | KPIs, Notification inbox, IT screens, CS, Store |
| 7 | M9: sửa lỗi, hiệu năng, kiểm tra RBAC toàn bộ | Deploy staging, ping, README, demo script | Hoàn thiện UI theo thiết kế, a11y, PWA, so ảnh |

**Đường găng:** M0 → M1 → M2 → M4 → M5 → M6 → M7. Frontend dùng mock từ ngày 1 để không chờ backend; backend ưu tiên endpoint theo thứ tự màn hình (Order queue → Plan review → Prep queue/Driver → Tracking).

## 10. Nghiệm thu MVP

- [ ] `docker compose up` + `make migrate seed` dựng toàn bộ hệ thống từ trống; seed lặp lại cho kết quả giống nhau.
- [ ] 16 kịch bản E2E (mục 6.3) pass; toàn bộ AC ở `02` pass.
- [ ] Mọi hàng ma trận quyền `06` mục 3 có test cho đường cho phép và bị cấm; CS/khách/sales không bao giờ nhận GPS.
- [ ] Không có double-book xe, tài xế, hàng (kiểm bằng test đồng thời); nạp lại idempotent.
- [ ] Mọi quyết định có `decision_log`; `decision_log`/`milestone_event` bất biến; log kỹ thuật không PII.
- [ ] Dashboard KPI đủ 8 chỉ số + 2 chẩn đoán, ngày theo múi giờ market, so với baseline; "cost per delivery" hiển thị là giờ công và km, không quy tiền.
- [ ] Engine ≥ 90% dòng; lập kế hoạch một đơn < 2 giây; bảng đơn < 1 giây với 1.000 đơn.
- [ ] Giao diện khớp ngôn ngữ hình ảnh và bố cục ở `03`; các điều chỉnh mục 7 của `03` đã áp dụng; driver PWA cài được, offline gửi lại không trùng.
- [ ] Staging online chạy với ping 5 phút; email qua Mailpit/Brevo; SMS mô phỏng; biểu ngữ DPIA hiện khi GPS bật.
- [ ] Thêm một nước giả (`add_market.py`) không sửa file nào trong `engine/`.
- [ ] `README`, hướng dẫn demo và `CHANGELOG` hoàn chỉnh.

## 11. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Engine phức tạp, nhiều biên | Test bảng viết trước, mypy strict, ví dụ số cụ thể ở `04`; hàm thuần dễ tách việc |
| Giữ chỗ và đồng thời | Ràng buộc EXCLUDE ở DB (kể cả `order_id WITH <>`), transaction + khóa, test đồng thời; thử `btree_gist` trên PostgreSQL 16 sớm (ngày 1) |
| Số liệu giả định sai thực tế | Tất cả ở `MarketConfig`/bảng định mức, có `improvement_log` để hiệu chỉnh sau pilot |
| GPS trên PWA hạn chế (iOS) | Bộ giả lập cho demo; app native ở phần mở rộng; DPIA trước khi dùng thật |
| Free-tier (ngủ, tạm dừng, quota) | Ping 5 phút, ma trận tính trước, cache, fallback lộ trình |
| Frontend chờ backend | Hợp đồng OpenAPI sớm + mock MSW; seed khớp thiết kế |
| Lệch giữa thiết kế UI và quy tắc | Bảng 24 điều chỉnh ở `03` mục 7 là chuẩn; mọi thay đổi ghi vào `CHANGELOG` |

## 12. Điểm cần xác nhận khi bắt đầu (mặc định đã chọn)

| # | Nội dung | Mặc định |
|---|---|---|
| 1 | Khóa ORS và quota | Có khóa miễn phí; nếu chưa, chạy bằng fallback có nhãn "Estimated route" |
| 2 | Dịch vụ email online | Mailpit khi local; Brevo hoặc Resend free khi staging |
| 3 | Tên miền và CORS | Chỉ origin của Vercel và localhost |
| 4 | Đồng hồ demo | `APP_NOW` = 2026-11-04 10:05 (Europe/Stockholm) khi quay demo |
| 5 | Mật khẩu demo | Ghi trong README, chỉ ở môi trường demo |
| 6 | Định mức, hệ số cờ, giờ hữu ích | Số minh họa ở `05` mục 11 (IT nhập cứng); IT thay bằng số thật khi có |
| 7 | Thiết bị kho | Không quản lý trong MVP; giả định mọi kho đủ thiết bị |
| 8 | Đơn cần nhiều xe | Không có thuật toán; ghi nhận `HANDLED_EXTERNALLY` |
| 9 | Doanh thu | Σ số lượng × đơn giá của đơn DELIVERED; mỗi nước một tiền tệ; xem bởi owner, admin, Business owner |
| 10 | Ngày demo | `APP_NOW` = Thứ Tư 2026-11-04 10:05; ví dụ trong `02` dùng cùng ngày |
| 11 | Gợi ý chuyển kho | Giữ trong MVP (quy tắc, không AI) |
| 12 | Hòa điểm cuối cùng | Giữ "mã xe nhỏ hơn"; "xe nhỏ hơn" là cải tiến sau pilot |
