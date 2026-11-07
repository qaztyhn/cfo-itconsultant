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
- **Q11 đã chốt:** `expected_staff` ở `shift_template` chỉ là **số lượng kế hoạch để so sánh**, không phải quota tự phân ca; không tự chia đều, không đưa nhân viên dư vào ca cuối. `attendance_gen` chỉ được tạo dòng `planned` từ **lịch người–ca đã được Warehouse Manager xác nhận**, không được tự suy lịch. Thiếu lịch chính thức → báo thiếu dữ liệu/công suất chưa xác minh, không làm giả danh sách nhân viên. **PR #37** hiện còn quy tắc Q11=B chia theo `expected_staff`/đẩy dư vào ca cuối; phải sửa/rebase trước khi merge.
