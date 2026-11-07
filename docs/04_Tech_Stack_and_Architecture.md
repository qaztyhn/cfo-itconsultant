# 04 — Tech Stack & Architecture (CFO MVP)

> Tài liệu giao cho agent code. Kết hợp với `05_Database_Design.md` (DDL), `06_API_Specification.md` (hợp đồng API), `09_AI_Coding_Rules.md` (quy tắc viết code). Nhãn: **[C]** đã chốt, **[S]** slide, **[T]** bản thiết kế, **[A]** giả định chỉnh được qua cấu hình.
>
> **Phiên bản 1.2 (06/11/2026):** một đơn có thể đi **nhiều xe** cùng kho (bước 2d mới, ít xe nhất trước); bỏ bước 0 "manual" và lối xử lý ngoài CFO; hòa điểm "xe nhỏ hơn mà vẫn đủ chứa"; giờ công theo đơn vị cơ sở nhỏ nhất; giữ chỗ lúc lập kế hoạch không khóa, chỉ chặn khi duyệt; **gợi ý lập lại tự động** khi đơn đã duyệt có thay đổi (mục 7.10); tạm dừng/tiếp tục chuẩn bị và dữ liệu giờ nhân công thực tế; cơ sở pháp lý GPS chốt là lợi ích hợp pháp.
>
> Lịch sử **v1.1:** bỏ thiết bị kho khỏi engine (không còn `eq_cap`, `PREP_NO_EQUIPMENT`); quy tắc khóa đồng thời cho hàng và giờ công (mục 7); đóng kế hoạch cũ khi lập lại/hủy/giao thất bại; lối "xử lý ngoài CFO" cho đơn cần nhiều xe; mã lý do `LOWEST_SCORE_OF_3`; cơ sở pháp lý GPS (mục 9).

## 1. Nguyên tắc kiến trúc

1. **Tích hợp trên hệ thống sẵn có, không thay thế [S].** CFO chỉ đọc từ hệ thống nguồn của từng nước, không ghi ngược.
2. **Một lõi quyết định dùng chung, quy tắc từng nước là cấu hình [S].** Không có `if market == 'SE'` trong lõi. Nước mới = adapter/instance nguồn mới + dòng cấu hình + bảng sản phẩm riêng.
3. **Mọi nước bình đẳng [C].** Thụy Điển chạy đúng đường mà nước khác sẽ chạy: hệ thống nguồn giả lập riêng, gọi qua `MarketAdapter`.
4. **Người quyết định, hệ thống đề xuất [S].** Không bao giờ tự duyệt kế hoạch; Dispatcher có đầy đủ quyền, Sales được bấm xác nhận rank-1 tiêu chuẩn đủ điều kiện ở cửa hàng mình; không tự đổi ngày giao khi khách chưa đồng ý.
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
5. **Đơn:** chỉ nhận đơn `SUBMITTED_FOR_PLANNING`. Đơn mới → `SUBMITTED` (rồi `OrderService.prepare_for_planning`: kiểm ánh xạ SKU, nếu thiếu → `BLOCKED_UNMAPPED_SKU` + `mapping_task`; ngược lại gọi `PlanningService.plan(order)`). Đơn đã APPROVED mà nguồn gửi bản mới (sửa/hủy) → **không ghi đè**, tạo alert `ORDER_CHANGED_AFTER_APPROVAL` và **tự gợi ý phương án mới** theo bản mới (mục 7.10); dispatcher quyết định.
6. **Tồn kho:** ghi đè `ops.stock_snapshot` bằng ảnh chụp mới và `as_of`; không đụng giữ chỗ của CFO. Nếu `now − as_of > 15 phút` → cờ vàng và alert `STALE_DATA`.
7. **Hàng nhập:** chỉ hàng chưa về; hàng `received` hoặc biến mất khỏi nguồn thì đặt `received = true`. Hàng chuyển kho tạo bởi CFO (`source='transfer'`) không bị nguồn ghi đè.
8. **Sau mỗi lượt tồn kho/hàng nhập/lịch xe thay đổi:** tìm các đơn đã duyệt bị ảnh hưởng và gọi `RiskService.recalculate(order, trigger='source_change')`.
9. **Lộ trình:** với mỗi cặp (kho, toạ độ giao) chưa có trong `plan.route_matrix`, `RoutingProvider` tính (ORS, hoặc fallback) và ghi `provider`. Việc này diễn ra trước khi lập kế hoạch, không trong engine.

### 5.3 Đồng bộ theo yêu cầu của Sales (Cách B)

Sau khi Sales submit tại POS, Sales mở **CFO Web riêng** và gọi `POST /integration/orders/sync-now`. CFO chủ động GET đơn từ nguồn thông qua `MarketAdapter` (API danh sách đơn phân trang hiện có), xác minh market/store, dùng chung upsert theo version, rejection/idempotency/checkpoint với polling. Giữ **hai database riêng** và không ghi ngược nguồn. Polling mỗi 5 phút vẫn dự phòng. Nếu POS thật không trả dữ liệu mới kịp thì hiển thị Retry, không hứa thời gian tuyệt đối.

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

**Bước 0, tiền kiểm.** Mọi dòng phải có `global_product_id` (nếu không, dừng ở service, không vào engine). (v1.2: không còn kết quả `manual`; đơn lớn được chia cho nhiều xe ở bước 2d.)

**Bước 1, khối lượng việc (độc lập kho) [C]: giờ công giống nhau ở mọi kho.**
```
prep_qty(line)   = qty_base / base_units_per_prep_unit        # tính theo ĐƠN VỊ CƠ SỞ nhỏ nhất (bao, tấm…), không làm tròn
                 = ceil(qty_base)                              # hàng không chia nhỏ được (không có base_units_per_prep_unit)
                 = 1                                           # prep_unit='line'
flag_mult(line)  = min(Π multiplier(flag), cfg.flag_multiplier_cap)
line_hours(line) = (group.fixed_hours + prep_qty × group.labour_hours_per_unit) × flag_mult   # fixed_hours tính MỖI DÒNG
labour_hours     = Σ line_hours + cfg.final_inspection_hours (0.5)
per warehouse    : labour_hours × location.efficiency_factor   (mặc định 1.0)
```
Ví dụ đơn vị nhỏ nhất: 20 bao xi măng (pallet 40 bao) = 0,5 pallet → 0,25 + 0,5×0,15 = 0,325 h (tương đương 0,00375 giờ/bao).
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

*2d. Xe và tài xế (v1.2: một hoặc nhiều xe).* Xe hợp lệ: cùng kho, `status='available'`, `allowed_group_ids` chứa nhóm các dòng nó chở (hoặc rỗng), `capabilities` thỏa `vehicle_requirement` của các dòng nó chở. **Chọn bộ xe:** tìm bộ xe hợp lệ, rảnh trong cùng ngày, có `Σ capacity_kg ≥ tổng kg` và `Σ capacity_m3 ≥ tổng m³` với **số xe ít nhất**; trong các bộ cùng số xe, ưu tiên tổng tải nhỏ hơn (xe nhỏ hơn mà vẫn đủ chứa). Không giới hạn số xe; bị chặn bởi số xe và tài xế rảnh của kho. **Chia hàng:** các dòng được tách qua nhiều xe theo tải và thể tích (một dòng có thể tách, ví dụ 40 pallet chia 2 xe), lưu `plan_vehicle.load_lines`. Mỗi kho sinh tối đa 2 bộ xe ứng viên (bộ ít xe nhất và bộ thay thế). Không ghép đơn: một xe chỉ chở một đơn trong một chuyến. Mỗi xe cần một tài xế: Tài xế ứng viên: `home_warehouse_id = w`, điểm danh `present/planned` ngày đó, hạng bằng `≥ required_licence` (CE ≥ C ≥ B), `licence_expires_on ≥` ngày chuyến, tổng giờ trong ngày (kể cả chuyến đã giữ) + chuyến này ≤ `driver_max_hours_day` (9), không trùng khoảng thời gian trong `vehicle_reservation` của đơn khác (kiểm trên cả xe lẫn tài xế). Tìm khoảng `[loading_start, trip_end]` không đụng bận cho từng xe: nếu đụng, dời `loading_start` tới hết khoảng bận (tối đa 10 lần). Các xe lên hàng lần lượt từ `goods_ready_at` (mỗi xe `loading_min` theo tải của nó). **Đến gần như cùng lúc:** mọi xe tới trong cùng cửa sổ nhận hàng và chênh nhau không quá `multi_vehicle.max_arrival_spread_min` (mặc định 30 phút); xe lên hàng xong sớm chờ để xuất phát sao cho tới cùng lúc. Không có bộ xe nào đủ (thiếu loại xe như cẩu/ben, hoặc cả đội xe kho đó không đủ tải trong ngày) → loại kho với `NO_TRUCK_FIT` (`detail.reason = capability | combined_capacity`) hoặc `TRUCK_BUSY`/`NO_DRIVER`.

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
Nếu `arrive` rơi ngoài cửa sổ thì chuyển sang ngày làm việc kế tiếp thuộc tập ngày cho phép. `eta_at = arrive` (làm tròn lên 15 phút); với nhiều xe, ETA của phương án = ETA của **xe tới cuối cùng**. `unload_min = base + per_ton × tấn`; `trip_end_at = eta + unload + drive về (đối xứng)`.

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

**Bước 4, xếp hạng [C].** Trên tập ứng viên khả thi (mỗi cặp kho–bộ xe tối đa một ứng viên). **Trước tiên ưu tiên số xe ít hơn** (v1.2), rồi mới tới điểm:
```
n_km   = minmax(distance_km)      ; nếu (max−min) < max(2 km, 5% × min) thì mọi n_km = 0   (vùng bỏ qua)
n_fill = minmax(capacity_fill)    ; nếu (max−min) < 0.05 thì mọi n_fill = 0
score  = w_km × n_km + w_fill × n_fill            # mặc định 0.5 / 0.5; thấp hơn là tốt hơn
```
Chỉ một ứng viên → score 0. Thứ tự sắp: `vehicle_count` tăng → `score` tăng; hòa (`|Δscore| < 0,001`) xét lần lượt: `planning_reserve` lớn hơn → `complexity_points` thấp hơn → `eta` sớm hơn → **tổng tải xe nhỏ hơn** (`total_capacity_kg`, rồi `total_capacity_m3`; xe nhỏ hơn mà vẫn đủ chứa) → mã xe nhỏ hơn (để kết quả luôn xác định). `complexity_points` = +1 mỗi lần: dùng hàng nhập chưa về, lên hàng dời sang ca sau, cần chuyển kho (+ điểm dừng thêm sau này khi có ghép đơn). Lấy **top 3** (tối đa 2 phương án mỗi kho). Giờ công đơn như nhau ở mọi kho nên **không** là tiêu chí xếp hạng.

Ví dụ: ba phương án khả thi, đơn 12 giờ công ở mọi kho.

| PA | Km | Mức đầy | n_km | n_fill | score |
|---|---|---|---|---|---|
| A Göteborg | 10 | 85% | 0 | 1 | 0,50 |
| B Stockholm | 40 | 40% | 1 | 0 | 0,50 |
| C Malmö | 12 | 60% | 0,07 | 0,44 | **0,26** |

C thắng; A và B hòa thì xét `planning_reserve`, rồi `complexity_points`…

**Bước 5, giải thích.** Sinh chuỗi từ `reason_codes` bằng mẫu câu cố định (không dùng AI trong MVP). Mã lý do của phương án hạng 1 là `LOWEST_SCORE_OF_3` (hoặc `LOWEST_SCORE_OF_2`, `ONLY_FEASIBLE`); **không** dùng mã hay chữ có nghĩa "rẻ nhất/cost", vì điểm là chỉ số thay thế, không phải tiền.

**Hạn chế đã biết của xếp hạng [A]:** điểm là tương đối trong cùng một đơn (min–max); cỡ xe chỉ dùng khi hòa điểm, chưa quy ra chi phí; khi hai phương án cùng kho thì `capacity_fill` bằng nhau nên thứ tự do tie-break quyết định. Ghép đơn ngoài MVP: đơn đã dùng gần hết tải xe thì không cần ghép. Ghi nhận để hiệu chỉnh sau pilot. Ví dụ: *"Điểm thấp nhất trong 3 phương án khả thi. Kho Malmö đủ hàng, mức đầy công suất 60%, xe 12t rảnh, giao cách 12 km, dự trữ 3 ngày (an toàn)."*

**Bước 6, không có ứng viên.** (a) `result = infeasible`, `failed_check` như trên. (b) `earliest_feasible_date`: chạy lại bước 2 **bỏ cận trên** của ngày yêu cầu, quét tối đa 14 ngày. (c) Nếu `failed_check = stock` ở mọi kho, sinh gợi ý chuyển kho (mục 6.4). (d) Service chuyển đơn sang `NO_FEASIBLE_DATE`. Gồm cả trường hợp đội xe không có loại xe cần (cẩu, ben) hoặc mọi kho đã kín xe trong các ngày khách chấp nhận (`failed_check = truck`); dispatcher thương lượng ngày mới, lập kế hoạch tay, hoặc hủy có lý do.

### 6.3 Theo dõi, ETA và rủi ro (`engine/forecast.py` + `RiskService`)

**Khi nào tính lại ETA (không quét định kỳ vô ích):** (1) có sự kiện mốc/ngoại lệ; (2) có điểm GPS mới; (3) dữ liệu nguồn đổi (hàng nhập, tồn, công suất/điểm danh, lịch xe, đơn); (4) mốc kế hoạch quá hạn 30 phút mà chưa có sự kiện (job 5 phút, truy vấn nhẹ); (5) 07:00 mỗi sáng với đơn nhiều ngày; (6) lúc duyệt. Không có thay đổi thì không tính lại.

**Công thức dự báo** (`forecast_eta`):
- Đơn nhiều xe: tính cho từng xe, `forecast_eta` của đơn = xe tới muộn nhất.
- Đang tạm dừng chuẩn bị (`PREP_PAUSED`): như dòng dưới, cận dưới `now`.
- Trước `GOODS_READY`: `goods_ready_f = planned_goods_ready + max(0, START_PREP_thực − START_PREP_kế_hoạch)`, nếu quá giờ kế hoạch mà chưa xong thì `max(…, now)` (MVP không theo dõi tiến độ bên trong bước chuẩn bị nên đây là cận dưới; hộp "Why it is late" ở UI chỉ diễn giải theo công thức này); `loading_start_f` theo `cutoff`; `depart_f = max(depart_kế_hoạch, loading_start_f + loading_min)`; `eta_f = depart_f + drive_min`. (Dự trữ giữa giờ có thể xuất phát sớm nhất và `depart_kế_hoạch` tự hấp thụ chậm trễ.)
- Sau `LOADED`: `depart_f = max(depart_kế_hoạch, loaded_at + 10 phút)`.
- Sau `DISPATCHED` không có GPS: `eta_f = depart_thực + drive_min`.
- Có GPS (điểm không quá `gps.lost_min` phút): `eta_f = recorded_at + thời gian đường còn lại` (ORS directions, fallback Haversine).
- Làm tròn lên 15 phút. Mỗi lần ghi một dòng `ops.eta_forecast` (phiên bản ETA).

**Giờ nhân công thực tế cho AI (v1.2).** Kho bấm `START_PREP` (nhập `crew_size`), có thể `PREP_PAUSED` / `PREP_RESUMED` (mỗi lần tiếp tục nhập lại `crew_size`), xong thì `GOODS_READY` (sửa `crew_size` nếu cần). Hệ thống cộng các đoạn làm việc: `actual_labour_hours = Σ crew_size × (kết thúc đoạn − bắt đầu đoạn)`. Chia giờ thực tế cho từng nhóm N1–N6 theo **tỷ lệ giờ kế hoạch** của nhóm trong đơn, rồi chia cho **số đơn vị cơ sở** của nhóm → `improvement_log.group_hours_per_unit` (giờ nhân công/đơn vị, không phụ thuộc số người). Đây là dữ liệu duy nhất AI giai đoạn 2 cần để hiệu chỉnh định mức (cần ≥ 30 đơn/nhóm).

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

### 6.6 Công suất theo lịch Warehouse Manager đã xác nhận (ASM-007/Q11)

Lịch phân ca chính thức cho **từng nhân viên/ngày/ca** do Warehouse Manager tạo/sửa. `shift_template.expected_staff` là mốc tham chiếu, **không phải dữ liệu nhân viên để `attendance_gen` tự chia ca**. `hr.attendance` chỉ ghi thực tế; engine dùng lịch hợp lệ và thông tin điểm danh/nghỉ phép để tính năng lực, và nếu thiếu lịch thì không tự bịa số người có mặt. Thao tác đổi lịch/điểm danh có audit và lý do khi chỉnh hồi tố. Quy tắc dữ liệu/API mục tiêu cần PR migration riêng.

## 7. Giữ chỗ và duyệt (`ReservationService`, `ApprovalService`)

1. **Đề xuất:** `PlanningService` gọi engine, rồi trong **một transaction**: tạo `planning_run` (+ `input_snapshot`), `fulfilment_plan` (3 phương án) + `plan_vehicle` (các xe của mỗi phương án), `plan.stock_reservation` và `prep_reservation` **một lần cho mỗi (đơn, kho)**, `vehicle_reservation` cho từng xe của từng phương án (**không khóa**, cho phép vượt, quy tắc 8); `hold_expires_at = now + 15 phút`; ghi `decision_log` (`PLAN_PROPOSED`, `RESERVATION_HELD`); chuyển đơn `PLANNED`.
2. **Gia hạn:** `POST /planning-runs/{id}/extend` cộng 15 phút, tối đa 2 lần.
3. **Hết hạn:** job `hold_expiry` đặt `held → expired`, kế hoạch `proposed → expired`; dispatcher phải chạy lại hoặc, nếu tài nguyên còn trống, nút Approve vẫn thành công vì bước kiểm tra lại (dưới đây).
4. **Duyệt** (`Idempotency-Key` bắt buộc): transaction lấy khóa theo quy tắc 8 bên dưới; **kiểm tra lại** tồn kho, công suất, xe, tài xế bằng chính engine với dữ liệu mới; nếu đổi `committed_date` so với ngày khách đã đồng ý thì cần bản ghi `date_negotiation.agreed`; phương án chọn → `approved`, giữ chỗ → `committed`, phương án khác → `superseded`/`released`; tạo mỗi xe một `delivery_trip` + `trip_stop`; đặt `committed_date`, `promise_start/end`; `order → APPROVED`; tạo thông báo `CONFIRMED`; `decision_log (PLAN_APPROVED hoặc ALT_SELECTED, snapshot)`; `eta_forecast` v1.
5. **Đổi tiêu chí/chạy lại:** tạo `planning_run` mới, giữ chỗ cũ → `released`; bắt buộc lý do; `CRITERIA_CHANGED_RERUN`.
6. **Kế hoạch tay:** từ đơn `PLANNED` hoặc `NO_FEASIBLE_DATE`, dispatcher nhập kho, một hoặc nhiều xe (mỗi xe một tài xế, phần hàng), giờ; engine vẫn kiểm gate; bắt buộc `manual_reason_code` (+ text); lưu snapshot đầy đủ; cờ `manual` vào KPI.
7. **Lập lại sau khi đã duyệt / xếp lại sau giao thất bại / hủy:** trong **một transaction**: kế hoạch cũ `approved`/`manual` → `superseded`; giữ chỗ `held`/`committed` → `released`; `trip_stop` `pending` → `cancelled`, `delivery_trip` chưa xong → `cancelled`; xóa `approved_plan_id`, `committed_date`, `promise_start/end` (giá trị cũ ghi vào `decision_log.before`); đơn → `SUBMITTED` (hoặc `CANCELLED`); bắt buộc lý do (`ORDER_REPLAN` / `ORDER_CANCELLED`). Lần duyệt mới tạo `CONFIRMED` mới (dedupe theo `plan_id`), không tự gửi gì khác cho khách. Lịch sử giao (POD theo `trip_stop`) được giữ nguyên.
8. **Khóa đồng thời cho hàng và giờ công (quyết định nhóm):** xe/tài xế đã có EXCLUDE ở DB; hàng và giờ công thì không. **Lúc lập kế hoạch không khóa**, cho phép giữ chỗ `held` vượt tồn kho/công suất. **Chỉ khi duyệt**, service lấy `pg_advisory_xact_lock` theo key `stock:<kho>:<sản phẩm>` và `labour:<kho>:<ngày>`, theo thứ tự cố định **kho → sản phẩm → ngày → xe → tài xế** (id tăng dần), rồi đọc lại phần còn trống (trừ `committed` của đơn khác). Thiếu → `409 RESOURCE_CONFLICT` và rollback; đơn duyệt trước thắng. Không `FOR UPDATE` trên `ops.stock_snapshot` (job đồng bộ ghi đè bảng này).
9. **Đơn nhiều xe khi thực thi:** mỗi xe một chuyến, một tài xế, một POD. Kho ghi `LOADED` theo từng xe; đơn `LOADED` khi mọi xe đã lên hàng; `DISPATCHED` khi xe đầu tiên xuất phát (thông báo `DISPATCHED` gửi một lần); `DELIVERED` khi mọi xe giao xong (thông báo `DELIVERED` một lần); nếu mọi chuyến đã kết thúc mà có xe thất bại → đơn `FAILED` (ghi phần đã giao), dispatcher xếp lại phần còn thiếu. Khách nhận một `CONFIRMED` cho cả đơn.
10. **Gợi ý lập lại tự động:** khi đơn đã duyệt gặp một trong bốn tín hiệu — nguồn sửa đơn sau khi duyệt, tồn kho đổi làm kế hoạch không còn hợp lệ (`PLAN_INVALIDATED`), `VEHICLE_ISSUE`, giao `FAILED` — `PlanningService` chạy `planning_run(kind='replan_suggestion')`, **coi như kế hoạch hiện tại của chính đơn không tồn tại** (cộng lại hàng, giờ công, xe, tài xế của nó vào phần khả dụng) và **không tạo giữ chỗ**; tạo alert `REPLAN_SUGGESTED` cho dispatcher kèm `run_id`. Dispatcher duyệt phương án gợi ý → trong một transaction: đóng kế hoạch cũ (quy tắc 7) rồi khóa, kiểm tra lại, commit kế hoạch mới, đơn → `APPROVED`, gửi `CONFIRMED` mới; hoặc giữ kế hoạch cũ (lý do, đóng alert). Không bao giờ tự duyệt (09 bất biến 1). Đơn đã `DISPATCHED` chỉ nhận alert.

### 7.1 Nhánh Sales xác nhận đơn tiêu chuẩn

Reuse PlanningService/ReservationService/ApprovalService; Sales cùng cửa hàng chỉ lập plan mặc định và approve rank 1 với 5 gate pass, reserve safe, một xe, dữ liệu tươi, hold còn hạn, không đổi ngày/transfer/manual/replan. ApprovalService dùng chính thứ tự lock và transaction hiện tại, ghi audit actor Sales. `held` của stock/labour có thể vượt, không phải cam kết: đơn cũ chưa duyệt có tranh chấp chưa chứng minh đủ công suất thì chuyển Dispatcher. Các đơn cũ đã duyệt được bảo vệ bằng `committed`. Không thay engine thành thuật toán tối ưu đa đơn.

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
  "multi_vehicle": {"max_arrival_spread_min": 30},
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
- **Cơ sở pháp lý GPS (chốt v1.2) [C][A]:** **lợi ích hợp pháp** kèm **thông báo minh bạch** và **DPIA**. Dữ liệu vị trí tài xế là dữ liệu cá nhân của người lao động. Nhóm giả định: tài xế được thông báo rõ khi ký hợp đồng lao động và trong app về mục đích (điều phối giao hàng), ai xem (chỉ dispatcher), khi nào gửi (chỉ khi chuyến `on_road`, không theo dõi ngoài giờ làm/ngoài chuyến) và thời gian lưu (30 ngày). Vì sự đồng ý trong quan hệ lao động thường không được coi là tự nguyện theo GDPR, cơ sở pháp lý dự kiến là **lợi ích hợp pháp/thực hiện hợp đồng**, kèm DPIA và tham vấn nhân viên **trước khi dùng thật**; bản demo hiện biểu ngữ "chưa có DPIA". Cần kiểm tra lại với bộ phận pháp lý khi pilot.
- **GPS [C][S]:** chỉ `dispatcher` đọc được `vehicle_position` (kiểm ở API, không trả cho vai trò khác dưới mọi hình thức); khách và CS không bao giờ thấy; cờ `gps_enabled` theo nước và `compliance_record(DPIA)`; PWA hiện thông báo quyền riêng tư (mục đích, ai xem, 30 ngày); bản demo hiện biểu ngữ "chưa có DPIA, chỉ demo"; không có báo cáo năng suất theo tài xế; job xóa điểm GPS sau `retention_days` kể từ khi chuyến kết thúc; mất tín hiệu quá 60 phút → alert `GPS_LOST`.
- **Dữ liệu cá nhân:** log kỹ thuật không chứa tên/điện thoại/email/địa chỉ; ẩn danh khách và nhân viên sau thời gian lưu giữ; email/SMS chỉ chứa trạng thái và ETA, không toạ độ.
- **API:** CORS giới hạn origin của web; giới hạn tần suất cơ bản trên `/auth/login`; `Idempotency-Key`; xác thực endpoint `/internal/*` bằng khóa riêng.

**ASM-006:** chuyển công tác, nghỉ việc, đổi quản lý/owner đều phải có actor và before/after trong `audit.decision_log` cùng transaction; thao tác hồi tố bắt buộc lý do. `EMPLOYEE_ASSIGNMENT_CHANGED` dùng cho phân công (đã nằm trong danh sách dưới). Các mã mới cho đổi manager/owner/terminate cần được định nghĩa trước PR code, không được miễn log vì hiện chưa có tên action chuẩn.

## 10. Logging và quan sát

Hai lớp (chi tiết cột ở `05_Database_Design.md`): **nhật ký quyết định** (`audit.decision_log` qua `record_decision()` cùng transaction nghiệp vụ) và **log kỹ thuật JSONL** (`logs/<service>/<YYYY-MM-DD>.jsonl`, `service ∈ api|engine|integration|scheduler|notify`; trường `ts, level, service, correlation_id, order_id, market, event, duration_ms, extra`; online ghi stdout). `correlation_id` sinh ở middleware (`X-Correlation-ID`) và truyền xuống mọi lớp, mọi job. `GET /health` kiểm DB, độ tươi lượt đồng bộ, hàng đợi thông báo.

**Mã hành động chuẩn của `decision_log`** (dùng đúng các mã này ở backend và hiển thị ở UI): `PLAN_PROPOSED`, `PLAN_APPROVED`, `ALT_SELECTED` (duyệt phương án rank > 1, bắt buộc lý do), `CRITERIA_CHANGED_RERUN` (bắt buộc lý do), `MANUAL_PLAN_CREATED` (bắt buộc mã lý do), `REPLAN_SUGGESTED` (v1.2, hệ thống), `REPLAN_KEPT` (v1.2, dispatcher giữ kế hoạch cũ, bắt buộc lý do), `DATE_NEGOTIATION_RECORDED`, `ORDER_REPLAN`, `ORDER_CANCELLED`, `MAPPING_CONFIRMED`, `MAPPING_REJECTED`, `HANDLING_GROUP_CHANGED` (IT đổi định mức/hệ số/quy tắc), `SHIFT_CHANGED`, `ATTENDANCE_CHANGED`, `EXCEPTION_REPORTED`, `TRANSFER_SUGGESTED`, `TRANSFER_APPROVED`, `TRANSFER_CONFIRMED`, `NOTIFICATION_SENT`, `NOTIFICATION_SUPPRESSED` (kèm lý do), `RESERVATION_HELD`, `RESERVATION_COMMITTED`, `RESERVATION_RELEASED`, `HOLD_EXTENDED`, `HOLD_EXPIRED`, `GPS_SETTING_CHANGED`, `CONFIG_CHANGED`, `EMPLOYEE_ASSIGNMENT_CHANGED`, `USER_ROLE_CHANGED`, `REVENUE_EXPORTED` (v1.2, snapshot gồm bộ lọc và số dòng).

## 11. Kiến trúc frontend

- **Routing theo vai trò** (guard theo `roles`): `/dispatcher/*`, `/warehouse/*`, `/store/*`, `/it/*`, `/cs/*`, `/kpi`, `/driver/*` (PWA), `/admin/*`.
- **Dữ liệu:** TanStack Query, polling (dashboard và cảnh báo 15–30 giây; không WebSocket trong MVP); client sinh từ OpenAPI; mọi lỗi API theo định dạng chuẩn (`06`).
- **PWA tài xế:** `vite-plugin-pwa`, cài được lên màn hình chính; **hàng đợi sự kiện offline** (IndexedDB) với `idempotency_key` và `occurred_at` là giờ chạm; Geolocation API gửi vị trí theo `gps.interval_min` khi chuyến `on_road`; hiển thị thông báo quyền riêng tư và xin quyền vị trí. Hạn chế: trình duyệt chỉ định vị khi app đang mở (iOS hạn chế khi tắt màn hình), nên bản demo dùng thêm `tools/gps_simulator.py`.
- **Bản đồ:** Leaflet + OSM, hiện kho, điểm giao, đường đi, vị trí xe (chỉ dispatcher).
- **i18n:** mặc định tiếng Anh, khung `i18next` để thêm tiếng Việt và ngôn ngữ từng nước. Thiết kế giao diện theo `03_UI_UX_Specification.md`.

## 12. Kiểm thử

- **Unit (engine, bắt buộc):** mỗi bước ở mục 6 có bộ test bảng (parametrized) gồm ca biên: thiếu hàng/có hàng nhập, hàng nhập chưa xác nhận, quá giờ cắt, thiếu công suất, không xe vừa, xe/tài xế bận, ngoài giờ nhận hàng, ba dạng ngày, vùng bỏ qua khi xếp hạng, một ứng viên, hòa điểm.
- **Integration:** ingestion idempotent, upsert theo version, checkpoint; giữ chỗ cả 3 phương án và EXCLUDE chặn đơn khác nhưng cho phép cùng đơn; lập kế hoạch đồng thời cho phép giữ chỗ vượt; duyệt đồng thời hai dispatcher (tranh **xe**, tranh **cùng SKU**, tranh **cùng ngày công suất**: đúng một bên thắng); đơn nhiều xe (chia hàng, ít xe nhất, đến cùng lúc, trạng thái tổng hợp); gợi ý lập lại không tính kế hoạch cũ của chính đơn; lập lại sau duyệt đóng kế hoạch cũ và duyệt được kế hoạch mới; giao thất bại rồi giao lại tạo hai POD; chuyển trạng thái trái phép bị trigger chặn; hold hết hạn.
- **E2E (Playwright):** kịch bản 1–18 ở `08_Development_Plan.md`.
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

`evaluate_rules()` / `rank_candidates()` (Drools, OR-Tools) · quản lý và xếp lịch thiết bị kho (bỏ khỏi MVP v1.1) · ghép nhiều đơn trên một xe · `delivery_trip`/`trip_stop` nhiều điểm dừng (ghép đơn) · `HandlingGroupSuggester` và `TransferSuggester` (AI) · `location.efficiency_factor` (học định mức) · `SmsProvider` thật · `PodStorage` (ảnh) · `status page` · `MarketAdapter` thật cho WMS/ERP/POS · cửa hàng làm nguồn hàng (`location.type = 'store'` đã có, kèm xe riêng qua `vehicle.home_warehouse_id` mở rộng thành `home_location_id`).
