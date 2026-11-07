# Assumptions (ASM-xxx)

> Ghi nhận cách diễn giải/giả định theo `09_AI_Coding_Rules.md` mục 14. Mục ở đây **không** thay thế phê duyệt
> thay đổi hợp đồng: thay đổi `05`/`06` vẫn phải sửa tài liệu + migration + `CHANGELOG` trong cùng PR.

## ASM-001 — Cột chung `created_at` / `updated_at` cho mọi bảng CFO

- **Ngày:** 2026-11-06
- **Trạng thái:** đã chốt bởi nhóm (không có ngoại lệ). Chỉ ghi nhận cách diễn giải; không sửa `05`.
- **Bối cảnh:** `05` mục 1 quy định cột chung `created_at timestamptz NOT NULL DEFAULT now()` và
  `updated_at timestamptz NOT NULL DEFAULT now()` (trigger `set_updated_at`) "có ở mọi bảng nghiệp vụ",
  nhưng DDL chi tiết không lặp lại hai cột này cho từng bảng.
- **Diễn giải đã chốt:**
  1. "Bảng nghiệp vụ" = **toàn bộ 57 bảng CFO** có `CREATE TABLE` trong `05` (schema `ref`, `hr`, `stg`, `ops`,
     `plan`, `audit`); không áp dụng cho bảng `src_*` của hệ thống nguồn giả lập.
  2. Không thêm trùng cột đã có trong DDL: `ref.market` đã có cả hai cột; `ops.idempotency_key` đã có
     `created_at` nên chỉ thêm `updated_at`.
  3. Trigger `set_updated_at` (BEFORE UPDATE) được tạo và gắn cho mọi bảng có cột `updated_at` ở migration
     `0007_audit_views_triggers`.
- **Không thay đổi bất biến:** `audit.decision_log` và `ops.milestone_event` vẫn bị trigger `forbid_mutation`
  chặn UPDATE/DELETE; POD cũ vẫn không được UPDATE (`09` bất biến 13, 22). `updated_at` chỉ là siêu dữ liệu
  kỹ thuật: **không** phải dấu vết audit (audit nằm ở `audit.decision_log`) và **không** ngăn việc sửa dữ liệu;
  các quy tắc cấm cập nhật vẫn phải được thực thi riêng.
- **Mốc nghiệp vụ khác `created_at`:** các cột như `contacted_at`, `completed_at`, `computed_at`, `received_at`,
  `occurred_at`, `ts`, `as_of`, `synced_at` là thời điểm nghiệp vụ (hoặc của nguồn); `created_at` là thời điểm
  ghi bản ghi vào CFO. Hai loại không mặc nhiên trùng nghĩa và đều được giữ nguyên.
- **Ảnh hưởng:** migration `0002`–`0007`; model SQLAlchemy (M1) cần khai báo hai cột; test PostgreSQL kiểm tra
  kiểu, `NOT NULL`, giá trị mặc định (T2) và trigger cập nhật thời gian cùng các thao tác bị cấm (T4).

## ASM-002 — Diễn giải seed tham chiếu `0008_seed_reference`

- **Ngày:** 2026-11-06
- **Trạng thái:** đề xuất của Dev 1, chờ nhóm xác nhận trong review PR T4. Không sửa `05`.
- **Bối cảnh:** `05` mục 11 liệt kê dữ liệu cần seed (market SE, N1–N6, special_flag, position, order_transition)
  nhưng không ghi đủ giá trị cho mọi cột.
- **Diễn giải:**
  1. **Vai trò "system"** trong bảng chuyển trạng thái (`05` mục 6; `app/domain/transitions.py`) không thuộc enum
     `ref.user_role`, nên `ops.order_transition.allowed_roles` lưu **mảng rỗng** cho các chuyển do hệ thống
     thực hiện. Không thêm giá trị enum mới.
  2. **`PLANNED → APPROVED`**: `requires_reason = false` (khớp `transitions.ALLOWED`); lý do chỉ bắt buộc khi
     chọn phương án khác hoặc lập tay, và được kiểm ở service qua `ALT_SELECTED` / `MANUAL_PLAN_CREATED`
     (`09` bất biến 14).
  3. **`ref.market` SE**: `gps_enabled = false`, `shadow_mode = false` (mặc định của `05`). `08` mục 5.1 yêu cầu
     `gps_enabled = true` **cho demo**; việc bật thuộc seed demo (`seed/generate_data.py`, Dev 2), không bật
     trong migration vì GPS là quyết định nhạy cảm cần DPIA (`04` mục 9, `09` mục 14.4).
     `source_api_key_ref = 'SOURCE_SE_API_KEY'` (tên biến môi trường, không phải bí mật); `source_base_url` để
     trống (cấu hình theo môi trường). `config` = `MarketConfig` mặc định `04` mục 8 cộng
     `routing.allow_fallback = true` (`06` Phụ lục A).
  4. **`handling_group.min_crew`**: N2 ghi "1–2" → seed `1` (cận dưới; cột "chỉ hiển thị, chưa ép buộc").
     `description` lấy nguyên văn cột "Mô tả" của `05` mục 11.
  5. **`hr.position`**: `name` tiếng Anh theo mã; `grp`: kho → `warehouse`; DRIVER, DISPATCHER → `transport`;
     STORE_MANAGER, SALES_* → `store`; CUSTOMER_SERVICE, IT_INTEGRATION, BUSINESS_OWNER, PROJECT_LEAD → `central`.
     `default_roles`: quản lý/phó/trưởng ca kho → `warehouse`; WAREHOUSE_OPERATOR, FORKLIFT_OPERATOR → rỗng
     (không có tài khoản, `09` bất biến 18); STORE_MANAGER, SALES_* → `sales`; còn lại theo tên vai trò.
     `default_kpi_scopes` đúng chú thích `05` mục 4.
  6. **Không seed** tài khoản, nhân viên, mật khẩu, ngày lễ hay dữ liệu demo trong migration (`08` mục 5 —
     `seed/generate_data.py`, Dev 2; `09` bất biến 25).
- **Ảnh hưởng:** `0008_seed_reference`; test `test_migration_0006_0008.py` đối chiếu seed `order_transition` với
  `transitions.ALLOWED` và `MarketConfig()`.

## ASM-003 — Chi tiết xác thực chưa có trong `06` mục 4

- **Ngày:** 2026-11-06
- **Trạng thái:** đề xuất của Dev 1, chờ nhóm xác nhận trong review PR T5. Không sửa `06`.
- **Diễn giải:**
  1. **Giới hạn tần suất login:** tính **mọi lần thử** (đúng hoặc sai) theo **IP client**, cửa sổ trượt 60 giây,
     tối đa 5 lần; lần thứ 6 → `429`. Bộ đếm in-memory theo tiến trình (MVP một instance), dùng đồng hồ đơn điệu
     nên không bị ảnh hưởng bởi `APP_NOW`.
  2. **Mã lỗi khi `429`:** `06` chỉ quy định HTTP 429, không có mã nghiệp vụ riêng; dùng mã có sẵn `AUTH_INVALID`
     với thông báo "Too many login attempts. Try again in a minute." (không thêm mã lỗi mới — `09` mục 13).
     Frontend phân biệt theo HTTP status (`03` màn Sign in).
  3. **`POST /auth/logout`:** cần token hợp lệ; trả `204 No Content` (06 không quy định thân phản hồi).
  4. **Email đăng nhập** so khớp không phân biệt hoa thường; sai email, sai mật khẩu, tài khoản khóa hoặc nhân viên
     `terminated` đều trả cùng `401 AUTH_INVALID` "Invalid email or password." (không lộ tài khoản tồn tại).
  5. **Tài khoản hệ thống** (không có `employee_id`): `name`, `market` = `null`, `location_ids` = `[]`, `locale` = `en`.
  6. **`location_ids`** = địa điểm của các phân công đang hiệu lực hôm nay theo múi giờ market.
  7. **Hồ sơ đọc lại từ DB mỗi request** (vai trò, `kpi_scopes`, `is_active`, trạng thái nhân viên) để thỏa
     US-EMP-03 AC4; claims trong token chỉ để client hiển thị.

## ASM-004 — Mã lỗi cho lỗi kỹ thuật ngoài danh sách `06` mục 1.1

- **Ngày:** 2026-11-06
- **Trạng thái:** đã chuyển thành **đề xuất thay đổi hợp đồng** `06` v1.2.1 + `CHANGELOG` trong PR #8, **chờ nhóm
  duyệt**. Mục ASM này chỉ ghi bối cảnh; không thay thế phê duyệt. PR #8 không được merge trước khi duyệt.
- **Bối cảnh:** `06` mục 1.1 bắt buộc mọi lỗi theo định dạng `{error: {code, message, details, correlation_id}}`
  nhưng danh sách mã chỉ gồm mã nghiệp vụ; HTTP 500/503 và một số 4xx kỹ thuật không có mã.
- **Diễn giải đang triển khai:**
  1. Lỗi không bắt (500) → `code = "INTERNAL_ERROR"`, thông báo cố định "Internal server error.", không stack
     trace, không thông điệp gốc (có thể chứa chuỗi kết nối hoặc PII). Đây là **mã mới** chưa có trong `06`; nếu
     nhóm đồng ý cần bổ sung vào `06` mục 1.1 + `CHANGELOG`, nếu không thì chọn mã khác.
  2. Lỗi Pydantic → `422 VALIDATION_ERROR`, `details.errors` chỉ gồm `loc`, `type`, `msg` (không trả lại giá trị
     đầu vào). HTTPException: 401 → `AUTH_INVALID`, 403 → `FORBIDDEN`, 404 → `NOT_FOUND`, 4xx khác (400, 405…)
     → `VALIDATION_ERROR`.
  3. `GET /health` khi DB lỗi trả `503` với thân health (`status = "error"`, `db = "unavailable"`), không dùng
     định dạng lỗi, để công cụ uptime/smoke đọc được (06 mục 15).

## ASM-006 — Quy tắc ghi nhân sự chưa ghi trong `06` mục 13

- **Ngày:** 2026-11-07
- **Trạng thái:** đề xuất của Dev 1 (M3-A), chờ nhóm xác nhận trong review PR. Không sửa `05`/`06`.
- **Bối cảnh:** `06` mục 13 cho đường dẫn và thân của `POST /employees/{id}/assignments`, `POST …/terminate`,
  `PUT /locations/{id}/managers`, `PATCH /locations/{id}/owner` nhưng không nêu phản hồi và một số quy tắc biên.
- **Diễn giải:**
  1. **Phản hồi:** trả lại tài nguyên theo schema đọc đã duyệt `06` v1.3 mục 13.1 (`EmployeeOut` / `LocationOut`,
     góc nhìn admin). Thân `PATCH …/owner` là `{ "owner_employee_id": <id> }` (tên cột `05`).
  2. **Chuyển công tác:** `start_date` ≥ hôm nay (múi giờ market) và ≥ `hire_date`; phải sau ngày bắt đầu của
     phân công đang mở; phân công cũ đóng `end_date = start_date − 1`. Cùng địa điểm → `422`. Địa điểm khác market
     hoặc đã đóng → `422`.
  3. **Quản lý không được chuyển hoặc nghỉ khi còn giữ vai trò quản lý** (hiện tại hoặc tương lai) tại địa điểm cũ:
     `422` (`details.field = employee_id`). Admin thay quản lý trước, để không địa điểm nào mất quản lý chính ngầm.
  4. **Nghỉ việc:** `status = terminated`, `employee.end_date` = hôm nay, phân công còn hiệu lực sau hôm nay
     đóng ở hôm nay, `app_user.is_active = false`. Nhân viên có phân công bắt đầu trong tương lai → `422`.
     Không xóa bản ghi.
  5. **Đổi quản lý:** bản ghi đang mở của cấp đổi người → `valid_to = max(valid_from, hôm nay) − 1`. Bản ghi bắt
     đầu từ hôm nay trở đi trở thành "không bao giờ hiệu lực" nhưng vẫn giữ lịch sử. Người mới có
     `valid_from` = hôm nay. Cấp không đổi người giữ nguyên bản ghi. `deputy_employee_id` vắng / `null` → đóng phó
     hiện tại.
  6. **Owner mặc định** (US-EMP-01 AC4): khi đổi quản lý chính, owner trống hoặc đang là quản lý chính cũ → chuyển
     sang quản lý chính mới. Owner do admin gán riêng được giữ.
  7. Các thay đổi này **không ghi `decision_log`**: `04` mục 10 không có mã hành động cho phân công / quản lý, và
     thêm mã là thay đổi hợp đồng.
- **Cần nhóm xác nhận:** các mục 2 (cấm ngày quá khứ), 3, 4 và 7.

## ASM-007 — Quy tắc điểm danh chưa ghi trong `06` mục 13

- **Ngày:** 2026-11-07
- **Trạng thái:** đề xuất của Dev 1 (M3-B), chờ nhóm xác nhận. Không sửa `05`/`06`.
- **Diễn giải** cho `PUT /warehouses/{id}/attendance` (tầng service `hr_service.set_attendance`):
  1. **Roster** của kho trong ngày là các dòng `hr.attendance` của ngày đó mà nhân viên có phân công hiệu lực tại kho
     hôm đó và chưa `terminated` (US-WH-01 AC3). Service **không tạo dòng mới**: dòng `planned` do job
     `attendance_gen` sinh. Nhân viên trong `items` mà không có dòng trong roster → `422` (`details.field = items`).
  2. `all_present` đặt mọi dòng của roster **trừ `leave`** thành `present` bằng một câu UPDATE, rồi `items` ghi đè.
     Trạng thái hợp lệ trong `items`: `present`, `absent`, `leave` (`planned` chỉ do job sinh).
  3. Chỉ vai trò `warehouse` của chính kho đó được ghi (06 mục 13). Admin/dispatcher chỉ đọc → `403`. Kho khác,
     cửa hàng hoặc id không tồn tại → `404`.
  4. `ATTENDANCE_CHANGED` ghi mỗi lần lưu: trước/sau là số đếm theo trạng thái, `snapshot.changed_employee_ids` chỉ
     chứa id (không có tên).
  5. Không giới hạn ngày (quá khứ / tương lai). Đây là câu hỏi mở cho nhóm.
- **Câu hỏi mở cho `attendance_gen`** (chưa làm): kho có nhiều ca trong một ngày thì nhân viên được xếp vào ca nào?
  `05` không có bảng gán nhân viên–ca. Cần nhóm chốt trước khi viết job.
