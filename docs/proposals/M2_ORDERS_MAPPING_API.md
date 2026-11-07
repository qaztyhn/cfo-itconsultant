# Đề xuất hợp đồng — API đơn hàng và ánh xạ SKU (M2, Dev 1)

> **Trạng thái: ĐỀ XUẤT — chờ nhóm review. Chưa phải hợp đồng.** Không có mã triển khai đi kèm. Khi nhóm chốt,
> nội dung được đưa vào `06` mục 5 và 12 cùng `CHANGELOG`; mã và test nằm trong cùng PR triển khai (`09` mục 6, 14).
> Tác giả: Dev 1. Ngày: 2026-11-07.
> Liên quan: `10` M2 Dev 1 ("API orders, counts, timeline, mapping"), US-PRD-01..05, US-ORD-02/03.
> Đã có tầng service: qaztyhn/cfo-itconsultant#34 (`transition`, `prepare_for_planning`) và
> qaztyhn/cfo-itconsultant#36 (`confirm`/`reject`).

## 0. Vì sao cần đề xuất

| Nội dung | `06` đã có gì | Còn thiếu |
|---|---|---|
| `GET /orders/{id}` | Schema đầy đủ (mục 5.1) | Phạm vi cho từng vai trò; các trường của "bản rút gọn" |
| `GET /orders` | Bộ lọc (mục 5) | Schema phần tử, sắp xếp mặc định, phạm vi |
| `GET /orders/counts` | Hình dạng JSON (Phụ lục A) | Mỗi bucket gồm những trạng thái nào |
| `GET /orders/{id}/timeline` | Mô tả (mục 5; US-ORD-03) | Schema phần tử; CS thấy gì |
| `/mapping/tasks*`, `/products/local` | Đường dẫn, payload confirm (mục 12.1) | Schema phản hồi; phản hồi của confirm/reject |

Theo `09` mục 14.3–14.4, đây là quyết định về hợp đồng và phân quyền nên Dev 1 **không tự chốt**.

## 1. Các quyết định cần nhóm chốt

| # | Câu hỏi | Phương án đề xuất (A) | Phương án khác |
|---|---|---|---|
| **Q5** | Phạm vi đơn theo vai trò (`06` §3 hàng "Đơn") | Mục 2 | **B.** Kho chỉ thấy đơn đã duyệt (`approved_plan_id`) |
| **Q6** | Bản rút gọn cho sales / CS / driver | Mục 3 | **B.** Sales nhận bản đầy đủ (chỉ đọc) |
| **Q7** | Schema `GET /orders` và bucket của `/orders/counts` | Mục 4 | Sửa tên trường / cách chia bucket |
| **Q8** | Schema `/mapping/tasks*`, `/products/local`, phản hồi confirm/reject | Mục 5 | — |
| **Q9** | Schema timeline; CS thấy gì | Mục 6 | **B.** CS không xem timeline (ma trận §5 chỉ ghi "dispatcher, warehouse, CS, admin") |
| **Q10** | Phản hồi `GET/PUT /warehouses/{id}/attendance`, `GET /warehouses/{id}/capacity` (M3) | Mục 7 | Sửa tên trường |
| **Q11** | `attendance_gen`: kho có nhiều ca/ngày thì nhân viên vào ca nào (`05` không có bảng gán người–ca) | **A.** Mọi người vào ca sớm nhất của ngày. **B.** Chia đều theo `expected_staff` của từng ca, theo `employee_no`. **C.** Thêm cột/bảng gán ca (thay đổi `05`) | Ảnh hưởng công suất theo ca; Dev 1 không tự chốt |

Quy tắc chung (giống `06` v1.3 mục 13.1 đã duyệt):
- Kiểm vai trò và phạm vi **ở máy chủ**. Vai trò không có quyền đọc → `403 FORBIDDEN`. Đơn hoặc task tồn tại
  nhưng ngoài phạm vi → `404 NOT_FOUND`.
- Phân trang `{items, page, page_size, total}` với `page_size` ≤ 200. `?sort=` dùng `-` cho chiều giảm;
  trường sắp xếp không hợp lệ → `422 VALIDATION_ERROR`.
- Bộ lọc `warehouse_id`/`store_id` ngoài phạm vi người gọi → danh sách rỗng, không báo lỗi.
- Không ghi log tên, điện thoại, email, địa chỉ hay tọa độ khách (`09` mục 5).

## 2. Q5 — Phạm vi đơn

| Vai trò | Thấy đơn khi |
|---|---|
| admin | Mọi đơn của mọi market (admin không gắn nhân viên) hoặc của market mình |
| dispatcher | `market_id` = market của nhân viên |
| warehouse | Có kế hoạch **chưa** `superseded` (`proposed`/`approved`/`manual`) với `warehouse_id` thuộc `location_ids` hôm nay (US-ORD-02 AC1 "có kế hoạch/giao từ kho"), **hoặc** có `delivery_trip` từ kho đó |
| sales | `origin_store_id` thuộc `location_ids` hôm nay (US-ORD-02 AC1, chỉ đọc) |
| driver | Có `trip_stop` (không `cancelled`) trên `delivery_trip` có `driver_employee_id` = mình |
| customer_service | `market_id` = market của nhân viên |
| viewer | `403` |

Đơn `SUBMITTED` / `BLOCKED_UNMAPPED_SKU` chưa có kế hoạch: chỉ admin, dispatcher, CS và sales (cửa hàng gốc) thấy.

## 3. Q6 — Bản rút gọn của `GET /orders/{id}` (mục 5.1)

| Khối | admin, dispatcher, warehouse | sales, customer_service | driver |
|---|---|---|---|
| `id`, `order_no`, `status`, `market`, `version`, `submitted_at` | ✓ | ✓ | ✓ |
| `external_ref` | ✓ | ✓ | — |
| `customer` | ✓ | ✓ | chỉ `name` |
| `contact`, `delivery`, `date_request.window` | ✓ | ✓ | ✓ |
| `date_request` (đầy đủ), `committed` | ✓ | ✓ | `committed` |
| `origin_store`, `sales` | ✓ | ✓ | — |
| `lines` | ✓ | ✓ không có `handling_group`, `flags` | `line_no`, `name`, `qty_sale`, `sale_unit` |
| `lines[].unit_price`, `line_total`, `totals.amount` | ✓ | ✓ | — |
| `totals.weight_kg`, `volume_m3` | ✓ | — | ✓ |
| `block_reason` | ✓ | ✓ | — |
| `approved_plan_id`, `latest_run_id` | ✓ | — | — |
| `risk` | ✓ đầy đủ | `{status, color, forecast_eta}` | — |

Khối không được phép bị **bỏ hẳn** (không trả `null`), giống quy tắc `06` v1.3 Q1.
`risk` = bản `eta_forecast` mới nhất:
`{status, color, forecast_eta, planned_eta, commitment_deadline, slack_min, consumption_pct}`; `null` nếu chưa có.
Không có GPS trong phản hồi này với bất kỳ vai trò nào.

## 4. Q7 — `GET /orders` và `/orders/counts`

Phần tử danh sách (một schema cho mọi vai trò; trường bị cấm theo Q6 thì bỏ):
```json
{ "id": 4021, "order_no": "SE-2026-004021", "status": "PLANNED", "customer_name": "Nordbygg AB",
  "site": "Göteborg", "warehouse": { "id": 7, "code": "STO" }, "origin_store": { "id": 21, "code": "GBG-V" },
  "date_request": { "mode": "latest", "date_from": null, "date_to": "2026-11-18" },
  "committed_date": null, "promise_end": null, "risk_color": null, "block_reason": null,
  "total_amount": "48300.00", "currency": "SEK", "submitted_at": "2026-11-05T07:12:00Z" }
```
- `site` lấy từ `delivery_address`: phần sau dấu phẩy cuối cùng (cột "CUSTOMER · SITE" của `03`). Driver không
  dùng danh sách này (dùng `/driver/trips`).
- `warehouse` = kho của kế hoạch đã duyệt, nếu chưa có thì của kế hoạch `proposed` rank 1, nếu không có thì `null`.
- Lọc `blocked=true` ⇔ `status = BLOCKED_UNMAPPED_SKU`. `q` khớp `order_no`, `external_ref` hoặc tên khách
  (không phân biệt hoa thường).
- Sắp xếp mặc định `promise_end` tăng dần, `NULL` xếp cuối, rồi `submitted_at` (US-ORD-02 AC3). Trường được phép
  sắp xếp: `promise_end`, `submitted_at`, `committed_date`, `order_no`, `status`.

Bucket của `/orders/counts` (theo phạm vi người gọi; ngày "hôm nay" tính theo múi giờ market):

| Bucket | Trạng thái / điều kiện |
|---|---|
| `all` | Mọi đơn trong phạm vi, trừ `DELIVERED`/`CANCELLED` đã đóng trước hôm nay |
| `needs_plan` | `SUBMITTED`, `BLOCKED_UNMAPPED_SKU` |
| `awaiting_approval` | `PLANNED` |
| `no_feasible_date` | `NO_FEASIBLE_DATE` |
| `in_execution` | `APPROVED`, `PREPARING`, `GOODS_READY`, `LOADED`, `DISPATCHED` |
| `replan_suggested` | Có `planning_run.kind = 'replan_suggestion'` chưa xử lý (chưa duyệt / giữ nguyên) |
| `delivered_today` | `DELIVERED` với `delivered_at` hôm nay |
| `nav.order_queue` | = `needs_plan` + `awaiting_approval` + `no_feasible_date` (chỉ dispatcher; vai trò khác `0`) |
| `nav.exceptions` | Alert mở loại `EXCEPTION` / `REPLAN_SUGGESTED` trong phạm vi |
| `nav.tracking_risk` | Đơn `in_execution` có `risk_color` `orange` hoặc `red` |

## 5. Q8 — Ánh xạ SKU

Quyền theo `06` §3: admin **W**; dispatcher và warehouse **R** (market mình); vai trò khác `403`.

`GET /mapping/tasks?status=&market=&q=` — phần tử:
```json
{ "id": 12, "market": "SE", "local_sku": "SE-NEW-77", "name": "…", "category": "…", "gtin": "…",
  "sale_unit": "pallet", "mapping_status": "pending", "status": "open", "blocked_order_count": 2,
  "candidates": [ { "global_product_id": 123, "code": "G-000123", "name": "…", "reason": "gtin", "score": 1.0 } ],
  "resolved_by": null, "resolved_at": null }
```
- Mặc định `status=open`. Sắp xếp mặc định `-blocked_order_count,local_sku`.
- `GET /mapping/tasks/{id}` dùng cùng schema, thêm:
  - `suggested_handling_group` (theo `handling_group_rule`, US-PRD-04 AC2);
  - `blocked_orders: [{id, order_no}]`. Với warehouse, chỉ liệt kê đơn trong phạm vi Q5; `blocked_order_count`
    vẫn là tổng số.
- `POST …/confirm` → `200`:
  `{ "task_id", "local_sku", "global_product_id", "mapping_status": "confirmed", "ready_order_ids": [...],
  "still_blocked_order_ids": [...] }`.
- `POST …/reject` → `200` `{ "task_id", "local_sku", "mapping_status": "rejected" }`.
- Lỗi:
  - `403` cho vai trò khác admin.
  - `404` khi không có task.
  - `422 VALIDATION_ERROR` kèm `details.field`.
  - `422 REASON_REQUIRED`.
  - Các quy tắc ASM-005 (task đã xong, ánh xạ đã xác nhận) cũng trả `422`.
- `GET /products/local?market=SE&mapping_status=&q=` — phần tử là các cột của `ref.v_product_local`:
  `{market, local_sku, name, category, gtin, sale_unit, units_to_base, unit_price, currency, global_product_id,
  mapping_status}` (US-PRD-05 AC1). Sắp xếp mặc định `local_sku`.

## 6. Q9 — Timeline `GET /orders/{id}/timeline`

Không phân trang; sắp xếp theo `at` tăng dần, cùng thời điểm thì theo thứ tự `kind` dưới đây.
```json
{ "items": [ { "at": "2026-11-05T07:12:00Z", "kind": "order_submitted", "title": "Order submitted",
               "detail": {}, "actor": null } ] }
```

| `kind` | Nguồn | admin / dispatcher / warehouse | customer_service |
|---|---|---|---|
| `order_submitted` | `customer_order.submitted_at` | ✓ | ✓ |
| `planning_run` | `plan.planning_run` (`kind`, kết quả) | ✓ | — |
| `decision` | `audit.decision_log` (`action`, `reason_text`, actor) | ✓ | — (quyết định nội bộ, US-ORD-03 AC2) |
| `milestone` | `ops.milestone_event` (`type`, `vehicle`) | ✓ | ✓ không có tọa độ |
| `notification` | `ops.notification` (`type`, `channel`, `status`) | ✓ | ✓ |
| `eta` | `ops.eta_forecast` (`version`, `forecast_eta`, `risk_status`, `risk_color`) | ✓ đầy đủ | `forecast_eta`, `risk_status` |

Không có điểm số, GPS hay `snapshot`/`before`/`after` của decision log trong timeline. Ai cần các trường đó dùng
`/audit/decisions` theo quyền riêng.

## 7. Q10 — Điểm danh và công suất (M3)

Service đã có: qaztyhn/cfo-itconsultant#39 (`set_attendance`, quy tắc ASM-007).

`GET /warehouses/{id}/attendance?date=` (warehouse của kho đó, dispatcher và admin trong market; ngoài phạm vi → `404`).
Phản hồi của `PUT` dùng cùng schema này:
```json
{ "warehouse_id": 1, "date": "2026-11-12",
  "counts": { "planned": 0, "present": 10, "absent": 2, "leave": 0 },
  "items": [ { "employee_id": 120, "name": "…", "position": "WAREHOUSE_OPERATOR", "counts_in_capacity": true,
               "shift": { "id": 4, "start": "07:00", "end": "15:00" }, "status": "present",
               "on_approved_leave": false } ] }
```

`GET /warehouses/{id}/capacity?from=&to=` (cùng phạm vi; tối đa 31 ngày; theo Phụ lục A):
```json
{ "warehouse_id": 1, "days": [ { "date": "2026-11-12", "holiday": false,
    "shifts": [ { "start": "07:00", "end": "15:00", "present": 8, "useful_hours": 7.0 } ],
    "labour_cap_hours": 50.4, "booked_hours": { "committed": 22.0, "held": 8.0 }, "free_hours": 20.4 } ] }
```
`labour_cap_hours` = Σ người × giờ hữu ích × `delivery_share` (US-WH-02 AC1). Ngày lễ trả `0` (AC3).
`booked_hours` gồm giờ của mọi đơn (AC2).

## 8. Thứ tự triển khai sau khi chốt
1. `06` mục 5 và 12 + `CHANGELOG` (một PR docs, giống `06` v1.3).
2. M2-C: `/mapping/tasks*`, `/products/local`. Ứng viên ánh xạ cần `engine.mapping_candidates`, đã có trên `main`
   nhưng chưa có trên `feat/m0-db-ref-hr`, nên cần qaztyhn/cfo-itconsultant#28.
3. M2-D: `/orders`, `/orders/{id}`, `/orders/counts`.
4. M2-E: `/orders/{id}/timeline`.
