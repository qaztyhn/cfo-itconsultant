# M0 — Bàn giao Backend lõi (Dev 1)

> Trạng thái: **mã M0 của Dev 1 đã xong và xanh CI trên từng PR; M0 CHƯA hoàn thành** cho tới khi kiểm chứng
> tích hợp cùng Dev 2 (mục 5). Không chứa mật khẩu, khóa hay giá trị biến môi trường (`09` bất biến 25).

## 1. Thứ tự merge (PR xếp chồng)

| Bước | PR | Nhánh → base | Nội dung | Điều kiện merge |
|---|---|---|---|---|
| 1 | qaztyhn/cfo-itconsultant#2 | `feat/m0-backend-foundation` → `main` | Alembic env, `0001`, fixture PostgreSQL | Review |
| 2 | qaztyhn/cfo-itconsultant#4 | `feat/m0-db-ref-hr` → #2 | `0002_ref`, `0003_hr`, ASM-001 | Review |
| 3 | qaztyhn/cfo-itconsultant#5 | `feat/m0-db-stg-ops` → #4 | `0004_stg`, `0005_ops` | Review |
| 4 | qaztyhn/cfo-itconsultant#6 | `feat/m0-db-plan-audit` → #5 | `0006`–`0008` (trigger, view, seed tham chiếu) | Review + **chốt ASM-002** |
| 5 | qaztyhn/cfo-itconsultant#7 | `feat/m0-auth` → #6 | Auth JWT/argon2, RBAC, `log_event` | Review + **chốt ASM-003** |
| 6 | qaztyhn/cfo-itconsultant#8 (draft) | `feat/m0-foundation-health` → #7 | Lỗi chuẩn, `record_decision`, `/health` | Review + **duyệt đề xuất `06` v1.2.1 + `CHANGELOG`**; Dev 2 review phần xóa stub ở `admin.py` |

Cách merge an toàn cho PR xếp chồng:
- Merge **theo đúng thứ tự** trên, dùng **"Create a merge commit"** (không squash). Squash làm các PR sau mang lại
  commit cũ và sinh xung đột.
- Sau mỗi lần merge, đổi base của PR kế tiếp sang `main` (GitHub tự đổi nếu nhánh base bị xóa khi merge) và chờ CI
  xanh lại trước khi merge tiếp.
- Nếu nhóm vẫn muốn squash: sau khi squash một PR, Dev 1 rebase nhánh kế tiếp lên `main` mới (không force-push
  lên nhánh người khác đang dùng; báo trước).

## 2. Migration

Yêu cầu: PostgreSQL 16; user có quyền tạo extension `pgcrypto`, `btree_gist`, `pg_trgm` (trusted extension: chủ
database là đủ). Thứ tự: `0001` → … → `0008` (head).

| Việc | Lệnh (từ thư mục gốc repo) |
|---|---|
| Nâng lên head (máy dev, venv backend đã kích hoạt) | `make migrate` (kiểm phụ thuộc rồi `cd backend && alembic upgrade head`) |
| Nâng lên head trong Docker | `make migrate-docker` |
| Xem phiên bản hiện tại | `cd backend && alembic current` → `0008 (head)` |
| Gỡ toàn bộ (chỉ DB dev/test) | `cd backend && alembic downgrade base` |

- `alembic/env.py` đọc `DATABASE_URL` (chấp nhận `postgresql://…` hoặc `postgresql+asyncpg://…`; mật khẩu
  URL-encode như `%40` dùng được). Không in URL ra log.
- `0008` chỉ seed tham chiếu: market SE + `MarketConfig` mặc định, N1–N6, special flags, 14 position, 26 cặp
  `order_transition`. **Không** có tài khoản, nhân viên, mật khẩu, ngày lễ, dữ liệu demo.
- `/health` trả `503` khi DB chưa migrate (bảng chưa có), nên smoke phải chạy migration **trước** khi kiểm CFO.

## 3. Cấu hình cho auth và health

| Biến | Bắt buộc | Ghi chú |
|---|---|---|
| `DATABASE_URL` | Có | Như mục 2 |
| `JWT_SECRET` | **Có** | Không có giá trị mặc định. Thiếu → mọi lệnh phát/kiểm token lỗi (`500`), tức **fail closed**. Dùng chuỗi ngẫu nhiên dài, khác nhau theo môi trường |
| `JWT_TTL_HOURS` | Không | Mặc định 8 (`06` mục 4, `expires_in = 28800`) |
| `APP_ENV` | Không | `local` → ghi thêm `logs/<service>/<ngày>.jsonl`; `test` → không ghi file; còn lại → chỉ stdout |
| `APP_NOW` | Không | Cố định đồng hồ demo (`2026-11-04T10:05:00+01:00`); hạn token tính theo đồng hồ này |
| `CORS_ORIGINS` | Không | Dạng JSON list, mặc định `["http://localhost:5173"]` |
| `TEST_DATABASE_URL` | Cho test | Server PostgreSQL mà user có quyền `CREATE DATABASE`; mỗi test tạo DB trống riêng |

Hành vi cần biết khi tích hợp:
- **Đăng nhập:** `POST /api/v1/auth/login` `{email, password}` → `access_token`, `expires_in`, `user`. Email không phân
  biệt hoa thường. Mọi lỗi đăng nhập trả cùng `401 AUTH_INVALID`.
- **Giới hạn tần suất:** quá 5 lần thử/phút **theo IP client** → `429` (ASM-003). Script smoke không nên đăng nhập
  lặp nhiều lần; sau Docker/reverse proxy, các client có thể chung một IP.
- **`/auth/me`** đọc lại hồ sơ từ DB mỗi request: khóa `app_user.is_active` hoặc nhân viên `terminated` → token
  bị từ chối ngay ở lần gọi kế (US-EMP-03 AC4).
- **`GET /api/v1/health`** công khai: `200 {status:"ok", db:"ok", last_sync_age_min, notify_queue}`; DB lỗi → `503
  {status:"error", db:"unavailable"}`. `tools/m0_smoke.py` kiểm `status == ok` và `db == ok`.
- **`X-Correlation-ID`:** chỉ chấp nhận UUID; giá trị khác được thay bằng UUID mới và trả lại trong header.

### Tài khoản seed tối thiểu (yêu cầu cho Dev 2, `08` mục 5.4)
- Mật khẩu đọc từ `SEED_DEMO_PASSWORD`, băm bằng `app.core.security.hash_password()` (argon2id); không ghi vào file.
- Mỗi tài khoản người: `hr.employee` (market SE) + `ref.app_user` (`employee_id`, `roles`, `kpi_scopes`) + **một**
  `hr.employee_assignment` đang hiệu lực (để `location_ids` đúng). `roles`/`kpi_scopes` sao từ
  `hr.position.default_roles` / `default_kpi_scopes` đã seed ở `0008`.
- Tối thiểu để kiểm M0: `dispatcher@cfo.demo` (`{dispatcher}`, `{ops}`), `admin@cfo.demo` (`{admin}`), một tài khoản
  vai trò khác (ví dụ `sales@cfo.demo`) để kiểm đường bị cấm, `owner@cfo.demo` (`{viewer}`, `{revenue_all}`),
  `projectlead@cfo.demo` (`{viewer}`, `{ops}`). Công nhân kho **không** có `app_user`.
- Demo bật GPS: seed demo đặt `ref.market.gps_enabled = true` cho SE (`08` mục 5.1); migration để `false` (ASM-002).

## 4. Trạng thái giả định / hợp đồng

| Mục | Trạng thái | Chốt ở |
|---|---|---|
| ASM-001 cột chung `created_at`/`updated_at` cho 57 bảng | **Đã chốt** (không ngoại lệ) | — |
| ASM-002 diễn giải seed `0008` (vai trò "system" = mảng rỗng, `gps_enabled=false`, `min_crew` N2 = 1, nhóm position) | **Chờ duyệt** | PR #6 |
| ASM-003 chi tiết auth (khóa giới hạn theo IP, `429` dùng `AUTH_INVALID`, logout `204`, tài khoản hệ thống) | **Chờ duyệt** | PR #7 |
| ASM-004 → đề xuất `06` §1.1 v1.2.1 (`INTERNAL_ERROR`, `NOT_FOUND`) + `CHANGELOG` | **Chờ duyệt — chặn merge PR #8** | PR #8 |
| Cấm UPDATE POD cũ (`09` bất biến 22) | Không có trigger DB trong `05`; thực thi ở `execution_service` (M6) trừ khi nhóm sửa `05` | Nhóm |
| `contracts/cfo.openapi.json` | Chưa có baseline đã duyệt; CI báo NOT VERIFIED | Nhóm |

## 5. Kiểm chứng tích hợp chung (Dev 1 + Dev 2) — điều kiện để báo M0 xong

Chạy trên stack Docker Compose sau khi các PR trên và phần của Dev 2 (seed tài khoản, smoke có migration) đã vào:

| # | Bước | Kỳ vọng |
|---|---|---|
| 1 | `docker compose up -d` | 5 service chạy |
| 2 | `make migrate-docker` trên DB trống | `alembic current` = `0008 (head)` |
| 3 | Seed tài khoản tối thiểu (Dev 2) | Không có mật khẩu trong file/log |
| 4 | `GET /api/v1/health` (CFO) và nguồn | `200`, `status=ok`, `db=ok` |
| 5 | Đăng nhập `dispatcher@cfo.demo` | `200`, `expires_in=28800`, `user.roles=["dispatcher"]`, `location_ids` đúng phân công |
| 6 | `GET /api/v1/auth/me` với token | Trùng `user` của bước 5 |
| 7 | `/auth/me` không token / token sai | `401 AUTH_INVALID` kèm `correlation_id` |
| 8 | Khóa tài khoản (`is_active=false`) rồi gọi lại `/auth/me` | `401` |
| 9 | `python tools/harness.py verify` và `smoke` | `HARNESS PASS` từ cùng một môi trường |

Bằng chứng đã có (chưa thay thế bước trên): CI từng PR (#8: backend 115 passed, source, frontend xanh);
local: `make migrate` trên DB trống, uvicorn, `/health` 200, login + `/auth/me` đúng hợp đồng, `harness verify`
và `smoke` PASS bằng tiến trình local (không phải Docker — môi trường Dev 1 không có Docker daemon).
