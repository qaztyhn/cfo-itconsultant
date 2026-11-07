# 10 — Phân công nhóm 3 người (CFO MVP)

> Dựa trên khung mã trong repo này và tài liệu `01`–`09` bản **v1.2**. Mỗi file trong khung có docstring ghi **Owner** và việc cần làm (`TODO(#…)`). Bảng dưới gom lại theo người. Thời gian không cố định (làm đến khi xong, càng nhanh càng tốt), nên công việc xếp theo **thứ tự phụ thuộc** (milestone M0 → M9 ở `08` mục 3), không theo ngày.
>
> Thay tên thật vào ba vai dưới đây khi nhóm chốt người.

## 1. Ba vai

| Vai | Người | Phụ trách chính | Thư mục sở hữu |
|---|---|---|---|
| **Dev 1 — Backend lõi** | _(điền tên)_ | Database, engine lập kế hoạch, giữ chỗ/duyệt, vòng đời đơn, rủi ro, KPI, audit | `backend/alembic/`, `backend/app/{core,domain,engine,audit}/`, phần lớn `backend/app/services/` và `backend/app/api/v1/` |
| **Dev 2 — Tích hợp, dữ liệu, hạ tầng** | _(điền tên)_ | Hệ thống nguồn giả lập, adapter + ingestion, routing, seed, GPS, thông báo, job, Docker/CI/deploy | `source_system/`, `backend/app/{adapters,providers,jobs,seed}/`, `tools/`, `docker-compose.yml`, `Makefile`, `.github/` |
| **Dev 3 — Frontend** | _(điền tên)_ | Design system, mọi màn web, driver PWA, POS UI, client OpenAPI, mock | `frontend/`, `source_system/pos_ui/` |

**Giao diện giữa các vai:** OpenAPI sinh từ backend (`06`) là hợp đồng giữa Dev 1/2 và Dev 3. Dev 3 dựng màn bằng mock MSW (`frontend/src/api/mocks/handlers.ts`) cho tới khi endpoint thật xong. Hợp đồng nguồn `source_system/openapi.yaml` là giao diện giữa Dev 2 và phần còn lại.

## 2. Việc cụ thể theo milestone

### M0 — Nền móng (không phụ thuộc, cả ba làm song song)

| Người | Việc | File trong khung | Xong khi |
|---|---|---|---|
| Dev 1 | Viết 8 migration đúng `05` (gồm `plan.plan_vehicle`, `planning_run.kind`, sự kiện `PREP_PAUSED`/`PREP_RESUMED`, POD theo `trip_stop_id`, `ux_alert_open_dedupe`, `kpi_scopes`, hai view doanh thu; không bảng thiết bị, không `MANUAL_PLANNING`); auth JWT + argon2 + RBAC; `record_decision()`; `logging.log_event` không PII | `alembic/versions/0001…0008`, `core/security.py`, `core/logging.py`, `deps.py`, `audit/recorder.py` | Migration chạy sạch trên DB trống; đăng nhập được; `/auth/me` trả vai trò |
| Dev 2 | Docker Compose chạy đủ 5 service; Makefile; CI xanh; khung `source_system` có DB riêng và model `src_*` | `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml`, `source_system/app/*` | `docker compose up` + `GET /health` ok cả CFO và nguồn |
| Dev 3 | Tailwind token, `AppShell`, `Sidebar` lọc theo vai trò, `DemoBanner`, `PageHeader`, `StatusChip`, `RiskChip`, `ReasonModal`, `MaskedText`, `StateViews`; màn Sign in; `apiFetch` + sinh client | `tailwind.config.ts`, `src/components/*`, `src/features/auth/SignIn.tsx`, `src/api/client.ts`, `src/app/router.tsx`, `src/app/guards.tsx` | Đăng nhập bằng tài khoản seed; menu đúng theo vai trò |

### M1 — Nguồn giả lập và seed

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 2 | Endpoint nguồn theo `06` mục 16 (validate/submit/cancel, phân trang); seed đầy đủ `08` mục 5 (random seed 20261104, không seed thiết bị, xe STO-CR-01 8 t, Business owner `kpi_scopes={revenue_all}`, Project lead `{ops}`, mật khẩu demo đọc từ `SEED_DEMO_PASSWORD`, không ghi vào file); `add_market.py`; contract test | `source_system/app/api.py`, `models.py`, `openapi.yaml`, `backend/app/seed/generate_data.py`, `tools/add_market.py` | US-SRC-01..03, US-INT-04 |
| Dev 1 | Model SQLAlchemy 6 schema; `GET /employees`, `/locations`, `/vehicles` | `domain/models/*.py`, `api/v1/hr.py` | — |
| Dev 3 | POS UI (Date type Exact/Range/Latest, không cột Handling group); Order queue tĩnh với mock; `FilterChips`, `JourneyBar` | `source_system/pos_ui/`, `features/dispatcher/OrderQueue.tsx` | US-ORD-01 |

### M2 — Tích hợp và nhập liệu

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 2 | `RestMarketAdapter`, `CsvMarketAdapter` (hash), registry; `ingest_service` (checkpoint −2', upsert theo version, reject, SKU chưa ánh xạ nạp `pending`, `ORDER_CHANGED_AFTER_APPROVAL`, `STALE_DATA`); ORS + fallback + `route_matrix`; APScheduler + `/internal/tick`; `/integration/overview`, `/sync/*`, `/markets/{code}/config` | `adapters/*`, `services/ingest_service.py`, `providers/routing_*.py`, `jobs/scheduler.py`, `jobs/ingest.py`, `api/v1/admin.py`, `api/v1/internal.py` | US-INT-01..05, US-ADM-01/02 |
| Dev 1 | `order_service.prepare_for_planning`; `mapping_service` + `engine/mapping_candidates.py` (N6 không FRAGILE); API orders, counts, timeline, mapping | `services/order_service.py`, `services/mapping_service.py`, `engine/mapping_candidates.py`, `api/v1/orders.py`, `api/v1/mapping.py` | US-PRD-01..05, US-ORD-02/03 |
| Dev 3 | Order queue nối API thật (cột CUSTOMER · SITE gộp, cột chip rủi ro); Data integration (unmapped tách khỏi rejected); Product mapping | `features/dispatcher/OrderQueue.tsx`, `features/it/DataIntegration.tsx`, `features/it/ProductMapping.tsx` | — |

**M2-S (US-INT-06):** Dev 2 chịu trách nhiệm sync-now API/adapter/ingestion/polling fallback; Dev 1 chịu trách nhiệm duyệt hợp đồng RBAC/scope; Dev 3 UI Sales trong CFO, không sửa POS cũ. Chốt OpenAPI trước.

### M3 — Nhân sự, công suất (song song M2)

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 1 | `hr_service` (một phân công hiệu lực, một quản lý chính, terminate); điểm danh All present; `capacity()` = người × giờ hữu ích × 90% (không thiết bị); job `attendance_gen` | `services/hr_service.py`, `api/v1/hr.py`, `jobs/attendance_gen.py` | US-WH-01/02, US-EMP-01..04 |
| Dev 2 | Seed nhân viên, ca mẫu, ngày lễ (`holidays`), bằng lái (1 bằng hết hạn) | `seed/generate_data.py` | — |
| Dev 3 | Attendance & shifts (không tab Equipment); Employees & locations; Vehicles & drivers; Users (`kpi_scopes`) | `features/warehouse/Attendance.tsx`, `features/it/{Employees,Vehicles,Users}.tsx` | — |

### M4 — Engine lập kế hoạch (đường găng)

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 1 | Viết test bảng **trước** cho từng bước (`08` mục 6.2), rồi hiện thực `workload` (đơn vị cơ sở nhỏ nhất) → `atp` → `capacity` → `schedule` → `delivery` (**bộ xe ít nhất**, chia hàng, tới cùng lúc ±30') → `gate` → `scoring` (ít xe trước, hòa điểm xe nhỏ hơn) → `explain` → `transfer` → `planner`; `planning_service` (một transaction, giữ chỗ qua `reservation_service`); `POST /orders/{id}/plan`, `GET /planning-runs/{id}` | `engine/*.py`, `services/planning_service.py`, `api/v1/planning.py`, `tests/unit/` | US-PLN-01..08, US-ATP-01 |
| Dev 2 | Ma trận lộ trình cho mọi cặp (kho, điểm giao) của đơn seed; dữ liệu seed cho kịch bản 1–7 (000123 ra 3 phương án, 000137 ngày sớm nhất 12/11, 000144 thiếu năng lực cẩu → `NO_FEASIBLE_DATE`, 000160 cần 2 xe) | `seed/scenarios.py` | — |
| Dev 3 | Plan review (thứ tự theo `rank` API, không tiền, Slack, Planning reserve); No feasible date (Dates searched, bảng check theo kho, Usable stock) — bằng mock rồi nối API | `features/dispatcher/PlanReview.tsx`, `features/dispatcher/NoFeasibleDate.tsx`, `components/PlanCard.tsx`, `components/RejectedCandidatesTable.tsx`, `components/CheckChip.tsx`, `components/VehicleList.tsx` | — |

**Xong M4 khi:** engine ≥ 90% dòng, mypy strict sạch, một đơn < 2 giây, AC US-PLN-01..08 pass.

### M5 — Giữ chỗ, duyệt, vòng đời, chuyển kho

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 1 | `reservation_service` (hold, extend ≤ 2, **không khóa khi giữ chỗ**); `approval_service` (approve với advisory lock `stock:`/`labour:` theo thứ tự kho → sản phẩm → ngày → xe → tài xế **chỉ khi duyệt**, manual plan nhiều xe, **duyệt/giữ phương án gợi ý lập lại**, date negotiation); `planning_service.suggest_replan` (4 tín hiệu, coi kế hoạch cũ như không tồn tại, không giữ chỗ); `domain/transitions.close_active_plan` (đóng kế hoạch cũ khi lập lại/hủy/xếp lại); `transfer_service`; Idempotency-Key; job `hold_expiry` | `services/reservation_service.py`, `services/approval_service.py`, `services/transfer_service.py`, `domain/transitions.py`, `core/db.py`, `api/v1/planning.py`, `api/v1/transfers.py`, `jobs/hold_expiry.py` | US-RES-01, US-APR-01..04, US-ATP-02/03, US-ORD-04/05, US-PLN-07 |
| Dev 2 | Test tải đồng thời: lập kế hoạch đồng thời cho phép vượt; duyệt đồng thời tranh **xe**, **cùng SKU**, **cùng ngày công suất** (mỗi trường hợp đúng một thắng); seed kịch bản 5, 6, 9, 12, 14, 16 | `backend/tests/integration/` | — |
| Dev 3 | Nút Approve, `DecisionBar`, bộ đếm hold + Extend, tick "accept tight", `ReasonModal`; màn kế hoạch tay nhiều xe; banner gợi ý lập lại + nút Approve suggested / Keep current; Plan review list; Exceptions (tab Replan suggested); Transfers; toast `409` có Re-run plan | `features/dispatcher/{PlanReviewList,ManualPlan,Exceptions,Transfers}.tsx`, `components/{DecisionBar,ReplanSuggestionBanner}.tsx` | — |

**M5-S (US-APR-05, US-ORD-06):** Dev 1 làm Sales guard trong ApprovalService, kiểm đơn trước & audit; Dev 2 test đồng thời cạnh tranh nguồn lực; Dev 3 màn Check feasibility/Confirm/Escalate. Không mở Sales quyền GPS, replan, manual plan hay thương lượng ngày.

### M6 — Thực thi, driver PWA, GPS

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 1 | `execution_service` (thứ tự, idempotency, `occurred_at`, **Pause/Resume** và giờ nhân công thực tế theo đoạn, sự kiện theo **từng xe** và trạng thái đơn tổng hợp, POD theo `trip_stop`, alert EXCEPTION, kích hoạt gợi ý lập lại khi `VEHICLE_ISSUE`/`FAILED`); `/driver/trips`, prep-queue | `services/execution_service.py`, `api/v1/execution.py` | US-WH-04/05, US-EXE-01..04 |
| Dev 2 | `gps_service` (chỉ `gps_enabled` + `on_road`; đọc chỉ dispatcher), `gps_simulator.py`, job `retention`, GPS lost check | `services/gps_service.py`, `api/v1/gps.py`, `tools/gps_simulator.py`, `jobs/retention.py`, `jobs/risk_check.py` | US-GPS-01..03 |
| Dev 3 | Prep queue (capacity × 90%, không hàng thiết bị, **Pause/Resume** hỏi số người làm, Mark loaded từng xe, 4 thẻ ngoại lệ, popover "Happened at"); Driver PWA (danh sách, chi tiết, hàng đợi offline IndexedDB, xin quyền vị trí, thông báo riêng tư, Failed bắt buộc lý do) | `features/warehouse/PrepQueue.tsx`, `features/driver/*` | — |

### M7 — Rủi ro, cảnh báo, thông báo

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 1 | `engine/forecast.py`; `risk_service` (chỉ tính khi có tín hiệu, `eta_forecast`, 2 lần liên tiếp); `alert_service` (dedupe khi đang mở); tạo nháp DELAY | `engine/forecast.py`, `services/risk_service.py`, `services/alert_service.py`, `api/v1/alerts.py` | US-RSK-01..03 |
| Dev 2 | `notify_service` (outbox, dedupe theo `plan_id`, giờ yên lặng, thử lại 3, Mailpit/Brevo, `sms_sim`, `shadow_mode`); job outbox, milestone overdue, morning check, stale data | `services/notify_service.py`, `providers/email_smtp.py`, `providers/sms_sim.py`, `api/v1/notifications.py`, `jobs/outbox.py`, `jobs/risk_check.py` | US-NOT-01..03 |
| Dev 3 | Tracking & risk (Live position chỉ dispatcher, "Why it is late" theo công thức 04); Notification inbox; Tracking list | `features/dispatcher/{Tracking,TrackingList}.tsx`, `features/notifications/NotificationInbox.tsx`, `components/{MilestoneTimeline,EventLog,NotificationPreview}.tsx` | — |

### M8 — KPI, nhật ký, quản trị, CS

| Người | Việc | File | Story |
|---|---|---|---|
| Dev 1 | `audit.v_kpi_daily`, `kpi_service` (8 KPI, chẩn đoán, chỉ `admin`/`ops`); **`revenue_service`** (`resolve_revenue_scope`, hai view, 5 endpoint `/revenue/*`, CSV `REVENUE_EXPORTED`, test nhất quán store = warehouse, ranh giới ngày Stockholm); `/audit/decisions`; job `nightly_metrics` (improvement_log theo trip_stop, `group_hours_per_unit`) | `services/kpi_service.py`, `services/revenue_service.py`, `api/v1/kpi.py`, `api/v1/revenue.py`, `jobs/nightly_metrics.py` | US-KPI-01/02, US-REV-01, US-LOG-01 |
| Dev 2 | Seed 48 đơn đã đóng cho tuần demo (trải đều cửa hàng và kho, có đoạn chuẩn bị với `crew_size`, 1 đơn giao lại, 1 đơn không có cửa hàng); ẩn danh theo hạn lưu giữ; GPS settings + compliance | `seed/generate_data.py`, `jobs/retention.py`, `api/v1/gps.py` | US-ADM-03 |
| Dev 3 | KPIs & decision log; **Revenue (A16)**: 5 thẻ, biểu đồ, bảng theo nơi, danh sách đơn, Export CSV, làm mới 60 giây; Handling groups & norms; Market config & GPS; CS Order lookup; My store orders | `features/kpi/KpiDashboard.tsx`, `features/revenue/Revenue.tsx`, `features/it/{HandlingGroups,MarketConfig}.tsx`, `features/cs/OrderLookup.tsx`, `features/store/MyStoreOrders.tsx` | US-CS-01/02 |

### M9 — Hoàn thiện và triển khai

| Người | Việc |
|---|---|
| Dev 1 | Kiểm tra quyền cho **mọi hàng** ma trận `06` mục 3 (đường cho phép và bị cấm); hiệu năng (lập kế hoạch < 2 s, bảng đơn < 1 s với 1.000 đơn); sửa lỗi backend |
| Dev 2 | 16 kịch bản E2E Playwright (cùng Dev 3); deploy staging (Supabase + Render + Vercel, vùng EU nếu có); ping 5 phút; README, hướng dẫn demo, `CHANGELOG` |
| Dev 3 | So giao diện với ảnh thiết kế theo `03` (gồm điều chỉnh #1–#36); a11y bằng axe; PWA cài được; offline gửi lại không trùng |

## 3. Tổng hợp trách nhiệm theo người

**Dev 1 — Backend lõi**
- Migration và model theo `05` (không đổi tên bảng/cột/enum).
- Toàn bộ `app/engine/` (hàm thuần, mypy strict, test trước, phủ ≥ 90%).
- Giữ chỗ (cho vượt), khóa khi duyệt, kế hoạch nhiều xe, kế hoạch tay, gợi ý lập lại, đóng kế hoạch cũ, chuyển kho.
- Thực thi (sự kiện theo xe, tạm dừng chuẩn bị, POD theo lần giao), rủi ro/ETA, cảnh báo, KPI, doanh thu, audit.
- Review bắt buộc: mọi PR đụng `domain/transitions.py`, `audit/`, `engine/`.

**Dev 2 — Tích hợp, dữ liệu, hạ tầng**
- Hệ thống nguồn giả lập + hợp đồng nguồn; adapter, ingestion, routing.
- Seed (khớp ảnh thiết kế, đủ cho 16 kịch bản), `add_market.py`, `gps_simulator.py`.
- GPS, thông báo (outbox, Mailpit, SMS mô phỏng), mọi job.
- Docker, Makefile, CI, deploy staging; test đồng thời và E2E.
- Review bắt buộc: mọi PR đụng `adapters/`, `jobs/`, CI, Docker.

**Dev 3 — Frontend**
- Design system theo `03` mục 2 và 11 (không hard-code màu hex ngoài token).
- 28 màn web (gồm Revenue) + POS UI + driver PWA (offline, GPS có xin quyền).
- Client sinh từ OpenAPI, mock MSW, trạng thái rỗng/tải/lỗi ở mọi màn, a11y.
- Review bắt buộc: mọi PR đụng `frontend/`.

## 4. Quy tắc làm việc chung

- **Đọc trước khi code:** `09_AI_Coding_Rules.md` (đặc biệt mục 4, 23 bất biến) và story/AC liên quan ở `02`.
- **Nhánh và PR:** `feat/<epic>-<mô-tả>`; Conventional Commits; PR ≤ ~400 dòng logic; mỗi PR do **một người khác** review; CI phải xanh (ruff, black, mypy, import-linter, pytest, build web).
- **Test theo AC:** tên `test_US_<EPIC>_<NN>_AC<k>_…`; không skip/xóa test để CI xanh.
- **Đổi hợp đồng** (`05`/`06`): sửa tài liệu + migration + `docs/CHANGELOG.md` trong cùng PR, báo cả nhóm.
- **Giả định mới:** ghi `docs/ASSUMPTIONS.md` (`ASM-xxx`); điểm nhạy cảm (duyệt, đổi ngày, báo trễ, GPS, ánh xạ SKU, doanh thu) thì hỏi nhóm trước.
- **Đồng bộ:** họp ngắn mỗi ngày làm việc (15 phút: xong gì, làm gì, kẹt gì); cập nhật tiến độ theo milestone trong GitHub Issues/Projects.

**Điểm nối nhánh Sales:** Dev 2 cung cấp API sync-now và dữ liệu nguồn; Dev 1 trả `sales_approvable` + lý do từ backend; Dev 3 chỉ bật Confirm theo quyền máy chủ. Chi tiết xem `docs/DECISION_SALES_CONFIRMATION.md`.

## 5. Điểm nối giữa các người (dễ kẹt)

| Điểm nối | Bên giao | Bên nhận | Cách tránh kẹt |
|---|---|---|---|
| OpenAPI endpoint | Dev 1, Dev 2 | Dev 3 | Khai báo schema Pydantic request/response **trước** khi viết logic; Dev 3 chạy `npm run gen:api` |
| Hợp đồng nguồn | Dev 2 | Dev 1 (ingestion dùng DTO) | Chốt `source_system/openapi.yaml` ở M1 |
| Seed khớp kịch bản | Dev 2 | Dev 1 (test engine), Dev 3 (so ảnh) | Seed kịch bản 1–7 xong trước khi Dev 1 viết integration test M4 |
| Khóa khi duyệt | Dev 1 | Dev 2 (test tải) | Dev 1 xong `approval_service` trước, Dev 2 viết test ngay sau |
| Kế hoạch nhiều xe | Dev 1 (engine) | Dev 3 (`VehicleList`, Prep queue, Driver) | Chốt schema `vehicles[]` trong `06` mục 6.2 trước khi dựng UI |
| `transition()` / `close_active_plan()` | Dev 1 | Dev 2 (ingestion), Dev 1 (execution) | Không ai `UPDATE customer_order SET status` ngoài hàm này |

## 6. Nếu chỉ còn 2 người

Dev 2 gộp vào Dev 1 (`08` mục 2): ưu tiên nguồn giả lập, seed, ingestion trước rồi mới tới engine; Dev 3 giữ nguyên. GPS simulator và deploy staging dời xuống M9.

## 7. Trạng thái khung hiện tại

- Backend: 84 endpoint đã khai báo đúng đường dẫn `06` (trả `NotImplementedError`); engine có đủ kiểu dữ liệu và chữ ký hàm; `core/clock.py`, `core/numbers.py`, `core/errors.py`, `core/correlation.py`, `core/config.py` (MarketConfig), bảng chuyển trạng thái, mã hành động audit, `engine.workload.prep_quantity` (đơn vị nhỏ nhất) và `engine.actuals` (giờ nhân công thực tế) đã hiện thực; 15 test pass; ruff, black, mypy strict (engine), import-linter đều xanh.
- Frontend: khung router, token Tailwind, 23 component và 26 màn dạng stub; `tsc` và `vite build` chạy được.
- Source system, tools, Docker, CI: khung có docstring, chưa chạy end-to-end (cần Postgres và migration của M0).

## 8. Sản phẩm nộp ban giám khảo (gợi ý người phụ trách)

| Sản phẩm | Phụ trách chính | Hỗ trợ | Ghi chú |
|---|---|---|---|
| MVP Demo Video (`MVP.mp4`) | Dev 3 | Dev 2 | Quay theo kịch bản E2E 1, 6, 8, 12, 17; dùng dữ liệu seed |
| User Journey document | Dev 3 | Dev 1 | Dựa trên `07` và `03` |
| System Diagram document | Dev 2 | Dev 1 | Dựa trên `04` và `05` |
| AI Journal template | Cả nhóm | — | Mỗi người ghi việc dùng AI trong phần mình |
| Kiểm tra trước khi nộp | Dev 2 | — | Tên file ngắn, rõ; mọi file truy cập được; **không mật khẩu, khóa API, thông tin mật** (`09` bất biến 25) |
