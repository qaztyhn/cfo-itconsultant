# 04 — Tech Stack & Architecture (CFO MVP)

> Tài liệu giao cho agent code. Kết hợp với `05_Database_Design.md` (DDL), `06_API_Specification.md` (hợp đồng API), `09_AI_Coding_Rules.md` (quy tắc viết code). Nhãn: **[C]** đã chốt, **[S]** slide, **[T]** bản thiết kế, **[A]** giả định chỉnh được qua cấu hình.
>
> **Phiên bản 1.1 (06/11/2026):** bỏ thiết bị kho khỏi engine (không còn `eq_cap`, `PREP_NO_EQUIPMENT`); quy tắc khóa đồng thời cho hàng và giờ công (mục 7); đóng kế hoạch cũ khi lập lại/hủy/giao thất bại; lối "xử lý ngoài CFO" cho đơn cần nhiều xe; mã lý do `LOWEST_SCORE_OF_3`; cơ sở pháp lý GPS (mục 9).

## 1. Nguyên tắc kiến trúc

1. **Tích hợp trên hệ thống sẵn có, không thay thế [S].** CFO chỉ đọc từ hệ thống nguồn của từng nước, không ghi ngược.
2. **Một lõi quyết định dùng chung, quy tắc từng nước là cấu hình [S].** Không có `if market == 'SE'` trong lõi. Nước mới = adapter/instance nguồn mới + dòng cấu hình + bảng sản phẩm riêng.
3. **Mọi nước bình đẳng [C].** Thụy Điển chạy đúng đường mà nước khác sẽ chạy: hệ thống nguồn giả lập riêng, gọi qua `MarketAdapter`.
4. **Người quyết định, hệ thống đề xuất [S].** Không bao giờ tự duyệt kế hoạch, không tự đổi ngày giao khi khách chưa đồng ý.
5. **Engine là hàm thuần**, không đọc DB, không gọi mạng. Dữ liệu vào là object, dữ liệu ra là object. Dễ test, dễ thay bằng Drools/OR-Tools sau này.
6. **Mọi quyết định để lại dấu vết** (`audit.decision_log`) và mọi dữ kiện có nguồn và độ tươi.
7. **Modular monolith**: một ứng dụng FastAPI, một SPA React, một PostgreSQL. Không microservice.

## 2. Tổng quan hệ thống

```
┌────────────────────────── Hệ thống nguồn giả lập (mỗi nước một instance, cùng mã nguồn) ─────────────────────────┐
│  POS mock (form nhập đơn)  ·  Customer/Address  ·  Product  ·  Stock  ·  Inbound  ·  Fleet calendar  ·  REST API  │
└──────────────────────────────────────────────▲──────────────────────────────────────────────────────────────────┘
                                               │ HTTPS (httpx), API key, updated_since
┌──────────────────────────────────────────────┴───────────────────────────────────────────────────────────────┐
│ CFO API (FastAPI)                                                                                              │
│  api/ → services/ → engine/ (pure)   adapters/   providers/ (ORS, email, sms_sim)   jobs/ (APScheduler)        │
│  modules: integration · mapping · orders · planning · reservation · execution · risk · notify · gps · hr · kpi │
└───────────────┬──────────────────────────────────────────────────────────────┬───────────────────────────────┘
                │ SQLAlchemy 2 / Alembic                                       │ REST + OpenAPI (client sinh tự động)
        PostgreSQL 16 (ref, hr, stg, ops, plan, audit)                 React SPA (dispatcher, kho, cửa hàng, IT, CS, KPI)
                                                                        Driver PWA (hàng đợi sự kiện offline, GPS)
```

## 3. Công nghệ

| Lớp | Lựa chọn MVP (miễn phí) | Ghi chú |
|---|---|---|
| Ngôn ngữ backend | Python 3.12 | Type hints bắt buộc, `mypy --strict` cho `engine/` |
| Web framework | FastAPI + Uvicorn | OpenAPI tự sinh là hợp đồng với frontend |
| ORM/migration | SQLAlchemy 2.0 (async) + Alembic | Migration sinh từ `05_Database_Design.md`, không autogenerate mù |
| Validation | Pydantic v2 | `MarketConfig` cũng là model Pydantic |
| HTTP client | httpx (async) | Adapter, ORS |
| Job | APScheduler (in-process) + `POST /internal/tick` | Không Celery/Redis |
| Auth | JWT (HS256), mật khẩu argon2 | Vai trò theo `ref.app_user.roles`, phạm vi theo phân công |
| Test | pytest, pytest-asyncio, httpx.AsyncClient, testcontainers hoặc DB Compose, Playwright (E2E) | Mục 12 |
| Lint | ruff, black, mypy | CI chạy |
| Frontend | React 18 + Vite + TypeScript (strict), React Router, TanStack Query, Zustand (state UI nhỏ), Tailwind, Leaflet + OpenStreetMap, vite-plugin-pwa, openapi-typescript | Một SPA, route theo vai trò |
| Database | PostgreSQL 16 | `pgcrypto`, `btree_gist`, `pg_trgm` |
| Lộ trình | OpenRouteService (khóa miễn phí, `driving-hgv`) bọc sau `RoutingProvider`; fallback Haversine × 1,3 tại 50 km/h | Ma trận tính trước, engine không gọi API |
| Email | Mailpit (local), Brevo/Resend free SMTP (online) | Interface `EmailProvider` |
| SMS | Mô phỏng (`sms_sim`) | Interface `SmsProvider` |
| Container | Docker Compose | `postgres`, `mailpit`, `source-se`, `cfo-api`, `cfo-web` |
| Staging | Supabase (DB) + Render (API) + Vercel (web) + UptimeRobot/cron-job.org (ping) | Không phải production; chọn vùng EU nếu gói miễn phí cho phép |

**So với slide proposal [C]:** lõi giống nhau (PostgreSQL, Python API, React, driver PWA). Chỉ hạ tầng và dịch vụ ngoài đổi sang bản miễn phí vì MVP là bản mô phỏng: Azure → Supabase/Render/Vercel; Azure Maps → OpenRouteService; SMS/email EU → Mailpit/Brevo + SMS mô phỏng; CSV qua SFTP → API hệ thống nguồn giả lập (CSV tải lên chỉ là dự phòng). Khi triển khai thật, công ty có thể quay lại stack của slide mà không đổi lõi (các provider nằm sau interface).

## 4. Cấu trúc repo (monorepo)

```
cfo/
  docker-compose.yml  .env.example  Makefile  README.md
  backend/
    pyproject.toml  alembic.ini  alembic/versions/
    app/
      main.py  deps.py
      core/        config.py  security.py  db.py  logging.py  correlation.py  errors.py  clock.py
      domain/      enums.py  models/ (SQLAlchemy theo schema)  transitions.py
      engine/      types.py  workload.py  atp.py  capacity.py  schedule.py  delivery.py
                   gate.py  scoring.py  explain.py  planner.py  forecast.py  transfer.py  mapping_candidates.py
      adapters/    base.py (MarketAdapter, DTO chuẩn)  rest_adapter.py  csv_adapter.py (dự phòng)  registry.py
      services/    ingest_service.py  mapping_service.py  order_service.py  planning_service.py
                   reservation_service.py  approval_service.py  execution_service.py  risk_service.py
                   notify_service.py  gps_service.py  hr_service.py  transfer_service.py  kpi_service.py  alert_service.py
      providers/   routing_ors.py  routing_fallback.py  email_smtp.py  sms_sim.py
      jobs/        scheduler.py  ingest.py  hold_expiry.py  risk_check.py  attendance_gen.py  retention.py  nightly_metrics.py
      audit/       recorder.py  actions.py  schemas.py
      api/v1/      auth.py  orders.py  planning.py  mapping.py  execution.py  gps.py  hr.py  transfers.py
                   alerts.py  notifications.py  kpi.py  admin.py  internal.py
      seed/        generate_data.py  scenarios.py
    tests/         unit/ (engine)  integration/  e2e/  fixtures/
  source_system/   app/ (FastAPI, DB riêng)  pos_ui/ (form nhập đơn)  seed/<cc>/  openapi.yaml
  frontend/
    src/ api/ (sinh tự động)  app/ (router, layout, guards)  features/{dispatcher,warehouse,store,it,cs,driver,kpi,admin}
         components/  hooks/  i18n/  styles/
  tools/           gps_simulator.py  add_market.py  seed_all.sh
  docs/            01..09 (các tài liệu này)
```

**Quy tắc phụ thuộc (kiểm bằng import-linter):** `api → services → (engine, adapters, providers, domain)`; `engine` không import `services`, `adapters`, `providers`, `sqlalchemy`, `httpx`; `domain` không import gì ngoài stdlib/SQLAlchemy; `jobs → services`.

## 5. Lớp adapter và nhập liệu

### 5.1 Interface

```python
class MarketAdapter(Protocol):
    market_code: str
    async def fetch_orders(self, updated_since: datetime, page_size: int = 200) -> AsyncIterator[OrderDTO]: ...
    async def fetch_customers(self, updated_since: datetime) -> AsyncIterator[CustomerDTO]: ...
    async def fetch_products(self, updated_since: datetime) -> AsyncIterator[ProductDTO]: ...
    async def fetch_stock(self) -> StockSnapshotDTO: ...          # ảnh chụp đầy đủ + as_of
    async def fetch_inbound(self) -> list[InboundDTO]: ...        # chỉ hàng chưa về
    async def fetch_fleet(self, date_from: date, date_to: date) -> list[FleetBlockDTO]: ...
```

`RestMarketAdapter` đọc `base_url` và khóa từ `ref.market`. Đặc thù của một nước (nếu có) chỉ nằm trong lớp con, không đụng lõi. `CsvMarketAdapter` giữ làm phương án dự phòng khi cần nạp từ file (kèm `file_sha256`).

### 5.2 Quy trình ingestion (job `ingest_*`, 5 phút/lần)

1. Đọc `stg.sync_checkpoint` → `updated_since = last_updated_since − 2 phút`; mở `stg.sync_run(status=running)`.
2. Gọi adapter theo trang; mỗi bản ghi qua Pydantic DTO. Lỗi → `stg.sync_reject` (mã: `BAD_QTY`, `UNKNOWN_WAREHOUSE`, `BAD_DATE`, `MISSING_COORDS`, `UNKNOWN_SKU`…), **không dừng cả lượt**.
3. **Upsert theo khóa tự nhiên** `(market_id, external_ref)`; dùng `source_version` để bỏ qua bản cũ hơn.
4. Cuối lượt: `status = ok | partial | failed`; chỉ khi `ok/partial` mới ghi `sync_checkpoint = max(updated_at)`. Thất bại → alert `SYNC_FAILED` cho IT.
5. **Đơn:** chỉ nhận đơn `SUBMITTED_FOR_PLANNING`. Đơn mới → `SUBMITTED` (rồi `OrderService.prepare_for_planning`: kiểm ánh xạ SKU, nếu thiếu → `BLOCKED_UNMAPPED_SKU` + `mapping_task`; ngược lại gọi `PlanningService.plan(order)`). Đơn đã APPROVED mà nguồn gửi bản mới (sửa/hủy) → **không ghi đè**, tạo alert `ORDER_CHANGED_AFTER_APPROVAL`; dispatcher quyết định lập lại.
6. **Tồn kho:** ghi đè `ops.stock_snapshot` bằng ảnh chụp mới và `as_of`; không đụng giữ chỗ của CFO. Nếu `now − as_of > 15 phút` → cờ vàng và alert `STALE_DATA`.
7. **Hàng nhập:** chỉ hàng chưa về; hàng `received` hoặc biến mất khỏi nguồn thì đặt `received = true`. Hàng chuyển kho tạo bởi CFO (`source='transfer'`) không bị nguồn ghi đè.
8. **Sau mỗi lượt tồn kho/hàng nhập/lịch xe thay đổi:** tìm các đơn đã duyệt bị ảnh hưởng và gọi `RiskService.recalculate(order, trigger='source_change')`.
9. **Lộ trình:** với mỗi cặp (kho, toạ độ giao) chưa có trong `plan.route_matrix`, `RoutingProvider` tính (ORS, hoặc fallback) và ghi `provider`. Việc này diễn ra trước khi lập kế hoạch, không trong engine.

## 6. Đặc tả engine (hàm thuần, trong `engine/`)

### 6.1 Kiểu dữ liệu vào/ra (rút gọn)

```python
@dataclass(frozen=True)
class OrderCtx:   # đơn đã chuẩn hóa
    id: int; version: int; lat: float; lon: float
    date_mode: Literal["exact","range","latest"]; date_from: date|None; date_to: date
    window: tuple[time,time]|None; lines: list[LineCtx]; now: datetime
@dataclass(frozen=True)
class LineCtx: product: ProductCtx; qty_base: Decimal   # ProductCtx: group, prep_unit, base_units_per_prep_unit, flags, weight, volume
@dataclass(frozen=True)
class WarehouseCtx:  # mọi thứ engine cần về một kho
    id: int; cutoff: time; efficiency: float
    stock_available: dict[int, Decimal]          # đã trừ wms_reserved và giữ chỗ của ĐƠN KHÁC (held còn hạn + committed)
    inbound: list[InboundCtx]                    # confirmed, chưa received
    capacity: dict[date, DayCapacity]            # theo ngày: ca, số người, giờ công khả dụng, giờ đã đặt (không có thiết bị trong MVP)
    vehicles: list[VehicleCtx]; drivers: list[DriverCtx]; route: RouteInfo|None
@dataclass(frozen=True)
class PlanCandidate: ...   # xem bảng plan.fulfilment_plan
@dataclass(frozen=True)
class PlanningResult:
    result: Literal["feasible","infeasible","manual"]
    candidates: list[PlanCandidate]              # tối đa 3, đã xếp hạng
    failed_check: str|None; earliest_feasible_date: date|None
    reserve_class: Literal["safe","tight","infeasible"]|None; planning_reserve_min: int|None
    transfer_suggestions: list[TransferSuggestion]
```

Hàm vào chính: `plan_order(order: OrderCtx, warehouses: list[WarehouseCtx], cfg: MarketConfig, weights: RankWeights|None) -> PlanningResult`.

### 6.2 Quy trình

**Bước 0, tiền kiểm.** Mọi dòng phải có `global_product_id` (nếu không, dừng ở service, không vào engine). Tổng khối lượng/thể tích > xe lớn nhất của mọi kho, hoặc nhóm cần `vehicle_requirement` mà không kho nào có xe phù hợp → `result = manual`, `reason = NEEDS_MULTI_VEHICLE | NO_CAPABLE_VEHICLE`.

**Bước 1, khối lượng việc (độc lập kho) [C]: giờ công giống nhau ở mọi kho.**
```
prep_qty(line)   = qty_base / base_units_per_prep_unit        # prep_unit='line' → 1
flag_mult(line)  = min(Π multiplier(flag), cfg.flag_multiplier_cap)
line_hours(line) = (group.fixed_hours + prep_qty × group.labour_hours_per_unit) × flag_mult   # fixed_hours tính MỖI DÒNG
labour_hours     = Σ line_hours + cfg.final_inspection_hours (0.5)
per warehouse    : labour_hours × location.efficiency_factor   (mặc định 1.0)
```
Ví dụ: 20 pallet xi măng (N3): 0,25 + 20×0,15 = 3,25 h; 15 pallet gạch (N2): 0,25 + 15×0,40 = 6,25 h; 3 dòng keo (N1): 3×0,05 = 0,15 h; kiểm cuối 0,5 → **10,15 giờ công**. MVP không tính giờ thiết bị: giả định mọi kho có đủ thiết bị và định mức giờ công đã bao gồm thời gian dùng thiết bị [C].

**Bước 2, từng kho `w` (loại kho không qua được thì ghi mã lỗi đầu tiên).**

*2a. ATP theo thời gian.* `usable(w,p,d) = stock_available[p] + Σ inbound(confirmed, !received, eta_date + receiving_lead_days làm việc ≤ d)`. `stock_ready_date(w)` = ngày sớm nhất `d ≥ hôm nay` mà mọi dòng đủ. Không có trong `search_days_max` (14) ngày → loại kho, mã `STOCK_SHORT`, ghi lại phần thiếu cho bước đề xuất chuyển kho. Phân loại để hiển thị: *đủ ngay* / *đủ sau hàng nhập (kèm ETA, thời điểm lấy T = cần − di chuyển − lên hàng)* / *không đủ*. Dựa vào hàng nhập thì `complexity_points += 1`.

*2b. Công suất và lịch chuẩn bị.* Công suất ngày `d`:
```
labour_cap(d) = Σ_ca  present_staff(d,ca) × useful_hours_per_staff(ca) × cfg.delivery_share (0.90)
free(d)       = labour_cap(d) − giờ đã đặt (committed + held của đơn khác)
```
`present_staff` = nhân viên kho `counts_in_capacity` có điểm danh `present` (ngày đã qua/hôm nay) hoặc `planned` (ngày tương lai), trừ nghỉ phép đã duyệt. Bỏ ngày không làm việc và ngày lễ của market.
Thuật toán xếp việc, **tiến tới sớm nhất có thể**:
1. `start_day` = ngày làm việc đầu tiên mà `≥ stock_ready_date` và có ca còn lại sau `now`.
2. Với mỗi ngày: `a_L = min(L_còn_lại, free_labour(d))`. Ghi `prep_reservation` theo ngày (`resource = 'labour'`).
3. Không đủ công suất trong chân trời `search_days_max` → loại kho, `PREP_NO_CAPACITY`.
4. `goods_ready_at` = giờ trong ngày cuối: đi qua các ca theo thứ tự, mỗi ca tiêu thụ `present_staff × share` giờ công/giờ đồng hồ, bắt đầu sau lượng giờ công đã đặt trước đó. Cộng `final_inspection` vào khối lượng.
5. `capacity_fill = (Σ giờ đã đặt trước + giờ công đơn này) / Σ labour_cap` trên các ngày chuẩn bị của đơn, kẹp `[0,1]`.

*2c. Lên hàng.* `loading_start_at = goods_ready_at` nếu ≤ `cutoff` của ngày đó, nếu không dời sang đầu ca ngày làm việc kế (`complexity_points += 1`, mã `PREP_AFTER_CUTOFF`). `loading_min = base + per_ton × tấn` (mặc định 20 + 6/tấn) [A].

*2d. Xe và tài xế.* Xe ứng viên: cùng kho, `status='available'`, `capacity_kg ≥ Σ`, `capacity_m3 ≥ Σ`, `allowed_group_ids` chứa nhóm các dòng (hoặc rỗng), `capabilities` thỏa `vehicle_requirement`. Tài xế ứng viên: `home_warehouse_id = w`, điểm danh `present/planned` ngày đó, hạng bằng `≥ required_licence` (CE ≥ C ≥ B), `licence_expires_on ≥` ngày chuyến, tổng giờ trong ngày (kể cả chuyến đã giữ) + chuyến này ≤ `driver_max_hours_day` (9), không trùng khoảng thời gian trong `vehicle_reservation` của đơn khác (kiểm trên cả xe lẫn tài xế). Tìm khoảng `[loading_start, trip_end]` không đụng bận: nếu đụng, dời `loading_start` tới hết khoảng bận (tối đa 10 lần).

*2e. Giao hàng và cửa sổ nhận.*
```
depart_min = loading_start + loading_min
arrive_min = depart_min + drive_min(route_matrix)
window(d)  = cửa sổ khách yêu cầu nếu có, nếu không thì default_receiving_hours theo thứ của d
```
Chọn ngày giao `T` theo `date_mode`:
- `exact`: chỉ `T = date_to`; không bao giờ giao sớm hơn ngày khách chọn. Nếu `arrive_min < window(T).open` → `arrive = open` (xuất phát muộn lại); nếu `arrive_min > window(T).close` → fail `DATE_AFTER_DEADLINE`.
- `range`: `T` = ngày làm việc sớm nhất trong `[date_from, date_to]` thỏa (không giao sớm hơn `date_from`).
- `latest`: `T` = ngày làm việc sớm nhất `≤ date_to`.
Nếu `arrive` rơi ngoài cửa sổ thì chuyển sang ngày làm việc kế tiếp thuộc tập ngày cho phép. `eta_at = arrive` (làm tròn lên 15 phút). `unload_min = base + per_ton × tấn`; `trip_end_at = eta + unload + drive về (đối xứng)`.

*2f. Dự trữ lập kế hoạch [C].* `earliest_feasible_eta(w,v)` = như trên nhưng **bỏ cận dưới của ngày** (không bị `date_from`/ngày `exact` kéo muộn). `planning_reserve = close(window(date_to)) − min earliest_feasible_eta` (phút). `reserve_class`: `safe` nếu `≥ reserve_safe_days × 1440`, `tight` nếu `0 ≤ … <`, `infeasible` nếu `< 0` hoặc không có ứng viên.

**Bước 3, gate 5 check (mọi ứng viên phải qua cả 5 mới được xếp hạng) [S].**

| Check | Mã đạt | Mã lỗi |
|---|---|---|
| `stock` | `STOCK_OK`, `STOCK_AFTER_INBOUND` | `STOCK_SHORT` |
| `preparation` | `PREP_OK`, `PREP_AFTER_CUTOFF` | `PREP_NO_CAPACITY` |
| `truck` | `TRUCK_OK` | `NO_TRUCK_FIT`, `TRUCK_BUSY`, `NO_DRIVER` |
| `site_date` | `DATE_OK` | `OUTSIDE_RECEIVING_HOURS`, `DATE_AFTER_DEADLINE`, `NON_WORKING_DAY` |
| `safety` | `SAFETY_OK` | `OVER_LOAD`, `DRIVER_HOURS_EXCEEDED`, `LICENCE_EXPIRED` |

Khi không còn ứng viên: `failed_check` = check **xa nhất trong thứ tự** (`stock → preparation → truck → site_date → safety`) mà ít nhất một kho đã đạt tới trước khi hỏng (nếu hòa, check đứng sớm hơn).

**Bước 4, xếp hạng [C].** Trên tập ứng viên khả thi (mỗi cặp kho–xe tối đa một ứng viên):
```
n_km   = minmax(distance_km)      ; nếu (max−min) < max(2 km, 5% × min) thì mọi n_km = 0   (vùng bỏ qua)
n_fill = minmax(capacity_fill)    ; nếu (max−min) < 0.05 thì mọi n_fill = 0
score  = w_km × n_km + w_fill × n_fill            # mặc định 0.5 / 0.5; thấp hơn là tốt hơn
```
Chỉ một ứng viên → score 0. Hòa (`|Δscore| < 0,001`) xét lần lượt: `planning_reserve` lớn hơn → `complexity_points` thấp hơn → `eta` sớm hơn → `vehicle.code` nhỏ hơn. `complexity_points` = +1 mỗi lần: dùng hàng nhập chưa về, lên hàng dời sang ca sau, cần chuyển kho (+ điểm dừng thêm sau này khi có ghép đơn). Lấy **top 3** (tối đa 2 phương án mỗi kho). Giờ công đơn như nhau ở mọi kho nên **không** là tiêu chí xếp hạng.

Ví dụ: ba phương án khả thi, đơn 12 giờ công ở mọi kho.

| PA | Km | Mức đầy | n_km | n_fill | score |
|---|---|---|---|---|---|
| A Göteborg | 10 | 85% | 0 | 1 | 0,50 |
| B Stockholm | 40 | 40% | 1 | 0 | 0,50 |
| C Malmö | 12 | 60% | 0,07 | 0,44 | **0,26** |

C thắng; A và B hòa thì xét `planning_reserve`, rồi `complexity_points`…

**Bước 5, giải thích.** Sinh chuỗi từ `reason_codes` bằng mẫu câu cố định (không dùng AI trong MVP). Mã lý do của phương án hạng 1 là `LOWEST_SCORE_OF_3` (hoặc `LOWEST_SCORE_OF_2`, `ONLY_FEASIBLE`); **không** dùng mã hay chữ có nghĩa "rẻ nhất/cost", vì điểm là chỉ số thay thế, không phải tiền.

**Hạn chế đã biết của xếp hạng [A]:** điểm là tương đối trong cùng một đơn (min–max); điểm không xét cỡ xe (xe 26 t và 12 t cùng quãng đường cùng điểm); khi hai phương án cùng kho thì `capacity_fill` bằng nhau nên thứ tự do tie-break quyết định. Ghi nhận để hiệu chỉnh sau pilot. Ví dụ: *"Điểm thấp nhất trong 3 phương án khả thi. Kho Malmö đủ hàng, mức đầy công suất 60%, xe 12t rảnh, giao cách 12 km, dự trữ 3 ngày (an toàn)."*

**Bước 6, không có ứng viên.** (a) `result = infeasible`, `failed_check` như trên. (b) `earliest_feasible_date`: chạy lại bước 2 **bỏ cận trên** của ngày yêu cầu, quét tối đa 14 ngày. (c) Nếu `failed_check = stock` ở mọi kho, sinh gợi ý chuyển kho (mục 6.4). (d) Service chuyển đơn sang `NO_FEASIBLE_DATE` (hoặc `MANUAL_PLANNING` nếu bước 0 báo).

### 6.3 Theo dõi, ETA và rủi ro (`engine/forecast.py` + `RiskService`)

**Khi nào tính lại ETA (không quét định kỳ vô ích):** (1) có sự kiện mốc/ngoại lệ; (2) có điểm GPS mới; (3) dữ liệu nguồn đổi (hàng nhập, tồn, công suất/điểm danh, lịch xe, đơn); (4) mốc kế hoạch quá hạn 30 phút mà chưa có sự kiện (job 5 phút, truy vấn nhẹ); (5) 07:00 mỗi sáng với đơn nhiều ngày; (6) lúc duyệt. Không có thay đổi thì không tính lại.

**Công thức dự báo** (`forecast_eta`):
- Trước `GOODS_READY`: `goods_ready_f = planned_goods_ready + max(0, START_PREP_thực − START_PREP_kế_hoạch)`, nếu quá giờ kế hoạch mà chưa xong thì `max(…, now)` (MVP không theo dõi tiến độ bên trong bước chuẩn bị nên đây là cận dưới; hộp "Why it is late" ở UI chỉ diễn giải theo công thức này); `loading_start_f` theo `cutoff`; `depart_f = max(depart_kế_hoạch, loading_start_f + loading_min)`; `eta_f = depart_f + drive_min`. (Dự trữ giữa giờ có thể xuất phát sớm nhất và `depart_kế_hoạch` tự hấp thụ chậm trễ.)
- Sau `LOADED`: `depart_f = max(depart_kế_hoạch, loaded_at + 10 phút)`.
- Sau `DISPATCHED` không có GPS: `eta_f = depart_thực + drive_min`.
- Có GPS (điểm không quá `gps.lost_min` phút): `eta_f = recorded_at + thời gian đường còn lại` (ORS directions, fallback Haversine).
- Làm tròn lên 15 phút. Mỗi lần ghi một dòng `ops.eta_forecast` (phiên bản ETA).

**Trạng thái rủi ro [C]:**
```
commitment_deadline = promise_end
reserve_total = max(30 phút, promise_end − planned_eta)
slack         = promise_end − forecast_eta                      (phút)
consumption%  = max(0, (forecast_eta − planned_eta) / reserve_total × 100)
```
| Điều kiện | `risk_status` | Màu | Hành động |
|---|---|---|---|
| `consumption < 33` | ON_TRACK | green | — |
| `33 ≤ consumption ≤ 66` | AT_RISK | yellow | Chỉ đổi màu trên bảng |
| `consumption > 66` hoặc `slack < 0` (lần đầu) | AT_RISK | orange | Alert `RISK_ORANGE` cho dispatcher |
| `slack < 0` ở **2 lần tính liên tiếp** (cách nhau ≥ 5 phút) | PREDICTED_LATE | red | Alert critical + **bản nháp thông báo trễ** cho dispatcher |
| `now > promise_end` và chưa giao | OVERDUE | red | Alert critical |

**Báo khách trễ là quyết định của dispatcher [C].** Hệ thống tạo `notification(status='draft', template='DELAY')` với khung ETA mới đề xuất; dispatcher sửa và bấm gửi. Sau khi đã gửi, chỉ tạo bản nháp mới khi `forecast_eta` lệch ≥ 30 phút so với khung đã thông báo.

### 6.4 Đề xuất chuyển kho bằng quy tắc [C]

Khi kho đích `w` thiếu hàng (mọi kho đều `STOCK_SHORT`): với từng kho nguồn `s ≠ w`, đủ điều kiện nếu `stock_available_now(s, p) ≥ phần thiếu` cho mọi `p` thiếu (chỉ hàng có sẵn, không dựa vào hàng nhập). Sắp xếp theo `lead_days` (cấu hình theo cặp kho, mặc định 1 ngày làm việc) tăng dần, rồi khoảng cách `s → w`. Trả tối đa 3 gợi ý (`ops.stock_transfer(status='suggested')`). Luồng: dispatcher duyệt (`approved`) → quản lý kho nguồn xác nhận (`source_confirmed`) → tạo `inbound_shipment(source='transfer', confirmed=true, eta=…)` → chạy lại kế hoạch (kho đích vẫn xử lý trọn đơn) → khi hàng về `received`. AI gợi ý chuyển kho thuộc phần mở rộng.

### 6.5 Ứng viên ánh xạ sản phẩm bằng quy tắc [C]

Cho `local_sku` chưa ánh xạ: (1) trùng `gtin` → ứng viên mạnh nhất; (2) độ tương đồng tên `pg_trgm` ≥ 0,45 cùng `category`; (3) gán nhóm xử lý theo `ref.handling_group_rule` (theo `category_like`, khoảng khối lượng, ưu tiên thấp trước). Lưu vào `mapping_task.candidates`. **Chỉ IT xác nhận**.

## 7. Giữ chỗ và duyệt (`ReservationService`, `ApprovalService`)

1. **Đề xuất:** `PlanningService` gọi engine, rồi trong **một transaction**: tạo `planning_run` (+ `input_snapshot`), `fulfilment_plan` (3 phương án), `plan.stock_reservation` và `prep_reservation` **một lần cho mỗi (đơn, kho)**, `vehicle_reservation` cho từng phương án; `hold_expires_at = now + 15 phút`; ghi `decision_log` (`PLAN_PROPOSED`, `RESERVATION_HELD`); chuyển đơn `PLANNED`.
2. **Gia hạn:** `POST /planning-runs/{id}/extend` cộng 15 phút, tối đa 2 lần.
3. **Hết hạn:** job `hold_expiry` đặt `held → expired`, kế hoạch `proposed → expired`; dispatcher phải chạy lại hoặc, nếu tài nguyên còn trống, nút Approve vẫn thành công vì bước kiểm tra lại (dưới đây).
4. **Duyệt** (`Idempotency-Key` bắt buộc): transaction lấy khóa theo quy tắc 8 bên dưới; **kiểm tra lại** tồn kho, công suất, xe, tài xế bằng chính engine với dữ liệu mới; nếu đổi `committed_date` so với ngày khách đã đồng ý thì cần bản ghi `date_negotiation.agreed`; phương án chọn → `approved`, giữ chỗ → `committed`, phương án khác → `superseded`/`released`; tạo `delivery_trip` + `trip_stop`; đặt `committed_date`, `promise_start/end`; `order → APPROVED`; tạo thông báo `CONFIRMED`; `decision_log (PLAN_APPROVED hoặc ALT_SELECTED, snapshot)`; `eta_forecast` v1.
5. **Đổi tiêu chí/chạy lại:** tạo `planning_run` mới, giữ chỗ cũ → `released`; bắt buộc lý do; `CRITERIA_CHANGED_RERUN`.
6. **Kế hoạch tay:** dispatcher nhập kho, xe, tài xế, giờ; engine vẫn kiểm gate; bắt buộc `manual_reason_code` (+ text); lưu snapshot đầy đủ; cờ `manual` vào KPI.
7. **Lập lại sau khi đã duyệt / xếp lại sau giao thất bại / hủy:** trong **một transaction**: kế hoạch cũ `approved`/`manual` → `superseded`; giữ chỗ `held`/`committed` → `released`; `trip_stop` `pending` → `cancelled`, `delivery_trip` chưa xong → `cancelled`; xóa `approved_plan_id`, `committed_date`, `promise_start/end` (giá trị cũ ghi vào `decision_log.before`); đơn → `SUBMITTED` (hoặc `CANCELLED`); bắt buộc lý do (`ORDER_REPLAN` / `ORDER_CANCELLED`). Lần duyệt mới tạo `CONFIRMED` mới (dedupe theo `plan_id`), không tự gửi gì khác cho khách. Lịch sử giao (POD theo `trip_stop`) được giữ nguyên.
8. **Khóa đồng thời cho hàng và giờ công:** xe/tài xế đã có EXCLUDE ở DB; hàng và giờ công thì không. Khi **tạo giữ chỗ** và khi **duyệt**, service lấy `pg_advisory_xact_lock` theo key `stock:<kho>:<sản phẩm>` và `labour:<kho>:<ngày>`, theo thứ tự cố định **kho → sản phẩm → ngày → xe → tài xế** (id tăng dần), rồi đọc lại phần còn trống (đã trừ `held` còn hạn và `committed` của đơn khác). Thiếu khi lập kế hoạch → loại kho; thiếu khi duyệt → `409 RESOURCE_CONFLICT` và rollback. Không `FOR UPDATE` trên `ops.stock_snapshot` (job đồng bộ ghi đè bảng này).
9. **Đơn cần nhiều xe hoặc xe ngoài đội (`MANUAL_PLANNING`, `NEEDS_MULTI_VEHICLE`/`NO_CAPABLE_VEHICLE`):** MVP không có thuật toán nhiều xe. Dispatcher có hai lối: (a) kế hoạch tay với **một** xe trong đội nếu qua gate; (b) **ghi nhận xử lý ngoài CFO** (`POST /orders/{id}/external-handoff`, mã lý do + thông tin bàn giao, ví dụ hãng vận tải đối tác) → đơn `HANDLED_EXTERNALLY` (trạng thái cuối), không giữ chỗ, không tạo chuyến, không GPS, không thông báo tự động; CS/dispatcher liên hệ khách ngoài hệ thống; `decision_log EXTERNAL_HANDOFF_RECORDED`; không tính vào `on_time_rate`, đếm ở `external_handoff_count`.

## 8. Cấu hình `MarketConfig` (JSON trong `ref.market.config`, mặc định [A])

```json
{
  "working_days": [1,2,3,4,5],
  "default_receiving_hours": {"mon-fri": ["07:00","16:00"]},
  "search_days_max": 14,
  "reserve_safe_days": 2,
  "promise_window_hours": 2,
  "eta_round_min": 15,
  "delivery_share": 0.90,
  "final_inspection_hours": 0.5,
  "flag_multiplier_cap": 2.0,
  "loading":   {"base_min": 20, "min_per_ton": 6},
  "unloading": {"base_min": 20, "min_per_ton": 6},
  "after_loaded_min": 10,
  "driver_max_hours_day": 9,
  "receiving_lead_days": 1,
  "transfer_lead_days_default": 1,
  "rank": {"w_km": 0.5, "w_fill": 0.5, "dz_km_abs": 2, "dz_km_pct": 0.05, "dz_fill": 0.05, "tie_eps": 0.001},
  "risk": {"yellow_pct": 33, "orange_pct": 66, "consecutive_negative": 2, "min_reserve_min": 30,
           "milestone_grace_min": 30, "consecutive_min_gap_min": 5},
  "hold": {"ttl_min": 15, "max_extensions": 2},
  "stale_stock_min": 15,
  "gps": {"interval_min": 30, "lost_min": 60, "retention_days": 30},
  "notify": {"quiet_hours": ["21:00","07:00"], "delay_min_shift_min": 30, "max_attempts": 3},
  "data_retention_days": {"personal": 365, "order": 730},
  "sync": {"interval_min": 5, "overlap_min": 2}
}
```

## 9. Bảo mật, quyền riêng tư, tuân thủ

- **Xác thực:** `POST /auth/login` → access JWT (8 giờ) kèm `roles`, `employee_id`, `location_ids`. Mật khẩu argon2. Tài khoản kho: công nhân kho **không** có tài khoản; chỉ quản lý/trưởng ca đăng nhập.
- **Phân quyền (RBAC + phạm vi):** kiểm ở phía máy chủ mỗi endpoint. Phạm vi: `warehouse` thấy dữ liệu kho của mình; `sales` (cửa hàng) thấy đơn của cửa hàng mình (chỉ xem); `dispatcher` thấy cả market; `driver` chỉ thấy chuyến của mình; `customer_service` xem đơn, ETA, lịch sử thông báo, ghi nhật ký liên hệ; `admin` (IT) quản trị; `viewer` chỉ xem KPI. Ma trận đầy đủ ở `06_API_Specification.md` mục 3.
- **Cơ sở pháp lý GPS (giả định cho MVP) [C][A]:** dữ liệu vị trí tài xế là dữ liệu cá nhân của người lao động. Nhóm giả định: tài xế được thông báo rõ khi ký hợp đồng lao động và trong app về mục đích (điều phối giao hàng), ai xem (chỉ dispatcher), khi nào gửi (chỉ khi chuyến `on_road`, không theo dõi ngoài giờ làm/ngoài chuyến) và thời gian lưu (30 ngày). Vì sự đồng ý trong quan hệ lao động thường không được coi là tự nguyện theo GDPR, cơ sở pháp lý dự kiến là **lợi ích hợp pháp/thực hiện hợp đồng**, kèm DPIA và tham vấn nhân viên **trước khi dùng thật**; bản demo hiện biểu ngữ "chưa có DPIA". Cần kiểm tra lại với bộ phận pháp lý khi pilot.
- **GPS [C][S]:** chỉ `dispatcher` đọc được `vehicle_position` (kiểm ở API, không trả cho vai trò khác dưới mọi hình thức); khách và CS không bao giờ thấy; cờ `gps_enabled` theo nước và `compliance_record(DPIA)`; PWA hiện thông báo quyền riêng tư (mục đích, ai xem, 30 ngày); bản demo hiện biểu ngữ "chưa có DPIA, chỉ demo"; không có báo cáo năng suất theo tài xế; job xóa điểm GPS sau `retention_days` kể từ khi chuyến kết thúc; mất tín hiệu quá 60 phút → alert `GPS_LOST`.
- **Dữ liệu cá nhân:** log kỹ thuật không chứa tên/điện thoại/email/địa chỉ; ẩn danh khách và nhân viên sau thời gian lưu giữ; email/SMS chỉ chứa trạng thái và ETA, không toạ độ.
- **API:** CORS giới hạn origin của web; giới hạn tần suất cơ bản trên `/auth/login`; `Idempotency-Key`; xác thực endpoint `/internal/*` bằng khóa riêng.

## 10. Logging và quan sát

Hai lớp (chi tiết cột ở `05_Database_Design.md`): **nhật ký quyết định** (`audit.decision_log` qua `record_decision()` cùng transaction nghiệp vụ) và **log kỹ thuật JSONL** (`logs/<service>/<YYYY-MM-DD>.jsonl`, `service ∈ api|engine|integration|scheduler|notify`; trường `ts, level, service, correlation_id, order_id, market, event, duration_ms, extra`; online ghi stdout). `correlation_id` sinh ở middleware (`X-Correlation-ID`) và truyền xuống mọi lớp, mọi job. `GET /health` kiểm DB, độ tươi lượt đồng bộ, hàng đợi thông báo.

**Mã hành động chuẩn của `decision_log`** (dùng đúng các mã này ở backend và hiển thị ở UI): `PLAN_PROPOSED`, `PLAN_APPROVED`, `ALT_SELECTED` (duyệt phương án rank > 1, bắt buộc lý do), `CRITERIA_CHANGED_RERUN` (bắt buộc lý do), `MANUAL_PLAN_CREATED` (bắt buộc mã lý do), `EXTERNAL_HANDOFF_RECORDED` (bắt buộc mã lý do, v1.1), `DATE_NEGOTIATION_RECORDED`, `ORDER_REPLAN`, `ORDER_CANCELLED`, `MAPPING_CONFIRMED`, `MAPPING_REJECTED`, `HANDLING_GROUP_CHANGED` (IT đổi định mức/hệ số/quy tắc), `SHIFT_CHANGED`, `ATTENDANCE_CHANGED`, `EXCEPTION_REPORTED`, `TRANSFER_SUGGESTED`, `TRANSFER_APPROVED`, `TRANSFER_CONFIRMED`, `NOTIFICATION_SENT`, `NOTIFICATION_SUPPRESSED` (kèm lý do), `RESERVATION_HELD`, `RESERVATION_COMMITTED`, `RESERVATION_RELEASED`, `HOLD_EXTENDED`, `HOLD_EXPIRED`, `GPS_SETTING_CHANGED`, `CONFIG_CHANGED`, `EMPLOYEE_ASSIGNMENT_CHANGED`, `USER_ROLE_CHANGED`.

## 11. Kiến trúc frontend

- **Routing theo vai trò** (guard theo `roles`): `/dispatcher/*`, `/warehouse/*`, `/store/*`, `/it/*`, `/cs/*`, `/kpi`, `/driver/*` (PWA), `/admin/*`.
- **Dữ liệu:** TanStack Query, polling (dashboard và cảnh báo 15–30 giây; không WebSocket trong MVP); client sinh từ OpenAPI; mọi lỗi API theo định dạng chuẩn (`06`).
- **PWA tài xế:** `vite-plugin-pwa`, cài được lên màn hình chính; **hàng đợi sự kiện offline** (IndexedDB) với `idempotency_key` và `occurred_at` là giờ chạm; Geolocation API gửi vị trí theo `gps.interval_min` khi chuyến `on_road`; hiển thị thông báo quyền riêng tư và xin quyền vị trí. Hạn chế: trình duyệt chỉ định vị khi app đang mở (iOS hạn chế khi tắt màn hình), nên bản demo dùng thêm `tools/gps_simulator.py`.
- **Bản đồ:** Leaflet + OSM, hiện kho, điểm giao, đường đi, vị trí xe (chỉ dispatcher).
- **i18n:** mặc định tiếng Anh, khung `i18next` để thêm tiếng Việt và ngôn ngữ từng nước. Thiết kế giao diện theo `03_UI_UX_Specification.md`.

## 12. Kiểm thử

- **Unit (engine, bắt buộc):** mỗi bước ở mục 6 có bộ test bảng (parametrized) gồm ca biên: thiếu hàng/có hàng nhập, hàng nhập chưa xác nhận, quá giờ cắt, thiếu công suất, không xe vừa, xe/tài xế bận, ngoài giờ nhận hàng, ba dạng ngày, vùng bỏ qua khi xếp hạng, một ứng viên, hòa điểm.
- **Integration:** ingestion idempotent, upsert theo version, checkpoint; giữ chỗ cả 3 phương án và EXCLUDE chặn đơn khác nhưng cho phép cùng đơn; duyệt đồng thời hai dispatcher (tranh **xe**, tranh **cùng SKU**, tranh **cùng ngày công suất**: đúng một bên thắng); lập lại sau duyệt đóng kế hoạch cũ và duyệt được kế hoạch mới; giao thất bại rồi giao lại tạo hai POD; chuyển trạng thái trái phép bị trigger chặn; hold hết hạn.
- **E2E (Playwright):** kịch bản 1–16 ở `08_Development_Plan.md`.
- **Phủ:** engine ≥ 90% dòng; service quan trọng (approval, reservation, risk) ≥ 80%.

## 13. Triển khai

- **Local:** `docker compose up -d` → `make migrate seed` → web `:5173`, API `:8000`, Mailpit `:8025`, POS giả lập `:8100`.
- **Staging:** Supabase (CFO DB; hệ thống nguồn dùng schema `src_se` trong cùng database), Render (cfo-api, source-se), Vercel (web). Biến môi trường: `DATABASE_URL`, `ORS_API_KEY`, `JWT_SECRET`, `SMTP_HOST/PORT/USER/PASSWORD`, `SOURCE_SE_BASE_URL`, `SOURCE_SE_API_KEY`, `INTERNAL_TICK_KEY`, `APP_ENV`. Ping 5 phút tới `/health` và `/internal/tick`. Giới hạn free-tier (Render ngủ, Supabase tạm dừng sau ~1 tuần, Vercel Hobby phi thương mại, quota ORS) cần kiểm tra lại trước khi deploy.
- **CI:** ruff + mypy + pytest + build frontend + openapi diff.

## 14. Yêu cầu phi chức năng

| Mục | Yêu cầu |
|---|---|
| Hiệu năng | Lập kế hoạch một đơn (3 kho, ~10 xe, 14 ngày) < 2 giây; bảng đơn tải < 1 giây với 1.000 đơn |
| Tính đúng | Không double-book xe/tài xế/hàng (ràng buộc DB), không nhân đôi khi nạp lại |
| Khả năng truy vết | Mọi quyết định tái lập được từ `input_snapshot` và `decision_log` |
| Khả năng mở rộng | Thêm nước không sửa lõi; thêm điểm dừng/chuyến (ghép đơn) không đổi schema |
| Khả dụng | Mất ORS hoặc nguồn không làm sập hệ thống: ORS → fallback; nguồn lỗi → cờ dữ liệu cũ + alert |
| Truy cập | WCAG AA cơ bản, thao tác bằng bàn phím trên màn dispatcher |

## 15. Điểm mở rộng đã chừa sẵn

`evaluate_rules()` / `rank_candidates()` (Drools, OR-Tools) · quản lý và xếp lịch thiết bị kho (bỏ khỏi MVP v1.1) · lập kế hoạch nhiều xe cho một đơn (MVP: `HANDLED_EXTERNALLY`) · `delivery_trip`/`trip_stop` nhiều điểm dừng (ghép đơn) · `HandlingGroupSuggester` và `TransferSuggester` (AI) · `location.efficiency_factor` (học định mức) · `SmsProvider` thật · `PodStorage` (ảnh) · `status page` · `MarketAdapter` thật cho WMS/ERP/POS · cửa hàng làm nguồn hàng (`location.type = 'store'` đã có, kèm xe riêng qua `vehicle.home_warehouse_id` mở rộng thành `home_location_id`).
