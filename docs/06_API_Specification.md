# 06 — API Specification (CFO MVP)

> **Phiên bản 1.2 (06/11/2026):** phương án có **nhiều xe** (`vehicles[]`); bỏ `MANUAL_PLANNING`, `result = manual`, `external-handoff`; kế hoạch tay nhận nhiều xe; gợi ý lập lại tự động (mục 6.6); sự kiện `PREP_PAUSED`/`PREP_RESUMED` và sự kiện theo từng xe (`trip_id`); doanh thu thành nhóm endpoint `/revenue/*` với `kpi_scopes` (mục 14.1); giữ chỗ chỉ khóa khi duyệt.
>
> Lịch sử **v1.1:** bỏ endpoint thiết bị kho; thêm `POST /orders/{id}/external-handoff`; đặc tả đóng kế hoạch khi lập lại/hủy; POD theo từng lần giao; quyền xem doanh thu qua `can_view_revenue`; mã lý do `LOWEST_SCORE_OF_3`; tách số đếm "unmapped" khỏi dòng bị loại ở Data integration.
>
> Hợp đồng REST giữa frontend/driver PWA và backend, kèm hợp đồng của hệ thống nguồn giả lập. Backend FastAPI sinh OpenAPI từ model Pydantic đúng theo tài liệu này; frontend sinh client bằng `openapi-typescript`. Tên bảng và cột tham chiếu `05_Database_Design.md`. Quy tắc nghiệp vụ tham chiếu `01_PRD.md` (mã BR-xxx).

## 1. Quy ước chung

| Mục | Quy ước |
|---|---|
| Base URL | `/api/v1` (CFO) |
| Định dạng | JSON UTF-8. Thời gian ISO 8601 có múi giờ (`2026-11-12T08:30:00Z`); ngày `YYYY-MM-DD`; giờ trong ngày `HH:MM` (theo múi giờ của market) |
| Xác thực | `Authorization: Bearer <JWT>` (trừ `/auth/login`, `/health`). `/internal/*` dùng header `X-Internal-Key` |
| Truy vết | Client có thể gửi `X-Correlation-ID` (uuid); server luôn trả lại header này |
| Idempotency | Header `Idempotency-Key: <uuid>` **bắt buộc** cho: `POST /plans/{id}/approve`, `POST /orders/{id}/events`, `POST /orders/{id}/manual-plan`, `POST /transfers/{id}/*`, `POST /notifications/{id}/send`. Cùng key + cùng body trả lại kết quả cũ; cùng key khác body → `409 IDEMPOTENCY_CONFLICT` |
| Phân trang | `?page=1&page_size=50` (tối đa 200) → `{ "items": [...], "page": 1, "page_size": 50, "total": 123 }` |
| Sắp xếp/lọc | `?sort=-committed_date,order_no`; lọc theo tên tham số từng endpoint; `?q=` tìm theo chuỗi |
| Số | Số lượng và giờ công là số thực dạng số JSON; tiền là chuỗi thập phân (`"1234.50"`) |
| Phạm vi dữ liệu | Server tự lọc theo vai trò và phân công của người dùng (mục 3). Truy cập ngoài phạm vi → `404` (không lộ sự tồn tại) |

### 1.1 Định dạng lỗi

```json
{ "error": { "code": "HOLD_EXPIRED", "message": "Planning hold expired. Re-run planning.",
             "details": { "run_id": 812 }, "correlation_id": "6c0f…" } }
```

| HTTP | Khi nào |
|---|---|
| 400 | Sai cú pháp, thiếu header bắt buộc |
| 401 | Chưa đăng nhập, token hết hạn |
| 403 | Không đủ quyền |
| 404 | Không tồn tại hoặc ngoài phạm vi |
| 409 | Xung đột trạng thái/tài nguyên |
| 422 | Dữ liệu sai quy tắc (Pydantic/nghiệp vụ) |
| 429 | Quá tần suất (login) |
| 500/503 | Lỗi máy chủ / phụ thuộc ngoài |

**Mã lỗi nghiệp vụ:** `AUTH_INVALID`, `FORBIDDEN`, `VALIDATION_ERROR`, `ILLEGAL_TRANSITION`, `REASON_REQUIRED`, `SKU_UNMAPPED`, `HOLD_EXPIRED`, `HOLD_EXTENSION_LIMIT`, `RESOURCE_CONFLICT` (xe, tài xế, tồn kho, công suất đã đổi khi duyệt), `PLAN_NOT_APPROVABLE`, `DATE_AGREEMENT_REQUIRED`, `IDEMPOTENCY_CONFLICT`, `GPS_DISABLED`, `NOT_ON_TRIP`, `LICENCE_EXPIRED`, `ORDER_LOCKED_AFTER_DISPATCH`, `DUPLICATE_EVENT`, `SYNC_IN_PROGRESS`.

**Mã lỗi kỹ thuật (v1.2.1 — đề xuất, chờ nhóm duyệt; xem `CHANGELOG`):** `NOT_FOUND` (404: không tồn tại, ngoài phạm vi hoặc route không có), `INTERNAL_ERROR` (500: lỗi không bắt; thông báo cố định "Internal server error.", không stack trace, không thông điệp gốc). Lỗi kiểm tra dữ liệu của framework (422) và 4xx kỹ thuật khác (400, 405…) dùng `VALIDATION_ERROR`; `details.errors` chỉ gồm `loc`, `type`, `msg`, không trả lại giá trị đầu vào. `GET /health` khi phụ thuộc lỗi trả `503` với chính thân health (`status = "error"`), không dùng định dạng lỗi. Header `X-Correlation-ID` không phải UUID hợp lệ thì server thay bằng UUID mới và trả lại giá trị đó.

## 2. Vai trò (`roles` trong JWT)

`admin` (IT) · `dispatcher` · `warehouse` (quản lý, phó, trưởng ca) · `sales` (nhân viên bán, quản lý cửa hàng) · `driver` · `customer_service` · `viewer` (Business owner, Project Lead — phân biệt bằng `kpi_scopes`: `revenue_all` / `ops`).

## 3. Ma trận quyền (R = đọc, W = ghi, — = cấm; phạm vi ghi chú)

| Nhóm endpoint | admin | dispatcher | warehouse | sales | driver | customer_service | viewer |
|---|---|---|---|---|---|---|---|
| Đơn (đọc, danh sách, timeline) | R | R (cả market) | R (đơn của kho mình) | R (đơn của cửa hàng mình) | R (đơn trên chuyến mình, rút gọn) | R (rút gọn, không GPS) | — |
| Lập kế hoạch, duyệt, lập lại, hủy, ghi nhận xử lý ngoài CFO | — | **W** | — | — | — | — | — |
| Thương lượng ngày | — | **W** | — | — | — | — | — |
| Chuyển kho: duyệt / hủy | — | **W** | — | — | — | — | — |
| Chuyển kho: xác nhận kho nguồn / nhận | — | — | **W** (kho nguồn / kho đích, cần `can_approve`) | — | — | — | — |
| Sự kiện kho (START_PREP, PREP_PAUSED, PREP_RESUMED, GOODS_READY, LOADED, ngoại lệ, SHIFT_CHANGE) | — | — | **W** | — | — | — | — |
| Sự kiện tài xế (DISPATCHED, DELIVERED, FAILED) | — | — | — | — | **W** (chuyến mình) | — | — |
| GPS: gửi | — | — | — | — | **W** (chuyến mình) | — | — |
| GPS: xem | — | **R** | — | — | — | **cấm** | — |
| Cảnh báo | R | **R/W** | R (kho mình) | — | — | R (rút gọn) | — |
| Thông báo khách: xem | R | R | — | — | — | R | — |
| Thông báo trễ: gửi/bỏ | — | **W** | — | — | — | — | — |
| Nhật ký liên hệ khách | — | R | — | — | — | **W** | — |
| Ánh xạ SKU, sản phẩm global, nhóm xử lý, cờ | **W** | R | R | — | — | — | — |
| Nhân sự: nhân viên, phân công, quản lý | **W** | R | R (kho mình) | — | — | — | — |
| Điểm danh, ca mẫu, nghỉ phép | R | R | **W** (kho mình) | — | — | — | — |
| Xe, tài xế (hồ sơ) | **W** | R | R (kho mình) | — | — | — | — |
| KPI vận hành | R (tất cả) | R (`ops`) | R (kho mình, `ops`) | — | — | — | R (chỉ `ops`: Project Lead) |
| Doanh thu (`/revenue/*`) | R (tất cả) | — | R (chỉ owner kho, góc nhìn warehouse) | R (chỉ owner cửa hàng, góc nhìn store) | — | — | R (chỉ `revenue_all`: Business owner) |
| Cấu hình market, đồng bộ, DPIA/GPS flag | **W** | — | — | — | — | — | — |
| Nhật ký quyết định (audit) | R | R | — | — | — | — | R (chỉ `ops`) |

### 3.1 Quyền xem KPI và doanh thu [C]
Không thêm vai trò mới. `kpi_scopes` trong token phân biệt: `revenue_all` (Business owner) và `ops` (Project Lead, dispatcher, quản lý/phó kho; sao chép từ `position.default_kpi_scopes`). **KPI vận hành** (`/kpi/*`, `/audit/decisions`): `admin` hoặc có `ops`. **Doanh thu** (`/revenue/*`): `resolve_revenue_scope(user)` — `admin` hoặc `revenue_all` → tất cả; nếu không, các nơi mà `location.owner_employee_id = user.employee_id` (owner cửa hàng → góc nhìn store, owner kho → góc nhìn warehouse); rỗng → `403`. Business owner gọi `/kpi/summary`, `/audit/decisions`, `/orders/{id}` nhận `403`. `customer_service` không xem KPI/doanh thu. "Cost per delivery" của slide được thay bằng giờ công và km mỗi lần giao (KPI vận hành), **không** phải doanh thu.

## 4. Xác thực

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/auth/login` | Đổi email/mật khẩu lấy JWT |
| GET | `/auth/me` | Thông tin người dùng, vai trò, địa điểm |
| POST | `/auth/logout` | Hủy phía client (MVP: no-op ghi log) |

```json
// POST /auth/login
{ "email": "dispatcher1@cfo.test", "password": "••••••••" }
// 200
{ "access_token": "eyJ…", "token_type": "bearer", "expires_in": 28800,
  "user": { "id": 12, "employee_id": 55, "name": "Anna Lind", "roles": ["dispatcher"],
            "market": "SE", "location_ids": [7], "locale": "en", "kpi_scopes": ["ops"] } }
```
Sai thông tin → `401 AUTH_INVALID`; quá 5 lần/phút → `429`.

## 5. Đơn hàng

| Phương thức | Đường dẫn | Vai trò | Ghi chú |
|---|---|---|---|
| GET | `/orders` | theo ma trận | Lọc: `status`, `risk_color`, `committed_date_from/to`, `warehouse_id`, `store_id`, `date_mode`, `q`, `blocked` |
| GET | `/orders/{id}` | theo ma trận | Chi tiết (mục 5.1) |
| GET | `/orders/{id}/timeline` | dispatcher, warehouse, CS, admin | Gộp sự kiện, quyết định, thông báo, ETA theo thời gian |
| GET | `/orders/{id}/eta-forecasts` | dispatcher, warehouse, CS | Các phiên bản ETA và rủi ro |
| POST | `/orders/{id}/replan` | dispatcher | `{ "reason_code": "customer_change", "reason_text": "…" }`. Từ `APPROVED` hoặc `FAILED`. Một transaction: kế hoạch cũ → `superseded`, giữ chỗ → `released`, `trip_stop`/`delivery_trip` chưa xong → `cancelled`, xóa `approved_plan_id`/`committed_date`/`promise_*`, đơn → `SUBMITTED`, ghi `ORDER_REPLAN` (trước/sau) |
| POST | `/orders/{id}/cancel` | dispatcher | `{ "reason_text": "…" }` (bắt buộc), chỉ trước `DISPATCHED`; đóng kế hoạch như `replan`; ghi `ORDER_CANCELLED` |

### 5.1 `GET /orders/{id}` — phản hồi

```json
{
  "id": 4021, "order_no": "SE-2026-004021", "external_ref": "POS-SE-88120", "status": "PLANNED",
  "market": "SE", "customer": { "id": 311, "name": "Nordbygg AB", "type": "business" },
  "contact": { "name": "Erik Berg", "phone": "+46…", "email": "erik@…" },
  "delivery": { "address": "Storgatan 12, Göteborg", "lat": 57.7089, "lon": 11.9746,
                "receiving_restrictions": "Gate code 4411", "special_requirements": "Crane needed" },
  "date_request": { "mode": "latest", "date_from": null, "date_to": "2026-11-18",
                    "window": { "start": "08:00", "end": "12:00" } },
  "committed": { "date": null, "promise_start": null, "promise_end": null },
  "origin_store": { "id": 21, "name": "Store Göteborg Väst" }, "sales": { "id": 90, "name": "Mats Holm" },
  "lines": [ { "line_no": 1, "local_sku": "SE-CEM-25", "global_code": "G-000123", "name": "Cement 25kg",
               "qty_sale": 20, "sale_unit": "pallet", "qty_base": 800, "unit_price": "950.00", "line_total": "19000.00",
               "handling_group": "N3", "flags": [] } ],
  "totals": { "weight_kg": 21450.0, "volume_m3": 18.2, "amount": "48300.00", "currency": "SEK" },
  "block_reason": null,
  "approved_plan_id": null, "latest_run_id": 812,
  "risk": null, "version": 1, "submitted_at": "2026-11-05T07:12:00Z"
}
```
`sales` (cửa hàng) và `customer_service` nhận bản rút gọn (không có `manual`, giá vốn, nhật ký quyết định). `driver` chỉ nhận địa chỉ, liên hệ, hàng, yêu cầu đặc biệt, cửa sổ nhận hàng.

## 6. Lập kế hoạch và duyệt

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/orders/{id}/plan` | Chạy engine. Body tùy chọn (mục 6.1). Tạo `planning_run`, giữ chỗ 3 phương án, hạn 15 phút |
| GET | `/orders/{id}/planning-runs` | Lịch sử các lần chạy |
| GET | `/planning-runs/{id}` | Kết quả một lần chạy (mục 6.2) |
| POST | `/planning-runs/{id}/extend` | Gia hạn giữ chỗ +15 phút, tối đa 2 lần → `409 HOLD_EXTENSION_LIMIT` |
| GET | `/plans/{id}` | Chi tiết một phương án |
| POST | `/plans/{id}/approve` | Duyệt. `Idempotency-Key` bắt buộc (mục 6.3) |
| POST | `/orders/{id}/manual-plan` | Kế hoạch tay (mục 6.4) |
| POST | `/orders/{id}/date-negotiations` | Ghi kết quả thương lượng ngày (mục 6.5) |
| GET | `/orders/{id}/date-negotiations` | Lịch sử |
| GET | `/orders/{id}/transfer-suggestions` | Gợi ý chuyển kho khi thiếu hàng (mục 7) |

### 6.1 `POST /orders/{id}/plan`

```json
{ "target_date": "2026-11-14",                 // tùy chọn: chỉ với range/latest, trong tập ngày khách chấp nhận
  "exclude_warehouse_ids": [3], "exclude_vehicle_ids": [],
  "weights": { "w_km": 0.5, "w_fill": 0.5 },   // mặc định theo cấu hình
  "reason_code": "criteria_change", "reason_text": "Prefer nearest" }   // bắt buộc nếu đây là lần chạy lại (run_no > 1)
```
Điều kiện: đơn `SUBMITTED` (tự động khi vừa nhập) hoặc `PLANNED`/`NO_FEASIBLE_DATE` khi chạy lại. Đơn `BLOCKED_UNMAPPED_SKU` → `409 SKU_UNMAPPED`.

### 6.2 Phản hồi `PlanningRun`

```json
{
  "id": 812, "order_id": 4021, "run_no": 1, "result": "feasible",
  "reserve_class": "safe", "planning_reserve_min": 5220,
  "hold_expires_at": "2026-11-05T09:15:00Z", "hold_extensions": 0,
  "failed_check": null, "earliest_feasible_date": null,
  "workload": { "labour_hours": 10.15, "lines": [ … ] },
  "plans": [
    { "id": 2001, "rank": 1, "status": "proposed",
      "warehouse": { "id": 3, "name": "Malmö DC" },
      "vehicle_count": 1, "total_capacity_kg": 6000, "total_capacity_m3": 40,
      "vehicles": [ { "seq": 1, "vehicle": { "id": 15, "code": "MLM-12-02", "name": "Truck 12 t", "capacity_kg": 6000, "capacity_m3": 40 },
                      "driver": { "employee_id": 71, "name": "Johan Ek" }, "load_kg": 4120, "load_m3": 9.6,
                      "load_lines": [ { "line_no": 1, "qty_base": 800 } ],
                      "loading_start_at": "2026-11-12T11:20:00Z", "depart_at": "2026-11-13T05:10:00Z", "eta_at": "2026-11-13T07:00:00Z" } ],
      "target_date": "2026-11-13",
      "goods_ready_at": "2026-11-12T11:20:00Z", "loading_start_at": "2026-11-12T11:20:00Z",
      "depart_at": "2026-11-13T05:10:00Z", "eta_at": "2026-11-13T07:00:00Z", "trip_end_at": "2026-11-13T09:30:00Z",
      "promise_window_preview": { "start": "2026-11-13T07:00:00Z", "end": "2026-11-13T09:00:00Z" },
      "distance_km": 12.0, "drive_min": 110, "prep_hours": 10.15, "capacity_fill": 0.60,
      "score": 0.26, "score_breakdown": { "n_km": 0.07, "n_fill": 0.44, "w_km": 0.5, "w_fill": 0.5 },
      "complexity_points": 0, "planning_reserve_min": 5220, "route_provenance": "ors",
      "checks": { "stock": { "pass": true, "code": "STOCK_OK" }, "preparation": { "pass": true, "code": "PREP_OK" },
                  "truck": { "pass": true, "code": "TRUCK_OK" }, "site_date": { "pass": true, "code": "DATE_OK" },
                  "safety": { "pass": true, "code": "SAFETY_OK" } },
      "reason_codes": ["LOWEST_SCORE_OF_3", "STOCK_OK", "TRUCK_OK", "RESERVE_SAFE"],
      "explanation": "Lowest score of 3 feasible plans. Malmö DC has stock, capacity fill 60%, truck 12t free, 12 km, reserve 3.6 days (safe)." },
    { "id": 2002, "rank": 2, … }, { "id": 2003, "rank": 3, … }
  ],
  "transfer_suggestions": []
}
```
Khi `result = "infeasible"`: `plans = []`, có `failed_check`, `earliest_feasible_date`, `transfer_suggestions` (nếu do thiếu hàng); đơn → `NO_FEASIBLE_DATE`. Đơn lớn hơn một xe: phương án có nhiều phần tử trong `vehicles` (ít xe nhất trước, mọi xe cùng kho, tới gần như cùng lúc, `eta_at` của phương án = xe tới cuối). Không còn `result = "manual"` (v1.2). Thiếu loại xe hoặc kín xe → `infeasible` với `failed_check = truck`. `kind` của lần chạy: `initial` | `rerun` | `replan_suggestion`.

### 6.3 `POST /plans/{id}/approve`

```json
{ "drivers": [ { "seq": 1, "driver_employee_id": 71 } ],   // tùy chọn: đổi tài xế được gợi ý cho từng xe (phải hợp lệ)
  "date_negotiation_id": 55,                      // bắt buộc nếu ngày giao khác ngày khách đã đồng ý
  "reason_code": "closest_to_customer", "reason_text": "…",   // bắt buộc nếu plan.rank > 1 (chọn phương án khác)
  "note": "Called customer, ok" }
```
Phản hồi `200`: `{ "order": { "status": "APPROVED", "committed": { "date": "2026-11-13", "promise_start": "…", "promise_end": "…" } }, "plan": { … "status": "approved" }, "trip_ids": [930, 931], "notifications": [ { "id": 77, "template": "CONFIRMED", "status": "queued" } ] }`.
Khóa: chỉ khi duyệt, theo `04` mục 7 quy tắc 8 (advisory lock theo kho → sản phẩm → ngày công suất, rồi mọi xe → mọi tài xế của phương án), kiểm tra lại sau khi có khóa. Lúc lập kế hoạch giữ chỗ không khóa và có thể vượt; đơn duyệt trước thắng.
Lỗi: `409 HOLD_EXPIRED` (nếu không thể xác nhận lại tài nguyên), `409 RESOURCE_CONFLICT` (xe/tài xế/hàng/công suất đã bị đơn khác chiếm, kèm `details.conflict` và gợi ý chạy lại), `422 REASON_REQUIRED`, `409 DATE_AGREEMENT_REQUIRED`, `409 ILLEGAL_TRANSITION`.

### 6.4 `POST /orders/{id}/manual-plan`

```json
{ "warehouse_id": 3, "target_date": "2026-11-13", "goods_ready_at": "…",
  "vehicles": [ { "vehicle_id": 15, "driver_employee_id": 71, "load_lines": [ { "line_no": 1, "qty_base": 400 } ],
                  "depart_at": "…", "eta_at": "…" },
                { "vehicle_id": 16, "driver_employee_id": 72, "load_lines": [ { "line_no": 1, "qty_base": 400 } ],
                  "depart_at": "…", "eta_at": "…" } ],
  "manual_reason_code": "special_vehicle", "manual_reason_text": "Customer needs crane truck" }
```
Dùng cho đơn `PLANNED` hoặc `NO_FEASIBLE_DATE` (v1.2). Engine vẫn kiểm gate cho từng xe và cho tổng hàng (mọi dòng phải được chia hết cho các xe); fail → `422` kèm mã check (ví dụ `NO_TRUCK_FIT`, `OVER_LOAD`). Thành công tạo plan `status = manual`, duyệt luôn, ghi snapshot đầy đủ gồm phương án hệ thống đã đề xuất (dữ liệu học cho AI sau này), `decision_log MANUAL_PLAN_CREATED`.

### 6.5 Thương lượng ngày

```json
// POST /orders/{id}/date-negotiations
{ "proposed_date": "2026-11-20", "outcome": "agreed", "channel": "phone",
  "contacted_at": "2026-11-05T09:40:00Z", "note": "Customer OK with 20 Nov" }
// 201 → nếu outcome = "agreed": đơn có thể chạy lại với date_mode/date_to mới (service cập nhật version + 1) khi dispatcher gọi /plan
// outcome = "declined": đơn có thể bị hủy; outcome = "unreachable": remind_at = now + 24h, tạo nhắc
```

### 6.6 Gợi ý lập lại tự động (v1.2)

Khi đơn đã duyệt gặp một trong bốn tín hiệu (nguồn sửa đơn sau duyệt, `PLAN_INVALIDATED`, `VEHICLE_ISSUE`, giao `FAILED`), hệ thống tạo `planning_run(kind='replan_suggestion')` (coi như kế hoạch hiện tại của chính đơn không tồn tại, **không giữ chỗ**) và alert `REPLAN_SUGGESTED` với `details.run_id`. Dispatcher xem bằng `GET /planning-runs/{id}` như lần chạy thường.

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/plans/{id}/approve` | Duyệt phương án gợi ý (Idempotency-Key). Một transaction: đóng kế hoạch cũ (`05` mục 6), khóa, kiểm tra lại, commit kế hoạch mới, đơn → `APPROVED`, `CONFIRMED` mới. Tài nguyên đã bị chiếm → `409 RESOURCE_CONFLICT` |
| POST | `/planning-runs/{id}/keep-current` | Giữ kế hoạch hiện tại: `{ "reason_text": "…" }` (bắt buộc), đóng alert, ghi `REPLAN_KEPT` |

Đơn đã `DISPATCHED` không có gợi ý, chỉ alert. Không có đường tự duyệt.

## 7. Chuyển kho

| Phương thức | Đường dẫn | Ai | Mô tả |
|---|---|---|---|
| GET | `/orders/{id}/transfer-suggestions` | dispatcher | Danh sách gợi ý theo quy tắc (kho nguồn, lead days, khoảng cách) |
| POST | `/orders/{id}/transfers` | dispatcher | Duyệt một gợi ý: `{ "from_warehouse_id": 2, "to_warehouse_id": 3, "lines": [{ "global_product_id": 12, "qty": 40 }], "lead_days": 1 }` → `stock_transfer(approved)` |
| GET | `/transfers` | dispatcher, warehouse | Lọc `status`, `warehouse_id` |
| POST | `/transfers/{id}/confirm-source` | warehouse (kho nguồn, `can_approve`) | Tạo `inbound_shipment(source=transfer, confirmed=true)`, đơn có thể chạy lại |
| POST | `/transfers/{id}/receive` | warehouse (kho đích) | Đánh dấu `received` |
| POST | `/transfers/{id}/cancel` | dispatcher | Cần lý do |

## 8. Thực thi

### 8.1 `POST /orders/{id}/events` (Idempotency-Key bắt buộc)

```json
{ "event_type": "GOODS_READY", "occurred_at": "2026-11-12T11:05:00Z", "payload": {} }
```

| `event_type` | Ai | Điều kiện | `payload` |
|---|---|---|---|
| `START_PREP` | warehouse | đơn `APPROVED` → `PREPARING` | `{ "crew_size": 3 }` (bắt buộc) |
| `PREP_PAUSED` | warehouse | đơn `PREPARING`, đang làm | `{ "note": "…" }` (tùy chọn); không đổi trạng thái đơn |
| `PREP_RESUMED` | warehouse | đơn `PREPARING`, đang tạm dừng | `{ "crew_size": 2 }` (bắt buộc) |
| `GOODS_READY` | warehouse | `PREPARING` (đang làm) → `GOODS_READY` | `{ "crew_size": 3 }` (tùy chọn, sửa đoạn cuối). Hệ thống tính `actual_labour_hours = Σ crew_size × độ dài từng đoạn` |
| `LOADED` | warehouse | theo **từng xe** (`trip_id` bắt buộc); đơn → `LOADED` khi mọi xe đã lên hàng | `{ "trip_id": 930 }` |
| `DISPATCHED` | driver | theo từng xe (chuyến của mình → `on_road`); đơn → `DISPATCHED` ở xe đầu tiên | `{ "trip_id": 930 }` |
| `DELIVERED` | driver | theo từng xe; tạo một `proof_of_delivery` cho `trip_stop` của xe đó; đơn → `DELIVERED` khi mọi xe giao xong | `{ "trip_id": 930, "recipient_name": "Erik Berg", "note": "…" }` |
| `FAILED` | driver | theo từng xe; tạo `proof_of_delivery(result=failed)`; đơn → `FAILED` khi mọi chuyến kết thúc và có xe thất bại (lần giao lại sau đó có POD riêng) | `{ "failure_reason": "customer_absent", "note": "…" }` (bắt buộc `failure_reason` thuộc danh sách chuẩn) |
| `SHORTAGE` | warehouse | mọi trạng thái đang chuẩn bị | `{ "sku": "SE-CEM-25", "qty_missing": 3, "note": "…" }` |
| `BREAKAGE` | warehouse | — | `{ "sku": "…", "qty": 2, "note": "…" }` |
| `VEHICLE_ISSUE` | warehouse | — | `{ "vehicle_id": 15, "note": "Flat tyre" }` |
| `SHIFT_CHANGE` | warehouse | — | `{ "date": "2026-11-12", "staff_present": 7, "note": "…" }` |

Quy tắc: sự kiện bất biến; không có bước duyệt; `occurred_at` ≤ `now + 5 phút` và không trước sự kiện trước đó của cùng đơn; sai thứ tự → `409 ILLEGAL_TRANSITION`; trùng `Idempotency-Key` → trả kết quả cũ. Sau khi ghi: chạy `RiskService.recalculate`, trả `{ "event_id": 9001, "order_status": "GOODS_READY", "risk": { "status": "ON_TRACK", "color": "green", "forecast_eta": "…" } }`. `SHORTAGE`/`BREAKAGE`/`VEHICLE_ISSUE` còn tạo alert `EXCEPTION` cho dispatcher. `FAILED` (cấp đơn) tạo thông báo `FAILED`, alert và **gợi ý lập lại tự động** (mục 6.6); dispatcher duyệt gợi ý hoặc dùng `/orders/{id}/replan`. `VEHICLE_ISSUE` cũng tạo gợi ý lập lại cho đơn đã duyệt dùng xe đó.

### 8.2 Quản lý kho

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/warehouses/{id}/prep-queue` | Đơn cần chuẩn bị theo ngày: workload từng nhóm, giờ kế hoạch, mốc đã ghi |
| GET | `/warehouses/{id}/capacity?from=&to=` | Công suất tính toán theo ngày: số người có mặt, giờ công khả dụng, đã đặt (`committed`, `held`) |

### 8.3 Tài xế

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/driver/trips?date=` | Chuyến của tôi (xe, kho, điểm dừng, địa chỉ, liên hệ, cửa sổ nhận hàng, trạng thái) |
| GET | `/driver/trips/{id}` | Chi tiết chuyến |

## 9. GPS (chỉ khi `market.gps_enabled`)

| Phương thức | Đường dẫn | Vai trò | Mô tả |
|---|---|---|---|
| POST | `/trips/{id}/positions` | driver (chuyến mình) | Gửi lô vị trí. Chuyến phải `on_road` → ngược lại `409 NOT_ON_TRIP`; GPS tắt → `403 GPS_DISABLED` |
| GET | `/trips/{id}/positions?since=` | dispatcher | Lịch sử điểm |
| GET | `/gps/live` | dispatcher | Vị trí mới nhất của mọi chuyến đang chạy, kèm ETA và rủi ro |
| GET/PUT | `/markets/{code}/gps-settings` | admin | `{ "gps_enabled": true, "interval_min": 30, "lost_min": 60, "retention_days": 30 }`; bật `gps_enabled` khi chưa có `compliance_record(DPIA).status='approved'` vẫn được (bản demo) nhưng API trả `warnings: ["DPIA_MISSING"]` và UI hiện biểu ngữ |
| GET/POST/PATCH | `/compliance-records` | admin | DPIA, tham vấn nhân viên, thông báo GPS |

```json
// POST /trips/930/positions
{ "positions": [ { "lat": 57.7001, "lon": 11.9801, "accuracy_m": 12.5, "recorded_at": "2026-11-13T05:40:00Z", "source": "device" } ] }
// 202 { "accepted": 1, "eta": { "forecast_eta": "2026-11-13T07:05:00Z", "risk": "ON_TRACK" } }
```

## 10. Rủi ro, cảnh báo, thông báo

| Phương thức | Đường dẫn | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/alerts` | dispatcher, warehouse, CS, admin | Lọc `type`, `level`, `resolved`, `order_id` (theo phạm vi) |
| POST | `/alerts/{id}/ack` | dispatcher, admin | Xác nhận đã xem |
| GET | `/notifications` | dispatcher, CS, admin | Lọc `order_id`, `template`, `status` |
| GET | `/orders/{id}/notifications` | dispatcher, CS | Lịch sử thông báo của đơn |
| POST | `/notifications/{id}/send` | dispatcher | Gửi bản nháp `DELAY`: `{ "eta_window": { "start": "…", "end": "…" }, "body": "…(tùy chọn sửa)" }`. Ghi `NOTIFICATION_SENT` |
| POST | `/notifications/{id}/discard` | dispatcher | Bỏ bản nháp, `{ "reason_text": "…" }` (bắt buộc), ghi `NOTIFICATION_SUPPRESSED` |
| POST | `/orders/{id}/delay-notice` | dispatcher | Tự soạn thông báo trễ không cần bản nháp của hệ thống |

Thông báo tự động (`CONFIRMED`, `DISPATCHED`, `DELIVERED`, `FAILED`) do hệ thống tạo, không có endpoint gửi tay. Nội dung chỉ gồm trạng thái và khung ETA; không toạ độ, không GPS.

## 11. Nhật ký liên hệ khách (CS)

```json
// POST /orders/{id}/contact-logs   (customer_service)
{ "channel": "phone", "reason_code": "where_is_my_order", "note": "Told ETA window 07–09" }
```
`GET /orders/{id}/contact-logs`: dispatcher và CS.

## 12. Sản phẩm, ánh xạ, nhóm xử lý (IT)

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/mapping/tasks` | Hàng đợi: lọc `status`, `market`; kèm `blocked_order_count` và `candidates` |
| GET | `/mapping/tasks/{id}` | Chi tiết SKU nội bộ + ứng viên (GTIN trùng, tên gần giống, nhóm xử lý theo quy tắc) |
| POST | `/mapping/tasks/{id}/confirm` | Xác nhận ánh xạ (mục 12.1) |
| POST | `/mapping/tasks/{id}/reject` | `{ "reason_text": "…" }` bắt buộc; SKU giữ `rejected` |
| GET | `/products/local?market=SE&mapping_status=` | Sản phẩm nội bộ của nước |
| GET/POST | `/products/global` | Danh sách / tạo sản phẩm global |
| PATCH | `/products/global/{id}` | Sửa (gán nhóm, quy đổi đơn vị chuẩn bị, cờ) |
| GET/PATCH | `/handling-groups`, `/handling-groups/{id}` | Định mức N1–N6 (tên, đơn vị chuẩn bị, giờ cố định/dòng, giờ/đơn vị, yêu cầu xe); một bộ chung mọi kho |
| GET/POST/PATCH/DELETE | `/handling-group-rules` | Bảng quy tắc gán nhóm |
| GET/PATCH | `/special-flags` | Hệ số cờ |

### 12.1 `POST /mapping/tasks/{id}/confirm`

```json
// Chọn sản phẩm global có sẵn
{ "global_product_id": 123, "units_to_base": 40 }
// hoặc tạo mới
{ "create_global": { "code": "G-000500", "name": "Cement 25kg", "category": "Cement", "gtin": "7312345678901",
                      "base_unit": "bag", "weight_kg": 25, "volume_m3": 0.018,
                      "handling_group_code": "N3", "base_units_per_prep_unit": 40, "flags": [] },
  "units_to_base": 40 }
```
Kiểm tra: sản phẩm nhóm `N6` không được có cờ `FRAGILE` (đã tính trong định mức) → `422 VALIDATION_ERROR`.
Hiệu ứng: `product_<cc>.mapping_status = confirmed`, `mapped_by`; các đơn `BLOCKED_UNMAPPED_SKU` chứa SKU này tự được kiểm tra lại và chuyển `SUBMITTED` → lập kế hoạch; `decision_log MAPPING_CONFIRMED`.

## 13. Nhân sự, điểm danh, công suất, xe

| Phương thức | Đường dẫn | Vai trò | Mô tả |
|---|---|---|---|
| GET/POST | `/employees` | admin; R: dispatcher, warehouse (kho mình) | Lọc `position_code`, `location_id`, `status` |
| GET/PATCH | `/employees/{id}` | | |
| POST | `/employees/{id}/assignments` | admin | Chuyển công tác `{ "location_id": 3, "start_date": "…" }` (đóng phân công cũ) |
| POST | `/employees/{id}/terminate` | admin | Khóa tài khoản, giữ lịch sử |
| GET | `/locations`, `/locations/{id}` | theo phạm vi | Kèm owner, quản lý |
| PATCH | `/locations/{id}/owner` | admin | Gán owner |
| PUT | `/locations/{id}/managers` | admin | `{ "primary_employee_id": 40, "deputy_employee_id": 41 }` |
| GET | `/locations/{id}/staff` | admin, quản lý nơi đó | |
| GET | `/warehouses/{id}/attendance?date=` | warehouse (kho mình), dispatcher, admin | |
| PUT | `/warehouses/{id}/attendance` | warehouse | `{ "date": "2026-11-12", "all_present": true, "items": [{ "employee_id": 120, "status": "absent" }] }`; ghi `ATTENDANCE_CHANGED` |
| POST | `/absences` | warehouse, admin | Nghỉ phép |
| GET/PUT | `/warehouses/{id}/shift-templates` | warehouse, admin | Ca mẫu |
| GET/POST/PATCH | `/vehicles`, `/vehicles/{id}` | admin | Hồ sơ xe |
| GET/POST | `/vehicles/{id}/availability` | admin, dispatcher | Bảo trì/không khả dụng |
| GET/POST/PATCH | `/users`, `/users/{id}`; POST `/users/{id}/reset-password` | admin | Tài khoản |

Quy tắc kiểm tra khi ghi (trả `422`): mỗi nhân viên `active` chỉ một phân công hiệu lực; mỗi kho/cửa hàng đúng một quản lý chính; chỉ quản lý có `can_approve` mới xác nhận chuyển kho / sửa ca / đóng ngoại lệ của kho đó.

## 14. KPI

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/kpi/summary?from=&to=&warehouse_id=&store_id=` | Tám chỉ số (xem `05`, mục 8) kèm baseline và thay đổi so với baseline |
| GET | `/kpi/daily?metric=&from=&to=` | Chuỗi theo ngày (cho biểu đồ) |
| GET/PUT | `/kpi/baseline`, `/kpi/baseline/{metric}` | admin: nhập baseline thủ công |

```json
// GET /kpi/summary  → 200
{ "period": { "from": "2026-11-01", "to": "2026-11-30" },
  "metrics": { "planning_time_min": { "value": 4.2, "baseline": 15.0 }, "on_time_rate": { "value": 0.94 },
               "labour_hours_per_delivery": { "value": 9.8 }, "km_per_delivery": { "value": 31.4 },
               "prep_error_min": { "value": 42 }, "eta_error_min": { "value": 28 },
               "plan_acceptance_rate": { "value": 0.78 }, "failed_delivery_rate": { "value": 0.03 },
               "capacity_utilisation": { "value": 0.71 }, "manual_plan_count": { "value": 6 } } }
```
`/kpi/*` chỉ cho `admin` hoặc người có `ops` trong `kpi_scopes`; Business owner nhận `403`.

### 14.1 Doanh thu `/revenue/*` (v1.2)

Báo cáo chỉ đọc. Doanh thu = tiền hàng (đơn giá × số lượng, `total_amount`); không có phí giao, phí đóng gói, nhân công, giá vốn, lợi nhuận. Định nghĩa đầy đủ ở `05` mục 8. Tham số chung: `from`, `to` (`YYYY-MM-DD`, mặc định 30 ngày gần nhất, tối đa 366 ngày, `from ≤ to`, ngày theo múi giờ market), `view` (`store` | `warehouse`), `location_id` (tùy chọn). Phạm vi theo `resolve_revenue_scope` (mục 3.1). Lỗi: `403 FORBIDDEN` (không có quyền doanh thu nào), `404` (nơi ngoài phạm vi), `422` (`view` không khớp loại nơi, ví dụ `view=store` với `location_id` của kho).

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/revenue/summary` | Thẻ số liệu của kỳ |
| GET | `/revenue/daily` | Chuỗi theo ngày cho biểu đồ |
| GET | `/revenue/by-location` | Bảng theo cửa hàng hoặc theo kho (owner chỉ nhận dòng của mình; đơn không có cửa hàng → dòng "Unassigned store") |
| GET | `/revenue/orders` | Danh sách đơn của một nơi (`location_id` bắt buộc), phân trang: `{ order_no, delivered_at, amount, currency, status }`; chỉ owner và admin có thêm `customer_name`; Business owner không có trường này |
| GET | `/revenue/export.csv` | Chỉ owner, Business owner, admin. Cột `day, view, location_code, location_name, orders_delivered, revenue_recognised, revenue_booked, currency`; dấu chấm thập phân; UTF-8 có BOM; mỗi lần ghi `decision_log REVENUE_EXPORTED` (snapshot: bộ lọc, số dòng) |

```json
// GET /revenue/summary?view=store&location_id=21&from=2026-11-01&to=2026-11-30
{ "period": { "from": "2026-11-01", "to": "2026-11-30" }, "view": "store", "location_id": 21,
  "currency": "SEK", "recognised": "1284500.00", "booked_not_delivered": "214300.00",
  "orders_delivered": 41, "avg_order_value": "31329.27", "share_of_market_pct": 8.4 }
// share_of_market_pct = null nếu người gọi không phải Business owner hoặc admin

// GET /revenue/daily
{ "currency": "SEK", "points": [ { "day": "2026-11-03", "recognised": "98200.00", "booked": "40100.00" } ] }

// GET /revenue/by-location?view=warehouse
{ "view": "warehouse", "currency": "SEK",
  "rows": [ { "location_id": 3, "code": "MLM", "name": "Malmö DC", "orders_delivered": 118,
              "recognised": "3410250.00", "booked_not_delivered": "402300.00", "share_pct": 31.2 } ] }
```
Không cộng góc nhìn store với warehouse; không gộp nhiều tiền tệ; không ghi thông tin khách vào log hay file xuất của Business owner.

## 15. Cấu hình, đồng bộ, nhật ký, nội bộ

| Phương thức | Đường dẫn | Vai trò | Mô tả |
|---|---|---|---|
| GET/PUT | `/markets/{code}/config` | admin | `MarketConfig` (04, mục 8); validate bằng Pydantic; ghi audit |
| GET | `/sync-runs?entity=&status=` | admin | Lịch sử đồng bộ, độ tươi |
| POST | `/sync/{entity}/run` | admin | Chạy tay; trùng lượt đang chạy → `409 SYNC_IN_PROGRESS` |
| GET | `/sync-runs/{id}/rejects` | admin | Dòng bị loại và lý do |
| GET | `/audit/decisions?order_id=&action=&from=&to=` | admin, dispatcher, viewer có `ops` | Nhật ký quyết định (chỉ đọc) |
| GET | `/health` | công khai | `{ "status": "ok", "db": "ok", "last_sync_age_min": 3, "notify_queue": 0 }` |
| POST | `/internal/tick?job=ingest_orders` | `X-Internal-Key` | Chạy một job theo yêu cầu (cho dịch vụ ping) |

## 16. Hợp đồng hệ thống nguồn giả lập (`source-<cc>`, mọi nước giống nhau)

Base `/api/v1`, xác thực `X-API-Key`. CFO **chỉ đọc**; POS UI và các endpoint ghi dùng để nhập dữ liệu demo.

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/orders?updated_since=&status=SUBMITTED_FOR_PLANNING&page=&page_size=` | Đơn kèm dòng, bản chụp địa chỉ + toạ độ, `version`, `updated_at` |
| GET | `/customers?updated_since=` | Khách |
| GET | `/products?updated_since=` | Sản phẩm nội bộ (mã, tên, loại, GTIN, đơn vị, quy đổi, giá, cân nặng, thể tích) |
| GET | `/stock` | Ảnh chụp tồn kho toàn bộ: `{ "as_of": "…", "items": [{ "warehouse_code": "GBG", "sku": "…", "on_hand": 800, "reserved": 20 }] }` |
| GET | `/inbound` | Hàng nhập chưa về: `inbound_ref, warehouse_code, sku, qty, eta_date, confirmed` |
| GET | `/fleet/calendar?from=&to=` | Khoảng bận của xe: `vehicle_code, from, to, kind` |
| POST | `/orders` | (POS giả lập) tạo đơn nháp |
| PUT | `/orders/{id}` | Sửa đơn, tăng `version` |
| POST | `/orders/{id}/validate` | **Sales Validation**: kiểm khách, địa chỉ/toạ độ, dòng hàng, dạng ngày, yêu cầu đặc biệt |
| POST | `/orders/{id}/submit` | Chuyển `SUBMITTED_FOR_PLANNING` (chỉ sau `validate` thành công) |
| POST | `/orders/{id}/cancel` | Hủy |
| GET | `/addresses?q=` | Địa chỉ seed sẵn kèm toạ độ (thay geocoding thật) |
| GET | `/health` | |

Đơn mẫu:
```json
{ "id": "POS-SE-88120", "version": 1, "updated_at": "2026-11-05T07:10:00Z", "status": "SUBMITTED_FOR_PLANNING",
  "customer_id": "C-311", "address_id": "A-5521", "contact": { "name": "Erik Berg", "phone": "+46…", "email": "…" },
  "date_mode": "latest", "date_from": null, "date_to": "2026-11-18", "window_start": "08:00", "window_end": "12:00",
  "receiving_restrictions": "Gate code 4411", "special_requirements": "Crane needed",
  "sales_code": "S-090", "store_code": "ST-021",
  "lines": [ { "line_no": 1, "sku": "SE-CEM-25", "qty": 20, "unit_price": "950.00" } ] }
```
Quy tắc phân trang: `page_size ≤ 500`; thứ tự ổn định theo `(updated_at, id)`; trả `X-Total-Count`.

---

## Phụ lục A — Bổ sung hợp đồng phát sinh từ thiết kế UI (`03_UI_UX_Specification.md`)

Các endpoint và trường dưới đây **bổ sung** cho các mục trước; backend phải cung cấp để dựng đủ màn hình.

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/orders/counts` | Số đếm cho chip lọc và huy hiệu menu: `{ "all": 34, "needs_plan": 6, "awaiting_approval": 4, "no_feasible_date": 1, "in_execution": 12, "replan_suggested": 1, "delivered_today": 9, "nav": { "order_queue": 6, "exceptions": 1, "tracking_risk": 2 } }` (theo phạm vi người gọi) |
| GET | `/integration/overview` | Thẻ nguồn: mỗi `entity` có `status`, `rows`, `rejected`, `unmapped` (chỉ `products`: số SKU `pending`, không phải dòng bị loại), `last_run_at`, `data_as_of`, `interval_min` (theo `MarketConfig.sync.interval_min`, mặc định 5); thêm `route_matrix { pairs, fallback_pairs, fetched_at, provider }` và `scheduler { tick_interval_min, last_tick_at, last_tick_status, jobs }` (admin; dispatcher đọc phần `data_as_of`) |
| GET | `/prep-queue?warehouse_id=&date=` | `capacity { booked_min, total_min, free_min, shifts[{name,start,end,present,useful_hours,share,minutes,booked}], cutoff }` và `orders[{order_id, order_no, lines, weight_kg, handling_mix[{code,name}], work_min, prep_window{start,end}, loading[{trip_id, at, vehicle_code, after_cutoff, loaded}], prep_state ('running'|'paused'|null), status, next_action}]` (một đơn nhiều xe có nhiều dòng loading) |
| GET | `/notifications/{id}` | Bản xem trước đã dựng: `{ template, channel, status, recipient_masked, subject, body_html, body_text, eta_window, suppressed_reason }` (người nhận đã che) |
| GET | `/kpi/diagnostics` | `{ hard_constraint_violations, event_to_alert_latency_s_median }` |

**Bổ sung vào phản hồi `PlanningRun` (mục 6.2):**
```json
{
  "rejected_candidates": [
    { "warehouse": {"id": 1, "name": "Stockholm DC"}, "vehicle": null,
      "failed_check": "site_date", "code": "OUTSIDE_RECEIVING_HOURS",
      "detail": { "message": "Drive 4 h 40 min; earliest arrival 15:10, after the site closes at 14:30.", "drive_min": 280, "earliest_arrival": "15:10", "close": "14:30" } },
    { "warehouse": {"id": 2, "name": "Göteborg DC"}, "vehicle": {"code": "GBG-03-02"},
      "failed_check": "truck", "code": "NO_TRUCK_FIT", "detail": { "message": "Order weighs 4 120 kg; van carries 3 500 kg." } }
  ],
  "candidates_checked": 9,
  "stock_matrix": {
    "date": "2026-11-09",
    "lines": [ { "local_sku": "SE-TIL-ADH-25", "name": "Tile adhesive C2TE, 25 kg", "unit": "bag", "needed": 160,
                 "usable": { "GBG": 42, "STO": 180, "MLM": 64 }, "inbound": { "MLM": [ { "qty": 200, "eta": "2026-11-11" } ] } } ]
  },
  "dates_searched": [ { "date": "2026-11-09", "result": "requested" }, { "date": "2026-11-10", "result": "fail", "check": "stock" },
                      { "date": "2026-11-11", "result": "fail", "check": "preparation" }, { "date": "2026-11-12", "result": "first_feasible" } ],
  "per_warehouse_checks": [ { "warehouse": "Malmö DC", "stock": { "pass": false, "code": "STOCK_SHORT", "detail": { "inbound_available_on": "2026-11-11" } },
                              "preparation": null, "truck": null, "site_date": null, "safety": null } ]
}
```
Mọi `checks.<name>` của một phương án có thêm `detail` (đối tượng tự do, luôn có `message` đọc được). Với `STOCK_SHORT` mà hàng nhập xác nhận về sau ngày cần, `detail.inbound_available_on` có ngày (UI gắn nhãn `INBOUND_LATE`).

**Bổ sung `GET /orders` (mỗi phần tử):** `journey: [{step:"approved", state:"done|todo|overdue"} ×6]`, `requested_label`, `window`, `source_warehouse`, `risk {status,color}`, `earliest_feasible_date` (khi `NO_FEASIBLE_DATE`), `feasible_plan_count` (khi `PLANNED`), `hold_expires_at`, `reserve_class`.

**Cấu hình thêm vào `MarketConfig` (`04` mục 8):** `"routing": { "allow_fallback": true }`. Khi `false`, cặp (kho, điểm giao) thiếu trong `route_matrix` làm ứng viên bị loại với mã `ROUTE_DATA_UNAVAILABLE` (check `site_date`).

**Tên hành động nhật ký hiển thị ở UI** dùng đúng mã trong `04` mục 10 (`ALT_SELECTED`, `CRITERIA_CHANGED_RERUN`, `MANUAL_PLAN_CREATED`, `MAPPING_CONFIRMED`, `NOTIFICATION_SENT`, …); các mã khác trong ảnh thiết kế chỉ là ví dụ.
