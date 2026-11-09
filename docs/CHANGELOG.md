# Changelog (hợp đồng `05` / `06`)

## [WMS Reservation Adapter (đề xuất/mock, KHÔNG bật ghi WMS) + D8 slot] — 2026-11-09 — Dev 2

- Thêm `adapters/wms_reservation.py` (port reserve/status/release **đề xuất, chưa xác minh**, `DisabledWmsPort` mặc định, khóa idempotency ổn định, kiểm ACK khớp tuyệt đối, timeout→status lookup, partial/mismatch→release bù, unknown→fail closed), `wms_sku.py` (ánh xạ ngược SKU gốc WMS, fail closed), `stock_accounting.py` (không trừ đôi `reserved`), `stock_refresh.py` (đọc lại ngay sau ACK, không đổi checkpoint) và `jobs/ops_review_slots.py` (07:00/13:00 giờ market, chưa bật cron). Test với WMS giả trong bộ nhớ.
- Chưa có API/credential WMS thật, nguồn quan hệ POS↔WMS SKU, trường `reflected_in_batch_id`, ledger/outbox (Dev 1). Xem `docs/proposals/WMS_RESERVATION_ADAPTER_CONTRACT.md`.



## [DEC-CS-SEARCH / DEC-CS-PRIVACY / DEC-M6-PREP-QUEUE / DEC-STOCK-GRANT-CONTROL / DEC-D8-STAGING-SCHEDULE — 20261109] — 2026-11-09 — five owner approvals, docs-only

- **CS-01:** `GET /orders?q=` được duyệt mở rộng tìm `contact_phone` (chuẩn hóa/giới hạn ở backend), ngoài mã đơn, external ref và tên; không thêm param mới. Scope và chống dò số/PII cần Dev 1 code/test.
- **CS-02:** CS có response projection do backend lọc, phone/email chỉ masked; loại tọa độ, mã cổng/receiving restrictions và dữ liệu lập kế hoạch nội bộ; không cấp quyền approve/dispatch/replan/DELAY-send. Contact-log/ETA/notifications stub chưa E2E, CS UI chỉ mock-only trong phạm vi riêng.
- **M6:** Owner phê duyệt nội dung `PROPOSAL-M6-PREP-QUEUE-001`: canonical `/warehouses/{id}/prep-queue`, `schedule_verified`, market IANA timezone. #129/#159/#154/#160 vẫn cần đối chiếu API, tests, không auto-merge.
- **STOCK:** chỉ System Admin được **Owner ủy quyền** mới cấp/thu hồi **tất cả** Stock Admin grant (ban đầu và tiếp theo) theo market; cấm self-grant. Phạm vi không bao gồm WMS on-hand writes; schema/RBAC/audit cần review.
- **D8:** phê duyệt lịch/cadence job trong D8 proposal **để triển khai/test staging/demo**, giữ review 07:00/13:00 Europe/Stockholm; không bật production, trả phí hosting, gửi khách thật hay theo dõi tài xế thật. `attendance_gen` vẫn disabled; tick DTO/code còn review riêng.
- [Biên bản quyết định](decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md); cập nhật `ASSUMPTIONS`, `02`, `03`, `05`, `06`, `09` và D8 proposal. **Chỉ docs, không code, migration, runtime activation hoặc merge PR**. Các mục ASM-004/ASM-008 và những đề xuất không được chọn tiếp tục chưa duyệt.

## [DEC-WMS-RESERVE-SYNC-20261109] — 2026-11-09 — owner-approved business workflow, docs-only

- Owner chốt quy trình **CFO so tồn WMS khi nhận đơn → Sales/Dispatcher xác nhận phương án → CFO yêu cầu WMS reserve bằng SKU gốc → WMS atomic ACK và giảm available (không giảm on_hand vật lý) → CFO đọc/cập nhật WMS ngay**, không chờ polling 5 phút. Không double-subtract reservation đã nằm trong WMS stock.
- Đây là **ngoại lệ reserve nghiệp vụ hẹp** với WMS chỉ đọc trước đó, không cho ghi on_hand/chuyển kho hay sửa POS. API/auth/release/timeout/compensation/production WMS writes vẫn phải qua Dev 1/2 xác minh, PR migration/contract tests và deployment sign-off. [Decision record](decisions/DEC_WMS_RESERVE_SYNC_20261109.md).

## [DEC-WMS-REVERSE-SKU-20261109] — 2026-11-09 — owner conditional mapping rule, docs-only

- Owner yêu cầu **nếu** CFO gửi reserve/release sang WMS, phải ánh xạ ngược global CFO thành **SKU gốc WMS đúng market/kho/dòng đơn và đơn vị tồn**. Local SKU nguồn POS phải được giữ; không mặc định POS SKU trùng WMS SKU. Global→local có thể 1:n, không tự chọn SKU hoặc pool; thiếu mapping confirmed/provenance ⇒ chặn lệnh.
- Vẫn **chưa có phê duyệt CFO ghi WMS** hay xác minh API WMS. [Decision record](decisions/DEC_WMS_REVERSE_SKU_FOR_RESERVATIONS_20261109.md).

## [ASM-WMS-RESERVATION-20261109] — 2026-11-09 — owner assumption, docs-only

- Owner cho phép **giả định WMS có chức năng reservation**. Reserve làm giảm **available** nhưng không trừ `on_hand` vật lý trước khi thực sự xuất kho. CFO không được double-subtract WMS-reserved quantity.
- Việc CFO chủ động gửi lệnh reserve/release tới WMS là **ngoại lệ write** với quyết định WMS read-only hiện hành; Owner mới hỏi cách hoạt động, **chưa phê duyệt write API**. Dev 1/2 phải đề xuất và kiểm chứng interface WMS, ACK, idempotency và failure recovery trước khi code. [Biên bản](decisions/ASM_WMS_RESERVATION_ASSUMED_20261109.md).



## [DEC-WMS-READONLY-20261109] — 2026-11-09 — owner scope clarification, docs only

- Owner nhắc lại CFO **chỉ lấy dữ liệu tồn kho từ WMS**, không quản lý nghiệp vụ xuất/nhập/chuyển hoặc đối soát vật lý. WMS chịu trách nhiệm sổ tồn và chứng từ; CFO đọc batch hợp lệ, kiểm freshness/coverage và giữ riêng lượng held/committed cho đơn để tránh hứa hàng trùng.
- **Thay thế đề xuất** luồng đối soát WMS/chứng cứ Warehouse Manager + independent reviewer trong CFO tại DEC-T18-WMS-RECON-20261109. Không triển khai trạng thái hàng đợi đối soát hoặc alarm Q3 24 giờ; không tự cộng inbound hoặc trừ lại physical outbound. #127 cần review lại phạm vi `confirm-source/receive` trước khi merge.
- [Decision record](decisions/DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md). Chỉ docs; không đổi API/DDL/runtime và không merge code PR.

## [DEC-STOCK-GRANT-BOOTSTRAP-20261109 / DEC-T18-WMS-RECON-20261109] — 2026-11-09 — owner-approved, docs-only

- Owner đồng ý **System Admin được ủy quyền cấp grant Stock Admin đầu tiên theo market**, bắt buộc audit và cấm tự cấp quyền cho mình; giữ S1/S2. Không có bootstrap/role mặc định được tạo bởi PR docs.
- Owner cho phép **giả định WMS cũ có ghi nhận xuất kho nguồn và nhập kho đích** cho luồng chuyển kho; **chưa xác minh** WMS API/CSV trả movement ID, transfer mapping hay acknowledgment. Đối soát ưu tiên chứng cứ WMS, thiếu thì Warehouse Manager nộp bằng chứng và reviewer độc lập có quyền duyệt; không suy theo batch time hoặc lượng tồn, không double-subtract/double-add; CFO read-only WMS.
- Biên bản [DEC_STOCK_BOOTSTRAP_AND_WMS_RECON_20261109.md](decisions/DEC_STOCK_BOOTSTRAP_AND_WMS_RECON_20261109.md); cập nhật ASSUMPTIONS, owner prior record, 02/04/05/06/09. **Q3 24h escalation chưa được duyệt; chưa có code/migration/Source E2E; không auto-merge code.**

## [DEC-GPS-RET-20261109 / DEC-D8-OPS-20261109] — 2026-11-09 — owner-approved amendment, docs-only

- Owner chốt **lưu lịch sử GPS đã thu hợp lệ tối đa 7 ngày** sau khi trip/ca kết thúc thay cho yêu cầu G4 trước đó xóa toàn bộ raw GPS ngay. **Ngừng thu và thu hồi quyền xem live ngay** lúc trip/ca kết thúc, không thu ngoài ca; chỉ cho phép tra soát lịch sử trong phạm vi/chứng cứ hợp lệ, có lý do và audit, yêu cầu privacy/legal/DPIA trước dữ liệu nhân viên thật, xóa khi hết hạn. Không tự mở endpoint historical/read mới hoặc kéo dài retention nếu chưa có quyết định riêng.
- Owner chốt **hai lượt rà soát vận hành tổng thể 07:00 và 13:00 giờ Thụy Điển** (Europe/Stockholm). Đây không phải lịch đồng bộ đơn 2 lần/ngày; **chưa duyệt toàn bộ D8**, tick API, chi phí hạ tầng hoặc lịch các Job còn lại.
- Thêm [decision record](decisions/DEC_GPS_7D_AND_D8_REVIEW_TIMES_20261109.md), cập nhật sổ `ASSUMPTIONS.md`, G4 amendment trong quyết định 27 mã, 02/03/04/05/06/09 và D8 proposal. Thay đổi **chỉ tài liệu**, code migration/runtime GPS cleanup hiện vẫn theo mô hình cũ cho đến khi được sửa, test và nghiệm thu trên PR khác. Không tự merge PR code.


## [DEC-OWNER-20261109 — 27 approved cross-workstream decisions] — 2026-11-09 — docs/contract only

- Chủ dự án phê duyệt **S1–S5, T18-1–3, D7-1–4, G1–G5, N1–N5, M6-1, API-1–2, KPI-1–2**; xem [biên bản](decisions/OWNER_CROSS_WORKSTREAM_APPROVED_20261109.md) và mục mới trong `ASSUMPTIONS.md`.
- Đồng bộ đặc tả `04/05/06/09` cho: market grant/versioned stock scope/evidence 30 ngày; đối soát WMS transfer không double count; D7 56 ngày/11h nghỉ và legal vehicle scope; GPS một Dispatcher chính/trip, chứng cứ thông báo theo tài xế, 100 điểm/batch và xóa theo trip/ca; D4 transactional outbox/ETA window; POD theo `trip_stop`; `checks.*.passed` và rejected candidates flat; 10 KPI, diagnostics `null`.
- Sửa ví dụ JSON trong `06` để không hiện `driver.name`, `promise_window_preview`, `drivers` override mà backend chưa hỗ trợ. Ghi rõ index unique POD theo `order_id` là lịch sử/superseded; **migration mới vẫn cần** để bỏ chỉ mục thực.
- Đồng bộ thêm `02_User_Stories_and_Acceptance_Criteria.md` và `03_UI_UX_Specification.md`: GPS đọc theo assignment, xoá theo trip/ca, simulator xác thực riêng; DELAY draft cần ETA được duyệt; UI không duyệt replan suggestion hoặc hold hết hạn. Giữ nguyên ngoại lệ quiet-hours cho DELAY hiện có, nếu thay đổi cần phê duyệt khác.
- **Không có thay đổi code, schema migration, router hay API runtime**. PR #136 đã merge, Dev 3 tạo hotfix mới; các PR #121/#127/#129/#137/#143 cần tiếp tục triển khai/kiểm thử, **không auto-merge code**.


## [06 §6 — T16 trusted five-gate recheck nối vào `POST /plans/{id}/approve`] — 2026-11-08 — Dev 1, chờ review

- `app/services/approval_recheck.py::five_gate_recheck` nạp lại đơn/market/đầu vào từ DB, chạy lại engine dưới khóa duyệt và chỉ xác nhận khi **đúng kế hoạch đã giữ** vẫn qua đủ 5 gate — so khớp từng `seq` (xe, tài xế, `load_kg`/`load_m3`/`load_lines`, 4 mốc giờ), các mốc giờ và giờ chuẩn bị cấp kế hoạch, khoảng cách/lái xe/dự phòng/route; Decimal so ở scale cột NUMERIC, thời điểm so như instant có múi giờ (naive không khớp); lỗi nạp đầu vào hoặc nguồn đổi sau khi đề xuất → từ chối. Route `approve` không còn truyền `recheck=None`.
- Không đổi route/payload/mã lỗi (thất bại vẫn `409 RESOURCE_CONFLICT`, `conflict=five_gates`). Gate `safety` của thị trường thật vẫn fail closed vì marker lịch sử 56 ngày (D7) chưa được lưu; adapter không bỏ qua điều đó.

## [M7 — đóng alert rủi ro khi đơn DELIVERED] — 2026-11-08 — PR #131, chờ review

- `risk_service.recalculate` với đơn `DELIVERED` đóng (`resolved_at`) các alert **mở** `RISK_ORANGE`/`PREDICTED_LATE`/`OVERDUE` của **đúng đơn và market đó** trong transaction của bên gọi, rồi trả `None`: không tính ETA, không tạo/mở lại alert. Alert không bị xóa; loại alert khác của cùng đơn (STALE_DATA, EXCEPTION, REPLAN_SUGGESTED, ORDER_CHANGED_AFTER_APPROVAL…) không bị đụng.
- Chính sách này đến từ yêu cầu review của Dev 1/owner; **chưa có điều khoản tài liệu riêng**. `FAILED`/`CANCELLED` giữ nguyên alert (chưa có chính sách duyệt). Bên thực thi (M6) phải gọi `recalculate(order_id, ..., session=...)` sau khi chuyển `DELIVERED` trong cùng transaction.

## [Plan vehicle DTO — object `vehicle` lồng] — 2026-11-08 — Dev 1 (chủ dự án chọn Option B)

- `GET /planning-runs/{id}` và `GET /plans/{id}` (view Dispatcher): mỗi phần tử `vehicles[]` giữ nguyên field cũ (`vehicle_id`, `driver_employee_id`, `load_*`, mốc giờ) và **thêm** `vehicle: {id, code, name, capacity_kg, capacity_m3}` từ `ref.vehicle` thật; capacity là chuỗi thập phân không số 0 thừa (`"12000"`, `"40"`). Không có biển số, bằng lái, lịch xe, GPS hay dữ liệu tài xế.
- Một truy vấn `plan.plan_vehicle` + một truy vấn `ref.vehicle` cho cả run (không N+1). View Sales giữ nguyên dạng gọn (`seq`, `eta_at`). Bản ghi xe thiếu -> `500 INTERNAL_ERROR` an toàn, không trả DTO thiếu. Không đổi quyết định lập kế hoạch/duyệt, route, DDL hay mã lỗi.
- Mẫu docs/06 §6.2: capacity chuyển từ số sang chuỗi cho khớp với các trường Decimal khác.

## [T14 — adapter `ReplanSource` cho T07] — 2026-11-08 — Dev 1, chờ Dev 2 nối

- `app/services/source_change_adapters.py::replan_source()` thỏa `ReplanSource` của T07: tham gia transaction của bên gọi, dùng `planning_service.suggest_replan` (trigger `source_change`): chỉ tạo run gợi ý **không giữ chỗ**, không tự duyệt, không đụng kế hoạch/tài nguyên đã cam kết, một run mỗi source version, sau `DISPATCHED` chỉ alert.
- Adapter `SourceRisk` **chưa có**: `risk_service.recalculate` còn là stub trên `main` (M7 #131 đang mở) và watermark tín hiệu nguồn chưa có contract. Không đổi route/DDL/mã lỗi.


## [DEC-DEV1-D1-01…04 — Audit chuyển kho và quản trị scope/evidence stock] — 2026-11-08 — docs-only, chờ Dev 1/2 review

- Chủ dự án phê duyệt **D1-01**: `TRANSFER_CANCELLED` với người thao tác, lý do, thời điểm, trước/sau; không dùng `TRANSFER_APPROVED` cho cancel. **D1-02**: `TRANSFER_CONFIRMED` chỉ kho nguồn xác nhận xuất, `TRANSFER_RECEIVED` mới cho kho đích nhận.
- Chủ dự án phê duyệt **D1-03**: admin có thẩm quyền quản trị/phê duyệt scope SKU CFO theo market/pilot, có version, hiệu lực, audit, không suy từ mapping. **D1-04**: Warehouse Manager cung cấp evidence kho/WMS về tồn độc lập; admin có thẩm quyền duyệt; lưu evidence/approver/version/hiệu lực/audit; thiếu xác minh => fail closed.
- Đồng bộ tài liệu: `ASSUMPTIONS`, `04`, `05`, `06`, `09` và `docs/decisions/DEV1_D1_01_04_APPROVED_20261108.md`. **Chưa có** code, migration, route quản trị, field mới, OpenAPI parity hay E2E từ PR docs này; Dev 1/Dev 2 review thiết kế và triển khai qua PR kỹ thuật riêng. Không tự merge.


## [06 §16.4 — chuẩn hóa tồn kho CFO theo DEC-CFO-STOCK-SCOPE-001 và DEC-CFO-STOCK-INDEPENDENCE-001] — 2026-11-08 — chờ review Dev 1/Dev 2

- `normalize_stock` nhận phạm vi SKU tường minh (ngoài phạm vi không chặn; trong phạm vi lỗi thì từ chối cả batch) và nhóm `verified_independent` (chỉ cộng nhiều SKU cùng kho cùng global product khi đã xác minh; mặc định từ chối). `GlobalStock.source_sku` đổi thành `source_skus`.
- Không đổi DDL/route/mã lỗi; nơi lưu phạm vi và bằng chứng độc lập, lưu `ops.stock_snapshot`, độ mới và kiểm tra nguyên tử vẫn chưa làm.


## [06 §16.4 — DTO tồn kho phía CFO theo fixed-SKU] — 2026-11-08 — thiết kế lại #107, chờ review Dev 1/Dev 2

- Ghi rõ DTO `GET /stock` thống nhất (`as_of`, `batch_id`, `item_count`, `items`) và các quy tắc từ chối/chuẩn hóa của adapter CFO theo DEC-SRC-Q10-SKU-001 và DEC-SRC-Q9-ERROR-001. Không pool.
- Không đổi DDL/route/mã lỗi mới ngoài `STOCK_UNAVAILABLE` đã duyệt; chưa có persistence tồn kho CFO.

## [05 §10 / 06 §16.4 — PR #105 căn chỉnh theo DEC-SRC-Q9-ERROR-001 và DEC-SRC-Q10-SKU-001] — 2026-11-08 — chờ review

- `GET /stock` nguồn: `200 {as_of, batch_id, item_count, items[{warehouse_code, sku, on_hand, reserved}]}` từ batch published hoàn chỉnh mới nhất; **`503 STOCK_UNAVAILABLE`** khi không có batch published hoặc batch mới nhất không qua kiểm tra toàn vẹn; `200` với `items=[]` chỉ cho batch published rỗng. Thay thế phản hồi `200 {complete:false, as_of:null}`.
- **Bỏ `physical_stock_pool_id`** khỏi DDL, DTO, CLI và test; `src_stock` có `UNIQUE(batch_id, warehouse_code, sku)`, mỗi batch giữ dòng của mình. Nâng cấp từng bước giữ dữ liệu; dòng legacy không batch không bao giờ được phục vụ.
- Phần mô tả pool của mục "Dev 2 source authoritative stock batches" bên dưới đã bị thay thế bởi mục này.
- Không đổi route; OpenAPI baseline nguồn chưa có trên `main` (đang chờ PR #99) nên chưa tái tạo ở PR này.


## [DEC-SRC-Q9-ERROR-001 — Source 503 STOCK_UNAVAILABLE approved] — 2026-11-08 — docs-only PR #101

- Chủ dự án đã duyệt phương án A: `GET /api/v1/stock` khi **chưa có batch tồn kho hoàn chỉnh nào đã publish** trả **HTTP 503**, `error.code = STOCK_UNAVAILABLE`, body/header lỗi chuẩn Source có `correlation_id`. Nếu published empty batch thì vẫn trả `200 items=[]` (tồn=0), không nhầm với unknown.
- Nếu batch mới thất bại nhưng còn bản đã publish trước đó, chỉ cung cấp bản đã published với `as_of` gốc; CFO kiểm độ mới 15 phút theo cấu hình, báo alert, không dùng dữ liệu stale làm cam kết; polling 5 phút **không đổi**.
- `STOCK_UNAVAILABLE` chỉ dùng trong Source API; không ảnh hưởng `GET /health`, không đồng nghĩa chấp thuận `501 NOT_IMPLEMENTED` đang được review ở PR #99. Triển khai handler/OpenAPI/adapter/test trong PR code sau này; **#101 chưa làm migration hay API**.


## [DEC-SRC-Q10-SKU-001 — owner revises Q10, Q9 unchanged] — 2026-11-08 — docs-only PR #101

- **Owner-directed change:** Owner requires **one stable inventory unit per product SKU**; changing packaging/order unit is a conversion into the SKU's declared stock unit, **not** a second inventory record. This **supersedes only the physical-stock-pool/alias portion of the earlier D1-D Q10 approval**. Do not introduce `physical_stock_pool_id` or infer shared inventory from numerically equal quantities.
- For each published batch, warehouse and SKU, accept **one stock row** `(batch_id,warehouse_code,sku)`. Source rejects duplicate rows; CFO converts quantities via `units_to_base` and only aggregates different SKUs into one global product if independence is positively verified. Unknown mapping/independence => fail closed and never expose incomplete replacement as a complete snapshot.
- **Q9 stays approved and unchanged:** atomic published complete batch, including authoritative zero-row batch; no published batch is unavailable/unknown (not zero). **Subsequent owner decision `DEC-SRC-Q9-ERROR-001` approves Source-only HTTP 503 `STOCK_UNAVAILABLE`** for the missing published batch; handler, OpenAPI and tests remain unimplemented by this docs PR.
- Synchronized `ASSUMPTIONS`, Q10 portions of `DEC_SRC_D1_APPROVED_20261108`, `05`, `06`, `09`, and PR #101 proposal; no code, SQL migration, OpenAPI regeneration or E2E in this PR. Dev 1+2 must review exact target schema/adapter/test and implement in subsequent PR(s).


## [06 §16.1 — triển khai 5 danh sách nguồn] — 2026-11-08 — theo DEC-SRC-D1-001 D1-A, chờ review

- Triển khai `GET /customers`, `/products`, `/inbound`, `/fleet/calendar`, `/addresses` với phong bì `{items,page,page_size,total}`, `X-Total-Count`, `updated_since` bao gồm, thứ tự `(updated_at, natural key)`.
- Ghi rõ các diễn giải kỹ thuật (cận `from`/`to` tùy chọn, `q` chỉ khớp văn bản địa chỉ, kiểu số/chuỗi) để review. Không đổi route/enum/mã lỗi, không migration.


## [DEC-SRC-D1-001 — owner-approved detailed Source D1-A–D] — 2026-11-08 — docs-only

- Owner trả lời **“ĐƯỢC ĐỒNG Ý”** với toàn bộ D1-A/B/C/D trong [PR #84](https://github.com/qaztyhn/cfo-itconsultant/pull/84). Ghi `DEC-SRC-D1-001` tại `ASSUMPTIONS` và hồ sơ quyết định `docs/decisions/DEC_SRC_D1_APPROVED_20261108.md`.
- **D1-A:** GET `/orders,/customers,/products,/inbound,/fleet/calendar,/addresses` phân trang `items,page,page_size,total` 50/max500, sort `updated_at,natural_key`, inclusive `updated_since >=`; đơn `CANCELLED` cần feed đồng bộ riêng; `/stock` không phân trang.
- **D1-B:** persisted DRAFT cần customer/address/store/date_mode; Validate/Submit yêu cầu contact/lines, qty dương, `unit_price` decimal chuỗi hai số (0 hợp lệ), date/hours nhận kiểm nguồn, 422 với stable path/reason không echo PII; source-known SKU chưa mapping không được POS chặn.
- **D1-C:** PUT sau submit full validation + `expected_version`, `409 VERSION_CONFLICT`; CANCELLED terminal có version/reason/idempotency. CFO chưa duyệt phải close/release hold qua state transition/audit; đã APPROVED chưa DISPATCHED tự tính `replan_suggestion` **không giữ chỗ/auto-approve**, Dispatcher mới quyết định; sau DISPATCHED alert-only.
- **D1-D:** lịch nhận market/address fail-closed nếu thiếu, tồn kho batch published atomically kể cả batch rỗng, nguồn chưa publish không phải tồn=0, normalize `units_to_base` và stock pool alias chống cộng trùng.
- Đồng bộ `03/05/06/09`; PR **docs-only** và không chứng minh endpoint, database migration hay tests đã xong. D6 tiếp tục owner tự tổ chức riêng, D8 mới là proposal; D2–D5 và D7 đã có owner approval độc lập.

## [DEC-DEV2-D2/3/4/5-001 — owner approvals; D6 deferred; D8 proposed] — 2026-11-08 — docs-only

- **D2:** chốt CSV UTF-8 versioned/schema, ISO dates/timezone + decimal, SHA-256 idempotent: file `ok` trùng skip; `failed` retry run mới; `partial` cần IT review, tuyệt đối không cộng/trùng stock hoặc ghi approval.
- **D3:** thu GPS **30 phút** chỉ khi on-road + tài xế trong ca; offline queue được phép nhưng xóa/bỏ khi chuyến hoặc ca kết thúc; **chỉ Dispatcher gán chuyến mới xem** trong ca, không toàn market. Raw GPS được xóa khi trip terminal/ca hết hiệu lực (không giữ 30 ngày như tài liệu cũ); đổi privacy/RBAC/config spec và yêu cầu migration/cleanup tests, giữ lịch sử duty/tachograph riêng.
- **D4:** notification phải render server từ template với biến allowlist, cấm body/subject free-text; DELAY chỉ draft/Dispatcher duyệt; giữ giới hạn gửi email demo theo DEC-NOTIFY-001. Backoff 5/15 phút chưa được chốt riêng.
- **D5:** chấp thuận con số policy theo loại customer/CS 90d, operations 365d, former-staff nonstatutory contact 90d, shift records 24mo (legal review), logs 30/90d, staging backups 30d; statutory tachograph/work-time/Swedish accounting căn cứ riêng, immutable audit review; **GPS theo D3 override**. GDPR là mục tiêu, legal/privacy review cần trước dữ liệu thật, không chứng nhận compliance.
- **D6:** owner sẽ tổ chức riêng, chưa phê duyệt deploy/chi phí/cloud. **D8:** mới yêu cầu đề xuất schedule theo Europe/Stockholm (PR tài liệu này), chưa duyệt; chưa triển khai scheduler.
- Đồng bộ `ASSUMPTIONS`, `03/04/05/06/09` cùng tài liệu quyết định và proposal D8; PR chỉ thay đổi docs, còn code/DDL/OpenAPI/tests pending, **không** tuyên bố M2/M6/M7/M8 đã hoàn thành.

## [DEC-DEV2-D7-001 — Synthetic vehicle and driver fixture rules] — 2026-11-08 — owner approved, docs-only

- Chủ dự án duyệt D7-A–E: seed xe và **56 ngày** lịch sử làm việc/lái/nghỉ tài xế synthetic, tách payload với `max_permissible_mass_kg`, xác định scope 561 theo tình huống, `unknown`/thiếu lịch sử → fail-closed; nghỉ mặc định 11h, không dùng ngoại lệ 9h, giờ lái khác giờ làm.
- Bổ sung quy tắc cho `04` §6.7, `05` (vehicle/driver duty), `06` §13.0b, `08` §5.3; sửa ví dụ van 3,5t trước đó không hợp lý. Chưa thay đổi migration/code/API; Dev 2 seed và Dev 1 nghiệm thu engine/approval trên test fixtures. Quyết định D1–D6/D8 không được chốt bởi mục này.

## [05 §10 / 06 §16 — bản chụp đơn nguồn và GET /orders] — 2026-11-08 — theo DEC-SRC-001, chờ review

- `05` §10: `src_order` thêm 8 cột bản chụp (SRC-Q1), nullable; nâng cấp cộng thêm, giữ dữ liệu.
- `06` §16: ghi rõ `GET /orders` — phong bì `{items,page,page_size,total}`, `page_size` mặc định 50 tối đa 500, `updated_since` bao gồm (`>=`), thứ tự `(updated_at, id)`, biểu diễn đơn, lỗi 422 không phản chiếu giá trị.
- Không đổi mã lỗi/route/enum; không thêm migration CFO. **Chưa** có: ghi đơn, validate/submit/cancel, các danh sách khác, OpenAPI baseline.


## [DEC-HOLD-001 — hết hold phải Plan Again, không hồi sinh plan cũ] — 2026-11-08 — owner approved, docs-only

- Hold hết hạn: trả giữ chỗ, đặt plan `expired`, trả đơn `PLANNED` về trạng thái chờ lập kế hoạch `SUBMITTED` **chỉ khi đúng run vừa hết hạn và chưa có run/approval mới**. Không được duyệt plan expired kể cả Dispatcher, dù nguồn lực vẫn còn.
- Người dùng muốn tiếp tục phải chủ động Plan Again: tạo `planning_run`/candidate/hold mới cho **cùng customer_order**, kiểm lại nguồn, ca kho, xe/tài xế và 5 gate; không sao chép đơn. Đây là quy tắc thay thế ngoại lệ cũ trong `04` §7 cho Dispatcher duyệt sau timeout.
- `04`, `05`, `06`, `ASSUMPTIONS` đồng bộ theo quyết định chủ dự án khi review #78; không có code/migration trong PR này. T14/T15/T16 cần test timeout, double click/race và status reset.

## [DEC-SRC-001 — M1 source contract SRC-Q1–Q10] — 2026-11-08 — owner approved direction, docs-only

- Chủ dự án phê duyệt hướng đề xuất tại `docs/proposals/M1_SOURCE_CONTRACT.md`: (Q1–Q3) snapshot địa chỉ/liên hệ và request/response đơn; (Q4–Q5) validation lỗi 422 + lifecycle; (Q6–Q7) danh sách nguồn phân trang mặc định **50**, tối đa **500** và đồng bộ gia tăng theo thứ tự ổn định; (Q8) bổ sung lịch nguồn/giờ nhận theo địa chỉ; (Q9) stock snapshot batch có `as_of` kể cả rỗng; (Q10) normalize SKU/units, tránh cộng hoặc ghi đè tồn kho sai.
- Quy tắc và biên phê duyệt đã ghi tại `docs/ASSUMPTIONS.md` (DEC-SRC-001); **không đồng nhất** phân trang của source với `GET /orders` CFO.
- **Chưa triển khai:** không sửa schema/API chuẩn `05`/`06`, không migration/code/test trong PR này. Dev 2 cần PR hợp đồng/triển khai với review Dev 1 (adapter, stock) và Dev 3 (POS), test nguồn nhiều instance. Các quyết định còn thiếu được liệt kê tại proposal; không tự điền theo suy đoán.

## [DEC-ORS-001 + DEC-NOTIFY-001 — owner approvals] — 2026-11-07 — docs-only

- Owner chấp nhận retry ORS fallback sau **60 phút** mặc định theo market, gắn nhãn tuyến ước lượng; TTL đã triển khai trong #67.
- Owner chốt **chỉ gửi email thử nghiệm qua Mailpit hoặc staging kiểm soát với địa chỉ demo**, không gửi khách thật khi chưa có chống trùng/đối soát. Quyết định chưa có guard đầy đủ trong code SMTP; Dev 2 phải bổ sung test/chặn người nhận ở staging.
- #68–#70 đã merge vào các nhánh trung gian, **chưa có đầy đủ code trên `main`**. Tạo PR tích hợp riêng và chạy CI trước khi kết luận đã hoàn tất.
- Phê duyệt này chỉ ghi vào `docs/ASSUMPTIONS.md` và cập nhật trạng thái changelog; không tự kích hoạt email gửi khách thật.

## [06 Phụ lục A — `routing.fallback_retry_min`] — 2026-11-07 — đã duyệt DEC-ORS-001

- Thêm khóa cấu hình `MarketConfig.routing.fallback_retry_min` (mặc định 60, phải > 0): fallback ORS không còn được lưu và dùng vô thời hạn; quá hạn thì thử ORS lại. Không đổi DDL/route/mã lỗi; `route_matrix.computed_at` sẵn có.
- Test PostgreSQL: `backend/tests/integration/test_dev2_route_cache.py`.


## [Approved decision register] — 2026-11-07 — docs-only

- Tập trung quyết định đã duyệt ở `docs/ASSUMPTIONS.md`: ASM-001/002/003/005/006/007; Sales confirmation, Q12/Q13/Q14 và giờ làm/nghỉ của kho/tài xế trong MVP Bắc Âu.
- **ASM-004 giữ trạng thái chưa duyệt**; các proposal kỹ thuật vẫn cần PR contract/migration/test riêng. Không dùng mã ASM đã cấp trùng với ASM-008 trong PR #55; quyết định sản phẩm dùng `DEC-xxx`.
- `AGENTS.md` và `09_AI_Coding_Rules.md`: bắt buộc Dev/agent cập nhật sổ khi owner chốt giả định mới, kiểm tra trước khi mở PR, dẫn nguồn và phân biệt phê duyệt với triển khai.
- Chỉ có thay đổi docs, không có migration/code/test trong PR này.


## [ASM-002, ASM-003, ASM-006, ASM-007/Q11 — quyết định chủ dự án] — 2026-11-07 — docs-only

- ASM-002: chấp thuận seed tham chiếu (market, N1–N6, position, transitions) riêng dữ liệu demo; GPS mặc định tắt ở migration, tài khoản/mật khẩu demo không nằm trong migration.
- ASM-003: chấp thuận giới hạn đăng nhập MVP 5 lượt/60 giây/IP và HTTP 429; logout 204; email không phân biệt hoa thường; khóa user ngay khi nghỉ việc. Hệ thống nhiều instance cần rate limiter chung trong lần mở rộng.
- ASM-006: chấp thuận bảo đảm quản lý thay thế trước chuyển công tác/nghỉ việc, khóa account người nghỉ, giữ owner gán riêng, audit mọi thay đổi nhân sự/quản lý/owner; chỉnh hồi tố phải có quyền và lý do. Không chấp thuận bỏ `decision_log`; action code chưa có cần PR hợp đồng.
- ASM-007/Q11: Warehouse Manager lập và xác nhận lịch phân ca **từng người/ngày/ca**. `expected_staff` chỉ để so sánh; không chia tự động, không dồn người dư vào ca cuối. Job chỉ sinh điểm danh planned từ lịch do quản lý xác nhận; warehouse ghi thực tế; thay đổi lịch/điểm danh có audit, hồi tố cần lý do.
- Mục tiêu docs, chưa có code/migration/test xác minh. Cần thiết kế bảng lịch ca chính thức mới, API và UI. PR #37 còn Q11=B phải cập nhật/rebase trước merge.

## [ASM-005 — quyết định phân luồng SKU] — 2026-11-07 — docs-only, chưa triển khai

- Khởi đầu khoảng 100 SKU mapping confirmed do IT quản lý, mở rộng danh mục từng giai đoạn.
- Chỉ đơn có **100% SKU confirmed** mới đi CFO. Đơn thiếu SKU tiếp tục quy trình cũ, không bị CFO chặn chờ mapping/không lập plan/hold.
- Mapping về sau không tự động chuyển các đơn đã đi quy trình cũ sang CFO. Bắt buộc ngăn xử lý trùng bằng xác minh luồng thực hiện tại đầu vào; CFO vẫn read-only với POS/WMS/ERP.
- API response, trạng thái theo dõi luồng cũ và bất biến tránh double fulfilment cần được Dev đề xuất trước triển khai. Không tự phục hồi trạng thái `HANDLED_EXTERNALLY` đã bỏ ở v1.2; không có migration/code trong PR này.


> Mỗi thay đổi `05`/`06` đi cùng migration/code và test trong cùng PR (`09` mục 6, `AGENTS.md`).
> Mục có trạng thái **chờ duyệt** chưa được merge cho tới khi nhóm phê duyệt trên PR.

## [DEC-ROUTING-002 — 05/06 + migration 0011] — 2026-11-07 — quyết định của chủ dự án, chờ review PR

- **Quyết định:** polling chỉ đồng bộ dữ liệu nguồn. Quyết định `cfo`/`legacy` chỉ ghi khi Sales Sync & check hoặc Dispatcher kiểm tra được ủy quyền, trên dữ liệu nguồn và mapping lúc đó. Đã ghi không tự đổi. Điều phối tay trước khi kiểm là ngoại lệ có lý do + audit; đơn đã `cfo` thì không đổi sang `legacy` mà chuyển Dispatcher. Thay thế phần "polling được quyết định" của Q14/DEC-ROUTING-001.
- **`05`:** `ops.order_routing.decided_by_user_id` NOT NULL, `decided_by_role` (`sales|dispatcher`) NOT NULL, `reason_text`, `ck_routing_manual_reason`. Trigger bất biến bao cả hai cột mới. Thêm loại alert `ROUTING_MANUAL_CONFLICT`. Migration `0011` thất bại nếu bảng đã có dữ liệu cũ (fail closed).
- **`06` §5.0.2:**
  - `sync-now` trả lại quyết định đã lưu (`already_decided`);
  - `routing-ack` `manual_started` có ba nhánh: chưa quyết định → `legacy/manual_started`; đã `legacy` → chỉ audit; đã `cfo` → `409 RESOURCE_CONFLICT` + escalation.
- **`04` §10:** mã hành động `ROUTING_DECIDED`, `ROUTING_LEGACY_ACKNOWLEDGED`, `ROUTING_MANUAL_START_RECORDED`, `ROUTING_MANUAL_CONFLICT_ESCALATED`.
- Service/API (`sync-now`, `routing-ack`, escalation) và ingestion **chưa code**. Dev 2 làm phần ingestion/sync-now, Dev 1 làm guard/routing-ack.

## [05 — migration 0010] — 2026-11-07 — quyết định phân luồng bất biến (Q14), chờ review

- `ops.order_routing`: trigger `trg_guard_order_routing` (hàm `ops.guard_order_routing`) chặn UPDATE khóa, `route`, `reason_code`, `unmapped_skus`, `decided_at`, `decided_source_version`, `decided_by_user_id`, `created_at` và mọi DELETE; chỉ cho ghi riêng `acknowledged_by_user_id`/`acknowledged_at` **một lần** (NULL → giá trị). `ck_routing_ack`: hai trường xác nhận cùng có hoặc cùng NULL.
- Tách thành migration riêng để DB đã chạy 0009 cũng nhận ràng buộc. Không đổi cột.
- **Cần nhóm chốt (mâu thuẫn hợp đồng):** `06` mục 5.0.2 cho phép `manual_started` lưu `legacy` "kể cả khi đủ SKU", còn polling được phép quyết định trước khi Sales kiểm. Với trigger này, quyết định `cfo` do polling ghi trước sẽ **không** đổi được sang `legacy/manual_started`. Đề xuất: polling không ghi quyết định `cfo` (chỉ Sales check hoặc Dispatcher ghi), hoặc định nghĩa rõ một chuyển đổi duy nhất `cfo → legacy/manual_started` trước khi có hold.

## [05 — migration 0009] — 2026-11-07 — DDL theo Q12/Q12b/Q14 đã duyệt (PR qaztyhn/cfo-itconsultant#53), chờ review PR migration

### Thêm
- `hr.employee_shift_schedule`: lịch ca chính thức của nhân viên kho và tài xế (giờ theo template hoặc giờ riêng, ca qua nửa đêm, giờ nghỉ, trạng thái `scheduled/cancelled`, người lập, lý do); `ux_shift_one_per_day` (Q12a).
- `hr.driver_duty_log`: kỳ làm việc/lái của tài xế (`duty_start/end`, `driving_min`, `source`, `trip_id`) — nguồn kiểm nghỉ 11 giờ và giờ lái (Q12b).
- `ops.order_routing`: quyết định luồng `cfo`/`legacy` một lần theo `(market_id, external_ref)`; `ck_routing_reason` (cfo ⇔ all_confirmed); `unresolved` không lưu được (Q14).
- `ref.vehicle.max_permissible_mass_kg`, `ref.vehicle.regulation_561_scope` (`in_scope|out_of_scope|unknown`, mặc định `unknown` → engine fail closed).
- Trigger `set_updated_at` cho ba bảng mới (ASM-001).

### Ảnh hưởng
- Không đổi bảng/cột cũ khác. Service/API dùng các bảng này (lịch ca, phân luồng, dựng ngữ cảnh engine) ở PR tiếp theo; Dev 2 seed lịch demo và phạm vi xe.

## [Q12–Q14 — lựa chọn nghiệp vụ đã duyệt] — 2026-11-07 — docs, DDL/API/engine chờ PR triển khai (PR qaztyhn/cfo-itconsultant#53)

- Q12: lịch ca chính thức một bảng cho nhân viên kho **và tài xế**; 1 ca/người/ngày; quản lý chính/phó `can_approve` cập nhật; sửa quá khứ cần lý do; thiếu lịch → `schedule_verified=false`, công suất 0; giờ riêng, ca qua nửa đêm, giờ nghỉ, nghỉ giữa ca `driver_min_rest_hours` (MarketConfig mới, mặc định 11).
- Yêu cầu mới của chủ dự án: phương án chỉ hợp lệ khi lên hàng trong ca kho chính thức có người và khoảng làm việc của từng tài xế nằm trọn trong ca thực tế; không mặc định 24/7. Engine: `WarehouseCtx.loading_windows`, `DriverCtx.shifts`, ghép tài xế bipartite, ràng buộc nhóm/năng lực theo dòng trên từng xe; mã `NO_WAREHOUSE_SHIFT`, `OUTSIDE_DRIVER_SHIFT` (`04` mục 6.7, `06` mục 13.0b).
- Q12b (chính sách Bắc Âu cho MVP, duyệt hướng 07/11/2026, không phải xác nhận pháp lý):
  - nghỉ hằng ngày 11 giờ; tắt nghỉ rút gọn 9 giờ;
  - tách thời gian lái (561/2006: 9 giờ/ngày, nghỉ 45 phút sau 4 giờ 30, giới hạn tuần/hai tuần) khỏi tổng giờ làm `driver_max_hours_day`;
  - phạm vi theo market/xe/loại vận hành (`ref.vehicle.regulation_561_scope`);
  - fail closed khi thiếu lịch sử hoặc phạm vi;
  - mã mới `DRIVER_REST_INSUFFICIENT`, `DRIVING_TIME_EXCEEDED`, `DRIVING_BREAK_REQUIRED`, `DRIVER_HISTORY_MISSING`, `VEHICLE_SCOPE_UNKNOWN`.
- Q13: mã audit `LOCATION_MANAGER_CHANGED`, `LOCATION_OWNER_CHANGED`, `EMPLOYEE_TERMINATED`, chỉnh hồi tố `EMPLOYEE_ASSIGNMENT_CHANGED`/`retroactive`.
- Q14: `ops.order_routing` (cfo/legacy, không đổi), trạng thái `unresolved` riêng, Sales kiểm CFO trước điều phối tay, `routing-ack` (`legacy_acknowledged`/`manual_started`), polling không tự tạo hold; nêu rõ bảng nội bộ không bảo đảm chặn điều phối tay (`06` mục 5.0.2).
## [06 v1.4] — 2026-11-07 — **đã duyệt** (Q5–Q10, PR qaztyhn/cfo-itconsultant#37; chủ dự án trả lời trong phiên làm việc 2026-11-07; Q11 thay bằng ASM-007, PR qaztyhn/cfo-itconsultant#50)

Quyết định: Q5 = A, Q6 = A, Q8 = A (điều chỉnh theo ASM-005), Q9 = A, Q10 = A. **Q11 = B bị thay thế** bởi ASM-007: lịch phân ca từng người do Warehouse Manager lập; không chia theo `expected_staff`, không dồn người dư vào ca cuối. Q7 được chốt lại theo nguyên tắc "ưu tiên đơn đặt trước, linh hoạt chèn đơn giao sớm, nhưng mọi đơn phải đúng hạn đã cam kết", khớp `docs/DECISION_SALES_CONFIRMATION.md` mục 5.

### Thêm
- `06` mục 5.2: phạm vi đơn theo vai trò (warehouse qua kế hoạch chưa superseded hoặc chuyến từ kho mình; sales theo cửa hàng gốc; driver theo chuyến mình; viewer `403`; ngoài phạm vi `404`).
- `06` mục 5.3: bảng trường của `GET /orders/{id}` theo vai trò; trường bị cấm thì bỏ khỏi phản hồi; không có GPS.
- `06` mục 5.4: phần tử `GET /orders`; **sắp mặc định `submitted_at ASC, id ASC`** (thay cho `promise_end` trong đề xuất ban đầu); bucket của `/orders/counts`. `BLOCKED_UNMAPPED_SKU` là legacy: không thuộc `needs_plan`/`all`/hàng đợi Dispatcher (ASM-005).
- `06` mục 5.5: timeline; CS không thấy quyết định nội bộ, lần chạy kế hoạch, điểm số, GPS.
- `06` mục 12.2: schema đọc `/mapping/tasks*`, `/products/local`; phản hồi confirm/reject. Theo ASM-005 (PR qaztyhn/cfo-itconsultant#49): confirm **không** mở khóa/chuyển trạng thái đơn, phản hồi không có `ready_order_ids`/`still_blocked_order_ids`; chi tiết task không liệt kê đơn khách; `blocked_order_count` là trường legacy, sắp mặc định theo `id` thay vì số đơn bị chặn.
- `06` mục 13.2: schema điểm danh và công suất. Roster và `attendance_gen` theo lịch chính thức của Warehouse Manager (ASM-007, mục 13.0a); khi chưa có bảng lịch thì job không tạo dòng, không suy từ `expected_staff`.

### Ảnh hưởng
- Mã: route M2-C (mapping), M2-D (orders, counts), M2-E (timeline), M3 (điểm danh, công suất). PR code căn chỉnh ASM-005/007 bỏ mở khóa đơn khi confirm và bỏ chia ca theo `expected_staff`. Không đổi `05`; bảng lịch ca chính thức cần PR migration riêng.
- Thứ tự thực thi không theo FIFO cứng: bảo vệ đơn cũ bằng `committed` (đã duyệt); đơn cũ chưa duyệt tranh nguồn lực thì Sales chuyển Dispatcher (`06` mục 6.3a, `09` bất biến 26–27).

## [Sales confirmation B — Product decision] — 2026-11-07 — docs-only, chưa triển khai

- Giữ POS/WMS/ERP, database riêng và read-only adapter; Sales yêu cầu CFO đọc đơn ngay qua `sync-now`, polling 5 phút dự phòng.
- Sales xác nhận trực tiếp trên màn CFO riêng chỉ khi plan rank 1 đủ 5 gate, reserve safe, một xe, không ngoại lệ, đúng cửa hàng; ApprovalService vẫn kiểm tra lại và khóa nguồn lực khi commit.
- FIFO hiển thị (`submitted_at,id`), không ép FIFO thực thi; bảo vệ committed của đơn cũ, cạnh tranh với đơn cũ chưa duyệt → Dispatcher.
- Bổ sung hợp đồng mục tiêu và acceptance criteria; không có code/migration/test thực thi trong PR docs này. PR #37 cần đối chiếu trước khi merge.

## [06 v1.3] — 2026-11-07 — **đã duyệt** (PR qaztyhn/cfo-itconsultant#12, comment của owner 2026-11-07)

### Thêm
- `06` mục 13.1: API đọc `/locations`, `/employees`, `/vehicles` (và `/{id}`): schema phản hồi, lọc, sắp xếp,
  phân trang, lỗi 401/403/404/422.
- Phạm vi: admin, dispatcher theo market; warehouse theo địa điểm có phân công hiệu lực; vai trò khác `403` (Q3 = A).
- Kiểm theo **ngày hiệu lực** cho phân công (`start_date`/`end_date`) và quản lý địa điểm (`valid_from`/`valid_to`),
  hôm nay theo múi giờ market (điều chỉnh Q1).
- Hiển thị trường nhân viên theo vai trò, tối thiểu hóa dữ liệu: dispatcher thấy thêm `driver_staff` (bằng lái),
  warehouse thấy thêm `warehouse_staff.role`, `counts_in_capacity`; thông tin liên hệ và hợp đồng chỉ admin (Q4 = C
  có điều chỉnh). Trường không hiển thị được bỏ khỏi phản hồi; liệt kê trường nullable (điều chỉnh Q1).

### Đổi
- `06` mục 13: quyền đọc `/vehicles` theo ma trận mục 3 — dispatcher (market), warehouse (xe thuộc kho mình) (Q2 = A);
  mô tả vai trò của `/employees`, `/locations` trỏ tới mục 13.1.

### Ảnh hưởng
- Backend: `app/api/v1/hr.py`, `app/services/hr_read_service.py`, phạm vi/phân trang dùng chung; test PostgreSQL
  quyền, phạm vi, ngày hiệu lực, hiển thị trường.
- Frontend (Dev 3): màn A9/A10 dùng schema mục 13.1; vai trò không phải admin nhận ít trường hơn.
- Không đổi bảng, cột, enum hay endpoint khác.

## [06 v1.2.1] — 2026-11-06 — **chờ nhóm duyệt** (PR qaztyhn/cfo-itconsultant#8)

### Thêm
- `06` mục 1.1: nhóm **mã lỗi kỹ thuật** ngoài danh sách mã nghiệp vụ:
  - `INTERNAL_ERROR` (HTTP 500) — lỗi không bắt; thông báo cố định, không stack trace, không thông điệp gốc.
  - `NOT_FOUND` (HTTP 404) — đã có trong khung mã (`app/core/errors.py`) và bảng HTTP 404, nhưng thiếu trong
    danh sách mã của `06`.
- Quy tắc ánh xạ lỗi framework: 422 / 4xx kỹ thuật khác → `VALIDATION_ERROR` (không trả lại giá trị đầu vào);
  `GET /health` lỗi phụ thuộc → `503` với thân health.
- `X-Correlation-ID` không phải UUID → server thay bằng UUID mới (cột `audit.decision_log.correlation_id` là `uuid`).

### Lý do
`06` mục 1.1 bắt buộc mọi lỗi có `code`, nhưng chưa có mã cho lỗi máy chủ (ASM-004). Không đổi tên/xóa mã nào.

### Ảnh hưởng
- Backend: `app/core/errors.py`, `app/core/correlation.py`, `app/audit/recorder.py`; test `tests/unit/test_core_errors.py`,
  `tests/unit/test_core_correlation.py`, `tests/integration/test_recorder_health.py`.
- Frontend (Dev 3): hiển thị lỗi chung theo `correlation_id`; có thể gặp `INTERNAL_ERROR`, `NOT_FOUND`.
- Nếu nhóm **không** duyệt: chọn mã khác cho 500 trước khi merge PR #8 (code hiện dùng `INTERNAL_ERROR`).
# Dev 2 source receiving calendar (2026-11-08)

- Implement D1-D explicit per-instance receiving coverage/timezone/holidays and per-address slots,
  active-customer flag, additive upgrade and preserved SE demo calendar seed. Missing legacy slots
  remain unknown. Clarify source DDL and address representation in 05/06 under DEC-SRC-D1-001.
- Source validation primitive rejects uncovered/closed/outside hours; POS lifecycle/API integration
  and CFO warehouse/driver feasibility remain separate. No existing source data reset.
# Dev 2 source sales/store references (2026-11-08)

- Add source-local active store/sales references for approved D1-B validation, with FK and preserved
  synthetic 25-store/100-sales seed. IDs align with synthetic CFO workforce fixtures without runtime
  cross-database reads. Bootstrap is additive; no source order endpoint is enabled by this task.
# Dev 2 source draft creation (2026-11-08)

- Enable approved D1-B POST /orders with server address/contact snapshot, source references, atomic
  lines and optional payload-bound UUID idempotency key protected by transaction lock. Add source-local
  clock with APP_NOW injection and additive src_create_request storage; document 05/06 behavior.
- DRAFT may omit lines/contact/date details; zero-price source lines are accepted without CFO mapping.
  Full validate/edit/submit/cancel and CFO ingestion remain separate implementation tasks.
# Dev 2 source validate/submit (2026-11-08)

- Implement locked source DRAFT→VALIDATED→SUBMITTED_FOR_PLANNING with source-only customer/reference,
  contact, SKU/lines, snapshot coordinates, date-mode and explicit receiving-calendar checks (D1-B/C).
- Validation failure preserves version/status; retries and concurrent submit bump only once. Recheck
  references/calendar on submit, inject APP_NOW into the source timestamp trigger within the transaction.
- CFO planning, stock feasibility, mapping, routing, approval and source PUT/cancel remain separate.
# Dev 2 source versioned PUT/cancel (2026-11-08)

- Complete approved D1-C source full replacement with expected_version/row lock, no-op detection,
  explicit snapshot refresh, validation invalidation and fully revalidated submitted edits.
- Add terminal idempotent cancellation provenance and DB immutability guard; expose cancellation
  metadata in the existing status=CANCELLED feed. Concurrent cancel/edit has one version winner.
- CFO transition/hold/replan/suggestion/approval propagation is not implemented by source writes.
# Dev 2 source authoritative stock batches (2026-11-08)

- Replace interim min(row.as_of) stock read with an atomically published complete batch, authoritative
  empty marker, row-count/content integrity, explicit physical pool IDs and repeatable-read snapshot.
- Add preserved source schema upgrade and explicit `python -m app.stock_batches --snapshot file.json
  --complete-snapshot` publisher. No existing environment was reset; tests use isolated schemas only.
- 05/06 define batch markers, retry/capture behavior and legacy UNKNOWN. CFO pool normalization and
  persistence remain a separate reviewed integration task.

# Dev 2 implemented source OpenAPI candidate (2026-11-08)

- Generate full D1 candidate from implemented read/write/batch routes; document real standard errors,
  ISO dates, health availability, API-key protection and page-count headers. Add consistent request IDs.
- Exercise source lifecycle and stock on SE and shadow instances and compare generated contract exactly.
  Review by Dev 1/3 remains separate from CI drift equality; CFO contract and end-to-end acceptance remain pending.
