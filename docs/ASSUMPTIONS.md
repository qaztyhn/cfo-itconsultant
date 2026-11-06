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
