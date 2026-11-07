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
