# Dev 1 — Backend Core: tiến độ

> Cập nhật: 2026-11-06. File theo dõi trên nhánh `chore/dev1-progress` (không sửa trực tiếp trên `main`).
> Mọi PR đều chưa merge; Dev 1 không tự merge. "CI" = backend + source + frontend của workflow `ci`.

## 1. PR theo chuỗi phụ thuộc

### Chuỗi M0 → M1 (stack 1: migration → auth → nền tảng)
| PR | Nhánh → base | Nội dung | Test | Trạng thái |
|---|---|---|---|---|
| qaztyhn/cfo-itconsultant#2 | `feat/m0-backend-foundation` → `main` | Alembic env, `0001`, fixture PG, sửa `%` DSN | CI ✅ | Chờ review |
| qaztyhn/cfo-itconsultant#4 | `feat/m0-db-ref-hr` → #2 | `0002`, `0003`, ASM-001 | CI ✅ | Chờ review |
| qaztyhn/cfo-itconsultant#5 | `feat/m0-db-stg-ops` → #4 | `0004`, `0005` | CI ✅ | Chờ review |
| qaztyhn/cfo-itconsultant#6 | `feat/m0-db-plan-audit` → #5 | `0006`–`0008` | CI ✅ | Chờ review + **ASM-002** |
| qaztyhn/cfo-itconsultant#7 | `feat/m0-auth` → #6 | JWT/argon2/RBAC, `/auth/*`, `log_event` | CI ✅ | Chờ review + **ASM-003** |
| qaztyhn/cfo-itconsultant#8 (draft) | `feat/m0-foundation-health` → #7 | Lỗi chuẩn, `record_decision`, `/health`, bàn giao M0 | CI ✅ | **Chờ duyệt `06` v1.2.1** |
| qaztyhn/cfo-itconsultant#9 | `feat/m1-models-ref-hr` → #6 | Model ref/hr + test drift | CI ✅ | Chờ review |
| qaztyhn/cfo-itconsultant#10 | `feat/m1-models-stg-ops` → #9 | Model stg/ops | CI ✅ | Chờ review |
| qaztyhn/cfo-itconsultant#11 | `feat/m1-models-plan-audit` → #10 | Model plan/audit, view chỉ đọc (57 bảng) | CI ✅ | Chờ review |
| qaztyhn/cfo-itconsultant#12 (draft) | `chore/m1-hr-read-api-proposal` → `main` | Đề xuất hợp đồng Q1–Q4 | — | **Chờ nhóm chốt** |

### Service trên model (xếp chồng #11, chưa có router vì cần auth #7)
| PR | Nhánh → base | Milestone | Nội dung | Stories | Trạng thái |
|---|---|---|---|---|---|
| qaztyhn/cfo-itconsultant#21 | `feat/m3-backend-capacity-context` → #11 | M3 | `hr_service.day_capacities` | US-WH-02 | CI ✅ |
| qaztyhn/cfo-itconsultant#22 | `feat/m4-backend-planning-context-stock` → #11 | M4 | Tồn khả dụng, hàng nhập, tuyến | US-ATP-01 AC1/AC3 | CI ✅ |
| qaztyhn/cfo-itconsultant#23 | `feat/m4-backend-planning-context-fleet` → #22 | M4 | Ngữ cảnh xe/tài xế | US-PLN-03 AC3–AC5 | CI ✅ |
| qaztyhn/cfo-itconsultant#24 | `feat/m8-backend-revenue-service` → #11 | M8 | `revenue_service` scope/summary/daily/by-location | US-REV-01 AC1–5, 7, 10 | CI ✅ |
| qaztyhn/cfo-itconsultant#25 | `feat/m7-backend-alert-service` → #11 | M7 | `alert_service` raise/ack/resolve | US-RSK-03 AC2–AC3 | CI ✅ |

### Engine thuần (độc lập DB/auth)
| PR | Nhánh → base | Milestone | Nội dung | Stories | Trạng thái |
|---|---|---|---|---|---|
| qaztyhn/cfo-itconsultant#13 | `feat/m4-backend-engine-workload-capacity` → `main` | M4 | Khối lượng việc, công suất ngày | US-PLN-01, US-WH-02 | CI ✅ |
| qaztyhn/cfo-itconsultant#14 | `feat/m4-backend-engine-atp` → #13 | M4 | ATP theo thời gian | US-ATP-01 | CI ✅ |
| qaztyhn/cfo-itconsultant#15 | `feat/m4-backend-engine-schedule` → #13 | M4 | Lịch chuẩn bị, giờ cắt | US-PLN-02 | CI ✅ |
| qaztyhn/cfo-itconsultant#16 | `feat/m4-backend-engine-ranking` → #13 | M4 | Gate, xếp hạng, giải thích | US-PLN-06/07/08 | CI ✅ |
| qaztyhn/cfo-itconsultant#19 | `feat/m4-backend-engine-delivery-dates` → #13 | M4 | Xe/tài xế hợp lệ, ngày giao, dự trữ | US-PLN-03/04/05 | CI ✅ |
| qaztyhn/cfo-itconsultant#17 | `feat/m4-backend-engine-transfer-mapping` → `main` | M4/M2 | Gợi ý chuyển kho, ứng viên ánh xạ | US-ATP-02, US-PRD-01 | CI ✅ |
| qaztyhn/cfo-itconsultant#18 | `feat/m7-backend-engine-forecast` → `main` | M7 | Dự báo ETA, phân loại rủi ro | US-RSK-01/02 | CI ✅ |
| qaztyhn/cfo-itconsultant#20 | `feat/m4-backend-engine-config` → `main` | M4 | `MarketConfig` → `EngineConfig` | (nền US-PLN) | CI ✅ |

Thứ tự merge gợi ý: stack 1 theo bảng đầu (merge commit, không squash); các PR engine vào `main` bất kỳ lúc nào
(#13 trước #14/#15/#16/#19); các PR service sau khi #11 vào `main`.

## 2. Kiểm tra đã chạy
- Mỗi PR: `tools/harness.py backend` PASS (ruff, black, mypy strict engine, import-linter, pytest) trên PostgreSQL 16
  local + mypy cho từng file đã sửa; CI GitHub xanh cho mọi PR trên.
- Cuối M0 (trên #8): `tools/harness.py verify` PASS (backend 100, frontend lint/test/build, source 17) và `smoke`
  PASS bằng tiến trình local (không có Docker daemon trong môi trường Dev 1).
- Hai lần commit chưa sạch trong phiên (lint trên #14, mypy trên #23) đã được sửa bằng commit bổ sung, không force push.

## 3. Bị chặn / chờ quyết định
| Hạng mục | Lý do | Cần ai |
|---|---|---|
| Engine bước 2d chọn **bộ nhiều xe**, chia hàng, đồng bộ giờ tới; `planner.plan_order`; US-PLN-03 AC1, US-ORD-05 | `AGENTS.md` yêu cầu nhóm sửa gạch đầu dòng cũ ở `09` §13 (mâu thuẫn bất biến 10) **trước** khi làm | Nhóm |
| `planning_service.plan()`, `POST /orders/{id}/plan` | Cần `planner` (trên) + auth (#7) | Nhóm, merge |
| API `/employees`, `/locations`, `/vehicles` (M1-D…G) | Đề xuất Q1–Q4 (#12) chưa chốt | Nhóm |
| Service cần **cả** model (#9–#11) và `record_decision`/auth (#7–#8): M2 mapping confirm, M5 giữ chỗ/duyệt/hold expiry, M6 execution, revenue export CSV, router `/revenue/*`, `/alerts` | Hai stack tách nhau từ #6; PR gộp sẽ lặp thay đổi chưa merge | Merge #7/#8 và #9–#11 vào `main` |
| `INTERNAL_ERROR` / `NOT_FOUND` trong `06` §1.1 | Đề xuất v1.2.1 (#8) | Nhóm |
| `audit.v_kpi_daily`, `kpi_service` (M8) | `05` chưa có DDL cho view | Nhóm (bổ sung `05`) |
| Cấm UPDATE POD cũ ở tầng DB | `05` không có trigger; thực thi ở `execution_service` (M6) trừ khi nhóm sửa `05` | Nhóm |
| M0 hoàn thành | Chờ Dev 2: seed tài khoản, smoke có migration, kiểm 9 bước (`docs/M0_BACKEND_HANDOFF.md` trên #8) | Dev 2 |
| ASM-002, ASM-003 | Chờ duyệt trên #6, #7 | Nhóm |

## 4. Việc còn lại khi hết chặn (theo `10` §2)
- M2: `order_service.prepare_for_planning`, `mapping_service` (confirm/reject, N6 không FRAGILE), API orders/mapping.
- M3: API điểm danh/ca/nhân sự (ghi), `jobs/attendance_gen`.
- M4: chọn bộ nhiều xe + `planner` + `planning_service.plan()` + API planning.
- M5: reservation (hold/extend/expiry), approval (advisory lock theo thứ tự), manual plan, replan suggestion, `close_active_plan`, transfer, Idempotency-Key.
- M6: execution (sự kiện theo xe, Pause/Resume, POD theo trip_stop), `/driver/trips`, prep-queue.
- M7: `risk_service` (dùng `engine/forecast`), nháp DELAY, router `/alerts`.
- M8: `kpi_service` (sau khi có DDL), revenue orders/export + router, `/audit/decisions`, `nightly_metrics`.
- M9: kiểm quyền mọi hàng ma trận `06` §3, hiệu năng (< 2 s/đơn, bảng đơn < 1 s).
