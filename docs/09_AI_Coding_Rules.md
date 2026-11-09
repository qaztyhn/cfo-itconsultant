# 09 — AI Coding Rules (CFO MVP)

> **Phiên bản 1.2 (06/11/2026):** bất biến 10 (nhiều xe/đơn, không ghép đơn), 11 (chỉ khóa khi duyệt), 21 (gợi ý lập lại), thêm 24–25 (đơn vị nhỏ nhất, không bí mật trong file nộp); bỏ `MANUAL_PLANNING`/`HANDLED_EXTERNALLY`; `kpi_scopes`.
>
> Lịch sử **v1.1:** bất biến 10, 11 sửa; thêm bất biến 21–23 (đóng kế hoạch cũ, POD theo lần giao, không quản lý thiết bị kho); thứ tự khóa mới; bảng tra tên chuẩn cập nhật.
>
> Quy tắc bắt buộc cho agent AI (và lập trình viên) khi viết mã cho dự án này. Đọc toàn bộ tài liệu này **trước khi viết dòng mã đầu tiên**, và đọc lại mục 4 (bất biến) trước mỗi lần mở PR. Nếu quy tắc ở đây mâu thuẫn với suy đoán của bạn, **làm theo quy tắc**. Nếu quy tắc mâu thuẫn với tài liệu 01–08, **làm theo tài liệu có thứ tự ưu tiên cao hơn ở mục 2** và ghi lại mâu thuẫn.

## 1. Dự án trong ba câu

CFO là lớp điều phối giao hàng đặt trên các hệ thống POS/WMS/ERP sẵn có của từng nước: nó nhận đơn, kiểm tra tồn kho theo thời gian, công suất kho và xe, đề xuất **3 phương án**, để **Dispatcher hoặc Sales đủ điều kiện bấm duyệt**, rồi theo dõi thực thi, ETA, GPS và báo trễ (do dispatcher gửi). MVP là **ứng dụng web chạy thật** (FastAPI + React + PostgreSQL) pilot ở Thụy Điển bằng dữ liệu giả lập, nhưng kiến trúc coi mọi nước bình đẳng. Hệ thống **đề xuất, con người quyết định**.

## 2. Nguồn sự thật và thứ tự ưu tiên

Khi có mâu thuẫn, tài liệu đứng trước thắng:

1. **`09` (tài liệu này)** — quy tắc làm việc và bất biến.
2. **`05_Database_Design.md`** — DDL, enum, ràng buộc (tên bảng/cột/enum là bất biến).
3. **`06_API_Specification.md`** (kèm Phụ lục A) — endpoint, payload, mã lỗi, ma trận quyền.
4. **`04_Tech_Stack_and_Architecture.md`** — kiến trúc, **thuật toán engine**, `MarketConfig`, bảo mật.
5. **`01_PRD.md`** — yêu cầu và quy tắc nghiệp vụ `BR-…`.
6. **`02_User_Stories_and_Acceptance_Criteria.md`** — tiêu chí chấp nhận (thành test).
7. **`07_User_Flows.md`** — luồng và trạng thái.
8. **`03_UI_UX_Specification.md`** — giao diện; **mục 7 của nó (24 điều chỉnh) thắng ảnh thiết kế**.
9. **`08_Development_Plan.md`** — thứ tự xây và seed.

Ảnh thiết kế gốc (`CFO_Web_Platform_UI.pdf`) chỉ là tham khảo hình ảnh; khi khác `03` thì theo `03`.

**Không có trong tài liệu = không được tự bịa.** Xem mục 14 (khi mơ hồ).

## 3. Quy trình làm việc cho mỗi nhiệm vụ

1. **Đọc**: story (`02`), quy tắc (`01`), endpoint (`06`), bảng (`05`), thuật toán (`04`) liên quan. Ghi ra mã story/AC/BR bạn sẽ thỏa.
2. **Lập kế hoạch ngắn** (5–10 dòng): file sẽ tạo/sửa, test sẽ viết, rủi ro. Nếu việc > 400 dòng thay đổi, chia nhỏ.
3. **Viết test trước** (hoặc cùng lúc) cho mọi hành vi mới, đặt tên theo AC (`test_US_PLN_03_AC2_…`).
4. **Viết mã** nhỏ nhất đủ để test pass; đúng cấu trúc thư mục ở `04` mục 4.
5. **Chạy** `ruff`, `black --check`, `mypy` (strict cho `engine/`), `pytest` (và `pnpm lint`, `pnpm test`, `pnpm build` cho frontend). Sửa đến khi xanh.
6. **Tự rà soát** bằng checklist mục 16.
7. **Báo kết quả**: nêu story/AC đã thỏa, file đã đổi, test đã thêm, giả định đã đặt, việc còn lại. Không tuyên bố "xong" khi test chưa chạy.

## 4. Bất biến (không bao giờ vi phạm)

> **ASM-005 — Quyết định phạm vi pilot ngày 07/11/2026:** Điều phối đơn chỉ khi **100% SKU mapping confirmed**. Thiếu SKU → quy trình cũ, không giữ đơn chờ IT trong CFO; không tự chuyển ngược sau mapping. Đây là **hợp đồng mục tiêu chưa implement**, cần xử lý chống double fulfilment trước khi cho chạy thật.


1. **Không tự duyệt.** Chỉ người dùng có quyền bấm duyệt: Dispatcher xử lý đầy đủ; Sales chỉ rank-1 tiêu chuẩn trong cửa hàng mình, đủ điều kiện theo `docs/DECISION_SALES_CONFIRMATION.md`. Không job/engine tự duyệt.
2. **Không tự đổi ngày giao.** Ngày yêu cầu (`date_from/date_to`) chỉ đổi khi tồn tại `ops.date_negotiation` với `outcome = 'agreed'` do dispatcher ghi.
3. **Báo trễ cho khách do dispatcher gửi.** Hệ thống chỉ tạo `notification` trạng thái `draft` cho mẫu `DELAY`. Bốn mẫu còn lại (`CONFIRMED`, `DISPATCHED`, `DELIVERED`, `FAILED`) tự động.
4. **GPS chỉ dispatcher xem.** Mọi endpoint trả vị trí xe kiểm vai trò `dispatcher` ở máy chủ; `customer_service`, `sales`, `warehouse`, `viewer`, khách: `403`. Không thêm GPS vào thông báo, log kỹ thuật, báo cáo tổng hợp theo tài xế, hay phản hồi của endpoint nào khác.
5. **CFO chỉ đọc từ hệ thống nguồn.** Không ghi ngược sang POS/WMS/ERP. Sync-now là CFO GET nguồn theo yêu cầu Sales, polling 5 phút dự phòng.
6. **Engine là hàm thuần.** Trong `engine/` không import `sqlalchemy`, `httpx`, `requests`, `datetime.now`, không đọc env/file, không ghi log, không gọi mạng. Mọi dữ liệu và "bây giờ" truyền vào qua tham số.
7. **Giờ công đơn như nhau ở mọi kho.** Không dùng giờ công làm tiêu chí so sánh giữa các kho; định mức là **một bộ chung** do IT quản lý (`efficiency_factor` mặc định 1,0, không có UI).
8. **Xếp hạng = 0,5 × `n_km` + 0,5 × `n_fill`** (min–max trong các phương án khả thi của cùng đơn, có vùng bỏ qua). **Không quy ra tiền, không dùng "cost/SEK" làm tiêu chí hay hiển thị xếp hạng.** KPI "cost per delivery" là giờ công và km.
9. **Chỉ IT ánh xạ SKU** sang sản phẩm global và gán nhóm xử lý. Không vai trò nào khác gọi được endpoint `mapping/*` ghi. Theo ASM-005, đơn thiếu bất kỳ SKU confirmed **không được CFO điều phối**, mà đi quy trình cũ; mapping về sau không kéo hồi tố đơn cũ vào CFO. Không tự động tạo plan/hold từ mapping.
10. **Một kho xử lý trọn đơn; một xe chỉ chở một đơn trong một chuyến (không ghép đơn); một đơn được dùng nhiều xe.** Engine chọn bộ xe **ít nhất** cùng kho, cùng ngày, chia hàng theo tải/thể tích, các xe tới chênh ≤ `multi_vehicle.max_arrival_spread_min`; không giới hạn số xe. Thiếu loại xe hoặc kín xe → `NO_FEASIBLE_DATE` (check `truck`). Không có trạng thái `MANUAL_PLANNING`/`HANDLED_EXTERNALLY`. Không bỏ qua gate để "cho qua".
11. **Giữ chỗ cả 3 phương án; hàng và giờ công chỉ tính một lần cho (đơn, kho).** Hold 15 phút, gia hạn tối đa 2 lần. Xe/tài xế của các phương án **cùng đơn** được trùng, **khác đơn** thì không (ràng buộc EXCLUDE ở DB). Hàng và giờ công **không** có ràng buộc DB: **lúc lập kế hoạch không khóa** (giữ chỗ `held` được phép vượt); **khi duyệt** phải lấy `pg_advisory_xact_lock` theo `stock:<kho>:<sản phẩm>` và `labour:<kho>:<ngày>` rồi kiểm tra lại; tổng `committed` không bao giờ vượt khả dụng.
12. **Chuyển trạng thái đơn chỉ qua `transition()`** tra `ops.order_transition`; không `UPDATE customer_order SET status` ở nơi khác.
13. **`audit.decision_log` và `ops.milestone_event` chỉ thêm.** Không UPDATE/DELETE, không "sửa bản ghi cho đúng".
14. **Mọi quyết định ghi `decision_log`** qua `record_decision()` trong **cùng transaction** với nghiệp vụ; hành động có lý do bắt buộc (`ALT_SELECTED`, `CRITERIA_CHANGED_RERUN`, `MANUAL_PLAN_CREATED`, từ chối ánh xạ, hủy/lập lại, bỏ nháp báo trễ) phải từ chối nếu thiếu lý do.
15. **Không có mã riêng nước trong lõi.** Cấm `if market == "SE"` ngoài `seed/`, `tests/`, `source_system/seed/`. Mọi khác biệt theo nước nằm ở `ref.market.config`, adapter hoặc bảng sản phẩm.
16. **Không PII trong log kỹ thuật** (tên, điện thoại, email, địa chỉ khách). Chỉ ID, mã đơn, mã kho.
17. **Thời gian lưu UTC**, tính ngày theo `market.timezone`; lấy giờ qua `clock.now()`; không `datetime.now()` / `date.today()` trực tiếp ngoài `core/clock.py`.
18. **Công nhân kho không có tài khoản.** Quản lý/trưởng ca ghi mốc và điểm danh thay.
19. **Một nhân viên chỉ một phân công hiệu lực; mỗi kho/cửa hàng đúng một quản lý chính.**
20. **Không hard-code số cấu hình** (giờ hữu ích, 90%, hold 15 phút, ngưỡng 33/66, buffer 2 ngày, tốc độ fallback…). Đọc từ `MarketConfig` hoặc bảng cấu hình.
21. **Đóng kế hoạch cũ trong cùng transaction.** Lập lại (`APPROVED → SUBMITTED`), xếp lại (`FAILED → SUBMITTED`), hủy, chạy lại: kế hoạch cũ → `superseded`, giữ chỗ → `released`, `trip_stop`/`delivery_trip` chưa xong → `cancelled`, xóa `approved_plan_id`/`committed_date`/`promise_*` (giá trị cũ vào `decision_log.before`). Không để hai kế hoạch `approved`/`manual` cùng tồn tại. Gợi ý lập lại tự động (`replan_suggestion`): tính coi như kế hoạch hiện tại của chính đơn không tồn tại, **không giữ chỗ**, **không bao giờ tự duyệt**; khi dispatcher duyệt thì đóng kế hoạch cũ và commit kế hoạch mới trong cùng transaction.
22. **POD theo từng lần giao** (`trip_stop_id`), không theo đơn; không UPDATE POD cũ khi giao lại.
23. **Không có quản lý thiết bị kho trong MVP.** Không tạo bảng, endpoint, check hay mã `PREP_NO_EQUIPMENT`; năng lực cẩu/ben chỉ là thuộc tính xe.
24. **Giờ công theo đơn vị cơ sở nhỏ nhất.** `prep_qty = qty_base / base_units_per_prep_unit` (không làm tròn); hàng không chia nhỏ được thì làm tròn lên; `line` = 1.
25. **Không bí mật trong file.** Không mật khẩu (kể cả mật khẩu demo), khóa API, token hay dữ liệu mật trong mã, README, seed, tài liệu nộp; đọc từ biến môi trường.

26. **Sales chỉ duyệt có điều kiện.** Cùng cửa hàng nguồn, rank 1, 5 gate pass, reserve safe, một xe, không transfer/manual/replan/date change, dữ liệu mới, hold còn hạn; dùng chung ApprovalService, lock và audit. Nếu đơn cũ chưa duyệt tranh công suất chưa chứng minh đủ nguồn lực, Sales phải chuyển Dispatcher.
27. **FIFO hiển thị, không FIFO thực thi bắt buộc.** Danh sách theo `submitted_at,id` tăng dần; chèn đơn giao sớm vào lịch nếu không lấn `committed` của đơn cũ. `held` stock/labour có thể vượt, không được hứa cam kết trước khi duyệt.

28. **ASM-006:** mọi thay đổi phân công, owner, quản lý, nghỉ việc ghi actor + before/after và `decision_log` cùng transaction. Sửa hồi tố chỉ admin đủ quyền, phải có lý do; quản lý chỉ rời vị trí sau khi có người thay thế. Chưa có action code phải đề xuất cập nhật hợp đồng trước, không bỏ audit.
29. **ASM-007/Q11:** Warehouse Manager lập lịch ca chính thức từng người/ngày; `expected_staff` chỉ dùng so sánh, không tự chia/dồn nhân viên theo ca. `attendance_gen` chỉ tạo `planned` từ lịch xác nhận. `all_present` không tạo ca hoặc thay đổi phân công. Sửa lịch và điểm danh có audit; hồi tố cần lý do. Thiếu lịch không tính công suất như đã đủ người.

30. **D1-01/02 — chuyển kho audit:** `TRANSFER_CANCELLED` dành cho hủy (reason bắt buộc, actor/ts/before/after; không dùng `TRANSFER_APPROVED`). `TRANSFER_CONFIRMED` **chỉ** kho nguồn xác nhận xuất; `TRANSFER_RECEIVED` **chỉ** kho đích nhận, không fake CONFIRMED với stage khác. Audit append-only trong **cùng transaction** với state change; RBAC/warehouse scope/idempotency. Chưa có hợp đồng hoàn nguyên WMS thì fail-closed.
31. **D1-03 — scope SKU CFO:** quản trị viên **có thẩm quyền** theo market/pilot quản lý/phê duyệt, lưu version/hiệu lực/audit. Cấm tự suy scope từ mappings hoặc Source batch; SKU trong scope sai mapping => không ghi bất kỳ phần nào của batch.
32. **D1-04 — evidence tồn kho độc lập:** Warehouse Manager cung cấp chứng cứ từ kho/WMS, quản trị viên có thẩm quyền duyệt; phải lưu evidence/provenance, approver, version, hiệu lực, audit trước khi cộng SKU cùng kho/global product. Thiếu/hết hiệu lực/không chắc => fail closed. Không tự invent DDL/field/route/evidence action chưa được Dev 1/2 review theo `05`/`06`.

**DEC-WMS-READONLY-20261109 (Owner clarification supersedes Q2 reconciliation workflow):** WMS owns physical transfer ledger, stock corrections and stock reconciliation. CFO read-only GETs authoritative WMS stock, checks batch freshness/completeness and subtracts its **own** held/committed reservations for ATP; CFO must **not** run a parallel WMS reconciliation queue/approval, synthesize extra inbound on-hand or subtract source physical stock a second time. Existing CFO transfer confirm/receive code/spec (#127) requires review, not automatic merge. No WMS reconciliation 24-hour escalation; WMS owners handle WMS discrepancies. [Decision](decisions/DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md).

33. **Owner Q1 — grant đầu tiên:** chỉ System Admin được Owner ủy quyền mới cấp Stock Admin grant đầu tiên cho market; **cấm self-grant**, cấm seed/implicit superuser permissions; identity, scope, actor, reason, timestamps, before/after audit. Thiếu quyền/ủy quyền ⇒ fail closed; không đổi S1/S2.
34. **Owner Q2 — WMS transfer evidence:** giả định WMS cũ ghi nhận xuất/nhập chuyển kho, nhưng chưa chứng minh WMS API expose ID/ACK. Dev 2 xác minh adapter/CSV; ưu tiên chứng cứ WMS gắn transfer/warehouse/SKU/qty/batch, thiếu thì Warehouse Manager nộp và reviewer độc lập có quyền theo market phê duyệt với audit. Không suy included-in-stock từ snapshot timestamp hoặc quantity delta; không double subtract/add, không ghi ngược WMS, test replay/rollback/concurrent/503. **24h escalation Q3 chưa duyệt**. [Quyết định](decisions/DEC_STOCK_BOOTSTRAP_AND_WMS_RECON_20261109.md).

## 5. Quy ước backend (Python)

- **Phiên bản/công cụ:** Python 3.12; FastAPI; SQLAlchemy 2.0 async; Alembic; Pydantic v2; httpx; APScheduler; pytest, pytest-asyncio; ruff, black, mypy.
- **Typing:** type hint đầy đủ; `mypy --strict` bắt buộc cho `engine/`; không `Any` trừ biên JSON và phải ghi lý do.
- **Tiền và số:** `Decimal` cho tiền, khối lượng, giờ công; không `float` cho tiền. Làm tròn theo hàm tiện ích duy nhất (`core/numbers.py`).
- **Cấu trúc:** theo `04` mục 4. Router mỏng (validate, quyền, gọi service); service chứa nghiệp vụ và transaction; repository/query nằm trong service hoặc `domain`; engine thuần.
- **Phụ thuộc:** `api → services → (engine, adapters, providers, domain)`; kiểm bằng import-linter trong CI.
- **Transaction:** mỗi use case một transaction; ghi `decision_log` trong cùng transaction; khi duyệt, khóa theo thứ tự cố định **kho → sản phẩm → ngày công suất → xe → tài xế** (id/ngày tăng dần) để tránh deadlock: hàng và ngày công suất dùng `pg_advisory_xact_lock`, xe/tài xế dùng `SELECT … FOR UPDATE`. Không `FOR UPDATE` trên `ops.stock_snapshot`.
- **Idempotency:** `Idempotency-Key` ở các endpoint ghi nêu ở `06` mục 1; lưu `ops.idempotency_key`; cùng key + khác body → `409 IDEMPOTENCY_CONFLICT`.
- **Lỗi:** dùng lớp lỗi miền (`DomainError(code, message, details)`); middleware chuyển thành định dạng chuẩn `06` mục 1.1 kèm `correlation_id`. Không để lộ stack trace ra client.
- **Phân trang, lọc, sắp xếp:** theo `06` mục 1; mặc định `page_size = 50`.
- **Job:** mỗi job idempotent, chạy được qua `POST /internal/tick?job=…`, ghi log JSONL, không giả định chạy đúng một lần.
- **Cấu hình:** Pydantic Settings đọc env; bí mật không có trong mã/ảnh/log.

## 6. Quy ước cơ sở dữ liệu và migration

- Nguồn sự thật là `05`. **Không đổi tên/xóa** bảng, cột, enum, ràng buộc; muốn đổi thì sửa `05` + thêm migration + ghi `CHANGELOG` trong cùng PR.
- Alembic: một migration một ý, có `upgrade` và `downgrade`; không `autogenerate` rồi gộp nguyên; kiểm bằng chạy trên DB trống và trên DB có seed.
- Mọi bảng nghiệp vụ có `created_at`, `updated_at` (trigger); khóa chính `bigint identity`; khóa ngoài đầy đủ; ràng buộc `CHECK` khớp quy tắc.
- Chỉ mục theo `05` mục 9; thêm chỉ mục khi truy vấn thật chậm và có `EXPLAIN` chứng minh.
- **Sản phẩm từng nước:** bảng `ref.product_<cc>` và view `ref.v_product_local`; thêm nước bằng `tools/add_market.py`, **không** thêm nhánh `if` trong mã.
- Truy vấn: tham số hóa, không nối chuỗi SQL; không N+1 (dùng `selectinload`/join có chủ đích).
- Seed: `seed/generate_data.py` với random seed cố định; chạy lại cho kết quả giống nhau; đồng hồ demo qua `APP_NOW`.

## 7. Quy ước API

- Đường dẫn, phương thức, payload, mã lỗi **đúng `06`** (kể cả Phụ lục A). Thêm endpoint ngoài tài liệu cần cập nhật `06` trước.
- Mọi endpoint có: kiểm xác thực, kiểm vai trò **và phạm vi địa điểm** ở máy chủ, schema Pydantic cho request/response, ví dụ trong OpenAPI, test cho đường được phép và bị cấm.
- Ngoài phạm vi → `404` (không lộ sự tồn tại); thiếu quyền trong phạm vi → `403`.
- Thời gian ISO 8601 có múi giờ; ngày `YYYY-MM-DD`; tiền là chuỗi thập phân.
- Không trả dữ liệu thừa cho vai trò thấp (CS/sales/driver nhận bản rút gọn theo `06` mục 5.1).
- Giữ tương thích: frontend sinh client từ OpenAPI; CI chạy `openapi diff` để chặn thay đổi phá vỡ.

## 8. Quy ước engine (`backend/app/engine/`)

- Triển khai **đúng `04` mục 6** (công thức, thứ tự bước, mã lý do). Không "cải tiến" thuật toán theo ý riêng; nếu thấy lỗi, báo và sửa tài liệu trước.
- Hàm thuần, `frozen dataclass`, không side-effect; mọi biên thời gian truyền vào `now`.
- Mỗi bước có test bảng (`pytest.mark.parametrize`) gồm ca biên (mục `08` 6.2); phủ ≥ 90% dòng.
- Số học: dùng `Decimal` hoặc phút nguyên; **làm tròn ETA lên 15 phút** theo cấu hình; không dùng `float` cho giờ công.
- Kết quả có thể giải thích: mọi loại ứng viên có `code` và `detail.message`; `reason_codes` và `explanation` sinh từ mẫu câu cố định (không gọi AI trong MVP).
- Không gọi ORS trong engine; đọc `route_matrix` đã chuẩn bị; thiếu cặp → xử lý theo `routing.allow_fallback`.
- Hiệu năng: lập kế hoạch một đơn < 2 giây; tránh quét toàn bộ dữ liệu (nạp ngữ cảnh theo kho và theo chân trời 14 ngày).

## 9. Quy ước frontend (React + TypeScript)

- **TypeScript `strict`**, ESLint + Prettier; không `any` (trừ khi có chú thích lý do); client API sinh tự động (`openapi-typescript`), không viết tay kiểu dữ liệu API.
- **Thiết kế:** theo `03` — token màu/phông ở mục 2, thành phần ở mục 4, màn hình ở mục 5, **24 điều chỉnh ở mục 7 là chuẩn**. Dùng Tailwind với token đã khai báo; không hard-code màu hex trong thành phần (trừ bộ token).
- **Dữ liệu:** TanStack Query; polling 15–30 giây cho Order queue/Tracking/Alerts/Prep queue; không WebSocket trong MVP.
- **Quyền:** ẩn điều khiển không có quyền (và máy chủ vẫn kiểm); mục menu lọc theo vai trò (`03` mục 3.2).
- **Che dữ liệu cá nhân** bằng `MaskedText` theo vai trò; không log PII ra console.
- **Trạng thái:** mọi màn có trạng thái rỗng, tải (skeleton), lỗi (kèm `correlation_id`, nút Retry).
- **Modal lý do** (`ReasonModal`) bắt buộc cho các hành động ở `03` mục 4; nút xác nhận chỉ bật khi đủ.
- **Driver PWA:** nút ≥ 48px, một hành động chính mỗi màn; hàng đợi offline bằng IndexedDB với `idempotency_key` và `occurred_at` là giờ chạm; thông báo riêng tư và xin quyền vị trí **trước** khi gửi GPS; không cache dữ liệu cá nhân quá cần thiết.
- **Truy cập:** nhãn cho mọi ô nhập, tương phản AA, điều hướng bàn phím, `aria-live` cho cảnh báo mới; trạng thái rủi ro luôn có chữ và biểu tượng, không chỉ màu.
- **i18n:** chuỗi qua `i18next`; mặc định tiếng Anh; định dạng ngày giờ/số theo `03` mục 8.

## 10. Bảo mật, riêng tư, logging

- JWT HS256, hết hạn 8 giờ; mật khẩu argon2; khóa/bí mật chỉ trong biến môi trường; không commit `.env`.
- Kiểm quyền theo vai trò **và** phạm vi địa điểm cho mọi truy cập dữ liệu; không tin tham số `location_id` từ client mà không đối chiếu phạm vi người dùng.
- CORS giới hạn origin; giới hạn tần suất `/auth/login`; `/internal/*` bằng khóa riêng.
- **Log kỹ thuật** JSONL theo `04` mục 10: `ts, level, service, correlation_id, order_id, market, event, duration_ms, extra`; **không PII**; không in toàn bộ body request chứa dữ liệu khách.
- **Nhật ký quyết định** trong DB: `record_decision(action, entity, entity_id, order_id?, plan_id?, reason_code?, reason_text?, snapshot?, before?, after?)`; dùng đúng mã hành động ở `04` mục 10.
- **D3 owner-approved GPS:** thu mỗi **30 phút**, offline queue chỉ trong trip `on_road` và ca chính thức, server derive employee từ JWT; chỉ Dispatcher **được gán trip** được xem live/history trong ca (không mở toàn market). Trip terminal hoặc hết ca ⇒ dừng thu và thu hồi live access ngay, xóa queue offline không hợp lệ, từ chối replay; vị trí đã thu hợp lệ có thể giữ **tối đa 7 ngày** để tra soát theo quyền riêng/audit, không phải 30 ngày; lịch sử duty/tachograph không bị xóa theo GPS. Thiếu mapping Dispatcher–trip phải fail closed; migration/contract test trước khi mở API. GPS không dùng để chấm công hoặc đo giờ nghỉ nhân viên. Không theo dõi ngoài ca; DPIA/notice trước dữ liệu thật.
- **D4 owner-approved notification:** dùng server template versioned `CONFIRMED|DISPATCHED|DELIVERED|FAILED|DELAY`, chỉ biến allowlist từ public order/status/approved ETA/reason enum; **không free-text subject/body, GPS, tên tài xế, tên người nhận hay CS notes**. Dispatcher chỉ chỉnh ETA và câu/lý do mẫu, duyệt DELAY draft. Giữ Mailpit/test-only, quiet-hours 21:00–07:00 theo market và retry cap hiện có; 5/15 phút backoff chưa là quyết định owner.
- **D5 owner-approved GDPR/retention:** GPS ngừng thu/live khi trip/ca kết thúc và lịch sử hợp lệ xóa sau tối đa 7 ngày. Customer contact/CS 90 ngày, operational order 365 ngày, employee nonstatutory contact 90 ngày, shifts/attendance 24 tháng (legal review), app/security logs 30/90 ngày, staging backup tối đa 30 ngày; luật riêng cho tachograph/driver work time/accounting. Không xóa audit/milestone bất biến; chỉ xóa/ẩn danh theo per-category policy có anchor/legal hold và dry-run, review privacy/legal trước real data. `data_retention_days` legacy không chứng nhận GDPR. D2 CSV UTF-8/version/ISO/SHA idempotent retry controlled, không đi qua approval. Xem `docs/decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md`.

**D1 / DEC-SRC-D1-001 — đã được owner duyệt 08/11/2026:** Source `GET /orders,/customers,/products,/inbound,/fleet/calendar,/addresses` có page1/page_size50/max500 + `updated_since >=` với stable composite key; `/stock` dùng coherent published batch không phân trang, zero-row batch phải được publish đầy đủ. **Q9 owner-approved `DEC-SRC-Q9-ERROR-001`: khi chưa có batch nào hoàn chỉnh được publish, Source GET `/stock` trả 503 `STOCK_UNAVAILABLE` với body lỗi chuẩn và `X-Correlation-ID`, không coi unknown là 0; CFO phải báo đồng bộ lỗi và fail-closed với stale/unknown (không tự gia hạn `as_of`).** POS DRAFT cần customer/address/store/date_mode, validate đủ contact/lines/date/receiving calendar, qty >0, `unit_price` decimal string 2 chữ số **cho phép 0**, 422 field errors no PII. Source PUT sau submit chỉ qua full revalidation, `expected_version`, row lock và `409 VERSION_CONFLICT`; CANCELLED terminal có lý do và version, adapter phải ingest cả status CANCELLED, không viết ngược POS. Đơn CFO đã APPROVED/chưa DISPATCHED mà source sửa → tự chạy `replan_suggestion` **không hold/auto-approve**, Dispatcher mới duyệt; sau DISPATCHED alert-only. Q8 receiving calendar riêng ca kho/tài xế; Q10 owner đã **thay bằng DEC-SRC-Q10-SKU-001**: một SKU một đơn vị tồn cố định, một dòng `(batch_id,warehouse_code,sku)`, đổi quy cách bán trong cùng SKU; **không tạo physical_stock_pool_id hay gom alias theo số lượng tương đương**. Nếu nhiều local SKU mapping một global mà không xác minh tồn độc lập thì fail-closed; không công bố snapshot một phần như đầy đủ. Dev 1/2/3 phải review DDL/API state transition và test trước code merge; không tự mặc định trạng thái CFO cho phép huỷ nếu 05 transition chưa có. Nguồn: `docs/decisions/DEC_SRC_D1_APPROVED_20261108.md`.

**D8: CHƯA PHÊ DUYỆT TOÀN BỘ; RIÊNG RÀ SOÁT VẬN HÀNH 07:00 VÀ 13:00 EUROPE/STOCKHOLM ĐÃ ĐƯỢC OWNER DUYỆT.** Tất cả scheduler ticks phải tôn trọng ca làm, 11h rest, GPS live revoke at trip/shift end and seven-day restricted history expiry và role scopes; không tự tạo thông báo DELAY gửi khách, không approve plan, không ghi routing không có Sales/Dispatcher. Chi tiết cadence tại `docs/proposals/D8_SCHEDULER_SWEDEN_PROPOSAL_20261108.md` chỉ là đề xuất cần owner chốt.

## 11. Quy tắc test

- **Mọi AC trong `02` có ít nhất một test**; đặt tên `test_US_<EPIC>_<NN>_AC<k>_<mô_tả>`.
- **Engine:** unit test thuần (không DB); ca biên theo `08` mục 6.2.
- **Integration:** DB PostgreSQL thật (Docker service); không mock DB cho ràng buộc, trigger, EXCLUDE.
- **E2E:** 18 kịch bản ở `08` mục 6.3 bằng Playwright trên Docker Compose.
- **Quyền:** mỗi hàng ma trận `06` mục 3 có test cho đường cho phép và bị cấm.
- **Đồng thời:** test lập kế hoạch đồng thời cho phép giữ chỗ vượt; test hai giao dịch duyệt cùng lúc tranh một xe, tranh cùng SKU ở cùng kho, tranh cùng ngày công suất: mỗi trường hợp đúng một thành công.
- **Vòng đời:** test lập lại sau duyệt rồi duyệt lại; FAILED → xếp lại → giao lại có hai POD; thông báo `CONFIRMED` mới sau lập lại.
- **Ổn định:** test không phụ thuộc giờ thật (dùng `clock`/`APP_NOW`) hay thứ tự chạy; seed cố định.
- Không xóa/skip test để CI xanh; test hỏng do yêu cầu đổi thì sửa test **và** tài liệu.

## 12. Git, commit, PR

- Nhánh: `feat/<epic>-<mô-tả>`, `fix/…`, `chore/…`. Commit nhỏ theo Conventional Commits (`feat(planning): …`).
- Mỗi PR: mô tả story/AC/BR đã thỏa, ảnh chụp hoặc mô tả thay đổi UI (so với `03`), danh sách test, ghi chú migration, **CHANGELOG** nếu đổi `05/06`.
- PR ≤ ~400 dòng thay đổi logic (không tính sinh tự động và seed); lớn hơn thì chia.
- CI phải xanh: ruff, black, mypy, pytest, openapi diff, build web.
- Không merge mã chết, `print` gỡ lỗi, `TODO` không kèm số issue, khóa hoặc dữ liệu thật.

## 13. Điều agent KHÔNG được làm

- Đổi tên/xóa bảng, cột, enum, endpoint, mã lỗi, mã hành động mà không cập nhật tài liệu.
- Thêm thư viện lớn, dịch vụ trả phí, hoặc phụ thuộc cloud trả phí (Azure, SMS thật…) — MVP dùng công cụ miễn phí ở `04` mục 3.
- Thêm microservice, Celery/Redis, WebSocket, ORM khác, framework UI khác (Material, Ant…) hay phông khác ngoài `03`.
- Hard-code dữ liệu giả vào mã nghiệp vụ; mọi dữ liệu giả ở `seed/` và `source_system/seed/`.
- Đưa AI/LLM vào đường quyết định (xếp hạng, gợi ý ánh xạ, giải thích) — MVP dùng quy tắc; AI là phần mở rộng.
- Gửi email/SMS thật ngoài cấu hình staging đã định; SMS luôn mô phỏng.
- Tắt kiểm tra quyền, trigger, ràng buộc DB hoặc test "cho nhanh".
- Ghi PII vào log, ảnh chụp màn hình, dữ liệu seed thật của người thật.
- Thêm GPS vào bất kỳ chỗ nào khách/CS/sales thấy được.
- Thêm lại quản lý/xếp lịch thiết bị kho (ngoài MVP); không được xóa thuật toán nhiều xe cho một đơn đã nằm trong MVP.
- Dùng chữ hay mã "cheapest/cost/SEK" cho xếp hạng (dùng `LOWEST_SCORE_OF_3`, "rank score").
- Tự quyết các điểm mơ hồ của nghiệp vụ mà không ghi giả định (mục 14).

## 14. Khi mơ hồ hoặc thiếu thông tin

**Bắt buộc ghi sổ quyết định:** trước khi bắt đầu task/PR, đọc các mục liên quan trong `docs/ASSUMPTIONS.md`. Khi owner/nhóm có thẩm quyền chốt thêm hoặc thay đổi assumption/quy tắc nghiệp vụ, Dev/agent phải bổ sung hoặc cập nhật trong file đó **cùng PR**; ghi mã duy nhất, ngày, ai chốt, quy tắc, trường hợp biên, nguồn PR/comment, ảnh hưởng và trạng thái triển khai. Quyết định cũ bị thay thì ghi `superseded by`, không xóa. Đề xuất chưa được duyệt không được ghi thành đã chốt. Thay đổi DB/API vẫn tuân thủ quy trình contract ở `05`/`06`, migration/test và `CHANGELOG`; ghi trong sổ **không phải bằng chứng code đã chạy**.


1. Tìm trong `01–08` (dùng thứ tự ưu tiên mục 2). Nhiều chỗ đã có số cụ thể (ví dụ giờ hữu ích 7,0, 90%, 15 phút, 2 lần gia hạn, 33/66%, 14 ngày, 9 giờ lái).
2. Nếu vẫn thiếu: **chọn phương án đơn giản, an toàn, tuân thủ bất biến**, ghi **giả định** vào mô tả PR và `docs/ASSUMPTIONS.md` (mã `ASM-xxx`, ngày, bối cảnh, phương án chọn, ảnh hưởng).
3. Nếu quyết định ảnh hưởng hợp đồng (DB/API), **dừng và hỏi** (mở issue/`docs/QUESTIONS.md`) trước khi viết mã.
4. Không bao giờ đoán các quy tắc kinh doanh nhạy cảm: duyệt, đổi ngày, báo trễ cho khách, quyền xem GPS, quyền ánh xạ SKU, quyền xem doanh thu, nội dung thông báo khách.

## 15. Mẫu giao việc cho agent (dùng cho từng milestone)

```
Nhiệm vụ: <tên> (milestone M<n>, luồng A|B|C)
Story/AC: US-…, AC1..ACk
Quy tắc: BR-…
Đọc: 05 mục …, 06 mục …, 04 mục …, 03 mục …
Việc cần làm: <danh sách file/hàm/màn>
Test bắt buộc: <tên test theo AC>
Không làm: <các mục ở 13 liên quan>
Đầu ra: mã + test + ghi chú giả định; chạy ruff, mypy, pytest, build web; cập nhật tài liệu nếu đổi hợp đồng
```

**Ví dụ (M4, engine ATP):** "Triển khai `engine/atp.py` theo `04` mục 6.2 bước 2a; thỏa US-ATP-01 AC1–AC5 và BR-ATP-01..04; viết test bảng đủ ca: đủ ngay, đủ sau hàng nhập (có thêm thời gian nhận kho), hàng nhập chưa xác nhận, giữ chỗ của đơn khác (held còn hạn + committed), 14 ngày không đủ; hàm thuần, `mypy --strict`; không import sqlalchemy; trả `stock_ready_date`, phân loại *đủ ngay/đủ sau hàng nhập/không đủ* và phần thiếu cho gợi ý chuyển kho."

## 16. Checklist trước khi báo "xong"

- [ ] Đúng story/AC/BR đã nêu; mọi AC có test và test pass.
- [ ] Không vi phạm mục 4 (bất biến) — đã rà từng điểm liên quan.
- [ ] Hợp đồng `05/06` không đổi, hoặc đã cập nhật tài liệu + migration + `CHANGELOG`.
- [ ] Quyền (vai trò **và** phạm vi) được kiểm ở máy chủ; có test đường bị cấm.
- [ ] Mọi quyết định ghi `decision_log` đúng mã hành động, kèm lý do khi bắt buộc.
- [ ] Đã đối chiếu `docs/ASSUMPTIONS.md`; quyết định mới được owner duyệt đã ghi trong sổ (mã/ngày/nguồn/impact/trạng thái), đồng bộ spec/CHANGELOG; nếu không có, PR ghi `Assumptions: reviewed — none`.
- [ ] Không PII trong log; không GPS ở nơi không được phép.
- [ ] Lập lại/hủy/xếp lại/duyệt gợi ý đóng kế hoạch cũ; khóa hàng và giờ công khi duyệt (bất biến 11, 21).
- [ ] Không mật khẩu, khóa API hay thông tin mật trong file commit/nộp (bất biến 25).
- [ ] Không hard-code số cấu hình; không mã riêng nước; giờ lấy qua `clock`.
- [ ] Engine vẫn là hàm thuần (không import hạ tầng).
- [ ] UI khớp `03` (kể cả mục 7); có trạng thái rỗng/tải/lỗi; truy cập được.
- [ ] `ruff`, `black`, `mypy`, `pytest`, build web đều xanh.
- [ ] Mô tả PR nêu giả định và việc còn lại.

## 17. Bảng tra nhanh tên chuẩn

**Vai trò (`ref.user_role`):** `admin` (IT) · `dispatcher` · `warehouse` · `sales` · `driver` · `customer_service` · `viewer` (Business owner `kpi_scopes = {revenue_all}`; Project lead `{ops}`; không thêm vai trò mới). **KPI scopes:** `revenue_all`, `ops`.
**Trạng thái đơn:** `SUBMITTED`, `BLOCKED_UNMAPPED_SKU`, `PLANNED`, `NO_FEASIBLE_DATE`, `APPROVED`, `PREPARING`, `GOODS_READY`, `LOADED`, `DISPATCHED`, `DELIVERED`, `FAILED`, `CANCELLED`.
**Dạng ngày:** `exact`, `range`, `latest`.
**Sự kiện:** `START_PREP`, `PREP_PAUSED`, `PREP_RESUMED`, `GOODS_READY`, `LOADED`, `DISPATCHED`, `DELIVERED`, `FAILED`, `SHORTAGE`, `BREAKAGE`, `VEHICLE_ISSUE`, `SHIFT_CHANGE`.
**Rủi ro:** `ON_TRACK`, `AT_RISK`, `PREDICTED_LATE`, `OVERDUE`; màu `green`, `yellow`, `orange`, `red`.
**Giữ chỗ:** `held`, `committed`, `released`, `expired`, `consumed`; kế hoạch: `proposed`, `expired`, `approved`, `superseded`, `rejected`, `manual`.
**Thông báo:** mẫu `CONFIRMED`, `DISPATCHED`, `DELIVERED`, `FAILED`, `DELAY`; trạng thái `draft`, `queued`, `sent`, `failed`, `suppressed`; kênh `email`, `sms_sim`.
**Chuyển kho:** `suggested`, `approved`, `source_confirmed`, `received`, `cancelled`.
**Check gate:** `stock`, `preparation`, `truck`, `site_date`, `safety` với mã `STOCK_OK/STOCK_AFTER_INBOUND/STOCK_SHORT`, `PREP_OK/PREP_AFTER_CUTOFF/PREP_NO_CAPACITY`, `TRUCK_OK/NO_TRUCK_FIT/TRUCK_BUSY/NO_DRIVER`, `DATE_OK/OUTSIDE_RECEIVING_HOURS/DATE_AFTER_DEADLINE/NON_WORKING_DAY`, `SAFETY_OK/OVER_LOAD/DRIVER_HOURS_EXCEEDED/LICENCE_EXPIRED` (và `ROUTE_DATA_UNAVAILABLE` khi `routing.allow_fallback = false`).
**Nhóm xử lý:** `N1` Small items & accessories · `N2` Boards, sheets & tiles · `N3` Bagged cement & mortar · `N4` Bulk materials · `N5` Long goods · `N6` Large & fragile items (không gắn cờ FRAGILE); đơn vị chuẩn bị `line`, `pallet`, `m3`, `bundle`, `package`.
**Mã lý do xếp hạng:** `LOWEST_SCORE_OF_3`, `LOWEST_SCORE_OF_2`, `ONLY_FEASIBLE`.
**Mã hành động nhật ký:** xem `04` mục 10.
**Cấu hình:** `MarketConfig` ở `04` mục 8 (cộng `routing.allow_fallback` ở `06` Phụ lục A).
**Doanh thu:** recognised = Σ `total_amount` đơn DELIVERED theo ngày giao (múi giờ market); booked = đơn APPROVED…DISPATCHED theo `committed_date`; hai góc nhìn store/warehouse không cộng với nhau; chỉ tiền hàng.
**Lần chạy kế hoạch:** `kind` = `initial` | `rerun` | `replan_suggestion` (không giữ chỗ). Alert `REPLAN_SUGGESTED`; hành động nhật ký `REPLAN_SUGGESTED`, `REPLAN_KEPT`, `REVENUE_EXPORTED`.
**Công thức cốt lõi:** giờ công dòng = `(fixed_hours + prep_qty × labour_hours_per_unit) × min(Π cờ, 2.0)`; công suất ngày = `Σ ca (người có mặt × giờ hữu ích) × 0.90 − đã đặt`; điểm = `0.5·n_km + 0.5·n_fill`; tiêu hao = `(forecast_eta − planned_eta) / max(30', promise_end − planned_eta)`; xanh < 33%, vàng 33–66%, cam > 66%, đỏ khi slack âm 2 lần liên tiếp; dự trữ lập kế hoạch an toàn ≥ 2 ngày.

## 18. Owner-approved cross-workstream rules (2026-11-09)

Read [DEC-OWNER-20261109](decisions/OWNER_CROSS_WORKSTREAM_APPROVED_20261109.md) and `docs/ASSUMPTIONS.md` before editing T07/T18/D7/M6/GPS/D4/Planning UI/KPI. The owner's approval is a **business/contract decision**, not permission to disable tests, waive legal review or auto-merge code.

1. **S1–5:** Admin must have explicit market grant; creator/submitter differs from approver; scope version effective after approval and bound by Source `batch.as_of`; expected in-scope warehouse × SKU missing = unknown and complete stock write rejected, never zero. Evidence of independent stock ≤30 pilot days; revoke on mapping/unit/scope changes; do not infer SKU scope or independence.
2. **T18-1–3:** WMS timestamp alone cannot prove transferred goods are included in stock; without reliable inclusion proof do not add inbound to stock available. Approved market-default lead with provenance only; block reversal after source confirmation until separate decision.
3. **D7-1–4/M6-1:** Qualified verified 56-day *daily* proof, explicit off-duty versus missing, real HR/tachograph evidence distinct from synthetic demo; official shifts and 11h rest; no unknown licence/mass/Regulation 561 scope auto-pass. Successful POD unique by `trip_stop`; forward DB migration required to replace old order-level index.
4. **G1–5:** One auditable primary Dispatcher/trip, explicit market-scoped assignment authority, no broad GPS reads. Per-driver notice/ack + privacy/legal signoff for real GPS; every-30-min device cadence, ≤100 positions/batch, delete on trip/duty end, simulator has separate authenticated producer.
5. **N1–5:** Dispatcher-approved, versioned DELAY start/end; changed date requires negotiated agreement; immutable approved template version + typed allowlist variables, queued notification in caller transaction, delivery only after commit from outbox; Mailpit/test recipients and approved retry cap.
6. **API-1/2/KPI-1/2:** Five-gate result uses `passed` not `pass`, rejected candidates are flat, no invented driver names. Exactly 10 published operational KPI keys; two unsupported diagnostics must remain `null`; market-local approval/delivery/work_date cohorts as approved.

Deliver changes in **focused reviewed PRs** with migration + actual PostgreSQL RBAC/concurrency/rollback/contract tests, preserving existing fail-closed guard until proven. PR #136 is already merged; Dev 3 must make a new hotfix PR, not rewrite history. Do **not** automatically merge code PRs or enable actual worker GPS/email sending solely because a decision record exists.

### 18.1 Approved amendment, 09/11/2026 — GPS 7 days; operational reviews twice daily

Read [DEC-GPS-RET-20261109 / DEC-D8-OPS-20261109](decisions/DEC_GPS_7D_AND_D8_REVIEW_TIMES_20261109.md) before GPS/M6/retention/scheduler PRs. Supersede immediate **raw historical GPS** purge: stop live collection/read at trip or official duty end, store only valid history up to **7 days** under case-specific, audited and privacy/legal-approved authority; purge invalid queues immediately, erase expired data, address backups. Do not enable historical GPS to all Dispatchers or bypass GDPR review. The two operational review times **07:00 and 13:00 Sweden local time** are approved; this does not approve all D8 cron frequencies, tick API or paid hosting. Update tests/contracts in focused PRs; never auto-merge code.

**ASM-WMS-RESERVATION-20261109:** Owner permits assuming WMS supports order reservations; not proof of WMS API or authorization for CFO write. WMS reserve affects `available`, not `on_hand`; never double-subtract an already-reflected WMS reservation. CFO outbound reserve/status/release is **pending explicit owner approval and reviewed idempotent/atomic acknowledgment/timeout contract**. Preserve current read-only guard until then. [Assumption record](decisions/ASM_WMS_RESERVATION_ASSUMED_20261109.md).

**DEC-WMS-REVERSE-SKU-20261109 (conditional):** For future explicitly authorized CFO→WMS reserve/release, reverse map global product to verified **WMS-native original SKU per market/warehouse**, preserving order-line POS local_sku, confirmed mapping/version, source WMS inventory unit and exact quantities. One global can map to multiple local SKUs: **never choose first/guess/pool aliases**. Do not assume POS SKU = WMS SKU without proven source mapping. Missing/ambiguous mapping, wrong unit, warehouse or version => **no WMS write**. Match WMS acknowledgment and do not subtract an already WMS-reflected reservation twice. The owner has not yet approved WMS write capability. [Decision](decisions/DEC_WMS_REVERSE_SKU_FOR_RESERVATIONS_20261109.md).
