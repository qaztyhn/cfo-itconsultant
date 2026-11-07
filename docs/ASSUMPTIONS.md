# Assumptions (ASM-xxx)

## Sổ quyết định đã chốt (cập nhật 2026-11-07)

**Mục đích:** đây là nơi tập trung ghi nhận **tất cả assumption/quyết định nghiệp vụ đã được chủ dự án hoặc nhóm có thẩm quyền xác nhận**, không chỉ những chỗ còn mơ hồ. Giữ nguyên mã `ASM-xxx` cũ; các quyết định sản phẩm liên chủ đề dùng mã `DEC-xxx` để tránh trùng với ASM do Dev đề xuất (như ASM-008 ở PR #55).

**Nguồn và mức độ hiệu lực:** quyết định đã duyệt được ghi ở đây là **ràng buộc về nghiệp vụ**; `05`/`06`/`04` và `09` vẫn phải được đồng bộ bằng PR được review. Ghi vào sổ **không có nghĩa code, migration hay kiểm thử đã hoàn thành**. Không tự đổi API/DDL chỉ vì có một đoạn giải thích trong sổ. Nếu có mâu thuẫn, dừng thay đổi liên quan và mở PR đồng bộ đặc tả.

| ID | Quyết định được xác nhận | Ngày | Bằng chứng / chi tiết | Tình trạng triển khai |
|---|---|---|---|---|
| [ASM-001](#asm-001--cột-chung-created_at--updated_at-cho-mọi-bảng-cfo) | Cột metadata chung cho 57 bảng CFO, không áp dụng `src_*`; log bất biến | 06/11 | Xem mục ASM-001 | Đã chốt quy tắc; cần test theo migration |
| [ASM-002](#asm-002--diễn-giải-seed-tham-chiếu-0008_seed_reference) | Seed tham chiếu tách seed demo; GPS migration mặc định tắt, không seed mật khẩu | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Đã duyệt hướng; kiểm tra seed/test |
| [ASM-003](#asm-003--chi-tiết-xác-thực-chưa-có-trong-06-mục-4) | Login tối đa 5 lần/60 giây/IP cho demo một instance; 429; 204 logout; hạn chế lộ thông tin | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Đã duyệt hướng; cần xác minh code |
| [ASM-005](#asm-005--quy-tắc-xác-nhận--từ-chối-ánh-xạ-và-phạm-vi-đơn-cfo) | Chỉ đơn **100% SKU confirmed** dùng CFO; thiếu SKU dùng quy trình cũ | 07/11 | [PR #49](https://github.com/qaztyhn/cfo-itconsultant/pull/49) | Nghiệp vụ đã duyệt; routing code còn phụ thuộc Q14 |
| [ASM-006](#asm-006--quy-tắc-ghi-nhân-sự-chưa-ghi-trong-06-mục-13) | Chuyển/nghỉ việc có người thay quản lý; khóa tài khoản, giữ lịch sử và audit | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Nghiệp vụ đã duyệt; mã audit đề xuất ở Q13 |
| [ASM-007](#asm-007--quy-tắc-điểm-danh-chưa-ghi-trong-06-mục-13) | Warehouse Manager quyết định lịch người–ca; `expected_staff` **chỉ để so sánh** | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Cần lịch chính thức, migration/API |
| [DEC-SALES-001](#dec-sales-001--sales-xác-nhận-có-điều-kiện-và-sync-now) | Sales dùng CFO riêng, sync-now; chỉ confirm phương án chuẩn an toàn | 07/11 | [PR #43](https://github.com/qaztyhn/cfo-itconsultant/pull/43) | Docs đã merge, code theo milestone |
| [DEC-ROUTING-001](#dec-routing-001--sales-kiểm-cfo-trước-khi-điều-phối-thủ-công) | Sales phải kiểm CFO trước khi điều phối tay; luồng CFO/legacy không tự đảo | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) | Quy tắc duyệt; chi tiết Q14 vẫn chờ migration/API |
| [DEC-SHIFTS-001](#dec-shifts-001--q12-lịch-làm-chính-thức-của-kho-và-tài-xế) | Q12a–d: 1 ca/người/ngày, manager chính/phó có quyền, hồi tố có lý do, thiếu lịch thì 0 công suất | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) | Quy tắc duyệt; bảng/API đề xuất cần review |
| [DEC-AUDIT-001](#dec-audit-001--q13-mã-nhật-ký-nhân-sự) | Q13 chấp thuận 3 mã audit mới và quy tắc hồi tố | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) | Chờ cập nhật contract/code |
| [DEC-DRIVER-001](#dec-driver-001--khung-giờ-làm-nghỉ-và-giới-hạn-lái-xe) | Kiểm ca tài xế và nhân viên kho; nghỉ mặc định 11h; lái xe/nghỉ theo phạm vi pháp luật | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53), [PR #54](https://github.com/qaztyhn/cfo-itconsultant/pull/54) | Quy tắc MVP đã duyệt; engine/schema cần nghiệm thu |

**Không nằm trong bảng đã duyệt:** [ASM-004](#asm-004--mã-lỗi-cho-lỗi-kỹ-thuật-ngoài-danh-sách-06-mục-11) đang được file này ghi **chờ phê duyệt hợp đồng**; không ngầm chuyển sang “đã chốt”. ASM-008 của Dev 3 trong PR #55 cũng là **đề xuất chưa duyệt**. Câu hỏi hoặc phương án do Dev tự nêu không mặc nhiên trở thành quyết định đã chốt.

### Cách ghi nhận quyết định mới — bắt buộc

1. **Chỉ sau khi có xác nhận rõ ràng từ owner/nhóm có thẩm quyền**, bổ sung/sửa một mục tại **`docs/ASSUMPTIONS.md`** trong PR hiện tại hoặc PR tài liệu riêng. Không ghi “đã chốt” cho suy đoán, bình luận chưa được chấp thuận, hoặc PR chưa review.
2. Mỗi bản ghi phải có **mã duy nhất, ngày, người/phạm vi phê duyệt, câu chốt nguyên nghĩa, trường hợp biên, nguồn (URL PR/comment), tài liệu/code bị ảnh hưởng, tình trạng triển khai**. Nếu thay đổi quyết định cũ, ghi **superseded by** và giữ lịch sử, không xóa.
3. **Cùng PR** cập nhật các hợp đồng `01`–`09` liên quan và `docs/CHANGELOG.md` khi thay đổi API/DDL/quyền/bất biến; thêm migration và test khi triển khai code. Không được âm thầm code chỉ từ đề xuất.
4. Trước khi tạo PR Dev phải **đọc sổ và kiểm tra quyết định mới nhất**; PR description và checklist phải có dòng “Assumptions: reviewed / new decision IDs / none”. Reviewer từ chối merge nếu PR làm trái quyết định chốt hoặc thiếu ghi nhận.
5. Khi chủ dự án chốt thêm trong **cuộc trò chuyện**, trợ lý cập nhật file qua GitHub ngay **nếu có quyền công cụ tại lượt đó**; nếu không có quyền thì soạn bản vá/prompt để Dev cập nhật. **Không có tiến trình tự chạy/giám sát GitHub liên tục**, nên không thể tự cập nhật file khi không có tương tác.

---

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
- **Trạng thái:** **chủ dự án chấp thuận hướng ASM-002 ngày 07/11/2026** cho MVP. Các chi tiết seed được giữ như danh sách bên dưới; test/migration vẫn phải xác minh trước khi coi là đã chạy.
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
- **Trạng thái:** **chủ dự án chấp thuận hướng ASM-003 ngày 07/11/2026** cho MVP. Giới hạn login 5 lượt/phút/IP chỉ là giới hạn demo một instance; triển khai nhiều instance phải dùng shared rate limiter, không tuyên bố đây là phòng chống brute-force hoàn chỉnh.
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

## ASM-005 — Quy tắc xác nhận / từ chối ánh xạ và phạm vi đơn CFO

- **Ngày:** 2026-11-07
- **Trạng thái:** chủ dự án chốt **quy tắc phân luồng** ngày 2026-11-07: đơn có bất kỳ SKU chưa mapping confirmed không dùng CFO, tiếp tục quy trình cũ. Quy tắc xử lý task xác nhận/từ chối chi tiết bên dưới vẫn cần rà soát và được triển khai bằng PR code riêng.
- **Quyết định phạm vi:** ban đầu IT xác nhận khoảng 100 SKU để phục vụ pilot, sau đó mở rộng dần. Mỗi đơn chỉ đủ điều kiện **đưa vào luồng điều phối CFO nếu 100% SKU của đơn đã mapping confirmed**; số 100 là phạm vi danh mục pilot, không phải giới hạn cố định. Nếu thiếu dù chỉ một SKU, **toàn bộ đơn tiếp tục theo quy trình xử lý cũ**, không chờ IT trong CFO, không giữ chỗ, không lập kế hoạch và không được CFO duyệt/xác nhận.
- **Bối cảnh phần mapping:** `06` mục 12/12.1 và US-PRD-02/03 chưa mô tả đủ trạng thái task xác nhận/từ chối, ai ghi `mapped_by` và lý do từ chối được trình bày ở đâu.
- **Diễn giải:**
  1. Chỉ `admin` **có hồ sơ nhân viên** được xác nhận/từ chối: `ck_se_confirmed` bắt buộc `mapped_by`
     (FK `hr.employee`). Admin hệ thống không có nhân viên → `403 FORBIDDEN`.
  2. Sau xác nhận hoặc từ chối, `mapping_task.status = done`, `resolved_by` = nhân viên, `resolved_at` = clock.
  3. Task đã `done` **không từ chối lại** được (`422 VALIDATION_ERROR`, `details.field = status`). SKU đã
     `confirmed` không từ chối được (`details.field = mapping_status`), vì đơn đã lập kế hoạch đang dùng ánh xạ đó.
  4. Task đã từ chối **vẫn xác nhận được** (nguồn có thể bổ sung dữ liệu sản phẩm); thay đổi được ghi
     `MAPPING_CONFIRMED` với trước/sau.
  5. IT ghi lý do từ chối trong `decision_log MAPPING_REJECTED` và trên mapping task/SKU cho đội IT. **Không** gắn đơn chưa mapping vào hàng đợi Dispatcher để chờ xử lý; đơn đó tiếp tục quy trình cũ. Cách hiển thị chi tiết lý do từ chối tại IT cần chốt trong contract API.
  6. `blocked_order_count` hiện là trường legacy gắn với đơn `BLOCKED_UNMAPPED_SKU`; với quyết định mới **không được dùng làm hàng đợi chờ đơn CFO**. Dev phải đề xuất cách thể hiện số SKU/tần suất đơn không đủ điều kiện nếu cần KPI, không tự tái sử dụng trường này như số đơn đang chờ lập kế hoạch.
  7. SKU chưa có trong `product_<cc>` không xác nhận được (`details.field = local_sku`): cần đồng bộ sản phẩm
     trước, vì các cột tên/đơn vị bán là NOT NULL.
- **Quy tắc chống trùng và ranh giới:** phân luồng phải xảy ra **trước khi CFO tạo planning run/hold hoặc cam kết nguồn lực**. Dữ liệu POS/WMS/ERP giữ nguyên, CFO chỉ GET; việc xử lý theo quy trình cũ vẫn do hệ thống/quy trình hiện tại đảm nhiệm. Việc IT mapping sau này **không tự chuyển** đơn đã đi quy trình cũ vào CFO. Cần cơ chế bền vững để nhận diện đơn đã được xử lý ở luồng cũ và ngăn hai luồng xử lý cùng một đơn; chưa có hợp đồng dữ liệu đầy đủ cho cơ chế này, Dev phải đề xuất ở PR triển khai và kiểm tra khả năng API POS cung cấp trạng thái/owner luồng.
- **Chưa thay đổi triển khai:** logic hiện có `BLOCKED_UNMAPPED_SKU → SUBMITTED` và `mapping_service.confirm()` còn khác quyết định mới. Không dùng `HANDLED_EXTERNALLY` đã bỏ ở v1.2. Không được cho agent tự đưa đơn cũ về CFO bằng logic mở khóa hiện tại.
- **Còn cần nhóm rà soát:** chi tiết các mục 1, 3, 4 và thiết kế trạng thái/quyền sở hữu luồng để bảo vệ một đơn chỉ có một hệ thống điều phối.

## ASM-006 — Quy tắc ghi nhân sự chưa ghi trong `06` mục 13

- **Ngày:** 2026-11-07
- **Trạng thái:** **chủ dự án chấp thuận nguyên tắc ASM-006 ngày 07/11/2026**, có điều chỉnh bắt buộc: thay đổi nhân sự/quản lý/owner phải có audit, sửa dữ liệu quá khứ cần quyền + lý do. Các tình huống biên và schema/API cần test, chưa phải code đã hoàn thành.
- **Bối cảnh:** `06` mục 13 cho đường dẫn và thân của `POST /employees/{id}/assignments`, `POST …/terminate`,
  `PUT /locations/{id}/managers`, `PATCH /locations/{id}/owner` nhưng không nêu phản hồi và một số quy tắc biên.
- **Diễn giải:**
  1. **Phản hồi:** trả lại tài nguyên theo schema đọc đã duyệt `06` v1.3 mục 13.1 (`EmployeeOut` / `LocationOut`,
     góc nhìn admin). Thân `PATCH …/owner` là `{ "owner_employee_id": <id> }` (tên cột `05`).
  2. **Chuyển công tác:** thao tác thường cho phép `start_date` ≥ hôm nay (múi giờ market) và ≥ `hire_date`, phải sau ngày bắt đầu phân công đang mở; phân công cũ đóng `end_date = start_date − 1`. Cùng địa điểm, khác market, nơi đã đóng → `422`. **Điều chỉnh hồi tố** chỉ admin có quyền, kèm lý do bắt buộc, ghi log trước/sau trong cùng transaction; không âm thầm ghi đè lịch sử hoặc tạo hai phân công chồng ngày.
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
  7. **Bắt buộc ghi lịch sử.** Ghi `audit.decision_log` trong cùng transaction với các thao tác đổi phân công/chuyển công tác (`EMPLOYEE_ASSIGNMENT_CHANGED` đã có trong `04` mục 10), thay quản lý/owner, nghỉ việc và điều chỉnh hồi tố. Phải có `actor`, `before`, `after`, `correlation_id`; điều chỉnh hồi tố bắt buộc có lý do. Đối với các nghiệp vụ chưa có mã action chuẩn (đổi owner/quản lý/nghỉ việc), Dev đề xuất bổ sung mã vào `04`/`06`, test và CHANGELOG trước khi triển khai; **không bỏ audit**.
- **Đã chốt:** quản lý phải có người thay hợp lệ trước khi chuyển/nghỉ; tài khoản người nghỉ bị khóa và lịch sử không bị xóa; owner admin gán riêng được giữ. **Điều chỉnh hồi tố** được phép cho admin với lý do và log. **Chờ thiết kế kỹ thuật:** action codes còn thiếu, kiểm tra các ràng buộc ngày hiệu lực và test thao tác atomic.

## ASM-007 — Quy tắc điểm danh chưa ghi trong `06` mục 13

- **Ngày:** 2026-11-07
- **Trạng thái:** **chủ dự án chấp thuận ASM-007 với điều chỉnh Q11 ngày 07/11/2026**. Warehouse Manager là người tạo/sửa lịch làm chính thức của từng người, CFO không được tự xếp/đổi ca dựa theo `expected_staff`. Chỉnh điểm danh/lịch phải ghi lịch sử; sửa ngày quá khứ bắt buộc có quyền và lý do.
- **Diễn giải** cho `PUT /warehouses/{id}/attendance` (tầng service `hr_service.set_attendance`):
  1. **Roster** trong ngày được tạo từ **lịch phân ca chính thức do Warehouse Manager lưu**, sau khi kiểm nhân viên đang được phân công tại kho và chưa nghỉ việc. `hr.attendance` ghi điểm danh thực tế trên các lịch đó. Service không tự tạo lịch mới từ số lượng `expected_staff`; nhân viên không nằm trong lịch chính thức → `422` và yêu cầu quản lý cập nhật lịch trước. 
     **Schema hiện có chưa tách lịch phân ca cá nhân khỏi attendance**: Dev 1 phải đề xuất bổ sung cấu trúc dữ liệu (vd. `hr.employee_shift_schedule`) và migration trong PR code riêng, không âm thầm biến điểm danh thành nguồn phân ca.
  2. `all_present` đặt mọi dòng của roster **trừ `leave`** thành `present` bằng một câu UPDATE, rồi `items` ghi đè.
     Trạng thái hợp lệ trong `items`: `present`, `absent`, `leave` (`planned` chỉ do job sinh).
  3. **Warehouse Manager** có phân công quản lý hợp lệ tại đúng kho lập/sửa lịch phân ca. Điểm danh thực tế do tài khoản warehouse được phép của chính kho đó ghi theo phân quyền hiện hành; admin/dispatcher chỉ đọc điểm danh thường, không được tự phân ca thay Warehouse Manager. Ngoài kho → `404`, không đủ quyền → `403`. Cần chốt rõ guard theo chức danh ở API trước khi code.
  4. Mỗi lần ghi điểm danh phải có `ATTENDANCE_CHANGED` với before/after, changed employee IDs (không PII). Mỗi lần Warehouse Manager lập/đổi lịch nhân viên phải ghi `SHIFT_CHANGED`, actor, trước/sau, ngày hiệu lực. Mọi ghi log trong **cùng transaction** với thay đổi.
  5. Lịch phân ca chính thức cho tương lai do Warehouse Manager lập/sửa; điểm danh ghi đúng ngày làm, người được ủy quyền ở kho có thể ghi `present`/`absent`/`leave`. **Sửa dữ liệu quá khứ** chỉ với quyền hợp lệ, lý do bắt buộc và log, không sửa âm thầm. Việc `all_present` chỉ tác động những người có trong lịch ca chính thức, không tự thêm/đổi ca.
- **Q11 đã chốt:** `expected_staff` ở `shift_template` chỉ là **số lượng kế hoạch để so sánh**, không phải quota tự phân ca; không tự chia đều, không đưa nhân viên dư vào ca cuối. `attendance_gen` chỉ được tạo dòng `planned` từ **lịch người–ca đã được Warehouse Manager xác nhận**, không được tự suy lịch. Thiếu lịch chính thức → báo thiếu dữ liệu/công suất chưa xác minh, không làm giả danh sách nhân viên. **PR #37** đã được Dev 1 báo cập nhật Q11 theo ASM-007 trong comment, nhưng vẫn phải review/rebase trước khi merge; không áp dụng lại Q11=B cũ.

## DEC-SALES-001 — Sales xác nhận có điều kiện và sync-now

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #43 đã merge](https://github.com/qaztyhn/cfo-itconsultant/pull/43).
- Sales vẫn submit đơn trên POS; **CFO là ứng dụng độc lập, chỉ đọc POS/WMS/ERP**, không ghi ngược và không gộp database. Sales có `Sync now` để yêu cầu CFO đọc đơn ngay, polling 5 phút làm dự phòng.
- CFO **không tự phê duyệt**. Sales của đúng cửa hàng được **chủ động** confirm duy nhất phương án **rank 1 tiêu chuẩn**: cả 5 gate pass, reserve safe, **một xe**, nguồn mới và hold còn hạn; không ngoại lệ/transfer/manual/replan/đổi ngày. Dùng chung `ApprovalService` để kiểm tra lại và lock trước commit; trường hợp khác thuộc Dispatcher.
- FIFO là **thứ tự hiển thị** `submitted_at,id`, không ép mọi đơn được thực thi FIFO; không lấn nguồn lực đã `committed` cho đơn cũ. Đơn cũ chưa duyệt gây tranh chấp nguồn lực phải chuyển Dispatcher.
- **Triển khai:** [`docs/DECISION_SALES_CONFIRMATION.md`](DECISION_SALES_CONFIRMATION.md) là tài liệu chi tiết; phê duyệt nghiệp vụ **không đồng nghĩa** API/UI đã chạy end-to-end.

## DEC-ROUTING-001 — Sales kiểm CFO trước khi điều phối thủ công

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53 Q14](https://github.com/qaztyhn/cfo-itconsultant/pull/53), [ASM-005/PR #49](https://github.com/qaztyhn/cfo-itconsultant/pull/49).
- Quy trình: **(1)** Sales nhập/submit đơn POS → **(2)** Sales bắt buộc kiểm trạng thái tại CFO (`Sync & check routing`) **trước khi bắt đầu điều phối thủ công** → **(3)** toàn bộ SKU confirmed thì dùng CFO, có ít nhất một SKU chưa confirmed thì **toàn bộ đơn** dùng quy trình thủ công cũ.
- Quy tắc được duyệt của **Q14 = phương án A**: mỗi đơn nguồn chỉ có một quyết định phân luồng đã lưu (`cfo` hoặc `legacy`), không tự chuyển luồng theo bản cập nhật mapping về sau. `legacy` không có plan, hold, approve trong CFO. Dữ liệu chưa đủ/CFO hoặc nguồn không truy cập được = **unresolved**, **không được mặc định thành legacy hoặc xác nhận giao**.
- Quy trình cũ được nhân viên **điều phối thủ công**, không có hệ thống tự động điều phối cạnh tranh. Vì CFO không ghi ngược POS, bảng routing nội bộ **không tự ngăn** nhân viên đã thực hiện thủ công; cần bước xác nhận bàn giao/audit và cơ chế chống xử lý trùng trước rollout.
- **Thiết kế Dev đề xuất, chưa được xem là DDL/API đã duyệt:** bảng `ops.order_routing`, `routing-ack` với lựa chọn `legacy_acknowledged` / `manual_started`, routing từ polling, cách xử lý đơn cũ. Xem [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) và yêu cầu review implementation. **Chưa có quyết định cho phép tự động chuyển sang quy trình cũ khi CFO lỗi**; phải hỏi owner nếu muốn làm ngoại lệ.

## DEC-SHIFTS-001 — Q12 lịch làm chính thức của kho và tài xế

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53 Q12](https://github.com/qaztyhn/cfo-itconsultant/pull/53), [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50).
- **Q12a = A:** tối đa **1 ca chính thức/người/ngày** cho MVP. Ca có thể kéo qua ngày hôm sau; khi đánh giá xung đột phải kiểm cả khoảng thời gian, không chỉ ngày bắt đầu.
- **Q12b = A:** Warehouse Manager chính hoặc phó đang hiệu lực, có `can_approve=true`, được lập/cập nhật lịch chính thức cho nhân viên kho và **tài xế thuộc kho**. Dispatcher/admin chỉ đọc lịch theo đề xuất nghiệp vụ hiện tại; quyền ghi phải kiểm ở server theo kho.
- **Q12c = A:** quản lý được phép sửa lịch quá khứ với **lý do bắt buộc** và audit actor + before/after trong cùng transaction; không xóa lịch sử.
- **Q12d = A:** thiếu lịch chính thức thì `schedule_verified=false`, công suất xác minh = **0**; không tự tạo người dựa trên `expected_staff`.
- Lịch điểm danh thực tế tách lịch phân ca; `expected_staff` chỉ là **mục tiêu để so sánh**, không phải quota, không cho auto-assign/dồn nhân viên dư vào ca cuối. `attendance_gen` chỉ sao lịch do Manager xác nhận.
- **Thiết kế Dev đề xuất cần review:** một bảng `hr.employee_shift_schedule` cho kho và tài xế, ca tùy chỉnh, nghỉ giữa ca, API `shift-schedule`, lịch sử hủy/thay ca, quyền chi tiết, xử lý ca qua nửa đêm. Tham khảo [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53). Không tự coi schema đề xuất là migration đã chạy.

## DEC-AUDIT-001 — Q13 mã nhật ký nhân sự

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53 Q13](https://github.com/qaztyhn/cfo-itconsultant/pull/53), ASM-006.
- Chấp thuận các action codes: `LOCATION_MANAGER_CHANGED`, `LOCATION_OWNER_CHANGED`, `EMPLOYEE_TERMINATED`; chuyển công tác dùng `EMPLOYEE_ASSIGNMENT_CHANGED` đã có.
- Chỉnh hồi tố phân công phải là admin có quyền, `reason_code=retroactive`, có `reason_text`, không tạo hai phân công hiệu lực trùng khoảng. Mọi thay đổi nhân sự/quản lý/owner/termination phải được audit actor, before/after, correlation ID trong cùng transaction.
- **Triển khai:** bổ sung code chuẩn vào `04`/`06` và actions, migration/test khi thích hợp; không coi đã có đầy đủ code chỉ vì owner đồng ý mã.

## DEC-DRIVER-001 — Khung giờ làm, nghỉ và giới hạn lái xe

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) và [PR #54](https://github.com/qaztyhn/cfo-itconsultant/pull/54), bao gồm phê duyệt đề xuất cho 5 nước Bắc Âu (SE, DK, NO, FI, IS).
- **Bất biến lập kế hoạch:** thời gian chuẩn bị/lên hàng phải nằm trong **ca kho chính thức có công suất**, và **toàn bộ ca nhiệm vụ tài xế** phù hợp lịch làm **chính thức của chính tài xế đó** (lên hàng/chờ, chạy xe, dỡ hàng, quay lại kho khi thuộc chuyến). Kiểm tra lịch bận đã nhận, bằng lái, giờ nghỉ và ca qua nửa đêm; **không mặc định 24/7**. Thiếu lịch hoặc lịch sử liên quan → không đưa ra phương án có thể duyệt một cách tự động.
- **Mốc mặc định của MVP:** nghỉ hằng ngày giữa các ca **11 giờ liên tục** (tài xế; nhân viên kho dùng mặc định thận trọng, tùy luật và thỏa ước). Nghỉ rút ngắn **9 giờ bị tắt khi tự động lập kế hoạch MVP**. Không có “override” tùy tiện vượt quy tắc an toàn.
- **Với vận tải thuộc phạm vi Quy định (EC) 561/2006 / quy định EEA tương ứng:** phải phân biệt **giờ lái xe** khỏi **tổng giờ làm/nhiệm vụ**; giới hạn thường dùng **9 giờ lái/ngày**, trường hợp đủ điều kiện có thể **10 giờ tối đa hai lần/tuần**; sau không quá **4 giờ 30 phút lái liên tục** phải có **45 phút nghỉ**, hoặc chia **15 phút rồi 30 phút**. Ngoại lệ 9 giờ nghỉ hằng ngày (nếu hợp lệ, không quá 3 lần giữa hai kỳ nghỉ hằng tuần) và các ngoại lệ khác **không tự kích hoạt trong MVP**; việc áp dụng phải kiểm tra phạm vi, nghỉ tuần, lái tuần/2 tuần, dữ liệu lịch sử.
- **Phạm vi là theo quốc gia + xe + loại hình vận tải** (nội địa/quốc tế/cabotage, trọng lượng được phép gồm rơ-moóc, ngoại lệ), **không áp dụng rập khuôn cho mọi xe và tài xế**. Các nước Bắc Âu cùng hệ thống EU/EEA liên quan nhưng có khác biệt thi hành/thỏa ước. Mốc cấu hình pilot **không phải chứng nhận tuân thủ pháp luật**; phải rà soát với bộ phận pháp lý/vận hành từng nước trước khi triển khai thật.
- Engine phải kiểm tra **thời gian làm nhiệm vụ** và **thời gian lái thực** riêng biệt; `driver_max_hours_day=9` trong code hiện tại **không được tự diễn giải** là đủ kiểm tra quy tắc lái xe của EU/EEA. Ca và dữ liệu nghỉ thiếu phải hiển thị lý do không thể duyệt, không chỉ coi là “không có tài xế”.
- **Triển khai:** Dev 1 phối hợp lịch chính thức Q12, sửa engine/kiểm thử trong PR #54; tài liệu/DB/API, seed driver, dữ liệu lịch sử chuyến và phạm vi áp dụng vẫn cần PR triển khai và test. Nguồn kiểm tra phạm vi: [European Commission — driving time and rest periods](https://transport.ec.europa.eu/transport-modes/road/social-provisions/driving-time-and-rest-periods_en), [EUR-Lex — Regulation 561/2006](https://eur-lex.europa.eu/eli/reg/2006/561/oj).

