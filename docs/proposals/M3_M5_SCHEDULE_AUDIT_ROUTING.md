# Đề xuất hợp đồng — lịch ca chính thức, mã audit nhân sự, phân luồng đơn (Q12–Q14)

> **Trạng thái: ĐỀ XUẤT — chờ chủ dự án/nhóm duyệt. Chưa phải hợp đồng, chưa có migration/code.**
> Tác giả: Dev 1. Ngày: 2026-11-07. Lý do: các quyết định ở qaztyhn/cfo-itconsultant#49 (ASM-005) và
> qaztyhn/cfo-itconsultant#50 (ASM-006/007) yêu cầu Dev 1 **đề xuất trước khi code**:
> - bảng lịch phân ca từng người kèm API (US-WH-06);
> - mã hành động còn thiếu cho đổi quản lý, đổi owner, nghỉ việc, chỉnh hồi tố (US-EMP-05);
> - cơ chế phân luồng một đơn chỉ thuộc một hệ thống điều phối (US-PRD-00 AC3).
>
> Khi được duyệt, Dev 1 làm một PR cho mỗi Q, gồm: `05`/`06`/`04` + `CHANGELOG`, migration và test PostgreSQL.

## Tóm tắt quyết định cần chốt

| # | Câu hỏi | Đề xuất (A) | Phương án khác |
|---|---|---|---|
| **Q12a** | Mỗi người được mấy ca trong một ngày? | **Tối đa 1 ca/người/ngày** (chỉ mục duy nhất) | **B.** Nhiều ca không chồng giờ, kiểm bằng trigger |
| **Q12b** | Ai được lập/sửa lịch? | Tài khoản `warehouse` có bản ghi `hr.location_manager` (primary **hoặc** deputy) hiệu lực tại kho, `can_approve = true` | **B.** Chỉ quản lý chính (primary) |
| **Q12c** | Sửa lịch ngày đã qua | Cùng người có quyền ở Q12b, **bắt buộc `reason_text`**; admin không sửa lịch thay | **B.** Chỉ admin, kèm lý do |
| **Q12d** | Công suất khi thiếu lịch | Ngày không có dòng lịch nào → `schedule_verified: false`, công suất 0 | **B.** Không thêm cờ, chỉ trả 0 |
| **Q13** | Mã audit ASM-006 | `LOCATION_MANAGER_CHANGED`, `LOCATION_OWNER_CHANGED`, `EMPLOYEE_TERMINATED`; chỉnh hồi tố phân công dùng `EMPLOYEE_ASSIGNMENT_CHANGED` kèm `reason_code = 'retroactive'` và **bắt buộc lý do** | Đặt tên khác |
| **Q14** | Phân luồng ASM-005, chống xử lý trùng | **A.** Bảng `ops.order_routing` ghi luồng được chọn lần đầu (`cfo`/`legacy`), **không bao giờ đổi**; đơn `legacy` không tạo `customer_order` | **B.** Giữ `customer_order` với `BLOCKED_UNMAPPED_SKU` làm dấu luồng cũ; bỏ chuyển `BLOCKED → SUBMITTED` khỏi seed để trạng thái này là cuối. **C.** Đọc owner luồng từ API POS (bị loại: hợp đồng nguồn không có trường này và không được sửa POS) |

---

## Q12 — Lịch phân ca chính thức (ASM-007, US-WH-06)

### Bảng đề xuất (`05` mục 4)
```sql
CREATE TABLE hr.employee_shift_schedule (        -- nguồn xác thực duy nhất cho lịch người–ngày–ca [C]
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  employee_id bigint NOT NULL REFERENCES hr.employee(id),
  warehouse_id bigint NOT NULL REFERENCES ref.location(id),
  work_date date NOT NULL,
  shift_template_id bigint NOT NULL REFERENCES hr.shift_template(id),
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','cancelled')),
  assigned_by bigint NOT NULL REFERENCES hr.employee(id),
  assigned_at timestamptz NOT NULL,
  cancelled_by bigint REFERENCES hr.employee(id), cancelled_at timestamptz,
  reason_text text,                              -- bắt buộc khi work_date < hôm nay (kiểm ở service)
  CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
);
CREATE UNIQUE INDEX ux_shift_one_per_day ON hr.employee_shift_schedule (employee_id, work_date)
  WHERE status = 'scheduled';                    -- Q12a = A
```
- Kèm cột chung `created_at` / `updated_at` theo ASM-001.
- **Đổi ca không UPDATE dòng cũ.** Dòng cũ chuyển `cancelled`, thêm dòng mới, ghi `SHIFT_CHANGED` (trước/sau) trong cùng transaction, nên lịch sử còn nguyên.
- **Service kiểm:**
  - nhân viên có phân công hiệu lực tại kho đúng ngày đó, chưa `terminated`;
  - `shift_template` thuộc đúng kho và đúng thứ trong tuần;
  - thiếu `reason_text` khi sửa ngày đã qua → `422 REASON_REQUIRED`.
- **`expected_staff` không giới hạn số người xếp vào ca và không dùng để tự xếp.** API chỉ trả lại số này để so sánh.

### API (`06` mục 13.0a / 13.2)
- `GET /warehouses/{id}/shift-schedule?from=&to=`
  - Quyền: warehouse (kho mình), dispatcher, admin trong market. Tối đa 31 ngày.
  - Phản hồi:
    ```json
    { "warehouse_id": 1, "days": [ { "date": "2026-11-12", "shifts": [ {
        "shift_template_id": 4, "start": "07:00", "end": "15:00", "expected_staff": 6, "scheduled_count": 5,
        "employees": [ { "employee_id": 120, "name": "…", "counts_in_capacity": true } ] } ] } ] }
    ```
- `PUT /warehouses/{id}/shift-schedule`
  - Quyền: chỉ người thỏa Q12b. Sai vai trò → `403`; kho khác → `404`.
  - Thân request: `{ "entries": [ { "employee_id": 120, "date": "2026-11-12", "shift_template_id": 4 } ], "reason_text": null }`. Đặt `shift_template_id: null` để bỏ người khỏi lịch ngày đó.
  - Áp dụng toàn bộ hoặc không gì cả. Phản hồi dùng cùng schema với GET.
- **`attendance_gen`:** với mỗi dòng `scheduled` trong 14 ngày tới, tạo `hr.attendance` (`planned`, đúng ca). Không ghi đè dòng điểm danh đã có; nếu lịch bị hủy mà dòng điểm danh vẫn là `planned` thì xóa cờ (đề xuất: đặt `shift_template_id = NULL`).
- **Công suất:** ngày không có dòng lịch → `schedule_verified: false` (Q12d), công suất 0, UI cảnh báo.

## Q13 — Mã hành động audit nhân sự (ASM-006, US-EMP-05)

Thêm vào `04` mục 10 và `app/audit/actions.py`:

| Mã | Khi nào | `before` / `after` |
|---|---|---|
| `LOCATION_MANAGER_CHANGED` | `PUT /locations/{id}/managers` | primary/deputy cũ → mới (`employee_id`, `valid_from/to`) |
| `LOCATION_OWNER_CHANGED` | `PATCH /locations/{id}/owner`, hoặc owner tự đổi theo quản lý chính | `owner_employee_id` cũ → mới, `reason_code = 'follows_primary'` khi tự đổi |
| `EMPLOYEE_TERMINATED` | `POST /employees/{id}/terminate` | `status`, `end_date`, phân công đóng, `app_user.is_active` |
| `EMPLOYEE_ASSIGNMENT_CHANGED` (đã có) | chuyển công tác; **chỉnh hồi tố** `reason_code = 'retroactive'`, `reason_text` bắt buộc | phân công cũ/mới |

**Chỉnh hồi tố phân công:**
- Chỉ admin.
- Thêm trường `reason_text` vào `POST /employees/{id}/assignments`, bắt buộc khi `start_date < hôm nay`.
- Service từ chối nếu tạo ra hai phân công chồng ngày.
- Không xóa bản ghi cũ: chỉ đóng hoặc mở `end_date`, có log trước/sau.

## Q14 — Phân luồng đơn: một đơn một hệ thống điều phối (ASM-005, US-PRD-00)

**Phương án A (đề xuất).** Thêm bảng sau vào `05` mục 6:
```sql
CREATE TABLE ops.order_routing (
  market_id smallint NOT NULL REFERENCES ref.market(id),
  external_ref text NOT NULL,                     -- mã đơn POS
  route text NOT NULL CHECK (route IN ('cfo','legacy')),
  decided_at timestamptz NOT NULL, decided_source_version int NOT NULL,
  reason_code text,                               -- 'unmapped_sku' | 'all_confirmed'
  unmapped_skus text[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (market_id, external_ref)
);
```
- **Quyết định một lần, không đổi:**
  - Lần đầu CFO thấy đơn (polling hoặc Sales `sync-now`), trong cùng transaction: lấy advisory lock `routing:<market>:<external_ref>`, rồi `INSERT … ON CONFLICT DO NOTHING`.
  - Bên thắng quyết định luồng; bên thua đọc kết quả đã có.
  - `legacy` → **không** tạo `customer_order`, không lập plan, không giữ chỗ.
  - Version nguồn đổi hoặc IT mapping xong cũng **không** đổi luồng (US-PRD-00 AC2).
- **Fail closed (AC3):** chưa đọc được đủ dòng hàng hoặc danh mục sản phẩm → không quyết định, không tạo đơn CFO. `sync-now` trả trạng thái "chưa xác định, thử lại".
- **`sync-now` cho đơn `legacy`:** trả `200 { "sync_status": "legacy_process", "unmapped_skus": [...] }`. Đề xuất dùng mã thành công thay vì lỗi: đơn hợp lệ, chỉ không thuộc CFO. Không có Confirm.
- **Dữ liệu cũ:** migration chuyển các `customer_order` đang `BLOCKED_UNMAPPED_SKU` thành `order_routing(route='legacy')`. Xử lý các dòng này (giữ chỉ đọc hay xóa khỏi danh sách) cần chốt thêm.
- **Phối hợp:** việc ghi `order_routing` nằm trong ingestion, thuộc Dev 2 (`ingest_service`). Dev 1 viết hàm kiểm điều kiện `route_for(order_lines)` và guard trong `order_service`/`planning_service`. Mọi đường lập plan/hold/approve kiểm `route = 'cfo'`.
- **Mapping task:** vẫn sinh từ đồng bộ danh mục sản phẩm (SKU `pending`), không phụ thuộc đơn bị chặn (US-PRD-01 AC1).

**Phương án B (ít thay đổi schema).**
- Giữ `customer_order` ở trạng thái `BLOCKED_UNMAPPED_SKU` làm dấu luồng cũ.
- Migration xóa cặp chuyển `BLOCKED_UNMAPPED_SKU → SUBMITTED` khỏi seed `ops.order_transition`, để đây là trạng thái cuối.
- Unique `(market_id, external_ref)` có sẵn đã chống tạo trùng.
- Nhược điểm: CFO vẫn lưu đơn không thuộc CFO; phải loại các đơn này khỏi mọi danh sách, KPI và doanh thu; dễ bị "mở khóa" nhầm.

## Ảnh hưởng nếu duyệt cả ba (phương án A)
- **Migration mới `0009_…`:** `hr.employee_shift_schedule`, `ops.order_routing`. Không đổi bảng cũ.
- **`06`:** chi tiết `13.0a` và `13.2` (lịch, `schedule_verified`), `5.0.1` (sync-now `legacy_process`), mã audit mới.
- **Code Dev 1:** schedule service + API, `attendance_gen` chép từ lịch, audit ASM-006 cho manager/owner/terminate và chỉnh hồi tố, guard `route = 'cfo'` trước plan/hold/approve.
- **Dev 2:** routing trong ingestion và sync-now.
- **Dev 3:** màn lập lịch (5.A5) và trạng thái "quy trình cũ" ở My store orders.
