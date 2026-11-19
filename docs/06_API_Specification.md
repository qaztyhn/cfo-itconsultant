# 06 — API Specification (CFO MVP)

> **Phiên bản 1.4 (07/11/2026):** phạm vi đơn theo vai trò (mục 5.2), trường hiển thị theo vai trò của chi tiết đơn (5.3), danh sách đơn sắp mặc định theo thứ tự đặt `submitted_at, id` và bucket của `/orders/counts` (5.4), timeline (5.5), schema đọc ánh xạ SKU và phản hồi confirm/reject (12.2), schema điểm danh/công suất (13.2). Chủ dự án chốt Q5–Q10 trong PR qaztyhn/cfo-itconsultant#37, khớp `docs/DECISION_SALES_CONFIRMATION.md` mục 5; Q11 được thay bằng ASM-007 (PR qaztyhn/cfo-itconsultant#50, mục 13.0a); đơn thiếu SKU theo ASM-005 (PR qaztyhn/cfo-itconsultant#49).
>
> **Phiên bản 1.3 (07/11/2026):** API đọc nhân sự, địa điểm, xe (mục 13.1): schema phản hồi, phạm vi theo vai trò và địa điểm, kiểm theo ngày hiệu lực, hiển thị trường theo vai trò; quyền đọc `/vehicles` theo ma trận mục 3. Duyệt ở PR qaztyhn/cfo-itconsultant#12 (Q1–Q4).
>
> **Phiên bản 1.2 (06/11/2026):** phương án có **nhiều xe** (`vehicles[]`); bỏ `MANUAL_PLANNING`, `result = manual`, `external-handoff`; kế hoạch tay nhận nhiều xe; gợi ý lập lại tự động (mục 6.6); sự kiện `PREP_PAUSED`/`PREP_RESUMED` và sự kiện theo từng xe (`trip_id`); doanh thu thành nhóm endpoint `/revenue/*` với `kpi_scopes` (mục 14.1); giữ chỗ chỉ khóa khi duyệt.
>
> Lịch sử **v1.1:** bỏ endpoint thiết bị kho; thêm `POST /orders/{id}/external-handoff`; đặc tả đóng kế hoạch khi lập lại/hủy; POD theo từng lần giao; quyền xem doanh thu qua `can_view_revenue`; mã lý do `LOWEST_SCORE_OF_3`; tách số đếm "unmapped" khỏi dòng bị loại ở Data integration.
>
> Hợp đồng REST giữa frontend/driver PWA và backend, kèm hợp đồng của hệ thống nguồn giả lập. Backend FastAPI sinh OpenAPI từ model Pydantic đúng theo tài liệu này; frontend sinh client bằng `openapi-typescript`. Tên bảng và cột tham chiếu `05_Database_Design.md`. Quy tắc nghiệp vụ tham chiếu `01_PRD.md` (mã BR-xxx).

### BE-02 — Production safety gate for GET phone lookup (2026-11-09)

The canonical `GET /api/v1/orders?q=` contract is unchanged for authorized synthetic
local/staging use. In a non-synthetic `APP_ENV` (for example `production`),
phone-shaped search is **403 FORBIDDEN** by default unless
`CS_PHONE_SEARCH_PRODUCTION_ENABLED=true` is explicitly configured after
security sign-off. The gate does not relax market/RBAC scope, min-query-length or
the application limiter. The error body and CFO JSONL logs do not echo the phone.

**Not a production privacy certification:** application middleware cannot redact
upstream reverse-proxy/WAF/APM/hosting access logs or browser history. Issue #181
requires independent log/telemetry redaction, a reviewed distributed abuse limit,
HTTPS, individual production approval and regression evidence *before* the opt-in.
Real customer phone lookup stays disabled pending those controls.

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

> **Round 3 (DEC-R3, 18/11/2026):** mục này bị thay một phần bởi [§19](#19-round-3-contract-changes--dec-r3-2026-11-18-owner-approved-code-pending).

| Nhóm endpoint | admin | dispatcher | warehouse | sales | driver | customer_service | viewer |
|---|---|---|---|---|---|---|---|
| Đơn (đọc, danh sách, timeline) | R | R (cả market) | R (đơn của kho mình) | R (đơn của cửa hàng mình) | R (đơn trên chuyến mình, rút gọn) | R (rút gọn, không GPS) | — |
| Lập kế hoạch và duyệt phương án tiêu chuẩn | — | **W** | — | **W** (đúng cửa hàng; rank 1/đủ điều kiện) | — | — | — |
| Lập lại, hủy, đổi tiêu chí, chọn phương án khác, lập tay, xử lý ngoài CFO | — | **W** | — | — | — | — | — |
| Thương lượng ngày | — | **W** | — | — | — | — | — |
| Chuyển kho: duyệt / hủy | — | **W** | — | — | — | — | — |
| Chuyển kho: xác nhận kho nguồn / nhận | — | — | **W** (kho nguồn / kho đích, cần `can_approve`) | — | — | — | — |
| Sự kiện kho (START_PREP, GOODS_READY, LOADED, ngoại lệ; R3: không còn PREP_PAUSED/PREP_RESUMED; SHIFT_CHANGE không còn tác dụng tính công suất) | — | — | **W** | — | — | — | — |
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

### ASM-002/003 — Giải thích hợp đồng seed và auth đã chốt

- **ASM-002:** seed tham chiếu migration chỉ chứa market, nhóm xử lý, cấu hình mặc định và position; không seed tài khoản/mật khẩu/dữ liệu demo; GPS mặc định tắt, bật cho demo ở seed riêng.
- **ASM-003:** giới hạn login **5 yêu cầu/60 giây/IP** trên MVP một instance, yêu cầu thứ 6 trả HTTP 429 (mã hiện tại `AUTH_INVALID`); email không phân biệt hoa thường; logout token hợp lệ → 204; người thôi việc/bị vô hiệu phải bị từ chối ở request tiếp theo. Multi-instance cần shared rate limiter, **chưa** thuộc MVP.


## 5. Đơn hàng

**Cách B (phân biệt source read và WMS reserve):** POS/WMS/ERP giữ database riêng; CFO **chỉ GET POS/ERP và authoritative WMS stock**, không sửa POS/ERP hoặc WMS physical on_hand/transfer. Sales có thể yêu cầu CFO GET đơn qua `Sync now`, polling 5 phút dự phòng. **Ngoại lệ nghiệp vụ có điều kiện đã được Owner duyệt:** CFO→WMS reserve/release hẹp khi authorized plan confirmation, có verify original WMS SKU/quantity, ACK và refresh ngay; **real WMS outbound write vẫn disabled** tới khi Dev 1/2 xác minh live API/permissions/contracts, test và được phê duyệt rollout. Adapter giả chỉ staging/demo, có nhãn simulated. [DEC-WMS-RESERVE-SYNC](decisions/DEC_WMS_RESERVE_SYNC_20261109.md).

### 5.0.1 Sales sync-now — endpoint mới

`POST /api/v1/integration/orders/sync-now`, role `sales`, header `Idempotency-Key` bắt buộc, body `{ "external_ref": "POS-SE-88120" }`. CFO dùng MarketAdapter GET nguồn, kiểm market/store, upsert theo source version, trả `200 { "order_id": 4021, "external_ref": "POS-SE-88120", "sync_status": "synced", "source_version": 1 }`, `already_current` nếu đã có. Sai quyền 403, khác cửa hàng/không tồn tại 404, xung đột 409, nguồn lỗi 503, dữ liệu không hợp lệ 422. Không ghi POS. Trạng thái endpoint chỉ là **hợp đồng mục tiêu**, chưa có code.


| Phương thức | Đường dẫn | Vai trò | Ghi chú |
|---|---|---|---|
| GET | `/orders` | theo phạm vi mục 5.2 | Lọc: `status`, `risk_color`, `committed_date_from/to`, `warehouse_id`, `store_id`, `date_mode`, `q`, `blocked`; phần tử và sắp xếp ở mục 5.4 |
| GET | `/orders/{id}` | theo phạm vi mục 5.2 | Chi tiết (mục 5.1), trường theo vai trò (mục 5.3) |
| GET | `/orders/{id}/timeline` | dispatcher, warehouse, CS, admin | Gộp sự kiện, quyết định, thông báo, ETA theo thời gian (mục 5.5) |
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
`sales` (cửa hàng), `customer_service` và `driver` nhận bản rút gọn theo mục 5.3.

### 5.2 Phạm vi đơn theo vai trò (v1.4, Q5)

Kiểm ở máy chủ cho `/orders`, `/orders/{id}`, `/orders/{id}/timeline`, `/orders/counts`. Vai trò không có quyền → `403 FORBIDDEN`; đơn tồn tại nhưng ngoài phạm vi → `404 NOT_FOUND`. Bộ lọc `warehouse_id`/`store_id` ngoài phạm vi → danh sách rỗng. "Hôm nay" và `location_ids` tính theo múi giờ market.

| Vai trò | Thấy đơn khi |
|---|---|
| admin | Đơn thuộc market của mình; tài khoản admin không gắn nhân viên thấy mọi market |
| dispatcher | `market_id` = market của nhân viên |
| warehouse | Có `fulfilment_plan` với trạng thái `proposed`/`approved`/`manual` và `warehouse_id` thuộc `location_ids`, **hoặc** có `delivery_trip` xuất từ kho đó |
| sales | `origin_store_id` thuộc `location_ids` (xem; quyền lập kế hoạch/duyệt của Sales theo mục 6.3a) |
| driver | Có `trip_stop` (không `cancelled`) trên `delivery_trip` có `driver_employee_id` = mình |
| customer_service | `market_id` = market của nhân viên |
| viewer | `403` |

Đơn `SUBMITTED` chưa có kế hoạch: chỉ admin, dispatcher, CS và Sales của cửa hàng gốc thấy. Theo ASM-005, đơn thiếu SKU confirmed đi quy trình cũ và **không** phải đơn chờ CFO xử lý; bản ghi `BLOCKED_UNMAPPED_SKU` còn lại chỉ là dữ liệu legacy (mục 5.4).

### 5.3 Trường của `GET /orders/{id}` theo vai trò (v1.4, Q6)

Trường/khối không được phép bị **bỏ hẳn** khỏi phản hồi (không trả `null`). Không vai trò nào nhận GPS ở endpoint này.

| Khối | admin, dispatcher, warehouse | sales, customer_service | driver |
|---|---|---|---|
| `id`, `order_no`, `status`, `market`, `version`, `submitted_at` | ✓ | ✓ | ✓ |
| `external_ref` | ✓ | ✓ | — |
| `customer` | ✓ | ✓ | chỉ `name` |
| `contact`, `delivery` | ✓ | **CS projection riêng: contact chỉ masked, delivery không có vị trí tọa độ/restrictions** (sales giữ hợp đồng trước) | ✓ |
| `date_request` | ✓ | ✓ | chỉ `window` |
| `committed` | ✓ | ✓ | ✓ |
| `origin_store`, `sales` | ✓ | ✓ | — |
| `lines[]` | ✓ | ✓ không có `handling_group`, `flags` | chỉ `line_no`, `name`, `qty_sale`, `sale_unit` |
| `lines[].unit_price`, `line_total`, `totals.amount`, `totals.currency` | ✓ | ✓ | — |
| `totals.weight_kg`, `totals.volume_m3` | ✓ | — | ✓ |
| `block_reason` | ✓ | ✓ | — |
| `approved_plan_id`, `latest_run_id` | ✓ | — | — |
| `risk` | đầy đủ | `{status, color, forecast_eta}` | — |

`risk` = bản `ops.eta_forecast` mới nhất: `{status, color, forecast_eta, planned_eta, commitment_deadline, slack_min, consumption_pct}`; `null` nếu chưa có.

**Owner-approved CS-02 (DEC-CS-PRIVACY-20261109):** Backend phải xuất allowlisted DTO **dành riêng cho `customer_service`**, không được chỉ ẩn dữ liệu ở frontend. `contact` giữ tên nhưng chỉ có phone/email **đã mask** (không chứa số/email gốc trong payload); loại `delivery.lat`, `delivery.lon`, `delivery.receiving_restrictions` và mọi gate/access code, GPS/điểm số/quyết định nội bộ khỏi response CS. Trường/kiểu masked cụ thể trong generated DTO cần Dev 1/3 thống nhất và kiểm thử trước triển khai, không tự dùng lại schema `ContactOut`/`DeliveryOut` đầy đủ cho CS. Sales và các vai trò khác không được tự nới quyền từ thay đổi này. CS không được approve/dispatch/replan/change promise/DELAY send; backend kiểm 403 ở các mutation. API ETA/notifications/contact-logs còn stub phải thông báo chưa khả dụng, không giả E2E. [Biên bản](decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md).

### 5.4 `GET /orders` và `GET /orders/counts` (v1.4, Q7)

Phần tử danh sách (trường bị cấm theo mục 5.3 thì bỏ):
```json
{ "id": 4021, "order_no": "SE-2026-004021", "status": "PLANNED", "customer_name": "Nordbygg AB",
  "site": "Göteborg", "warehouse": { "id": 7, "code": "STO" }, "origin_store": { "id": 21, "code": "GBG-V" },
  "date_request": { "mode": "latest", "date_from": null, "date_to": "2026-11-18" },
  "committed_date": null, "promise_end": null, "risk_color": null, "block_reason": null,
  "total_amount": "48300.00", "currency": "SEK", "submitted_at": "2026-11-05T07:12:00Z" }
```
- `site` = phần sau dấu phẩy cuối cùng của `delivery_address` (cột CUSTOMER · SITE của `03`).
- `warehouse` = kho của kế hoạch đã duyệt; nếu chưa có thì kho của kế hoạch `proposed` rank 1; nếu không có thì `null`.
- `blocked=true` ⇔ `status = BLOCKED_UNMAPPED_SKU` (bản ghi legacy, chỉ để tra cứu; ASM-005). Các đơn này **không** nằm trong hàng đợi Dispatcher.
- **Owner-approved CS-01 (DEC-CS-SEARCH-20261109):** giữ nguyên tham số `q`, khớp `order_no`, `external_ref`, tên khách hoặc **số điện thoại liên hệ trên đơn**; mã/tên không phân biệt hoa thường. Khi `q` là điện thoại, backend chuẩn hóa cách ghi quốc tế/dấu cách/ký tự phân cách; từ chối truy vấn quá ngắn/dễ dò và áp dụng kiểm soát tần suất/chống enumeration, không ghi raw phone trong URL/access/analytics/error logs. Thực thi role+market scope như §5.2, phân trang và không trả phone thô trong danh sách. Không tự tạo tham số mới; Dev 1 phải cập nhật index/query và regression tests. [Biên bản](decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md).
- **Sắp xếp mặc định: thứ tự đặt hàng** `submitted_at ASC, id ASC` (đơn đặt trước hiện trước; BR-ORD-05, `09` bất biến 27). Có thể chọn `?sort=` theo `submitted_at`, `date_to` (ngày yêu cầu), `promise_end` (`NULL` xếp cuối), `committed_date`, `order_no`, `status`. Thứ tự hiển thị **không** ép thứ tự thực thi: đơn đặt sau cần giao sớm vẫn có thể được chuẩn bị/giao trước nếu không lấn nguồn lực `committed` của đơn trước (mục 6.3a).

Bucket của `/orders/counts` (Phụ lục A), theo phạm vi mục 5.2; "hôm nay" theo múi giờ market:

| Bucket | Trạng thái / điều kiện |
|---|---|
| `all` | Mọi đơn trong phạm vi, trừ `DELIVERED`/`CANCELLED` đã đóng trước hôm nay và `BLOCKED_UNMAPPED_SKU` legacy |
| `needs_plan` | `SUBMITTED` (không gồm `BLOCKED_UNMAPPED_SKU` legacy — ASM-005) |
| `awaiting_approval` | `PLANNED` |
| `no_feasible_date` | `NO_FEASIBLE_DATE` |
| `in_execution` | `APPROVED`, `PREPARING`, `GOODS_READY`, `LOADED`, `DISPATCHED` |
| `replan_suggested` | Có `planning_run.kind = 'replan_suggestion'` chưa được duyệt hoặc giữ nguyên |
| `delivered_today` | `DELIVERED`, `delivered_at` hôm nay |
| `nav.order_queue` | `needs_plan` + `awaiting_approval` + `no_feasible_date` (dispatcher; vai trò khác `0`) |
| `nav.exceptions` | Alert mở loại `EXCEPTION` / `REPLAN_SUGGESTED` trong phạm vi |
| `nav.tracking_risk` | Đơn `in_execution` có `risk_color` `orange`/`red` |

### 5.5 `GET /orders/{id}/timeline` (v1.4, Q9)

Không phân trang; sắp theo `at` tăng dần, cùng thời điểm theo thứ tự `kind` trong bảng.
```json
{ "items": [ { "at": "2026-11-05T07:12:00Z", "kind": "order_submitted", "title": "Order submitted",
               "detail": {}, "actor": null } ] }
```

| `kind` | Nguồn | admin, dispatcher, warehouse | customer_service |
|---|---|---|---|
| `order_submitted` | `customer_order.submitted_at` | ✓ | ✓ |
| `planning_run` | `plan.planning_run` (`kind`, kết quả) | ✓ | — |
| `decision` | `audit.decision_log` (`action`, `reason_text`, người thực hiện) | ✓ | — (US-ORD-03 AC2) |
| `milestone` | `ops.milestone_event` (`type`, xe) | ✓ | ✓ không tọa độ |
| `notification` | `ops.notification` (`type`, `channel`, `status`) | ✓ | ✓ |
| `eta` | `ops.eta_forecast` (`version`, `forecast_eta`, `risk_status`, `risk_color`) | ✓ | `forecast_eta`, `risk_status` |

Không có điểm số, GPS, `snapshot`/`before`/`after` của decision log trong timeline; xem các trường đó qua `/audit/decisions` theo quyền riêng.

## 6. Lập kế hoạch và duyệt

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/orders/{id}/plan` | Chạy engine. Body tùy chọn (mục 6.1). Tạo `planning_run`, giữ chỗ 3 phương án, hạn 15 phút |
| GET | `/orders/{id}/planning-runs` | Lịch sử các lần chạy |
| GET | `/planning-runs/{id}` | Kết quả một lần chạy (mục 6.2) |
| POST | `/planning-runs/{id}/extend` | Gia hạn giữ chỗ +15 phút khi còn hiệu lực, tối đa 2 lần → `409 HOLD_EXTENSION_LIMIT`; quá hạn → `409 HOLD_EXPIRED` |
| GET | `/plans/{id}` | Chi tiết một phương án |
| POST | `/plans/{id}/approve` | Duyệt. `Idempotency-Key` bắt buộc (mục 6.3) |
| POST | `/orders/{id}/manual-plan` | Kế hoạch tay (mục 6.4) |
| POST | `/orders/{id}/date-negotiations` | Ghi kết quả thương lượng ngày (mục 6.5) |
| GET | `/orders/{id}/date-negotiations` | Lịch sử |
| GET | `/orders/{id}/transfer-suggestions` | Gợi ý chuyển kho khi thiếu hàng (mục 7) |

**Sales planning (mở rộng):** Chỉ role `sales` đúng cửa hàng mới được gọi `POST /orders/{id}/plan` với body mặc định `{}` cho lần lập plan hợp lệ; không thay ngày, kho, trọng số hay lựa chọn plan khác. `GET /planning-runs/{id}` và `GET /plans/{id}` cho Sales phải rút gọn còn rank-1/ETA/hold/`sales_approvable`/`sales_block_reason`, không lộ scores/GPS/decision log. Dispatcher giữ đủ quyền.

### 6.1 `POST /orders/{id}/plan`

```json
{ "target_date": "2026-11-14",                 // tùy chọn: chỉ với range/latest, trong tập ngày khách chấp nhận
  "exclude_warehouse_ids": [3], "exclude_vehicle_ids": [],
  "weights": { "w_km": 0.5, "w_fill": 0.5 },   // mặc định theo cấu hình
  "reason_code": "criteria_change", "reason_text": "Prefer nearest" }   // bắt buộc nếu đây là lần chạy lại (run_no > 1)
```
Điều kiện: đơn thuộc luồng CFO và **100% SKU đã được IT mapping confirmed**, trạng thái `SUBMITTED` hoặc các trạng thái lập lại được phép. Đơn chưa mapping **không được vào luồng điều phối CFO**, phải xử lý theo quy trình cũ; không dùng `409 SKU_UNMAPPED` như cách giữ đơn khách chờ IT trong CFO.

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
      "vehicles": [ { "seq": 1, "vehicle": { "id": 15, "code": "MLM-12-02", "name": "Truck 12 t", "capacity_kg": "6000", "capacity_m3": "40" },
                      "vehicle_id": 15, "driver_employee_id": 71, "load_kg": "4120", "load_m3": "9.6",
                      "load_lines": [ { "line_no": 1, "qty_base": 800 } ],
                      "loading_start_at": "2026-11-12T11:20:00Z", "depart_at": "2026-11-13T05:10:00Z", "eta_at": "2026-11-13T07:00:00Z" } ],
      "target_date": "2026-11-13",
      "goods_ready_at": "2026-11-12T11:20:00Z", "loading_start_at": "2026-11-12T11:20:00Z",
      "depart_at": "2026-11-13T05:10:00Z", "eta_at": "2026-11-13T07:00:00Z", "trip_end_at": "2026-11-13T09:30:00Z",
      "distance_km": 12.0, "drive_min": 110, "prep_hours": 10.15, "capacity_fill": 0.60,
      "score": 0.26, "score_breakdown": { "n_km": 0.07, "n_fill": 0.44, "w_km": 0.5, "w_fill": 0.5 },
      "complexity_points": 0, "planning_reserve_min": 5220, "route_provenance": "ors",
      "checks": { "stock": { "passed": true, "code": "STOCK_OK" }, "preparation": { "passed": true, "code": "PREP_OK" },
                  "truck": { "passed": true, "code": "TRUCK_OK" }, "site_date": { "passed": true, "code": "DATE_OK" },
                  "safety": { "passed": true, "code": "SAFETY_OK" } },
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
{ "date_negotiation_id": 55,                      // bắt buộc nếu ngày giao khác ngày khách đã đồng ý
  "reason_code": "closest_to_customer", "reason_text": "…",   // bắt buộc nếu plan.rank > 1 (chọn phương án khác)
  "note": "Called customer, ok" }
```
Phản hồi `200`: `{ "order": { "status": "APPROVED", "committed": { "date": "2026-11-13", "promise_start": "…", "promise_end": "…" } }, "plan": { … "status": "approved" }, "trip_ids": [930, 931], "notifications": [ { "id": 77, "template": "CONFIRMED", "status": "queued" } ] }`.
**Hold đã hết hạn (DEC-HOLD-001):** không được Approve phương án cũ, dù là Dispatcher và dù tài nguyên vẫn còn; trả `409 HOLD_EXPIRED` và đề nghị **Plan Again**. Sau expiry, nếu order vẫn `PLANNED` do run này và không có run/plan mới hơn hoặc approval, job đưa order về `SUBMITTED` an toàn kèm audit. Plan Again dùng `POST /orders/{id}/plan` theo contract hiện có khi order đủ điều kiện; **tạo `planning_run` mới trên cùng order**, kiểm lại toàn bộ nguồn lực/ca kho/tài xế/5 gate và tạo hold mới. Không tạo `customer_order` mới và không hồi sinh hold cũ. Đóng kế hoạch cũ, version/idempotency và trình tự chuyển trạng thái phải được T14/T15/T16 kiểm thử đồng thời; tài liệu này không mở endpoint mới.

Khóa: chỉ khi duyệt, theo `04` mục 7 quy tắc 8 (advisory lock theo kho → sản phẩm → ngày công suất, rồi mọi xe → mọi tài xế của phương án), kiểm tra lại sau khi có khóa. Lúc lập kế hoạch giữ chỗ không khóa và có thể vượt; đơn duyệt trước thắng.
Lỗi: `409 HOLD_EXPIRED` (nếu không thể xác nhận lại tài nguyên), `409 RESOURCE_CONFLICT` (xe/tài xế/hàng/công suất đã bị đơn khác chiếm, kèm `details.conflict` và gợi ý chạy lại), `422 REASON_REQUIRED`, `409 DATE_AGREEMENT_REQUIRED`, `409 ILLEGAL_TRANSITION`.

### 5.0.2 Phân luồng đơn khi Sales kiểm trên CFO (Q14 phương án A; DEC-ROUTING-002)

(chi tiết: `docs/ASSUMPTIONS.md` DEC-ROUTING-001/002; `05` `ops.order_routing` (migration 0009–0011))

**Ai được ghi quyết định**
- **Polling chỉ đồng bộ dữ liệu nguồn, không ghi quyết định phân luồng.**
  - Không ghi `ops.order_routing`.
  - Không tạo `customer_order` cho đơn chưa có quyết định.
  - Không tạo plan/hold.
  - Chỉ cập nhật theo version các đơn đã có `route = cfo`.
- Quyết định `cfo` / `legacy` chỉ được lưu khi **Sales chạy "Sync & check routing"** hoặc **Dispatcher kiểm tra được ủy quyền**.
  - CFO đọc lại nguồn **ngay lúc đó** và đánh giá trạng thái mapping **tại thời điểm đó**.
  - Lưu kèm `decided_by_user_id` và `decided_by_role` ∈ `sales` | `dispatcher`, ghi `ROUTING_DECIDED`.
  - Đã ghi thì **không bao giờ tự chuyển luồng**: không do mapping về sau, không do version nguồn đổi, không do báo cáo của Sales.

**`POST /integration/orders/sync-now`** (sales, đúng cửa hàng; dispatcher trong market). Trả `routing_status`:
- `cfo`: đủ dữ liệu, 100% SKU confirmed. CFO điều phối; không điều phối tay.
- `legacy`: có SKU chưa confirmed. Quy trình tay; CFO không plan/hold/approve; mapping sau không kéo đơn vào CFO.
- `unresolved`: nguồn/CFO không sẵn sàng hoặc dữ liệu thiếu. **Không** coi là legacy, không lưu quyết định, trả `retry_after_s`.
- Gọi lại khi đã có quyết định → trả lại đúng quyết định đã lưu (`already_decided: true`).
- Lỗi kỹ thuật của nguồn vẫn là `503`.

**`POST /integration/orders/{external_ref}/routing-ack`** (sales, đúng cửa hàng). Thân request: `{ "choice": "legacy_acknowledged" | "manual_started", "reason_text"? }`.
- `legacy_acknowledged`: chỉ khi đã có quyết định `legacy`. Ghi riêng cặp `acknowledged_by_user_id` / `acknowledged_at`, đúng một lần. Ghi `ROUTING_LEGACY_ACKNOWLEDGED`.
- `manual_started`, `reason_text` bắt buộc (thiếu → `422 REASON_REQUIRED`):
  - **Chưa có quyết định** → lưu `legacy` / `manual_started` kèm lý do, ghi `ROUTING_MANUAL_START_RECORDED`.
  - **Đã có `legacy`** → chỉ ghi audit `ROUTING_MANUAL_START_RECORDED`; quyết định không đổi.
  - **Đã có `cfo`** → **không đổi luồng**. Trả `409 RESOURCE_CONFLICT` với `details.escalated = true`. Ghi `ROUTING_MANUAL_CONFLICT_ESCALATED` và tạo alert `ROUTING_MANUAL_CONFLICT` (critical, target dispatcher). Dispatcher xử lý để tránh giao trùng.

**Giới hạn:** bảng định tuyến nội bộ **không bảo đảm** chặn được điều phối tay ngoài CFO, vì CFO chỉ đọc POS. Chống trùng dựa vào:
1. quy trình kiểm trước;
2. xác nhận bàn giao có audit;
3. ngoại lệ `manual_started` có lý do;
4. escalation sang Dispatcher.

### 6.3a Sales approve (mở rộng endpoint đã có)

> **Round 3 (DEC-R3, 18/11/2026):** mục này bị thay một phần bởi [§19](#19-round-3-contract-changes--dec-r3-2026-11-18-owner-approved-code-pending).

`POST /plans/{id}/approve` cho Sales **chỉ** khi đúng cửa hàng nguồn, rank 1, 5 gate pass, reserve safe, một xe, version/dữ liệu nguồn còn mới, giữ chỗ hợp lệ, không transfer/manual/replan/date change, không làm trễ đơn cũ. Dùng chính ApprovalService, locks/transaction/audit với actor Sales. Thiếu quyền 403; ngoài cửa hàng 404; không đủ điều kiện hoặc đơn đặt trước chưa duyệt có cạnh tranh chưa chứng minh đủ năng lực: 409 `PLAN_NOT_APPROVABLE`; nguồn lực đổi: 409 `RESOURCE_CONFLICT`; hold hết: 409 `HOLD_EXPIRED`. Không auto-approve.

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
// 201 chỉ lưu date_negotiation/DATE_NEGOTIATION_RECORDED; "agreed" KHÔNG tự đổi date_to/version hoặc replan.
// Sau đó Dispatcher chủ động gọi hành động Apply agreed date (API/DTO kỹ thuật cần review), server xác minh agreement/version/audit trước khi đổi ngày và chạy planning mới; không auto approve, không sửa POS.
// outcome = "declined": đơn có thể bị hủy; outcome = "unreachable": remind_at = now + 24h, tạo nhắc
```

### 6.6 Gợi ý lập lại tự động (v1.2)

> **Round 3 (DEC-R3, 18/11/2026):** mục này bị thay một phần bởi [§19](#19-round-3-contract-changes--dec-r3-2026-11-18-owner-approved-code-pending).

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
| POST | `/transfers/{id}/confirm-source` | warehouse (kho nguồn, `can_approve`) | **Không khả dụng theo DEC-INT-TRANSFER-BOUNDARY/Q3:** 409 `ILLEGAL_TRANSITION` sau RBAC, không tạo inbound hoặc thay đổi WMS |
| POST | `/transfers/{id}/receive` | warehouse (kho đích) | **Không khả dụng theo Q3:** 409 `ILLEGAL_TRANSITION` sau RBAC, không ghi nhận nhập hàng trên CFO |
| POST | `/transfers/{id}/cancel` | dispatcher | Lý do bắt buộc; audit `TRANSFER_CANCELLED` (actor/ts/before/after), không dùng `TRANSFER_APPROVED` |

**D1-01/02 — owner-approved audit semantics (08/11/2026):** `POST /transfers/{id}/confirm-source` ghi `TRANSFER_CONFIRMED` **chỉ khi kho nguồn xác nhận xuất**; `POST /transfers/{id}/receive` ghi **`TRANSFER_RECEIVED`** khi kho đích nhận (không reuse CONFIRMED dưới `snapshot.stage` khác); `POST /transfers/{id}/cancel` bắt buộc lý do, ghi **`TRANSFER_CANCELLED`**, không dùng `TRANSFER_APPROVED`. Cả ba phải kiểm quyền/market/warehouse, state transition và idempotency; audit append-only gồm actor, ts, before/after trong **cùng transaction** với state change. Hủy sau `received` hoặc tác động hoàn nguyên WMS chưa có contract an toàn phải fail closed; không ghi ngược Source. Các semantics `TRANSFER_CONFIRMED`/`TRANSFER_RECEIVED` bên trên là lịch sử/hợp đồng cũ; hai thao tác xác nhận xuất/nhận hiện **không cho thực thi trên CFO theo DEC-INT-TRANSFER-BOUNDARY/Q3**. PR #127 chỉ triển khai gợi ý/yêu cầu/hủy trước khi xuất, và các đường xác nhận xuất/nhận từ chối 409 sau kiểm quyền. `TRANSFER_CANCELLED` yêu cầu lý do, dispatcher, audit và idempotency. Việc thực thi vật lý và chứng cứ thuộc WMS; không ghi tồn kho trên CFO từ một lần bấm. Dev 1/2 vẫn phải đối soát contract và test thật trước khi bật luồng chuyển kho.

**Chốt mới nhất — [DEC-WMS-READONLY-20261109](decisions/DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md) và ngoại lệ reserve có điều kiện [DEC-WMS-RESERVE-SYNC-20261109](decisions/DEC_WMS_RESERVE_SYNC_20261109.md):** WMS quản lý physical stock, xuất/nhập/chuyển kho và đối soát. CFO chỉ GET stock batch có freshness/coverage/provenance và quản lý pending CFO holds; **ngoại lệ reserve/release tại confirmation là hợp đồng nghiệp vụ được duyệt nhưng chưa có quyền kích hoạt real WMS write**. Không tạo luồng CFO reconciliation/evidence review, không tự cộng physical inbound, không trừ đôi WMS ACK phản ánh trong batch; transfer CFO chỉ gợi ý/yêu cầu/hủy, các route `confirm-source`/`receive` từ chối 409 sau RBAC. [Q3](decisions/DEC_INTEGRATION_UNBLOCK_Q2_Q10_20261109.md).

**LƯU Ý LỊCH SỬ — quyết định first-grant và đề xuất CFO WMS transfer reconciliation [DEC-STOCK-GRANT-BOOTSTRAP-20261109 / DEC-T18-WMS-RECON-20261109](decisions/DEC_STOCK_BOOTSTRAP_AND_WMS_RECON_20261109.md):** Phần **first grant** đã được mở rộng bởi [DEC-STOCK-GRANT-CONTROL-20261109](decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md): chỉ System Admin có ủy quyền Owner được cấp **và thu hồi mọi grant**, không chỉ lần đầu. Phần **CFO chứng từ/chờ reviewer/đối soát chuyển kho thủ công** đã bị [DEC-WMS-READONLY](decisions/DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md) và [Q3](decisions/DEC_INTEGRATION_UNBLOCK_Q2_Q10_20261109.md) thay thế; **không implement** queue nhận/chấp thuận chứng cứ vật lý trong CFO. Vẫn phải xác minh khi nào authoritative WMS snapshot đã phản ánh hàng chuyển, không dựa vào `as_of` hay chênh lệch qty đơn lẻ; thiếu dữ liệu thì fail closed. **Không có production WMS write permission** từ ghi chú này.

## 8. Thực thi

### 8.1 `POST /orders/{id}/events` (Idempotency-Key bắt buộc)

> **Round 3 (DEC-R3, 18/11/2026):** mục này bị thay một phần bởi [§19](#19-round-3-contract-changes--dec-r3-2026-11-18-owner-approved-code-pending).

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
| GET | `/warehouses/{id}/prep-queue?date=YYYY-MM-DD` | Endpoint chính Prep queue: approved-plan workload, capacity theo ca và milestones; contract chi tiết ở Phụ lục A |
| GET | `/warehouses/{id}/capacity?from=&to=` | Công suất tính toán theo ngày: số người có mặt, giờ công khả dụng, đã đặt (`committed`, `held`) |

### 8.3 Tài xế

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/driver/trips?date=` | Chuyến của tôi (xe, kho, điểm dừng, địa chỉ, liên hệ, cửa sổ nhận hàng, trạng thái) |
| GET | `/driver/trips/{id}` | Chi tiết chuyến |

## 9. GPS (DEC-DEV2-D3-001, owner-approved policy, contract implementation pending)

> **Round 3 (DEC-R3-01):** không thu theo chu kỳ, không offline, không bản đồ, không lịch sử; vị trí chỉ do tài xế chủ động gửi (một điểm/lần), bắt buộc khi `DELIVERED`/`FAILED`; Dispatcher được gán luân phiên thấy một dòng vị trí gần nhất; tọa độ xóa khi đơn kết thúc. §19.3 thay các quy tắc dưới đây.

**Quyền/phiên:** đọc GPS chỉ cho Dispatcher **được gán rõ cho trip**, không phải mọi Dispatcher của market. Trip phải `on_road`, `market.gps_enabled=true`, tài xế đúng chuyến và thuộc **ca chính thức đang có hiệu lực**; ngoài ca/trước hoặc sau chuyến không đọc/thu điểm. Driver xác thực JWT, ID tài xế từ server-side assignment; **không nhận driver_id tự khai**. Thiếu mapping Dispatcher–trip thì fail closed, cần Dev 1/2 thống nhất migration/RBAC. Driver chỉ gửi/nhận ack của điểm chuyến mình; CS/Sales/warehouse/admin/customer/viewer không bao giờ thấy tọa độ.

| Phương thức | Đường dẫn | Vai trò | Hợp đồng mục tiêu |
|---|---|---|---|
| POST | `/trips/{id}/positions` | driver (chuyến mình) | Gửi lô vị trí sau mỗi **30 phút** khi trip/shift hợp lệ; suggest max 100 điểm/lô. Offline queue chỉ đồng bộ nếu trip **vẫn on_road** và điểm ghi trong ca; khi hoàn tất/hết ca phải xóa local queue và server từ chối upload muộn; `409 NOT_ON_TRIP`, `403 GPS_DISABLED` giữ tương thích |
| GET | `/trips/{id}/positions?since=&until=&page=&page_size=` | Dispatcher **được gán trip** | GPS live/ongoing-trip history only during active trip/shift; **case-specific restricted historical access up to 7 days requires a separately reviewed API contract**, không tự cho Dispatcher đọc sau khi trip/ca kết thúc; đề xuất page_size=50/max=500, sort `recorded_at,id` |
| GET | `/gps/live` | Dispatcher **được gán trip** | Chỉ các chuyến mà Dispatcher được ủy quyền, đang `on_road` trong ca; điểm mới nhất, `recorded_at`, `accuracy_m`, `gps_status=fresh|lost|no_fix`, ETA và risk nếu đã tính; **không** trả toàn market |
| GET/PUT | `/markets/{code}/gps-settings` | admin | `gps_enabled`, `interval_min=30`, `lost_min=60`, legacy `retention_mode=trip_end_delete` / `retention_days=0` **đã bị supersede**, policy mục tiêu là tối đa **7 ngày** lịch sử hợp lệ, runtime/config migration cần review; cài đặt không cho phép vượt scope ca/chuyến; demo DPIA missing vẫn cảnh báo, không GPS người thật trước compliance review |
| GET/POST/PATCH | `/compliance-records` | admin | DPIA/nhân viên/thông báo GPS; không cho phép admin đọc vị trí qua endpoint này |

```json
// POST /trips/930/positions — employee/driver ID derived from JWT+trip, not sent by client
{ "positions": [ { "lat": 57.7001, "lon": 11.9801, "accuracy_m": 12.5, "recorded_at": "2026-11-13T05:40:00Z", "source": "device" } ] }
// Existing success code 202 preserved until code/contract review
// 202 { "accepted": 1, "eta": { "forecast_eta": "2026-11-13T07:05:00Z", "risk": "ON_TRACK" } }
```

**Xóa dữ liệu GPS đã chốt:** khi **trip kết thúc/hủy** hoặc driver hết ca hợp lệ (mốc đến trước), **dừng thu và thu hồi quyền xem live ngay**; xóa queue thiết bị không hợp lệ, còn điểm GPS đã thu hợp lệ chỉ giữ tối đa **7 ngày** trong kho lịch sử bị hạn chế quyền tra soát và có audit; không mở lịch sử cho live Dispatcher sau trip/ca. Nếu trip có nhiều stop, không kết thúc GPS chỉ vì một stop/đơn đã giao; kết thúc khi trip thực sự terminal. Cleanup phải xóa lịch sử hết hạn 7 ngày và các điểm bất hợp lệ (cadence cleanup thực tế còn nằm trong D8 chưa duyệt); **không** lưu 30 ngày. Không xóa duty/tachograph records theo quy tắc GPS. `GPS_LOST` chỉ trong ca/trip hợp lệ, sau >60 phút không nhận fix; không tiếp tục GPS ngoài ca. Dữ liệu GPS trong backup cần rà soát riêng theo GDPR, không tuyên bố xóa vật lý tức thời khỏi provider backup.

**Lưu ý implementation:** DTO/rate limit/assignment scope cần migration/contract tests và cross-review; PR docs này chưa triển khai. IMY Thụy Điển: <https://www.imy.se/verksamhet/dataskydd/dataskydd-pa-olika-omraden/arbetsliv/kontroll-och-overvakning-av-anstallda/>.

## 10. Rủi ro, cảnh báo, thông báo

| Phương thức | Đường dẫn | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/alerts` | dispatcher, warehouse, CS, admin | Lọc `type`, `level`, `resolved`, `order_id` (theo phạm vi) |
| POST | `/alerts/{id}/ack` | dispatcher, admin | Xác nhận đã xem |
| GET | `/notifications` | dispatcher, CS, admin | Lọc `order_id`, `template`, `status` |
| GET | `/orders/{id}/notifications` | dispatcher, CS | Lịch sử thông báo của đơn |
| POST | `/notifications/{id}/send` | dispatcher | D4: chỉ Send bản nháp `DELAY` với `eta_window` đã validate, `reason_code`/phrase từ template allowlist, `Idempotency-Key`; **không** nhận body/subject free-text. Ghi `NOTIFICATION_SENT` |
| POST | `/notifications/{id}/discard` | dispatcher | Discard `DELAY` với `reason_text` bắt buộc cho audit nội bộ; **không** chèn reason_text vào thư gửi khách |
| POST | `/orders/{id}/delay-notice` | dispatcher | Chỉ tạo **draft** từ template đã kiểm tra, không có đường gửi trực tiếp bỏ qua Dispatcher |

**D4 owner-approved (2026-11-08):** server render `CONFIRMED`, `DISPATCHED`, `DELIVERED`, `FAILED`, `DELAY` theo template có phiên bản. Biến chỉ từ `public_order_ref`, trạng thái/khung đã duyệt, ETA và reason_code thuộc enum/câu mẫu đã duyệt. Tuyệt đối không lấy arbitrary POS/CS/free-text, tên tài xế/nhân viên, tên người nhận, GPS/tọa độ, thông tin riêng tư hoặc risk scores. Trường `body` tự do trước đây **bị thay thế** bởi các biến có kiểu; request chứa body không khớp render phải trả 422, không đưa thẳng tới provider. `DELAY` luôn cần Dispatcher xem trước/duyệt gửi hoặc Discard. Giữ quiet hours market-local 21:00–07:00 (ngoại lệ gửi DELAY do Dispatcher kích hoạt), cap 3 attempts và `DEC-NOTIFY-001`: chỉ Mailpit/test recipient, chưa gửi khách thật. Retry 5/15 phút là đề xuất Dev 2, chưa tự owner-approved; Dev 2 cần trình policy/code review.

**D2 CSV owner-approved:** schema UTF-8/version/ISO/decimal và SHA-256, retry `failed`, IT review `partial`, trùng `ok` bỏ qua; thao tác nhập nguồn admin-only, CFO không ghi ngược POS. Cần cập nhật OpenAPI/migration/test trước khi coi đã triển khai.

**D5 GDPR owner-approved policy:** raw GPS **ngừng thu/live** khi trip/ca hợp lệ chấm dứt, lịch sử đã thu hợp lệ lưu tối đa **7 ngày** theo DEC-GPS-RET-20261109 (D3 supersedes 30 days); customer/contact/CS 90 ngày, nonfinancial operational order 365 ngày, employee nonstatutory contacts 90 ngày, workforce shifts/attendance 24 tháng (cần pháp lý), logs tech/security 30/90 ngày, staging backup 30 ngày; tachograph/driver working-time và Swedish accounting giữ theo luật áp dụng. DSAR, ROPA, DPIA/GPS, legal holds và retention theo mục đích cần sign-off trước dữ liệu người thật; không xem legacy config `personal=365/order=730` là GDPR compliant. Xem `docs/decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md`.

## 11. Nhật ký liên hệ khách (CS)

> **Round 3 (DEC-R3, 18/11/2026):** mục này bị thay một phần bởi [§19](#19-round-3-contract-changes--dec-r3-2026-11-18-owner-approved-code-pending).

```json
// POST /orders/{id}/contact-logs   (customer_service)
{ "channel": "phone", "reason_code": "where_is_my_order", "note": "Told ETA window 07–09" }
```
`GET /orders/{id}/contact-logs`: dispatcher và CS.

## 12. Sản phẩm, ánh xạ, nhóm xử lý (IT)

**ASM-005 — Chính sách phạm vi CFO:** Khoảng 100 SKU mapping confirmed ban đầu (pilot) và mở rộng dần. CFO chỉ điều phối đơn có toàn bộ SKU đã xác nhận. Đơn thiếu SKU đi theo quy trình cũ; API đồng bộ đơn của CFO phải đánh giá điều kiện trước khi tạo planning run/hold, trả kết quả **không đủ điều kiện CFO / tiếp tục quy trình cũ**, không gọi Dispatcher để giữ đơn chờ IT. Không được tự chuyển đơn cũ vào CFO sau mapping. Mã phản hồi, dữ liệu định danh luồng, cách ngăn hai luồng cùng xử lý và xử lý đơn đã nhập ở CFO trước thay đổi là **thiết kế cần chốt khi triển khai**, không tự coi API hiện tại đã hỗ trợ.


| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/mapping/tasks` | Hàng đợi SKU cho IT: lọc `status`, `market`; kèm `candidates` (`blocked_order_count` là trường legacy — mục 12.2) |
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
Hiệu ứng: `product_<cc>.mapping_status = confirmed`, `mapped_by`, ghi `decision_log MAPPING_CONFIRMED`; **không tự chuyển** các đơn đã đi quy trình cũ thành `SUBMITTED`, **không tự lập kế hoạch/giữ chỗ** khi IT mapping xong. Các đơn mới sau đó có thể được CFO điều phối nếu 100% SKU confirmed.

### 12.2 Đọc ánh xạ và phản hồi (v1.4, Q8)

Quyền (mục 3): admin **W**; dispatcher, warehouse **R** trong market mình; vai trò khác `403`. Task ngoài market → `404`.

`GET /mapping/tasks?status=&market=&q=` (phân trang; mặc định `status=open`; sắp mặc định `id` — task cũ trước; có thể sắp `local_sku`). Phần tử:
```json
{ "id": 12, "market": "SE", "local_sku": "SE-NEW-77", "name": "…", "category": "…", "gtin": "…",
  "sale_unit": "pallet", "mapping_status": "pending", "status": "open", "blocked_order_count": 2,
  "candidates": [ { "global_product_id": 123, "code": "G-000123", "name": "…", "reason": "gtin", "score": 1.0 } ],
  "resolved_by": null, "resolved_at": null }
```
`blocked_order_count` là trường legacy (ASM-005 mục 6): **không** phải số đơn đang chờ CFO xử lý, không dùng để ưu tiên hay làm hàng đợi Dispatcher; giữ trong phản hồi để tương thích cho tới khi có thiết kế KPI thay thế.

`GET /mapping/tasks/{id}`: cùng schema, thêm `suggested_handling_group` (theo `handling_group_rule`, US-PRD-04 AC2). Không liệt kê đơn khách: đơn thiếu SKU đi quy trình cũ.

`POST /mapping/tasks/{id}/confirm` → `200 { "task_id", "local_sku", "global_product_id", "mapping_status": "confirmed" }`. Không mở khóa, không chuyển trạng thái, không lập kế hoạch/giữ chỗ cho đơn nào (mục 12.1, ASM-005).
`POST /mapping/tasks/{id}/reject` → `200 { "task_id", "local_sku", "mapping_status": "rejected" }`.
Lỗi: `403`; `404`; `422 VALIDATION_ERROR` kèm `details.field`; `422 REASON_REQUIRED`.

`GET /products/local?market=SE&mapping_status=&q=` (phân trang, sắp mặc định `local_sku`): phần tử là các cột của `ref.v_product_local` — `{market, local_sku, name, category, gtin, sale_unit, units_to_base, unit_price, currency, global_product_id, mapping_status}` (US-PRD-05 AC1).

## 13. Nhân sự, điểm danh, công suất, xe

| Phương thức | Đường dẫn | Vai trò | Mô tả |
|---|---|---|---|
| GET/POST | `/employees` | admin; R: dispatcher (market), warehouse (kho mình) — mục 13.1 | Lọc `position_code`, `location_id`, `status`, `q` |
| GET/PATCH | `/employees/{id}` | | |
| POST | `/employees/{id}/assignments` | admin | Chuyển công tác `{ "location_id": 3, "start_date": "…" }` (đóng phân công cũ) |
| POST | `/employees/{id}/terminate` | admin | Khóa tài khoản, giữ lịch sử |
| GET | `/locations`, `/locations/{id}` | admin, dispatcher (market), warehouse (nơi được phân công) — mục 13.1 | Kèm owner, quản lý (theo ngày hiệu lực) |
| PATCH | `/locations/{id}/owner` | admin | Gán owner |
| PUT | `/locations/{id}/managers` | admin | `{ "primary_employee_id": 40, "deputy_employee_id": 41 }` |
| GET | `/locations/{id}/staff` | admin, quản lý nơi đó | |
| GET | `/warehouses/{id}/attendance?date=` | warehouse (kho mình), dispatcher, admin | |
| PUT | `/warehouses/{id}/attendance` | warehouse | `{ "date": "2026-11-12", "all_present": true, "items": [{ "employee_id": 120, "status": "absent" }] }`; ghi `ATTENDANCE_CHANGED` |
| POST | `/absences` | warehouse, admin | Nghỉ phép |
| GET/PUT | `/warehouses/{id}/shift-templates` | warehouse, admin | Ca mẫu |
| GET/POST/PATCH | `/vehicles`, `/vehicles/{id}` | admin; R: dispatcher (market), warehouse (xe có kho gốc thuộc kho mình) — mục 13.1 | Hồ sơ xe |
| GET/POST | `/vehicles/{id}/availability` | admin, dispatcher | Bảo trì/không khả dụng |
| GET/POST/PATCH | `/users`, `/users/{id}`; POST `/users/{id}/reset-password` | admin | Tài khoản |

Quy tắc kiểm tra khi ghi (trả `422`): mỗi nhân viên `active` chỉ một phân công hiệu lực; mỗi kho/cửa hàng đúng một quản lý chính; chỉ quản lý có `can_approve` mới xác nhận chuyển kho / sửa ca / đóng ngoại lệ của kho đó.

### 13.0a ASM-006/007 — Nhân sự, lịch làm chính thức và điểm danh (hợp đồng mục tiêu)

- **Nhân sự (ASM-006):** trước khi đổi/chấm dứt phân công của quản lý chính phải bố trí người quản lý hợp lệ thay thế. Khóa user người đã nghỉ; lịch sử không xóa. Đổi phân công, quản lý, owner, nghỉ việc phải ghi audit actor, before/after cùng transaction. Sửa hồi tố chỉ admin đủ quyền và phải có `reason_text`; các action code mới cho đổi manager/owner/terminate cần được bổ sung contract trước code.
- **Lịch ca chính thức (ASM-007/Q11):** Warehouse Manager được phân công làm quản lý tại kho đó có quyền tạo/cập nhật **lịch nhân viên–ngày–ca**; API đích dự kiến `GET /warehouses/{id}/shift-schedule?from=&to=`, `PUT /warehouses/{id}/shift-schedule` (payload người–ngày–ca, kèm `reason_text` khi sửa hồi tố). Định dạng cụ thể/chống lịch chồng/lưu revision và migration phải được Dev 1 đề xuất và review trước triển khai. Sai role → 403; ngoài kho → 404.
- `expected_staff` của `shift_template` chỉ là số dự kiến để so sánh; tuyệt đối **không** là số lượng dùng tự phân người hoặc dồn người vào ca cuối. `attendance_gen` chỉ chép lịch đã được Manager xác nhận để tạo `planned`, không tự dựng từ `expected_staff`.
- `PUT /warehouses/{id}/attendance` chỉ cập nhật tình trạng thực tế cho người **đã có lịch**; `all_present` không tự tạo ca hay sửa lịch. Sửa dữ liệu quá khứ phải có quyền và lý do. Mọi cập nhật ghi `SHIFT_CHANGED` hoặc `ATTENDANCE_CHANGED` với actor/before/after cùng transaction. Thiếu lịch chính thức → trả/cảnh báo thiếu dữ liệu, không xác nhận công suất dựa trên người giả định.
- Đây là **đặc tả mục tiêu của PR docs**; không tuyên bố endpoint, bảng hoặc migration hiện có đã hỗ trợ.


### 13.0b Lịch ca chính thức của kho và tài xế, mã audit nhân sự (Q12/Q13, đã duyệt)

(chi tiết: `docs/proposals/M3_M5_SCHEDULE_AUDIT_ROUTING.md`; lựa chọn nghiệp vụ đã duyệt ở PR qaztyhn/cfo-itconsultant#53; DDL/API/engine cuối cùng review ở PR triển khai)
- Một bảng lịch cho **nhân viên kho và tài xế** (tài xế theo kho gốc). Người cập nhật: quản lý chính/phó `can_approve` của kho (Q12b); 1 ca/người/ngày (Q12a); sửa quá khứ cần lý do (Q12c); giờ riêng, ca qua nửa đêm, giờ nghỉ; kiểm nghỉ giữa ca `driver_min_rest_hours`.
- `GET /warehouses/{id}/shift-schedule?from=&to=&kind=staff|driver|all`, `PUT /warehouses/{id}/shift-schedule` (`entries[{employee_id, date, shift_template_id|null, start_time?, end_time?, break_start?, break_end?}]`, `reason_text?`); ghi `SHIFT_CHANGED`. Công suất trả `schedule_verified` (Q12d).
- Engine chỉ đề xuất phương án khi lên hàng nằm trong ca kho chính thức có người và khoảng làm việc của từng tài xế nằm trọn trong ca thực tế của tài xế; mã mới `NO_WAREHOUSE_SHIFT`, `OUTSIDE_DRIVER_SHIFT` (Phụ lục A).
- **Thời gian lái/nghỉ của tài xế (Q12b, chính sách Bắc Âu cho MVP, không phải xác nhận pháp lý):**
  - `MarketConfig.driver_rules` (nghỉ hằng ngày 11 giờ, tắt nghỉ rút gọn, lái 540 phút/ngày, nghỉ 45 phút sau 270 phút lái, giới hạn tuần/hai tuần) được validate ở `PUT /markets/{code}/config`.
  - `ref.vehicle` thêm `regulation_561_scope` (`in_scope|out_of_scope|unknown`) và `max_permissible_mass_kg`.
  - Mã safety mới (Phụ lục A): `DRIVER_REST_INSUFFICIENT`, `DRIVING_TIME_EXCEEDED`, `DRIVING_BREAK_REQUIRED`, `DRIVER_HISTORY_MISSING`, `VEHICLE_SCOPE_UNKNOWN`.
  - UI phân biệt thiếu dữ liệu với không có tài xế khả thi.
  - **D7 được duyệt (`DEC-DEV2-D7-001`, 08/11/2026):** fixture synthetic 56 ngày lịch sử duty/driving/rest của tài xế và thông số xe (payload riêng max permissible mass, scope theo loại vận tải/xe/rơ-moóc); Dev 2 seed, Dev 1 test chung PlanningService/ApprovalService. Thời gian nghỉ mặc định 11h; không bật giảm 9h; kiểm thời gian làm việc khác giờ lái. Ca/historical evidence hoặc xe scope thiếu => trả safety reason thích hợp và không cho tự duyệt. Không có quyền tự cấp ca hoặc bỏ qua `DEC-SHIFTS-001`; không có API mới trong PR tài liệu này.
- Mã audit mới (Q13): `LOCATION_MANAGER_CHANGED`, `LOCATION_OWNER_CHANGED`, `EMPLOYEE_TERMINATED`; chỉnh hồi tố phân công `EMPLOYEE_ASSIGNMENT_CHANGED` + `reason_code=retroactive` + lý do; `ROUTING_LEGACY_ACKNOWLEDGED` (Q14).

### 13.1 API đọc nhân sự, địa điểm, xe (v1.3)

Duyệt ở PR qaztyhn/cfo-itconsultant#12 (Q1 chấp nhận có điều chỉnh, Q2 phương án A, Q3 phương án A, Q4 phương án C có điều chỉnh).

**Quy tắc chung**
- Kiểm vai trò và phạm vi ở máy chủ. Thiếu/sai token → `401 AUTH_INVALID`; vai trò không được đọc nhóm endpoint → `403 FORBIDDEN`; bản ghi không tồn tại **hoặc** ngoài phạm vi → `404 NOT_FOUND` (không lộ sự tồn tại); tham số sai → `422 VALIDATION_ERROR`.
- Vai trò được đọc: `admin`, `dispatcher`, `warehouse`. `sales`, `driver`, `customer_service`, `viewer` → `403`. Người có nhiều vai trò dùng vai trò rộng nhất theo thứ tự `admin` > `dispatcher` > `warehouse`.
- **Phạm vi market:** dispatcher và warehouse chỉ thấy dữ liệu của market của nhân viên mình. Admin gắn nhân viên thấy market của mình; tài khoản admin hệ thống (không gắn nhân viên) thấy mọi market.
- **Phạm vi địa điểm của warehouse:** các địa điểm có phân công **đang hiệu lực hôm nay** của người dùng (`location_ids` trong `/auth/me`).
- **Ngày hiệu lực** (hôm nay theo `ref.market.timezone`): phân công hiệu lực khi `start_date ≤ hôm nay` và (`end_date` rỗng hoặc `≥ hôm nay`); quản lý địa điểm hiệu lực khi `valid_from ≤ hôm nay` và (`valid_to` rỗng hoặc `≥ hôm nay`).
- Không tin `location_id` từ client: lọc theo nơi ngoài phạm vi trả danh sách rỗng.
- Phân trang `?page=1&page_size=50` (`page ≥ 1`, `1 ≤ page_size ≤ 200`) → `{items, page, page_size, total}`; sắp xếp `?sort=` theo các trường liệt kê dưới đây (tiền tố `-` = giảm dần); trường lạ → `422`.
- Trường không hiển thị cho vai trò được **bỏ hẳn** khỏi phản hồi (không trả `null`). Trường đánh dấu *nullable* có thể là `null`.
- Tên, email, điện thoại nhân viên không ghi vào log kỹ thuật (`09` bất biến 16).

**`GET /locations`, `GET /locations/{id}`** — admin, dispatcher (market), warehouse (nơi được phân công).
Lọc: `type`, `is_active` (mặc định `true`), `q` (mã hoặc tên). Sắp xếp: `code` (mặc định), `name`, `type`. Danh sách và chi tiết cùng schema; mọi vai trò được phép nhận cùng trường.
```json
{ "id": 7, "market": "SE", "timezone": "Europe/Stockholm", "type": "warehouse", "code": "STO", "name": "Stockholm DC",
  "address": "…", "lat": 59.3293, "lon": 18.0686, "loading_cutoff_time": "15:00", "is_active": true,
  "owner": { "employee_id": 40, "name": "…" },
  "managers": { "primary": { "employee_id": 40, "name": "…" }, "deputy": null } }
```
Nullable: `address`, `lat`, `lon`, `loading_cutoff_time` (chỉ kho bắt buộc), `owner`, `managers.primary`, `managers.deputy`. `managers` = bản ghi `hr.location_manager` hiệu lực hôm nay. Không trả `efficiency_factor`. `timezone` là trường **bắt buộc, không nullable**, giá trị IANA lấy từ `ref.market.timezone` qua `location.market_id`; trả cho **mọi loại location** trong cả list lẫn detail. Không suy timezone từ trình duyệt và không dùng `/auth/me` làm nguồn riêng; market timezone bị thiếu/không hợp lệ phải báo lỗi rõ, không mặc định UTC.

**`GET /employees`, `GET /employees/{id}`** — admin; dispatcher (nhân viên của market); warehouse (nhân viên có phân công hiệu lực hôm nay tại nơi của mình).
Lọc: `position_code`, `location_id` (phân công hiệu lực hôm nay), `status`, `q` (tên; admin thêm `employee_no`). Sắp xếp: `last_name` (mặc định `last_name,first_name`), `first_name`, `position_code`; admin thêm `employee_no`, `hire_date`. Dispatcher và warehouse không thấy nhân viên `terminated`.

| Trường | admin | dispatcher | warehouse |
|---|---|---|---|
| `id`, `first_name`, `last_name`, `position {code, name}`, `assignment` | ✓ | ✓ | ✓ |
| `driver_staff {licence_class, licence_expires_on, home_warehouse_id, adr}` | ✓ | ✓ | — |
| `warehouse_staff {role, counts_in_capacity}` | ✓ | — | ✓ |
| `sales_staff {role}`, `dispatcher_staff {can_send_delay_notice}`, `cs_staff {team}` | ✓ | — | — |
| `employee_no`, `status`, `employment_type`, `hire_date`, `end_date`, `work_email`, `work_phone` | ✓ | — | — |
| Chỉ chi tiết: `weekly_hours`, `reports_to_employee_id`, `assignment_history` | ✓ | — | — |

```json
{ "id": 55, "first_name": "Anna", "last_name": "Lind", "position": { "code": "DRIVER", "name": "Driver" },
  "assignment": { "location_id": 7, "location_code": "STO", "location_name": "Stockholm DC", "start_date": "2025-03-01" },
  "driver_staff": { "licence_class": "C", "licence_expires_on": "2027-01-31", "home_warehouse_id": 7, "adr": false } }
```
Nullable: `assignment` (không có phân công hiệu lực), các khối `*_staff` (không áp dụng), `end_date`, `work_email`, `work_phone`, `reports_to_employee_id`. `assignment_history` = mọi phân công, mới nhất trước: `[{location_id, location_code, start_date, end_date}]`. Không trả thông tin tài khoản (`roles`, `is_active`, email đăng nhập).

**`GET /vehicles`, `GET /vehicles/{id}`** — admin; dispatcher (xe của market); warehouse (xe có `home_warehouse_id` thuộc nơi của mình).
Lọc: `home_warehouse_id`, `status`, `capability`. Sắp xếp: `code` (mặc định), `capacity_kg`, `status`.
```json
{ "id": 3, "code": "STO-CR-01", "plate": "…", "name": "Crane truck",
  "home_warehouse": { "id": 7, "code": "STO", "name": "Stockholm DC" },
  "capacity_kg": 8000.0, "capacity_m3": 30.0, "capabilities": ["crane"], "required_licence": "C",
  "allowed_groups": [ { "id": 4, "code": "N4" } ], "status": "available" }
```
`allowed_groups: []` = chở được mọi nhóm. Lịch bận ở `GET /vehicles/{id}/availability`.

### 13.2 Điểm danh và công suất (v1.4, Q10; Q11 thay bằng ASM-007)

> **Round 3 (DEC-R3, 18/11/2026):** mục này bị thay một phần bởi [§19](#19-round-3-contract-changes--dec-r3-2026-11-18-owner-approved-code-pending).

`GET /warehouses/{id}/attendance?date=`: warehouse của kho đó, dispatcher và admin trong market; ngoài phạm vi → `404`. Phản hồi của `PUT /warehouses/{id}/attendance` dùng cùng schema:
```json
{ "warehouse_id": 1, "date": "2026-11-12",
  "counts": { "planned": 0, "present": 10, "absent": 2, "leave": 0 },
  "items": [ { "employee_id": 120, "name": "…", "position": "WAREHOUSE_OPERATOR", "counts_in_capacity": true,
               "shift": { "id": 4, "start": "07:00", "end": "15:00" }, "status": "present",
               "on_approved_leave": false } ] }
```

`GET /warehouses/{id}/capacity?from=&to=`: cùng phạm vi; tối đa 31 ngày (vượt → `422`).
```json
{ "warehouse_id": 1, "days": [ { "date": "2026-11-12", "holiday": false,
    "shifts": [ { "start": "07:00", "end": "15:00", "present": 8, "useful_hours": 7.0 } ],
    "labour_cap_hours": 50.4, "booked_hours": { "committed": 22.0, "held": 8.0 }, "free_hours": 20.4 } ] }
```
`labour_cap_hours` = Σ người có mặt × giờ hữu ích × `delivery_share` (US-WH-02 AC1). Ngày lễ trả `0` (AC3). `booked_hours` gồm giờ của mọi đơn (AC2).

**Nguồn roster và `attendance_gen` (ASM-007, thay Q11 = B):** roster điểm danh lấy từ **lịch phân ca chính thức do Warehouse Manager lập cho từng nhân viên/ngày/ca** (mục 13.0a). `shift_template.expected_staff` chỉ là số dự kiến để so sánh: hệ thống **không** tự chia người vào ca theo số này, **không** đưa người dư vào ca cuối. `attendance_gen` chỉ chép lịch đã được quản lý xác nhận thành dòng `planned`; khi bảng lịch chính thức chưa có (chờ PR migration riêng) thì job **không tạo dòng nào**. `PUT …/attendance` và `all_present` chỉ cập nhật người đã có trong lịch, không tạo ca. Thiếu lịch → công suất chỉ tính từ dòng điểm danh thực có (có thể bằng 0) và phải được cảnh báo là chưa xác minh, không dựng số người giả định.

## 14. KPI

> **Round 3 (DEC-R3, 18/11/2026):** mục này bị thay một phần bởi [§19](#19-round-3-contract-changes--dec-r3-2026-11-18-owner-approved-code-pending).

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/kpi/summary?from=&to=&warehouse_id=&store_id=` | 10 metric key KPI vận hành (xem `05`, mục 8) kèm baseline và thay đổi so với baseline |
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
| POST | `/internal/tick?job=notify_outbox&market=SE` | `X-Internal-Key` | E2 gửi các notification email `queued` đã đến hạn trong market xác định; `market` **bắt buộc**, phải là code hiện có trong `ref.market` |
| POST | `/internal/tick?job=hold_expiry` | `X-Internal-Key` | E2 xử lý các hold hết hạn **toàn cục**, không nhận tham số `market` |

**Hợp đồng E2 của `POST /internal/tick` (chỉ `local`, `test`, `staging`):** Cần header `X-Internal-Key` bằng secret `INTERNAL_TICK_KEY`; thiếu/sai hoặc chứa ký tự ngoài ASCII ⇒ `401 AUTH_INVALID`, không chạy handler. Key đúng nhưng production ⇒ `403 FORBIDDEN`. Chỉ `notify_outbox` và `hold_expiry` là handler hợp lệ; job sai, `notify_outbox` thiếu hoặc sai market, và `hold_expiry` có `market` (kể cả rỗng) ⇒ `422 VALIDATION_ERROR`. Lỗi handler được chuẩn hóa thành `503 INTERNAL_ERROR` không tiết lộ SMTP/DB/secret.

**Response `200`** trả dữ liệu thực sau khi job hoàn tất (header `X-Correlation-ID` khớp trường `correlation_id`):
```json
{
  "job": "notify_outbox",
  "market": "SE",
  "status": "ok",
  "started_at": "2026-11-19T10:00:00+00:00",
  "finished_at": "2026-11-19T10:00:01+00:00",
  "processed": 1,
  "correlation_id": "example-id"
}
```
Với `hold_expiry`, `market` trong response là `null`. `processed` là số đối tượng do handler xử lý; gọi lại khi không còn việc có thể trả `0`. Timestamps UTC ISO 8601. Endpoint này không kích hoạt scheduler, không tự approve hoặc tự gửi DELAY. Các job khác chưa triển khai phải bị từ chối.

**D8 được owner phê duyệt chỉ để triển khai và kiểm thử staging/demo (DEC-D8-STAGING-SCHEDULE-20261109):** danh sách job/tần suất trong proposal là baseline staging, chưa bật production; tick endpoint/auth/response và mã lỗi vẫn phải review kỹ thuật. Đề xuất tách riêng tại `docs/proposals/D8_SCHEDULER_SWEDEN_PROPOSAL_20261108.md`: 5 phút ingest/stock/gps-lost/stale/milestone, 1 phút hold expiry/outbox, morning 07:00 và nightly 04:00/04:15 giờ Thụy Điển; bảo vệ DB lock/mỗi job/market, không tác động đến ca/GPS ngoài giờ, không tự approve hay gửi DELAY, D6 hosting chờ owner. Chưa thay route/code trong tài liệu này.

**Cách B:** Hệ thống nguồn giữ nguyên thao tác POS create/validate/submit và database riêng. CFO đọc API nguồn theo yêu cầu Sales bằng các GET sẵn có, không thay POS. Nếu API nguồn thực tế không thể truy vấn đơn vừa nộp nhanh, trả Retry/Wait; không mặc định mọi POS có khả năng real-time.

## 16. Hợp đồng hệ thống nguồn giả lập (`source-<cc>`, mọi nước giống nhau)

**DEC-SRC-D1-001 — D1-A/B/C/D đã được chủ dự án duyệt ngày 08/11/2026.** Base `/api/v1`; source API xác thực `X-API-Key`; CFO **chỉ đọc từ Source**, POS UI/nhân viên nguồn sử dụng API ghi cho demo. Các mô tả dưới đây là **contract mục tiêu**, không khẳng định toàn bộ endpoint/DDL/OpenAPI đã có trong code; Dev 2 phải cập nhật source OpenAPI/migration/tests và Dev 1/3 review. Chi tiết [D1 owner-approved](decisions/DEC_SRC_D1_APPROVED_20261108.md).

### 16.1 D1-A — Inventory GET và đồng bộ gia tăng

| GET | Nội dung / filter | Natural key bảo đảm thứ tự sau `updated_at` |
|---|---|---|
| `/orders?updated_since=&status=&page=&page_size=` | Mặc định `status=SUBMITTED_FOR_PLANNING`; **phải cho `status=CANCELLED`** để CFO đồng bộ hủy; có thể query trạng thái nháp phục vụ POS; order+lines+snapshot+version | `id` |
| `/customers?updated_since=&page=&page_size=` | Khách nguồn | `id` |
| `/products?updated_since=&page=&page_size=` | SKU nguồn, `units_to_base`, GTIN, giá, khối lượng | `sku` |
| `/inbound?updated_since=&page=&page_size=` | Hàng nhập, kho, SKU, ngày ETA, trạng thái nhận | `(inbound_ref,warehouse_code,sku)` |
| `/fleet/calendar?from=&to=&updated_since=&page=&page_size=` | Khoảng thời gian xe bận, filter giao nửa mở `[from,to)` | `(vehicle_code,from_ts,to_ts)` |
| `/addresses?customer_id=&q=&updated_since=&page=&page_size=` | Địa chỉ khách hàng; filter theo khách / tên, có tọa độ | `id` |
| `/stock` | **KHÔNG** phân trang; snapshot nguyên batch `{as_of,items}`; xem 16.4 | Batch có một `as_of` duy nhất |
| `/health` | Health source, không phân trang | — |

Mọi danh sách trừ `/stock`/`/health` trả `200 ` với **`{items,page,page_size,total}`**, header **`X-Total-Count`**, `page=1` và `page_size=50` mặc định, `1 ≤ page_size ≤ 500`. Sắp xếp `updated_at ASC` rồi natural key ASC; `updated_since` yêu cầu aware timestamp, lọc **`updated_at >= updated_since`**. Tham số sai → 422 `VALIDATION_ERROR` có field path, không phản chiếu PII. Kết nối nhiều trang dùng durable checkpoint sau khi nạp hết, so trùng bằng version/natural key và overlap thời gian; offset pagination đơn thuần **không phải** snapshot transaction khi source thay đổi đồng thời.

**Triển khai 5 danh sách (khách, sản phẩm, hàng nhập, lịch xe, địa chỉ) — diễn giải kỹ thuật cần review, không đổi quyết định D1-A:** phần tử là các cột bảng nguồn (`05` §10) cộng `updated_at`; số lượng/quy đổi/khối lượng là số JSON, `unit_price` là chuỗi decimal đúng như đã lưu, `lat`/`lon` là số hoặc `null`; lịch xe trả khóa `vehicle_code, from, to, kind, updated_at`. `from` và `to` của `/fleet/calendar` đều **tùy chọn** (mỗi cận áp dụng độc lập); khi có cả hai, `from < to`, sai → `422` (`type = invalid_range`); khoảng bận trùng nếu `from_ts < to` và `to_ts > from`. `/addresses?q=` so khớp **văn bản địa chỉ** không phân biệt hoa thường, ký tự `%`/`_` là ký tự thường; `customer_id` lọc đúng khách.

### 16.2 D1-B — POS ghi đơn và validate

| Phương thức | Path | Thành công | Bất biến |
|---|---|---|---|
| `POST` | `/orders` | **201**, order DTO | Sinh ID nguồn, `status=DRAFT`, `version=1`; draft persist cần customer_id, address_id, store_code, date_mode |
| `PUT` | `/orders/{id}` | **200**, order DTO | Full replacement, `expected_version` bắt buộc, atomic; 409 khi stale |
| `POST` | `/orders/{id}/validate` | **200**, order DTO | Validate toàn bộ, vào VALIDATED từ DRAFT; 422 khi lỗi không thay status/version |
| `POST` | `/orders/{id}/submit` | **200**, order DTO | Chỉ từ VALIDATED, revalidate dưới row lock, vào SUBMITTED_FOR_PLANNING |
| `POST` | `/orders/{id}/cancel` | **200**, order DTO | Có `expected_version` và lý do, chuyển terminal CANCELLED; retry idempotent |

Request fields nguồn có thể chứa `customer_id, address_id, store_code, sales_code, contact:{name,phone,email}, date_mode, date_from,date_to,window_start,window_end,receiving_restrictions,special_requirements,lines:[{line_no,sku,qty,unit_price}]`. `id/status/version/updated_at/address/lat/lon` là **server-owned**; từ chối field lạ. Server xác minh address thuộc customer rồi snapshot `address,lat,lon` và contact vào đơn. Thay đổi hồ sơ địa chỉ về sau không âm thầm sửa snapshot đơn; chỉ ghi snapshot mới khi chính người dùng đổi địa chỉ hoặc yêu cầu refresh tường minh.

**Valid DRAFT:** cần `customer_id,address_id,store_code,date_mode`, có thể thiếu contact/date details/lines để người dùng bổ sung trước validate. **VALIDATED/SUBMITTED** cần khách đang hoạt động, địa chỉ thuộc khách và có tọa độ hợp lệ, sales/store reference, tên liên hệ và ít nhất phone hoặc email, ít nhất một line SKU **tồn tại trong nguồn**, `line_no` dương không trùng, `qty > 0` tối đa 3 chữ số thập phân, `unit_price` là **chuỗi decimal chính xác hai chữ số thập phân và không âm (cho phép `"0.00"`)**. SKU có trong POS nhưng chưa CFO mapping confirmed **không** bị POS từ chối, mà điều phối toàn đơn theo ASM-005 / DEC-ROUTING-002.

`POST /orders` nhận optional `Idempotency-Key` UUID; POS nên gửi cùng key khi retry/double-click.
Cùng key + typed payload trả cùng order ID (representation hiện tại), vẫn 201; khác payload →
409 `IDEMPOTENCY_CONFLICT`, không tạo thêm order. Không gửi key nghĩa là tạo draft mới.
Nếu gửi lines trong DRAFT thì mỗi line phải có đầy đủ line_no/sku/qty/unit_price đúng kiểu; có thể dùng
`lines:[]` khi chưa nhập hàng. Reference sales/store sai dùng field `value_error` chuẩn 422; không tạo
reason code mới. Order clock nhận APP_NOW aware của instance, lưu UTC; id/status/version/snapshot do server quản lý.

**Date modes:** `exact` → `date_from` bắt buộc, `date_to=null`; `range` → cần cả hai, `from<=to`; `latest` → `date_to` bắt buộc, `date_from=null`. Date là `YYYY-MM-DD` theo IANA timezone của source instance/market. `window_start` và `window_end` cùng có hoặc cùng null, dạng 24h `HH:MM`, start < end, phải phù hợp lịch nhận từng địa chỉ (xem 16.4); thiếu receiving calendar phải trả lỗi, không đoán mở 24/7. `special_requirements` và `receiving_restrictions` là optional text snapshot, **không** được Planning Engine tự suy luận thành khả năng/safety của xe; thiếu trường có cấu trúc phải chuyển Dispatcher kiểm tra.

**Lỗi 422 có cấu trúc cố định:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Order validation failed",
    "details": {
      "errors": [
        { "loc": ["body", "lines", 0, "qty"], "type": "invalid_quantity", "msg": "Quantity must be positive" }
      ]
    },
    "correlation_id": "<opaque>"
  }
}
```

Các business reason ổn định: `customer_not_found`, `address_customer_mismatch`, `missing_coordinates`, `contact_required`, `invalid_date_mode`, `invalid_date_range`, `invalid_receiving_window`, `outside_receiving_hours`, `receiving_calendar_missing`, `lines_required`, `duplicate_line_no`, `unknown_sku`, `invalid_quantity`, `invalid_price`. Lỗi framework cũng dùng path/type/msg ổn định. Không echo input values/contact/address/PII trong thông báo lỗi/log.

**Response:** một biểu diễn order nhất quán cho GET, POST 201 và các write 200; `date_*` là `YYYY-MM-DD`, `window_*` `HH:MM`, `updated_at` aware timestamp, `qty` numeric, `unit_price` string, `lines` sắp theo `line_no`, snapshot địa chỉ và contact theo thời điểm ghi. POS không tự gửi tọa độ thay server.

### 16.3 D1-C — Version, sửa/hủy sau submit và CFO propagation

PUT full replacement dùng cùng OrderIn + `expected_version` int≥1; optional `refresh_address=false`
chỉ lấy snapshot mới khi true hoặc đổi address/customer reference. No-op giữ version; edit VALIDATED
thành DRAFT, edit SUBMITTED phải validate toàn đơn và vẫn SUBMITTED. Stale version → 409 VERSION_CONFLICT.
Cancel body `{expected_version,reason_code,reason_text?}`: reason_code token chữ thường/số/gạch dưới
(bắt đầu bằng chữ, tối đa 64 ký tự), reason_text tối đa 1000 ký tự printable, bắt buộc nếu code=`other`.
Retry cùng reason, với version trước hủy hoặc version hiện tại, trả cùng CANCELLED/provenance không tăng
version; intent khác không ghi đè provenance. Common order DTO thêm nullable `cancel_reason` và
`cancelled_at`, gồm cả GET feed status=CANCELLED; không trả dữ liệu này như thông báo khách tự do.

- `PUT /orders/{id}`: bắt buộc `expected_version`, compare + row lock; đổi thực tế tăng version/updated_at, identical no-op có thể không tăng. Sai version → **409 `VERSION_CONFLICT`** (mã mới **chỉ áp dụng hợp đồng Source API**); trạng thái không hợp lệ → **409 `ILLEGAL_TRANSITION`**.
- `DRAFT → VALIDATED → SUBMITTED_FOR_PLANNING`; chỉnh đơn VALIDATED → DRAFT, invalidates validation. Chỉnh đơn đã `SUBMITTED_FOR_PLANNING` được phép **nếu toàn bộ nội dung mới validate thành công trong cùng transaction**; giữ status `SUBMITTED_FOR_PLANNING`, tăng source version. PUT lỗi không làm mất đơn khỏi feed.
- `POST /orders/{id}/cancel` từ DRAFT/VALIDATED/SUBMITTED_FOR_PLANNING có `expected_version`, `reason_code` và reason_text bảo đảm an toàn khi `other`; terminal CANCELLED không được sửa/reopen/resubmit; retry cancel không nhân phiên bản/hủy trùng.
- CFO adapter phải đồng bộ các bản ghi `CANCELLED` độc lập với feed SUBMITTED, dùng `source_version` và checkpoint per status. **Chưa duyệt plan:** release/close holds và xử lý state theo transition/audit hợp lệ; Dev 1 phải review/sửa transition table trước vì không được bịa status mới. **Đã APPROVED, chưa DISPATCHED:** `ORDER_CHANGED_AFTER_APPROVAL`, tự chạy `planning_run(kind='replan_suggestion')` và kiểm 5 gate (tồn, công suất/ca kho, xe, tài xế/giờ lái-nghỉ, lịch nhận), **không hold hoặc auto-approve**, không tự giải phóng plan đã committed khi đang gợi ý. Dispatcher duyệt phương án mới với locks và transaction atomic thay thế plan cũ, giữ plan cũ có lý do, hoặc giải quyết ngoại lệ. Source CANCELLED đã approved không tự tạo chuyến mới.
- **Đã DISPATCHED/đang giao:** alert Dispatcher xử lý thủ công, không tự thay chuyến/commit hoặc xóa lịch sử giao hàng. CFO không bao giờ POST/PUT/cancel ngược POS và không tự đảo routing legacy/cfo.

### 16.4 D1-D — Calendar / stock batch / fixed-unit SKU (Q10 owner override)

`GET /stock` (**không phân trang**) trả `200 {as_of, batch_id, item_count, items}`; item chỉ có
`warehouse_code, sku, on_hand, reserved` (số lượng là số JSON, theo **đơn vị tồn kho khai báo của SKU**).
Đó là **batch published hoàn chỉnh mới nhất** (`as_of` cao nhất, rồi `batch_id`), `as_of` là thời điểm chụp
của batch, `item_count` bằng số dòng; batch published rỗng hợp lệ trả `200` với `items=[]` (tồn 0 trong
phạm vi batch). **Không có `physical_stock_pool_id`** hay trường nhóm/alias nào (DEC-SRC-Q10-SKU-001); mỗi batch
tối đa một dòng `(batch_id, warehouse_code, sku)`, trùng khóa làm batch bị từ chối khi publish (không cộng,
không last-row-wins). Không có batch published hoàn chỉnh, hoặc batch mới nhất không qua kiểm tra toàn vẹn
(số dòng/hash/`as_of`) ⇒ **`503 STOCK_UNAVAILABLE`** (DEC-SRC-Q9-ERROR-001), thân lỗi chuẩn kèm
`X-Correlation-ID`, sau bước xác thực `X-API-Key`; không bao giờ trả 200 rỗng thay cho "không biết". Batch
mới lỗi khi đã có batch published cũ: batch lỗi bị rollback hoàn toàn và Source tiếp tục trả batch cũ với
`as_of` thật của nó (CFO phải tự kiểm độ mới). Đọc marker và dòng trong cùng một MVCC snapshot. Dòng tồn
cũ không có `batch_id` (legacy) không bao giờ được phục vụ cho đến khi có batch được publish.

Receiving representation: `/addresses` bổ sung optional nullable `receiving_hours` theo 05 §10.1,
weekday ISO → list `[start,end]` HH:MM. Validation một ngày yêu cầu ngày trong calendar coverage,
working_days và không phải holiday; khung người dùng (nếu có) phải nằm trọn trong một slot nhận hàng.
Thiếu toàn bộ lịch/giờ hoặc ngày ngoài coverage → `receiving_calendar_missing`; ngày đóng/khung ngoài
slot → `outside_receiving_hours`. Đây là lịch nhận nguồn, không thay ca/lịch nhân viên kho hoặc tài xế CFO.

- **Q8 receiving:** lịch ngày làm việc/ngày nghỉ/holiday nguồn theo source market instance, giờ nhận cụ thể theo địa chỉ; thiếu lịch hoặc giờ nhận → validation fail closed. Lịch nhận người mua **khác** lịch Warehouse Manager/tài xế mà CFO kiểm ở safety/capacity.
- **Q9 published batch:** `GET /stock` trả `{as_of,items}` từ **một batch đã hoàn tất và publish atomically**. Batch đủ có thể có **items=[]** và khi đó phải có completeness marker đáng tin để coi là 0 tồn; batch chưa publish/nguồn lỗi **không** tự thành tồn=0. `as_of` không được tính bằng `min/max(per-row as_of)` thay cho batch chung. Chính sách thời điểm stale stock vẫn theo MarketConfig; adapter không cộng bừa row không cùng batch.
- **Q9 Source 503 — DEC-SRC-Q9-ERROR-001 (owner-approved 08/11/2026):** khi **không có bất kỳ batch nào đã publish hoàn chỉnh**, kể cả nguồn chỉ có batch `loading`/`failed`, `GET /api/v1/stock` trả **HTTP 503** với phong bì lỗi chuẩn Source: `{ "error": { "code": "STOCK_UNAVAILABLE", "message": "Stock snapshot is unavailable.", "details": {}, "correlation_id": "<opaque>" } }`, header `X-Correlation-ID`, và xác thực `X-API-Key` như bình thường. **Không** trả `200 items=[]` khi unknown. Ngược lại, snapshot **published complete** có `items=[]` trả `200` (tồn=0 trong phạm vi snapshot). Batch mới lỗi khi vẫn có bản published cũ: chỉ serve latest **published** với `as_of` thật; CFO vẫn kiểm freshness, không tự gia hạn thời điểm. CFO gặp 503 phải báo sync failure/alert, giữ dữ liệu lịch sử để audit nhưng không dùng tồn kho stale/unknown để hứa giao. Mã này **chỉ cho Source API** (không áp dụng `GET /health`, vẫn theo health body riêng), chi tiết OpenAPI/runtime cần PR code và CI.
- **Q10 local/global SKU — thay thế bằng DEC-SRC-Q10-SKU-001 (08/11):** mỗi SKU có đúng **một đơn vị tồn kho chuẩn, cố định**, `on_hand` và `reserved` trên `/stock` dùng đơn vị đó; SKU giữ nguyên đơn vị qua mọi warehouse/batch. Mỗi batch **chỉ có một dòng `(batch_id,warehouse_code,sku)`**; trùng thì reject batch, không cộng/last-row-wins. Đơn bán theo pallet/bao khác chuẩn phải được quy đổi về đơn vị tồn của **cùng SKU** trước khi trừ tồn, không sinh SKU tồn giả. CFO dùng `units_to_base` để đổi sang base unit; không dựng `physical_stock_pool_id`, không suy ra hai SKU cùng tồn chỉ vì số lượng quy đổi bằng nhau. Nếu nhiều local SKU ánh xạ một global product thì chỉ cộng tồn khi **đã xác minh lượng tồn độc lập**; chưa xác minh phải fail closed, giữ dữ liệu cũ ở trạng thái stale/unavailable, không phát hành snapshot partial như complete. API stock Q9 vẫn yêu cầu published complete batch; **mã lỗi `503 STOCK_UNAVAILABLE` đã được owner duyệt riêng theo DEC-SRC-Q9-ERROR-001**, còn các field provenance như `batch_id`/`item_count` và migration cần review kỹ thuật ở PR #101.

- **DTO tồn kho thống nhất giữa Source và adapter CFO (đề xuất kỹ thuật theo DEC-SRC-Q9-ERROR-001 / DEC-SRC-Q10-SKU-001, chờ review Dev 1/Dev 2):** `200 {"as_of": <aware>, "batch_id": <int>0>, "item_count": <int≥0>, "items": [{"warehouse_code","sku","on_hand","reserved"}]}`. Không có `physical_stock_pool_id` hay bất kỳ trường định danh nhóm/alias nào; mỗi `(warehouse_code, sku)` tối đa một dòng, số lượng theo đơn vị tồn kho khai báo của SKU. Adapter CFO **từ chối** (không ghi gì) khi: thiếu `batch_id`/`item_count` (bản cũ `{as_of, items}` không chứng minh được tính đầy đủ), `item_count != len(items)`, `as_of` không có múi giờ, trùng khóa, số không hữu hạn, hoặc có trường lạ (kể cả `physical_stock_pool_id`). `503 STOCK_UNAVAILABLE` là `StockUnavailable`: giữ snapshot trước, không thay bằng rỗng; `200` với `items=[]` chỉ là batch rỗng đã publish đầy đủ. Chuẩn hóa (`backend/app/adapters/stock_batches.py`, hàm thuần; DEC-CFO-STOCK-SCOPE-001 và DEC-CFO-STOCK-INDEPENDENCE-001): chỉ SKU thuộc **phạm vi SKU CFO được định nghĩa trước** (tham số tường minh, không suy ra từ batch) được chuẩn hóa; dòng ngoài phạm vi bị bỏ qua và không bao giờ chặn. Một SKU trong phạm vi chưa ánh xạ/chưa xác nhận, mâu thuẫn đơn vị hoặc `units_to_base` so với ánh xạ đã xác nhận, hoặc lượng không biểu diễn chính xác được trong NUMERIC(12,3) → từ chối **cả** batch, không bao giờ trả kết quả một phần. Mỗi SKU quy đổi **một lần**; nhiều SKU cùng kho cùng một global product chỉ được cộng (sau quy đổi) khi **tất cả** nằm trong một nhóm `verified_independent` (tồn vật lý độc lập đã xác minh), mặc định rỗng = từ chối; các kho không bao giờ gộp. **D1-03/04 owner-approved bổ sung (08/11/2026):** scope SKU CFO chỉ do quản trị viên có thẩm quyền theo **market/pilot** quản lý và phê duyệt, có version, hiệu lực, actor/approver và audit; **không suy scope từ mapping**. Bằng chứng tồn SKU độc lập do Warehouse Manager trong phạm vi kho cung cấp từ kho/WMS, quản trị viên có thẩm quyền duyệt, lưu evidence/provenance, approver, version, hiệu lực và audit. Thiếu/hết hiệu lực/mâu thuẫn thì reject toàn batch CFO liên quan, không publish partial. `scope` và `verified_independent` vẫn là đầu vào tường minh của normalizer; **schema, DTO, endpoint quản trị và cách binding effective version với stock batch chưa chốt**. Dev 1/2 phải đề xuất và review `05/06` + migration/auth/contract tests trước khi bật writer T07.

**Implementation handoff:** Dev 2 source endpoints/DDL/OpenAPI/seed/CSV integration, Dev 1 adapter/stock normalization/cancel-replan/locks, Dev 3 POS error UX. Phải có PostgreSQL multi-instance tests cho equal timestamp, cancellation after submitted/approved/dispatched, submitted edit race, snapshot zero-row, duplicate `(batch,warehouse,sku)`, đơn vị SKU cố định, chuyển quy cách bán, nhiều SKU ánh xạ một global chưa rõ độc lập, và new-version idempotency. **Hợp đồng đã được owner duyệt, code chưa được chứng minh hoàn chỉnh bởi tài liệu này.**

---

## Phụ lục A — Bổ sung hợp đồng phát sinh từ thiết kế UI (`03_UI_UX_Specification.md`)

Các endpoint và trường dưới đây **bổ sung** cho các mục trước; backend phải cung cấp để dựng đủ màn hình.

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/orders/counts` | Số đếm cho chip lọc và huy hiệu menu: `{ "all": 34, "needs_plan": 6, "awaiting_approval": 4, "no_feasible_date": 1, "in_execution": 12, "replan_suggested": 1, "delivered_today": 9, "nav": { "order_queue": 6, "exceptions": 1, "tracking_risk": 2 } }` (theo phạm vi người gọi) |
| GET | `/integration/overview` | Thẻ nguồn: mỗi `entity` có `status`, `rows`, `rejected`, `unmapped` (chỉ `products`: số SKU `pending`, không phải dòng bị loại), `last_run_at`, `data_as_of`, `interval_min` (theo `MarketConfig.sync.interval_min`, mặc định 5); thêm `route_matrix { pairs, fallback_pairs, fetched_at, provider }` và `scheduler { tick_interval_min, last_tick_at, last_tick_status, jobs }` (admin; dispatcher đọc phần `data_as_of`) |
| GET | `/warehouses/{id}/prep-queue?date=YYYY-MM-DD` | Endpoint **chuẩn** của Prep queue (thay cho `/prep-queue?warehouse_id=&date=`): `capacity { booked_min, total_min, free_min, schedule_verified, shifts[{name,start,end,present,useful_hours,share,minutes,booked}], cutoff }` và `orders[{order_id, order_no, lines, weight_kg, handling_mix[{code,name}], work_min, prep_window{start,end}, loading[{trip_id,at,vehicle_code,after_cutoff,loaded}], prep_state ('running'|'paused'|null), status, next_action}]`. Đơn nhiều xe có nhiều dòng loading. |
| GET | `/notifications/{id}` | Bản xem trước đã dựng: `{ template, channel, status, recipient_masked, subject, body_html, body_text, eta_window, suppressed_reason }` (người nhận đã che) |
| GET | `/kpi/diagnostics` | `{ hard_constraint_violations, event_to_alert_latency_s_median }` |

### A.1 M6 Prep queue contract alignment (OWNER APPROVED 09/11/2026 — DEC-M6-PREP-QUEUE-20261109; code/E2E pending)

- **Một nguồn contract:** `GET /api/v1/warehouses/{id}/prep-queue?date=YYYY-MM-DD`; `date` là ngày nghiệp vụ theo `ref.market.timezone` của kho (nếu bỏ qua: ngày hiện tại theo market). Dùng cùng RBAC và warehouse/market scope như §8.2. Đường dẫn `GET /prep-queue?warehouse_id=&date=` trong Phụ lục A cũ không còn canonical; nếu giữ tương thích, phải delegate cùng implementation và cùng shape, không triển khai một endpoint thứ hai với nghiệp vụ khác.
- **Đơn vị:** `share` là JSON number từ 0 đến 1 (`delivery_share`); `present` và `lines` là integer. `booked_min`, `total_min`, `free_min`, `shifts[].minutes`, `shifts[].booked`, `orders[].work_min` là số nguyên JSON theo phút; `useful_hours`, `weight_kg` là JSON number có thể có phần thập phân. **Không** serialize các trường capacity/weight dưới dạng Decimal string (chuỗi decimal chỉ dành cho tiền theo §1). Tất cả các tổng và phần tử ca phải dùng cùng quy tắc làm tròn để đối chiếu được.
- **Thời gian:** `cutoff` là `HH:mm` theo market; `shifts[].start/end`, `prep_window.start/end`, `loading[].at` là ISO 8601 **có offset** vì biểu thị thời điểm/ca cụ thể (hỗ trợ ca qua ngày và DST). UI luôn hiển thị thành giờ 24h theo `location.timezone`, không theo browser; schema `/warehouses/{id}/capacity` tại §13.2 vẫn dùng giờ ca `HH:mm` cho mục đích riêng.
- **Dữ liệu tin cậy:** `capacity.schedule_verified` **bắt buộc boolean**; chỉ `true` khi roster ca chính thức do Warehouse Manager/quản lý có thẩm quyền xác nhận và dữ liệu cần thiết để xác minh công suất của ngày đó đã đủ; không suy từ `expected_staff`, seed hoặc ca tự tạo. Khi `false`, server có thể trả **200 read-only** với `total_min=0`, `free_min=0`, `shifts=[]` (hoặc chỉ ca có provenance rõ, không tính capacity), trong khi `booked_min` vẫn phản ánh đặt chỗ thực đã có nếu xác minh được; UI phải hiện `Capacity not verified` và không trình bày 0 như một kết luận rằng có đủ công suất. Quy tắc không phê duyệt kế hoạch khi thiếu lịch, ca tài xế hoặc duty history **vẫn fail closed**.
- **Tính toán:** `shifts[].minutes` là phút công suất khả dụng ca theo `present × useful_hours × share × 60`, có làm tròn nhất quán; `shifts[].booked` và `capacity.booked_min` là phút đã giữ/đặt thực theo `committed` và `held` trong `/capacity`, không cộng trùng; `free_min=max(0,total_min-booked_min)`. Booked có thể lớn hơn total sau thay đổi lịch; khi đó hiện cảnh báo thiếu công suất, không tạo free âm.
- **Triển khai (backend)** *(R3: `schedule_verified` = có dòng `warehouse_day_capacity` đã xác nhận cho kho/ngày, §19.5; đoạn sau là lịch sử)*: `schedule_verified=true` chỉ khi mọi dòng `hr.employee_shift_schedule` `scheduled` của kho/ngày do quản lý `can_approve` hiệu lực lúc nhập (`assigned_at` theo ngày market) và dùng được; chia `shifts[].booked` theo tỷ lệ phút ca (largest remainder, tổng khớp `booked_min`); `prep_window.start` là `START_PREP` thực tế hoặc `null` (giờ bắt đầu kế hoạch chưa được lưu), `end` là `GOODS_READY` thực tế hoặc `goods_ready_at` kế hoạch; `next_action` ∈ `START_PREP | PREP_RESUMED | GOODS_READY | LOADED | null`.
- **Orders:** chỉ các đơn với plan đã duyệt và thuộc kho/ngày phù hợp; mỗi xe có một phần tử `loading[]`, giữ `loaded` riêng từng trip; `next_action` lấy từ trạng thái/quyền kiểm tra ở server (nullable khi không có hành động), không suy đoán từ UI. Nếu backend **chưa tính được shape đáng tin cậy**, trả lỗi API chuẩn (không đổi stub `409 PLAN_NOT_APPROVABLE` thành `200` có số giả); `200` thiếu roster là trường hợp hợp lệ khác với service chưa tích hợp.
- **Tích hợp:** cập nhật OpenAPI/DTO, UI `resolveTimeZone`, test API contract/role-scope, đa xe, ca qua nửa đêm/DST và thiếu lịch xác minh. PR #129 vẫn Draft cho đến khi phụ thuộc execution/risk/notification và các blocker an toàn được giải quyết; riêng API read-only không được coi là chứng minh toàn bộ M6 đã xong.

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

**Cấu hình thêm vào `MarketConfig` (`04` mục 8):** `"routing": { "allow_fallback": true, "fallback_retry_min": 60 }`. `fallback_retry_min` (> 0, phút): route fallback đã lưu trong `route_matrix` chỉ được dùng lại trong khoảng này; quá hạn thì job chuẩn bị route gọi lại ORS — thành công thì thay bằng route `ors`, thất bại thì lưu fallback mới với `computed_at` mới (giới hạn tần suất gọi lại). Route `ors` được dùng lại như cũ. Khi `false`, cặp (kho, điểm giao) thiếu trong `route_matrix` làm ứng viên bị loại với mã `ROUTE_DATA_UNAVAILABLE` (check `site_date`).

**Tên hành động nhật ký hiển thị ở UI** dùng đúng mã trong `04` mục 10 (`ALT_SELECTED`, `CRITERIA_CHANGED_RERUN`, `MANUAL_PLAN_CREATED`, `MAPPING_CONFIRMED`, `NOTIFICATION_SENT`, …); các mã khác trong ảnh thiết kế chỉ là ví dụ.

## 17. Owner-approved API contract alignment — 2026-11-09

Source: [27 owner-approved decisions](decisions/OWNER_CROSS_WORKSTREAM_APPROVED_20261109.md); `DEC-OWNER-20261109` in `ASSUMPTIONS.md`. **This is a target contract; routes/migrations not shown as implemented must have their own reviewed PR.**

- **API-1/2:** `checks.stock|preparation|truck|site_date|safety` use `{passed: boolean, code: string, detail?: object}`; missing/unknown is not true. `rejected_candidates[]` is flat `{warehouse_id, vehicle_code, failed_check, code, detail}`; no nested warehouse/vehicle name is guaranteed. The live `vehicles[]` DTO has `vehicle_id`, `driver_employee_id`, and nested **public** `vehicle: {id,code,name,capacity_kg,capacity_m3}` (capacity Decimal strings), but **not** nested driver name. Backend does not return `promise_window_preview`; UI cannot fabricate it. Current approval rejects `drivers` override (changing a driver requires Plan Again), never approves `replan_suggestion` or an expired/missing hold, and requires agreed matching `date_negotiation_id` if proposed date differs. Approval still depends on verified D7 safety evidence.
- **S1–5:** future stock-scope/evidence admin routes must require active market-specific grant and separation of creator/approver; warehouse manager supplies WMS proof but cannot approve it. Version after approval by batch `as_of`, expected warehouse × SKU coverage (missing row = reject CFO stock write, zero only if explicit), independence evidence ≤30 pilot days with automatic invalidation on mapping/unit/scope changes. No unreviewed API names/DDL paths are authorized by the policy alone; T07 stock writer stays gated until completion.
- **T18-1–3:** never count transfer inbound as available unless destination WMS proof shows inclusion; `as_of` alone is insufficient. Fallback lead must be configured/approved with provenance; cancellation/reversal after source confirmation stays `409 ILLEGAL_TRANSITION`.
- **D7/M6:** trusted 56 market-local daily coverage facts (off-duty vs absent), qualified verifier, independent official shift, 11h rest, licence/Regulation 561/mass checks; one delivered POD per `trip_stop` (forward DB migration pending).
- **G1–5** *(R3: thay bởi §19.3 — gán luân phiên, vị trí do tài xế bấm, xóa khi đơn kết thúc)*: only active assigned primary Dispatcher can read current trip GPS, within actual duty; individual driver notice+ack and privacy/legal proof before real-worker collection. Device upload ≤100 valid positions every 30 min in authorized trip/shift; purge raw points at earliest terminal/duty boundary. Authenticated simulator separate; no 30-day raw retention.
- **N1–5:** Dispatcher-approved DELAY `start/end/version`; agreed date negotiation for changed promised date; fixed template version and typed allowlist variables, atomic event/risk/queued notification outbox in caller transaction, external send only after commit, same retry cap and Mailpit/test recipients.
- **KPI-1/2:** retain all 10 existing published keys: `planning_time_min`, `on_time_rate`, `labour_hours_per_delivery`, `km_per_delivery`, `prep_error_min`, `eta_error_min`, `plan_acceptance_rate`, `failed_delivery_rate`, `capacity_utilisation`, `manual_plan_count`. Unsupported diagnostic keys `hard_constraint_violations`, `event_to_alert_latency_s_median` remain `null` (no guessed 0). Planning cohort date = approved date; delivery cohort = delivery/completion date; capacity cohort = warehouse `work_date`, all in market local timezone. Do not invent other metric cohort formulas.

**Implementation status:** PR #136 was merged and needs a new Dev 3 fix PR for UI/backend mismatches. #121/#127/#129/#137 and M8 need separate implementation reviews, database/API tests and CI. This contract is not evidence those features operate end-to-end.

### 17.1 GPS retention amendment and D8 clock times — 2026-11-09

**Owner-approved specific amendments:** [DEC-GPS-RET-20261109 and DEC-D8-OPS-20261109](decisions/DEC_GPS_7D_AND_D8_REVIEW_TIMES_20261109.md). Stop collecting/revoke live read at trip/duty end; keep only previously lawfully captured GPS **up to seven days**, for case-restricted review with reason/access audit, then erase. This does **not** authorize adding unreviewed historical read APIs or showing a closed trip's GPS to an ordinary Dispatcher. The existing `trip_end_delete`/zero-day config and terminal purge assumptions require reviewed new DB/API/service contracts and privacy/legal/DPIA signoff for real employee data. **Operational review 07:00 and 13:00 Europe/Stockholm** is approved; **job cadences are also approved for staging/demo only** by DEC-D8-STAGING-SCHEDULE-20261109. Production job activation, D6 hosting/SLA/cost and internal tick DTO remain unapproved.

**ASM-WMS-RESERVATION-20261109 (approved assumption only):** Owner assumes legacy WMS supports stock reservation; WMS reservation reduces **available-to-promise**, not physical on-hand until actual WMS issue. CFO must not double-subtract WMS-reflected reservations. CFO→WMS reserve/release writes would be a **new explicit exception to DEC-WMS-READONLY-20261109**, *not yet owner-approved*: do not expose or call such write endpoints until the real WMS read/write contract, ACK/idempotency, cross-system failure recovery and owner authorization are reviewed. [Decision assumption](decisions/ASM_WMS_RESERVATION_ASSUMED_20261109.md).

**DEC-WMS-REVERSE-SKU-20261109 (yêu cầu có điều kiện):** Khi CFO→WMS reserve/release được Owner duyệt riêng, phải gửi **SKU gốc WMS** theo kho/market, không gửi mã `global_product_id/global_code` của CFO. Giữ `order_line.local_sku` từ POS, mapping confirmed+version; nếu POS SKU khác WMS SKU phải có mapping riêng đã được xác minh. Global→local có thể 1:n: chỉ dùng nguồn SKU có chứng cứ phân bổ đúng dòng đơn/kho, không chọn đại hoặc cộng pool suy đoán. Quy đổi số lượng theo đơn vị tồn WMS đã được xác nhận, không tự làm tròn; ACK WMS phải khớp mã/kho/qty/idempotency. Thiếu/mơ hồ/không đủ thông tin ⇒ chặn request. **Chưa phê duyệt quyền ghi WMS hay endpoint mới.** [Biên bản](decisions/DEC_WMS_REVERSE_SKU_FOR_RESERVATIONS_20261109.md).


### 17.2 WMS reservation confirmation and CFO stock refresh — owner-approved target workflow

[DEC-WMS-RESERVE-SYNC-20261109](decisions/DEC_WMS_RESERVE_SYNC_20261109.md) **overrides the general WMS GET-only policy for one narrow, as-yet-unimplemented business action**. CFO reads complete fresh WMS stock before plan; on authorized Sales/Dispatcher plan confirmation it proposes a WMS **reserve** in original verified WMS SKU and stock units (not CFO global ID), with order-line, market/warehouse, external idempotency and mapping/source versions. WMS must atomically reject insufficient stock across systems or acknowledge accepted reservation ID/SKU/qty/version. Until positive ACK, do not return or display final guaranteed approval. After ACK CFO must **immediately refresh/re-read WMS inventory** and update its stock view/order state; periodic 5-minute polling is follow-up only. WMS decreases available by reservation but does not change physical on_hand until warehouse issues goods. Never subtract a WMS-included reservation twice. Missing/stale refresh, partial ACK, timeout or uncertain WMS state ⇒ conservative pending protection/status lookup or fail closed, not fabricated success.

**OpenAPI endpoint/path/DTO, external auth, release/adjust/consume lifecycle, cross-service ACK compensation and transactional patterns require Dev 1/2 contract review and deployment approval.** No actual WMS reserve endpoint, CFO API or code is declared live by this docs update; no WMS physical stock write, POS mutation or CFO transfer reconciliation. Existing Sales approval 5-gate/hold restrictions remain binding.

**E1 disposable demo implementation (migration 0017, PR #224):** the existing `POST /plans/{id}/approve` can use a separate loopback synthetic WMS only with `APP_ENV=test`, `DEMO_DISPOSABLE=1`, an approved demo clock, and explicit `WMS_RESERVATION_MODE=simulated`; the default is disabled and production refuses this mode. The endpoint checks role/market, current order/plan versions, live hold, resources and five gates before committing a durable intent. It sends reserve outside DB locks, stores the verified ACK in a second transaction, then ingests a signed post-ACK batch through T07's scope gate under origin `wms_synthetic`. The final approval transaction checks reservation ID, request, ACK, signed batch inclusion, accepted write and ingest run, current snapshots, and resources before committing order/trips/audit/CONFIRMED together. Retry uses the same immutable WMS request key and checks status before reserve. This synthetic flow does not authorize a production WMS write contract.


### 17.2 Additional owner-approved contracts — CS, Prep Queue, Stock Admin and D8 staging (2026-11-09)

[Decision record](decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md) and [ASSUMPTIONS entries](ASSUMPTIONS.md): DEC-CS-SEARCH, DEC-CS-PRIVACY, DEC-M6-PREP-QUEUE, DEC-STOCK-GRANT-CONTROL, DEC-D8-STAGING-SCHEDULE (all 20261109). **Only** these five proposals are newly approved.

- **CS search/privacy:** §5.3–5.4 above now require `q` matching contact phone and a CS-specific masked/allowlisted server DTO, no private delivery/access information. Dev 1/3 must test actual API and not label mock-only contact logging as production.
- **Prep Queue:** Appendix A.1 is now an **approved target contract**; backend #129/#159 and UI #154/#160 still require harmonization/real-DB tests before merge.
- **Stock Admin:** only **Owner-delegated System Admin** may issue and revoke market-specific Stock Admin grants (first and future), no self-grant; Dev 1/2 must review delegation record, audit and migration. Does not grant physical WMS access.
- **D8:** stage/test approved proposal job cadence on synthetic data only. `attendance_gen` disabled; no prod cron/worker/hosting, no real notifications or GPS. Internal tick security/DTO, new codes and job runtime remain subject to review.


## 18. Owner-approved integration decisions Q2–Q10 — 09/11/2026

[DEC_INTEGRATION_UNBLOCK_Q2_Q10_20261109](decisions/DEC_INTEGRATION_UNBLOCK_Q2_Q10_20261109.md) and `ASSUMPTIONS.md` establish the **target behavior** below; changing existing routes, DTOs or migrations still requires Dev 1/2/3 contract review, implementation and tests. **The Owner alone merges code PRs after they are Ready, reviewed, mergeable and checks pass.**

- **Q2 WMS demo:** simulated reserve/status/release permitted in staging only, explicit `simulated` provenance/indicator; real port remains disabled. No WMS physical stock write.
- **Q3 T18:** CFO may request or suggest transfer; existing `/transfers/{id}/confirm-source` and `/receive` descriptions are **superseded for physical confirmation/stock authority**. Dev 1/2 must reconcile or disable such effects in #127; real WMS alone records outbound/inbound/receipt.
- **Q4 Date negotiation:** contact `agreed` is **not** date mutation. An authorized Dispatcher explicitly applies a verified agreement with version/concurrency/audit, then starts a new plan (all five gates). Exact endpoint/DTO and POS read-only boundary need reviewed update, **not an invented endpoint implemented from this note**.
- **Q5 GPS history:** only explicitly case-authorized privacy/compliance reviewer may see retained points (max 7 days), with case ID/reason/trip/market access audit and legal/privacy clearance. Regular Dispatcher live role is not historical authorization.
- **Q6 KPI:** default reporting window **30 days**, maximum **366 days**; multi-market System Admin selects a concrete market; use local market timezone/cohort rules. Preserve 10 KPI keys and unknown diagnostics `null`. Review request parameter/date boundary specification before coding.
- **Q7 M6:** `prep_window.start` is actual persisted `START_PREP` aware ISO instant, or **`null`** before START_PREP. Not a planned start. Implement in backend/frontend DTO with nullable schema/tests.
- **Q8 Demo seeds:** expected golden scenario outputs stay; synthetic input corrections need independent tests, never override fail-closed.
- **Q9 CS phone search:** existing GET `q` requires TLS, scoped/rate-limited backend, raw query/phone suppression in server/proxy/APM/access/analytics/error logs and `Referrer-Policy: no-referrer`. **A GET URL may still remain in browser history/network/proxy traces**; stronger URL privacy would require an independently approved POST search contract.
- **Q10 D8:** staging/manual triggers only using existing resources; no real customer notifications, actual worker GPS, production cron/hosting or paid worker. D8 cadence proposals approved only for staging.

## 19. Round 3 contract changes — DEC-R3 (2026-11-18, owner-approved; code pending)

> Nguồn: [DEC-R3-01…14](decisions/DEC_R3_SCOPE_CRM_20261118.md); DDL ở `05` mục 13. Mục này **thắng** các mục cũ mâu thuẫn
> (§3, §6.3a, §6.6, §8.1, §9, §11, §13.2, §14). Không thêm mã lỗi mới: chỉ dùng mã đã có ở §1.1. Chưa có code cho mục này.

### 19.1 Ma trận quyền thay đổi

| Nhóm endpoint | dispatcher | sales | warehouse | driver | customer_service |
|---|---|---|---|---|---|
| Lập kế hoạch, **đổi tiêu chí/chạy lại** (`POST /orders/{id}/plan` có body) | **W** | **W** (đơn cửa hàng mình, trước duyệt) | — | — | — |
| Duyệt rank 1–3 (`POST /plans/{id}/approve`) | **W** | **W** (đơn cửa hàng mình; rank 2–3 bắt buộc `reason_code`) | — | — | — |
| Thương lượng ngày (`/orders/{id}/date-negotiations`, apply agreed date) | **W** | **W** (đơn cửa hàng mình, trước duyệt) | — | — | — |
| Kế hoạch tay, override | **W** | — (403) | — | — | — |
| `POST /orders/{id}/replan` (mọi `scope`), `POST /orders/{id}/cancel` sau duyệt | **W** | — (403) | — | — | — |
| Gửi/bỏ `DELAY` | **W** | — (403) | — | — | — |
| `POST /trips/{id}/positions` (vị trí tài xế bấm gửi), sự kiện `DRIVER_INCIDENT` | — | — | — | **W** (chuyến mình) | — |
| Xem dòng vị trí gần nhất (`GET /gps/live`) | R **chỉ chuyến được gán cho mình** và đang `on_road` | — | — | — | — |
| Bàn giao chuyến (`POST /trips/{id}/handover`) | **W** (trong market) | — | — | — | — |
| Sự kiện kho `PREP_PAUSED`, `PREP_RESUMED` | không còn hỗ trợ | | | | |
| Contact log CS (§11) | không mount → `404 NOT_FOUND` | | | | |
| Công suất ngày (`/warehouses/{id}/day-capacity`) | R | — | **W** (kho mình, `can_approve`) | — | — |
| Chuyển kho (`/orders/{id}/transfer-suggestions`, `/transfers/*`) | không mount (`404`) mọi vai trò (DEC-R3-15) | | | | |
| Ghi dữ liệu quản trị (`POST /employees`, `/users*`, `POST /vehicles`, `/markets/{code}/config`, `/warehouses/{id}/shift-templates`, `/absences`) | không mount (`404`); dữ liệu từ seed/file cấu hình (DEC-R3-15) | | | | |

Sales gọi trên đơn cửa hàng khác → `404 NOT_FOUND`; gọi hành động chỉ của Dispatcher → `403 FORBIDDEN`. Quy tắc "đơn đặt trước chưa duyệt tranh nguồn lực chưa chứng minh đủ → `409 PLAN_NOT_APPROVABLE`, chuyển Dispatcher" giữ nguyên cho Sales. Dispatcher đọc được mọi đơn Sales đã duyệt (`decision_log.actor_role = 'sales'`).

### 19.2 `POST /plans/{id}/approve` (thay §6.3a)

```json
{ "reason_code": "customer_prefers_earlier_slot", "reason_text": "…" }
```
- Rank 1: `reason_*` tùy chọn. Rank 2–3: thiếu `reason_code` → `422 REASON_REQUIRED` (cả hai vai trò).
- **Không còn `accept_tight`** cho mọi vai trò: phương án qua đủ 5 gate là duyệt được, kể cả `reserve_class = tight`; trường `accept_tight` trong request bị bỏ qua. `reserve_class` vẫn được tính để xếp hạng và theo dõi rủi ro, không phải điều kiện duyệt. Phương án nhiều xe được phép cho cả hai vai trò.
- Các lỗi còn lại như §6.3: `HOLD_EXPIRED`, `RESOURCE_CONFLICT`, `IDEMPOTENCY_CONFLICT`. `decision_log PLAN_APPROVED` ghi `actor_role`, `rank`, `reason_code`.

### 19.3 Sự kiện thực thi (thay một phần §8.1)

| `event_type` | Ai | Điều kiện | `payload` |
|---|---|---|---|
| `START_PREP` | warehouse | `APPROVED` → `PREPARING` | `{ "crew_size": 3 }` |
| `GOODS_READY` | warehouse | `PREPARING` → `GOODS_READY`; `prep_actual_min = GOODS_READY − START_PREP` | `{}` |
| `PREP_PAUSED`, `PREP_RESUMED` | — | → `422 VALIDATION_ERROR` (`details.reason = "event_not_supported_r3"`) | — |
| `DRIVER_INCIDENT` | driver | chuyến của mình đang `on_road`; không đổi trạng thái đơn | `{ "trip_id": 930, "reason": "traffic_or_accident", "note": null, "position": { "lat": 57.70, "lon": 11.97, "accuracy_m": 25, "recorded_at": "…" } }` (`position` tùy chọn) |
| `DELIVERED` | driver | theo chuyến, như §8.1; **`position` bắt buộc** | `{ "trip_id": 930, "recipient_name": "…", "position": { … } }` |
| `FAILED` | driver | theo chuyến, như §8.1; **`position` bắt buộc** | `{ "trip_id": 930, "failure_reason": "customer_absent", "note": "…", "position": { … } }` |

**Vị trí tài xế (DEC-R3-01):**
- `POST /trips/{id}/positions` với **một điểm** `{ "lat", "lon", "accuracy_m", "recorded_at" }`, `Idempotency-Key` bắt buộc, `source='driver_tap'`. Không có chu kỳ, không gửi lô, không hàng đợi offline. Chỉ tài xế của chuyến, chuyến `on_road`, `recorded_at` trong khung khả dụng của tài xế (`05` §13.3); ngược lại `404` (không phải chuyến mình) hoặc `409 NOT_ON_TRIP`.
- `DELIVERED`/`FAILED` thiếu `position` → `422 VALIDATION_ERROR` (`details.reason = "position_required"`); không có đường xác nhận giao xong khi không có vị trí. Server ghi một dòng `vehicle_position(source='driver_completion')` và `proof_of_delivery.site_distance_m` trong cùng transaction; tọa độ không vào payload milestone, audit hay thông báo.
- `DRIVER_INCIDENT`: `reason ∈ {vehicle_breakdown, traffic_or_accident, site_inaccessible, other}` (`other` cần `note`); luôn tạo alert `DRIVER_INCIDENT` cho Dispatcher (`level=critical` nếu `vehicle_breakdown`, ngược lại `warning`). Có `position` → ghi `vehicle_position(source='driver_incident')` và tính lại ETA; `vehicle_breakdown` → không tính ETA mới, alert ghi "ETA không xác định"; không tự lập lại kế hoạch.
- Mỗi lần nhận vị trí: service gọi `RoutingProvider` (ORS, fallback Haversine × 1,3 ở 50 km/h gắn nhãn ước lượng) để lấy `remaining_km`/`remaining_min` tới điểm giao, lưu vào dòng vị trí, rồi gọi `RiskService.recalculate(trigger="position")`. Engine không gọi provider.
- **Không có bản đồ.** `GET /gps/live` trả cho Dispatcher các chuyến `on_road` có `assigned_dispatcher_employee_id` = chính mình, mỗi chuyến **một dòng**: `{ "trip_id", "order_id", "vehicle_code", "last_position": { "lat", "lon" } | null, "remaining_km", "updated_at", "forecast_eta", "risk": {status, color}, "open_incident": reason | null }`; giao diện hiển thị "Vị trí gần nhất · Giờ cập nhật · ETA". `GET /trips/{id}/positions` (danh sách điểm) không còn mount. Chuyến kết thúc → không còn trong danh sách. Chưa gán Dispatcher → không ai thấy. Khách, CS, Sales: luôn `403`.
- **Gán luân phiên** (`05` §13.1): khi duyệt kế hoạch, mọi chuyến của đơn nhận cùng một Dispatcher theo vòng. `POST /trips/{id}/handover` `{ "to_employee_id": 42, "reason_text": "…" }` (Dispatcher trong market, người nhận phải `in_rotation`), audit `TRIP_DISPATCHER_HANDOVER`.
- **Xóa tọa độ** khi đơn `DELIVERED`/`CANCELLED`; đơn `FAILED` chậm nhất 7 ngày. Không có API đọc lịch sử vị trí (thay §9 và §17.1 về lịch sử theo case).

ETA (pure engine `forecast`): gốc = `depart_actual_at` (DISPATCHED) + thời gian tuyến của chuyến; có vị trí mới → `recorded_at` + `remaining_min` + thời gian dỡ hàng kế hoạch. ETA đơn = ETA muộn nhất trong các chuyến chưa kết thúc. Mỗi lần tính lưu một `eta_forecast`. **ETA chỉ tính lại khi có sự kiện mới** (duyệt, mốc kho, `DISPATCHED`, vị trí tài xế gửi, `DRIVER_INCIDENT` có vị trí, `DELIVERED`/`FAILED`, nguồn sửa đơn); không có trigger theo chu kỳ (`morning_check`). Job quá hạn tạo alert `OVERDUE` cho Dispatcher khi đã quá ETA **30 phút** mà chưa có `DELIVERED`/`FAILED`, hoặc mốc kho quá 30 phút; không ghi `eta_forecast` mới. KPI 5 so ETA tại `DISPATCHED` với giờ POD.

`FAILED` và `VEHICLE_ISSUE` **không** tạo `replan_suggestion` (thay §6.6 và đoạn cuối §8.1):
- `FAILED` theo chuyến: lưu POD `failed`. Khi **mọi chuyến của kế hoạch đã kết thúc và có ít nhất một chuyến failed** → đơn `FAILED` qua `transition()`, email `FAILED` cho khách, alert `DELIVERY_FAILED` (`level=critical`, `target_roles={dispatcher}`, `dedupe_key = 'DELIVERY_FAILED:<order_id>:<plan_id>'`, `details.trips = [{trip_id, result, failure_reason}]`).
- `VEHICLE_ISSUE`: chỉ alert `EXCEPTION` kèm danh sách đơn đã duyệt dùng xe đó.

### 19.4 Xử lý sau thất bại (Dispatcher)

`POST /orders/{id}/replan` (mở rộng §5 bảng hành động):
```json
{ "scope": "remaining", "reason_code": "vehicle_breakdown", "reason_text": "…" }
```
- `scope ∈ {full, remaining}`, mặc định `full` (hành vi cũ). `remaining` chỉ hợp lệ khi đơn `FAILED` và có ít nhất một chuyến `delivered`; ngược lại `409 ILLEGAL_TRANSITION`.
- Một transaction: tính `remaining_lines` (`05` §13.4), đóng kế hoạch cũ như §5, đơn → `SUBMITTED`, tạo `planning_run(kind='remaining_replan', remaining_lines)` và chạy engine **chỉ** với các dòng/số lượng còn lại; ghi `ORDER_REPLAN` (before/after, `scope`). POD đã giao giữ nguyên.
- Hẹn giao lại khi khách vắng: dùng §6.5 (ghi thỏa thuận) rồi apply agreed date → planning mới. Hủy: `POST /orders/{id}/cancel` (Dispatcher, lý do bắt buộc).
- Không có đường nào tự chạy planner sau `FAILED`/`VEHICLE_ISSUE`.

### 19.5 Công suất kho theo ngày (thay §13.2)

`GET /warehouses/{id}/day-capacity?date=YYYY-MM-DD` · `PUT /warehouses/{id}/day-capacity` (`Idempotency-Key`):
```json
{ "date": "2026-11-20",
  "shifts": [ { "shift_code": "AM", "start": "07:00", "end": "15:00", "headcount": 8, "productive_hours": 7.0 },
              { "shift_code": "PM", "start": "15:00", "end": "23:00", "headcount": 5, "productive_hours": 7.0 } ],
  "change_reason": null }
```
- Phản hồi thêm `confirmed_by`, `confirmed_at`, `labour_cap_hours`, `schedule_verified`. PUT thay toàn bộ ca của ngày đó (đóng dòng cũ, thêm dòng mới).
- Sửa ngày đã có dữ liệu hoặc ngày đã qua mà thiếu `change_reason` → `422 REASON_REQUIRED`. Ngoài kho mình → `404`; thiếu `can_approve` → `403`.
- `GET /warehouses/{id}/capacity` giữ đường dẫn, `shifts[]` trả `{shift_code, start, end, headcount, productive_hours}` thay cho `present/useful_hours`. `/warehouses/{id}/attendance` không còn mount (`404`).

### 19.6 Dữ liệu tài xế từ đội quản lý tài xế (bổ sung §16)

Nguồn (giả lập trong `source-<cc>`, cùng quy ước API key/`updated_since`/phân trang như §16.1):
```json
// GET /fleet/driver-availability?updated_since=…
{ "items": [ { "source_ref": "AV-2026-11-20-071", "employee_no": "SE-D-071", "work_date": "2026-11-20",
               "available_from": "2026-11-20T06:00:00+01:00", "available_to": "2026-11-20T16:00:00+01:00",
               "max_driving_min": 540, "verified_by": "Fleet desk SE", "verified_at": "…", "superseded": false } ],
  "next_cursor": null }
// GET /fleet/driver-eligibility?updated_since=…
{ "items": [ { "source_ref": "EL-071-C", "employee_no": "SE-D-071", "vehicle_code": null, "licence_class": "C",
               "verified_until": "2027-03-31", "verified_by": "Fleet desk SE", "verified_at": "…", "revoked": false } ],
  "next_cursor": null }
```
CFO upsert theo `(source, source_ref)`; dòng sai (thiếu xác minh, khung giờ ngược, nhân viên không khớp) vào reject log, không đoán. Gate tài xế theo `05` §13.3; thiếu dữ liệu → reason code `DRIVER_NOT_VERIFIED` trong kết quả planning (không phải mã lỗi HTTP).

### 19.7 Thông báo (thay một phần §10)

- Kênh duy nhất `email`. `DISPATCHED` gửi một lần khi chuyến đầu tiên của đơn xuất phát, bật/tắt bằng `NOTIFY_DISPATCHED_ENABLED` (tắt → `suppressed`, `skipped_reason='SKIPPED_FLAG_DISABLED'`).
- `FAILED` luôn gửi khi đơn chuyển `FAILED`. `DELAY` giữ nguyên quy tắc Dispatcher (§10).
- CFO lấy email của khách và lưu email đích trong thông báo. DB không lưu kênh gửi hoặc sở thích kênh. Response giữ trường `channel` suy từ đích: `email` nếu có email, `null` nếu không có.
- Khách không có email → `suppressed`, `SKIPPED_NO_CHANNEL`, `recipient = NULL`. SMS lịch sử dang dở bị bỏ qua khi gửi.

### 19.8 KPI (thay §14)

```json
// GET /kpi/summary?from=&to=&warehouse_id=&store_id=  → 200
{ "period": { "from": "2026-11-01", "to": "2026-11-30" },
  "metrics": {
    "planning_time_min":    { "value": 4.2, "baseline": 15.0, "by_path": { "sales": 2.1, "dispatcher": 6.0 } },
    "on_time_rate":         { "value": 0.94 },
    "plan_acceptance_rate": { "value": 0.81, "by_path": { "sales": 0.88, "dispatcher": 0.72 } },
    "manual_intervention_rate": { "value": 0.09, "baseline": 0.35 },
    "eta_error_min":        { "median": 18, "p90": 52, "target": { "median": 20, "p90": 60 } } },
  "supporting": {
    "order_to_commit_min": { "by_path": { "sales": 6, "dispatcher": 95 } },
    "counter_commit_rate": { "value": 0.42 },
    "manual_plan_count":   { "value": 6 } } }
```
- Định nghĩa theo DEC-R3-03. `manual_intervention_rate` = đơn có kế hoạch tay hoặc override ÷ đơn được cam kết. `eta_error_min` = |ETA dự báo gần nhất trước `DISPATCHED` − giờ POD| theo chuyến; không có `baseline`.
- `GET /kpi/daily?metric=` chỉ nhận 5 key trên. `PUT /kpi/baseline/eta_error_min` → `422 VALIDATION_ERROR`. Các metric cũ (`labour_hours_per_delivery`, `km_per_delivery`, `prep_error_min`, `failed_delivery_rate`, `capacity_utilisation`) không còn được trả về.

> §19.9 (CRM) và §19.10 (Đan Mạch, AI theo lô) đã bị gỡ ngày 19/11/2026 do Owner hủy DEC-R3-12 và DEC-R3-14.

### 19.11 Đơn hàng & doanh thu — nhóm trạng thái (DEC-R3-15)

`GET /revenue/order-status?view=store|warehouse&location_id=&from=&to=` — cùng quyền, tham số và lỗi với `/revenue/*` (§14.1, §3.1): Business owner mọi nơi; owner cửa hàng/kho chỉ nơi mình (nơi khác → `404`); admin tất cả; vai trò khác → `403`; `view` không khớp loại địa điểm → `422`; kỳ tối đa 366 ngày (vượt → `422`).

```json
{ "period": { "from": "2026-11-01", "to": "2026-11-30" }, "view": "store", "location_id": 21, "currency": "SEK",
  "total": { "orders": 116, "amount": "1569100.00" },
  "groups": [
    { "key": "approved", "statuses": ["APPROVED","PREPARING","GOODS_READY","LOADED"], "date_basis": "committed_date", "orders": 30, "amount": "402100.00" },
    { "key": "in_transit", "statuses": ["DISPATCHED"], "date_basis": "committed_date", "orders": 6, "amount": "88400.00" },
    { "key": "completed", "statuses": ["DELIVERED"], "date_basis": "committed_date", "orders": 72, "amount": "1012600.00" },
    { "key": "failed", "statuses": ["FAILED"], "date_basis": "committed_date", "orders": 3, "amount": "41000.00" },
    { "key": "cancelled", "statuses": ["CANCELLED"], "date_basis": "cancelled_at", "orders": 5, "amount": "25000.00" } ] }
```
- Bốn nhóm đầu tính vào kỳ theo `committed_date`. Nhóm `cancelled` tính theo ngày hủy = thời điểm chuyển sang `CANCELLED` (`ops.order_transition`/`decision_log ORDER_CANCELLED`), gồm cả đơn hủy trước khi duyệt; không dùng `committed_date` vì hủy đơn xóa trường này (`05` §6). Ngày quy theo timezone market.
- Đơn chờ duyệt (`SUBMITTED`, `PLANNED`, `NO_FEASIBLE_DATE`) và `BLOCKED_UNMAPPED_SKU` (legacy) **không** nằm trong báo cáo. Mỗi đơn chỉ thuộc một nhóm theo trạng thái hiện tại; `total` = tổng 5 nhóm.
- `amount` = tổng `total_amount` của đơn trong nhóm (giá trị đơn, **không** phải doanh thu ghi nhận). Doanh thu ghi nhận vẫn lấy từ `/revenue/summary` theo ngày giao thực tế (BR-KPI-01).
- Không trả tên, điện thoại, địa chỉ khách. Góc nhìn store và warehouse không cộng nhau.
- `/revenue/orders` nhận thêm `status_group=<key>` để liệt kê đơn của một nhóm (phân trang, cùng quy tắc trường như hiện tại).
