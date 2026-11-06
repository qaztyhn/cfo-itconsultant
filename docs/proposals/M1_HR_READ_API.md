# Đề xuất hợp đồng — API đọc nhân sự, địa điểm, xe (M1-D … M1-G)

> **Trạng thái: ĐỀ XUẤT — chờ nhóm review. Chưa phải hợp đồng.** Không có mã triển khai đi kèm. Khi nhóm chốt,
> nội dung được đưa vào `06` mục 3 và 13 cùng `CHANGELOG`, mã và test trong cùng PR triển khai (`09` mục 6, 14).
> Tác giả: Dev 1. Ngày: 2026-11-06. Liên quan: `10` mục 2 M1 (Dev 1: `GET /employees`, `/locations`, `/vehicles`).

## 0. Vì sao cần đề xuất

`06` mục 13 có đường dẫn, vai trò và tham số lọc nhưng **không có schema phản hồi**. Có thêm ba điểm chưa rõ:
quyền đọc `/vehicles` (mục 13 và ma trận mục 3 khác nhau), phạm vi của `/locations`, và trường dữ liệu nhân viên
nào được trả cho vai trò không phải admin. Theo `09` mục 14.3–14.4, đây là quyết định về hợp đồng và phân quyền
nên Dev 1 **không tự chốt**.

## 1. Các quyết định cần nhóm chốt

| # | Câu hỏi | Phương án | Ghi chú của Dev 1 |
|---|---|---|---|
| **Q1** | Schema phản hồi cho `GET /locations[/{id}]`, `/employees[/{id}]`, `/vehicles[/{id}]` | Chấp nhận / sửa schema ở mục 2 | Tên trường lấy từ `05`; chỉ thêm khối lồng nhau (owner, managers, assignment) đã nêu ở `06` §13 ("Kèm owner, quản lý") và `03` A9/A10 |
| **Q2** | Ai đọc được `/vehicles` | **A.** Theo ma trận `06` §3: admin, dispatcher (cả market), warehouse (xe có kho gốc thuộc kho mình); sửa câu ở §13 thành "admin; R: dispatcher, warehouse (kho mình)". **B.** Theo §13: chỉ admin | Đối chiếu nghiêng về A (`04` §9 gọi §3 là ma trận đầy đủ; màn kế hoạch tay M5 cần dispatcher đọc xe). **Chưa coi là đã duyệt** |
| **Q3** | Phạm vi `/locations` | **A.** Như hàng "Nhân sự" của §3: admin, dispatcher (cả market), warehouse (nơi mình được phân công); vai trò khác `403`. **B.** A + sales (cửa hàng mình), driver (kho gốc). **C.** Mọi người đã đăng nhập đọc danh mục địa điểm trong market của mình; khối `owner`/`managers` chỉ cho admin, dispatcher, warehouse | Quyết định phân quyền → nhóm chốt |
| **Q4** | Dữ liệu nhân viên trả cho dispatcher/warehouse | **A.** Admin: đầy đủ; dispatcher/warehouse: không có `work_email`, `work_phone`. **B.** Mọi vai trò được phép đọc đều thấy đầy đủ (danh bạ nội bộ). **C.** Dispatcher/warehouse chỉ thấy `id`, tên, vị trí, phân công hiện tại và khối `driver_staff` (cho cảnh báo bằng lái US-EMP-04 AC1) | Dữ liệu nhân viên → nhóm chốt. Dù chọn gì: tên/email/điện thoại nhân viên **không** ghi log |

Quy tắc chung đề xuất (áp dụng cho mọi phương án):
- Kiểm vai trò và phạm vi **ở máy chủ**; vai trò không được đọc nhóm endpoint → `403 FORBIDDEN`; bản ghi tồn tại
  nhưng ngoài phạm vi người dùng → `404 NOT_FOUND` (không lộ sự tồn tại — `06` §1, US-EMP-03 AC2).
- Phạm vi market: dispatcher/warehouse chỉ thấy dữ liệu market của nhân viên đó; tài khoản admin không gắn nhân
  viên thấy mọi market.
- Không tin `location_id` từ client: lọc theo `location_id` ngoài phạm vi → danh sách rỗng (không lỗi).
- Mã `NOT_FOUND` hiện thuộc đề xuất `06` v1.2.1 đang chờ duyệt (PR qaztyhn/cfo-itconsultant#8). Nếu v1.2.1 bị
  từ chối, cần chọn mã cho 404 trước khi triển khai mục này.

## 2. Schema phản hồi đề xuất (Q1)

Quy ước theo `06` §1: phân trang `{items, page, page_size, total}` (`page_size` mặc định 50, tối đa 200); số lượng,
tải, thể tích, tọa độ là số JSON; ngày `YYYY-MM-DD`; giờ trong ngày `HH:MM`; sắp xếp `?sort=` theo tên trường.

### 2.1 `GET /locations`, `GET /locations/{id}`

Lọc: `type`, `is_active` (mặc định `true`), `q` (mã hoặc tên). Sắp xếp mặc định: `code`.

```json
{
  "id": 7, "market": "SE", "type": "warehouse", "code": "STO", "name": "Stockholm DC",
  "address": "…", "lat": 59.3293, "lon": 18.0686, "loading_cutoff_time": "15:00", "is_active": true,
  "owner": { "employee_id": 40, "name": "…" },
  "managers": {
    "primary": { "employee_id": 40, "name": "…" },
    "deputy":  { "employee_id": 41, "name": "…" }
  }
}
```
- `owner`, `managers.primary`, `managers.deputy` là `null` khi chưa gán. Quản lý = bản ghi `hr.location_manager`
  đang hiệu lực (`valid_to IS NULL`).
- Không trả `efficiency_factor` (cột chưa có UI — `05` mục 3, `09` bất biến 7).
- Danh sách và chi tiết dùng cùng một schema.

### 2.2 `GET /employees`, `GET /employees/{id}`

Lọc (`06` §13): `position_code`, `location_id` (phân công đang hiệu lực), `status`; thêm `q` (tên hoặc
`employee_no`). Sắp xếp mặc định: `last_name,first_name`.

```json
{
  "id": 55, "employee_no": "SE-0055", "first_name": "Anna", "last_name": "Lind",
  "position": { "code": "DISPATCHER", "name": "Dispatcher" },
  "status": "active", "employment_type": "full_time", "hire_date": "2025-03-01", "end_date": null,
  "assignment": { "location_id": 7, "location_code": "STO", "location_name": "Stockholm DC", "start_date": "2025-03-01" },
  "warehouse_staff": null,
  "sales_staff": null,
  "dispatcher_staff": { "can_send_delay_notice": true },
  "driver_staff": null,
  "cs_staff": null,
  "work_email": "…", "work_phone": "…"
}
```
- Năm khối `*_staff` đặt tên theo 5 bảng con của `05` mục 4; khối không áp dụng là `null`.
  `driver_staff` = `{licence_class, licence_expires_on, home_warehouse_id, adr}`;
  `warehouse_staff` = `{role, counts_in_capacity}`; `sales_staff` = `{role}`; `cs_staff` = `{team}`.
- `assignment` = phân công đang hiệu lực hôm nay theo múi giờ market, hoặc `null`.
- `work_email`, `work_phone`: phụ thuộc **Q4** (phương án A: chỉ admin; trường bị bỏ khỏi phản hồi, không trả `null`).
- Chi tiết `GET /employees/{id}` (admin) thêm `weekly_hours`, `reports_to_employee_id`, `assignment_history`
  (`[{location_id, location_code, start_date, end_date}]`, mới nhất trước).
- Không trả thông tin tài khoản (`roles`, `is_active`, `email` đăng nhập) — thuộc `/users` (admin).

### 2.3 `GET /vehicles`, `GET /vehicles/{id}`

Lọc: `home_warehouse_id`, `status`, `capability`. Sắp xếp mặc định: `code`.

```json
{
  "id": 3, "code": "STO-CR-01", "plate": "…", "name": "Crane truck",
  "home_warehouse": { "id": 7, "code": "STO", "name": "Stockholm DC" },
  "capacity_kg": 8000.0, "capacity_m3": 30.0, "capabilities": ["crane"], "required_licence": "C",
  "allowed_groups": [ { "id": 4, "code": "N4" } ],
  "status": "available"
}
```
- `allowed_groups: []` nghĩa là chở được mọi nhóm (`05`: `allowed_group_ids` rỗng = tất cả).
- Lịch bận ở endpoint riêng `GET /vehicles/{id}/availability` (đã có trong `06` §13, không thuộc đề xuất này).

## 3. Bảng quyền đề xuất (điền sau khi chốt Q2–Q4)

| Endpoint | admin | dispatcher | warehouse | sales | driver | customer_service | viewer |
|---|---|---|---|---|---|---|---|
| `GET /locations[/{id}]` | R (mọi market) | R (market) | R (nơi mình) | Q3 | Q3 | Q3 | Q3 |
| `GET /employees[/{id}]` | R (đầy đủ) | R (market; trường theo Q4) | R (nhân viên có phân công ở kho mình; trường theo Q4) | — | — | — | — |
| `GET /vehicles[/{id}]` | R | Q2 | Q2 (kho gốc thuộc kho mình) | — | — | — | — |

Mỗi ô sẽ có test đường được phép và bị cấm trên PostgreSQL thật (US-EMP-03 AC2, AC3).

## 4. Không thay đổi

Không đổi bảng, cột, enum, endpoint hiện có, mã lỗi hay ma trận cho các nhóm khác. Endpoint ghi (`POST/PATCH/PUT`
của `/employees`, `/locations/*`, `/vehicles`) giữ nguyên trong `06` và thuộc milestone sau (M3).

## 5. Sau khi nhóm chốt

1. PR triển khai đầu tiên cập nhật `06` §3, §13 bằng nội dung đã chốt + mục `CHANGELOG`.
2. Các PR theo thứ tự: M1-D (phạm vi + phân trang) → M1-E (`/locations`) → M1-F (`/employees`) → M1-G (`/vehicles`),
   mỗi PR có schema Pydantic + ví dụ OpenAPI và test quyền theo bảng mục 3.
3. Dev 3 có thể dựng màn A9/A10 bằng mock theo schema mục 2 ngay khi nhóm chốt Q1.
