# 02 — User Stories & Acceptance Criteria (CFO MVP)

> Mỗi story có mã `US-…`, vai trò, giá trị, tham chiếu yêu cầu (`FR-…`, `BR-…` ở `01_PRD.md`) và tiêu chí chấp nhận theo dạng **Given / When / Then**. Mỗi AC phải kiểm thử được (unit/integration/E2E) và dùng làm tên test (`test_US_PLN_03_AC2_…`). Mọi story đều **M** (bắt buộc MVP) trừ khi ghi khác. Các endpoint nêu theo `06_API_Specification.md`.
> Quy ước: "hôm nay" trong ví dụ là 2026-11-04 (Thứ Tư) 10:05, giờ địa phương Europe/Stockholm, trùng đồng hồ demo `APP_NOW` ở `08`.
> **Phiên bản 1.2 (06/11/2026):** US-ORD-05 thành xếp lịch nhiều xe; US-APR-04 thành gợi ý lập lại tự động; bỏ mọi AC về `MANUAL_PLANNING`/`HANDLED_EXTERNALLY`; thêm AC đơn vị nhỏ nhất, hòa điểm xe nhỏ hơn, giữ chỗ chỉ chặn khi duyệt, tạm dừng chuẩn bị, giao nhiều xe; thêm US-REV-01 (doanh thu).
>
> Lịch sử **v1.1:** bỏ US-WH-03 và US-PLN-02 AC3 (thiết bị kho ngoài MVP); thêm US-APR-04 (xử lý ngoài CFO); bổ sung AC cho lập lại sau duyệt, giao lại sau thất bại, giữ chỗ đồng thời, dedupe thông báo/cảnh báo, doanh thu.

---

> **Round 3 ([DEC-R3](decisions/DEC_R3_SCOPE_CRM_20261118.md), 18–19/11/2026):** các Epic 5, 7, 8, 9, 10, 11, 13, 14 dưới đây đã được viết lại theo DEC-R3-01 → 10. Mã US/AC cũ bị bỏ được giữ dòng "Đã bỏ (R3)" để không đánh số lại.

## Epic 1 — Tích hợp và hệ thống nguồn

**US-INT-01 — Kéo đơn từ hệ thống nguồn** · Là *hệ thống*, tôi kéo đơn đã qua Sales Validation mỗi 5 phút để dispatcher có việc để lập kế hoạch. · FR-INT-02/04, BR-ORD-01
- AC1. *Given* nguồn SE có 3 đơn `SUBMITTED_FOR_PLANNING` và 2 đơn `DRAFT`, *When* job `ingest_orders` chạy, *Then* CFO tạo đúng 3 đơn `SUBMITTED`, không có đơn nào từ `DRAFT`.
- AC2. *Given* cùng 3 đơn đã được kéo, *When* job chạy lại, *Then* không tạo bản ghi trùng (theo `(market_id, external_ref)`), `rows_ok` ghi đúng, `sync_checkpoint` tiến lên.
- AC3. *Given* một đơn có `qty = -5`, *When* chạy, *Then* dòng đó vào `stg.sync_reject` mã `BAD_QTY`, các đơn còn lại vẫn nạp, `sync_run.status = partial`.
- AC4. *Given* nguồn lỗi 500, *When* chạy, *Then* `sync_run.status = failed`, `sync_checkpoint` không đổi, có alert `SYNC_FAILED` cho IT.
- AC5. *Given* đơn được cập nhật sát mốc checkpoint, *When* chạy, *Then* vẫn được kéo nhờ mốc trùng 2 phút.

**US-INT-02 — Đơn đã duyệt bị sửa/hủy ở nguồn** · Là *dispatcher*, tôi muốn được cảnh báo thay vì bị ghi đè kế hoạch. · FR-INT-05
- AC1. *Given* đơn `APPROVED` và nguồn gửi `version = 2` đổi số lượng, *When* ingestion chạy, *Then* dữ liệu đơn trong CFO không đổi, có alert `ORDER_CHANGED_AFTER_APPROVAL` cho dispatcher kèm khác biệt.
- AC2. *Given* nguồn hủy đơn đã `DISPATCHED`, *When* ingestion chạy, *Then* chỉ tạo alert, không đổi trạng thái.
- AC3. *Given* AC1, *Then* hệ thống tạo gợi ý lập lại theo bản mới của đơn (US-APR-04).

**US-INT-03 — Đồng bộ tồn kho, hàng nhập, lịch xe** · Là *hệ thống*, tôi muốn dữ liệu tồn kho là ảnh chụp mới nhất và cờ khi quá cũ. · FR-INT-06
- AC1. *Given* tồn kho SKU X ở kho Malmö đổi từ 800 → 750, *When* đồng bộ, *Then* `stock_snapshot.on_hand = 750`, `as_of` mới, giữ chỗ của CFO không bị ghi đè.
- AC2. *Given* `now − as_of > 15 phút`, *When* `stale_data_check` chạy, *Then* tạo alert `STALE_DATA` và dispatcher thấy cờ vàng trên màn lập kế hoạch.
- AC3. *Given* hàng nhập `confirmed = false`, *When* tính ATP, *Then* không được cộng vào.
- AC4. *Given* hàng nhập biến mất khỏi nguồn vì đã về, *When* đồng bộ, *Then* `received = true` và không tính hai lần.

**US-INT-04 — Thêm nước không sửa lõi** · Là *IT*, tôi muốn thêm một nước chỉ bằng cấu hình/adapter/bảng sản phẩm. · BR-GEN-02, FR-INT-01
- AC1. *Given* chạy `tools/add_market.py DK`, *When* hoàn tất, *Then* có dòng `ref.market(DK)`, bảng `ref.product_dk`, view `ref.v_product_local` có DK, không file nào trong `engine/` thay đổi.
- AC2. *Given* nước DK chưa có adapter, *When* bật job, *Then* job báo lỗi cấu hình rõ ràng, không ảnh hưởng SE.

**US-INT-05 — Tính trước ma trận lộ trình** · Là *hệ thống*, tôi muốn engine không gọi API ngoài. · FR-DEL-02
- AC1. *Given* đơn mới với toạ độ giao chưa có trong `route_matrix`, *When* chuẩn bị lập kế hoạch, *Then* `RoutingProvider` tính các cặp (kho, điểm giao), ghi `provider = ors`.
- AC2. *Given* ORS hết quota hoặc lỗi, *When* tính, *Then* dùng fallback (Haversine × 1,3, 50 km/h), ghi `provider = fallback`, phương án hiện `route_provenance = fallback`.
- AC3. *Given* engine chạy, *Then* không có lời gọi mạng nào bên trong `engine/` (kiểm bằng test import/mocking).

---

**US-INT-06 — Sales đồng bộ ngay đơn POS** · FR-INT-08
- AC1. Sales cùng cửa hàng gọi `POST /integration/orders/sync-now` với `external_ref`; CFO GET nguồn, upsert đúng 1 đơn theo version; không nhân đôi với polling.
- AC2. Sai vai trò 403, đơn ngoài cửa hàng 404, nguồn lỗi có Retry; không có duyệt thành công giả hoặc writeback POS.

## Epic 2 — Sản phẩm và ánh xạ (IT)

**US-PRD-00 — Phân luồng theo 100% SKU đã mapping** · FR-PRD-02, BR-PRD-03
- AC1. Đơn có đủ tất cả SKU mapping confirmed được phép vào CFO; chỉ một SKU `pending`/`rejected`/không tồn tại thì **toàn bộ đơn** thuộc quy trình cũ và CFO không được lập plan/hold/approve.
- AC2. Khi IT mapping SKU về sau, đơn đã đi theo quy trình cũ **không tự động** quay lại CFO; chỉ các đơn mới đủ điều kiện mới đi luồng CFO.
- AC3. Cần bảo đảm một đơn không được hai luồng cùng điều phối, kể cả polling và Sales sync-now cạnh tranh hoặc khi version nguồn thay đổi; nếu chưa đủ thông tin quyết định hệ thống điều phối, CFO phải fail closed và không xác nhận giao hàng.
- AC4. Không thay POS/WMS/ERP hay ghi ngược để phân luồng; khả năng xác minh nguồn sở hữu đơn phải được đánh giá trước khi triển khai.


**US-PRD-01 — Hàng đợi ánh xạ SKU** · Là *IT*, tôi muốn thấy SKU chưa xác nhận để mở rộng phạm vi CFO, **không giữ đơn khách chờ mapping trong CFO**. · FR-PRD-02/03
- AC1. *Given* đơn nguồn chứa SKU `SE-NEW-77` chưa được IT xác nhận, *When* đánh giá điều kiện sử dụng CFO, *Then* toàn bộ đơn **không được CFO lập plan/giữ chỗ/duyệt**; tiếp tục quy trình cũ. SKU xuất hiện trong hàng đợi IT qua đồng bộ danh mục sản phẩm, không phụ thuộc tạo đơn chặn trong CFO.
- AC2. *Given* nhiều đơn nguồn cùng có SKU chưa mapping, *Then* không tạo nhiều mapping task cho một SKU ở cùng market; không coi `blocked_order_count` là số đơn **chờ được CFO xử lý**.
- AC3. *Given* SKU có `gtin` trùng sản phẩm global G-000123, *Then* `candidates` có G-000123 với `reason = gtin`.
- AC4. *Given* tên SKU giống 0,6 theo `pg_trgm` và cùng category, *Then* xuất hiện ứng viên `name_sim` kèm điểm.

**US-PRD-02 — Xác nhận ánh xạ** · Là *IT*, tôi chọn hoặc tạo sản phẩm global để các đơn **mới** có thể được CFO xử lý khi đủ SKU. · BR-PRD-02
- AC1. *Given* tôi là `admin`, *When* `POST /mapping/tasks/{id}/confirm` với `global_product_id`, *Then* `product_se.mapping_status = confirmed`, `mapped_by` là tôi; **không** tự chuyển đơn đã chạy theo quy trình cũ sang `SUBMITTED`, không tạo planning run/hold cho các đơn đó.
- AC2. *Given* tôi là `dispatcher`, `warehouse` hoặc `sales`, *When* gọi endpoint, *Then* `403 FORBIDDEN`.
- AC3. *Given* tạo global mới, *Then* bắt buộc: nhóm xử lý, `base_unit`, cân nặng, thể tích, `base_units_per_prep_unit` (trừ nhóm đơn vị `line`), `units_to_base` > 0; thiếu → `422`.
- AC4. *Then* ghi `decision_log MAPPING_CONFIRMED` kèm trước/sau.

**US-PRD-03 — Từ chối ánh xạ** · Là *IT*, tôi từ chối với lý do. · BR-GEN-04
- AC1. *When* `reject` không có `reason_text`, *Then* `422 REASON_REQUIRED`.
- AC2. *When* reject hợp lệ, *Then* SKU giữ `rejected`, lý do được lưu cho IT; các đơn có SKU đó tiếp tục ở quy trình cũ, **không** biến thành danh sách chờ Dispatcher của CFO.

**US-PRD-04 — Quản lý nhóm xử lý và định mức** · Là *IT*, tôi chỉnh N1–N6, hệ số cờ, quy tắc gán nhóm. · FR-PRD-05
- AC1. *Given* sửa `labour_hours_per_unit` của N3 từ 0,15 → 0,18, *When* lập kế hoạch đơn mới, *Then* khối lượng việc dùng 0,18; kế hoạch đang giữ chỗ không đổi.
- AC2. *Given* `handling_group_rule` `category_like='Cement%'` → N3, *When* tạo global trong category 'Cement 25kg', *Then* nhóm được gợi ý N3 (IT vẫn có thể đổi).
- AC3. *Then* định mức là **một bộ chung** cho mọi kho; không có endpoint sửa định mức theo kho.
- AC4. *When* tạo hoặc sửa sản phẩm global nhóm N6 có cờ `FRAGILE`, *Then* `422 VALIDATION_ERROR`.

**US-PRD-05 — Danh mục sản phẩm cục bộ và global** · Là *IT*, tôi tra cứu và lọc. · 
- AC1. *When* `GET /products/local?market=SE&mapping_status=pending`, *Then* trả đúng các SKU chưa ánh xạ có phân trang.

---

## Epic 3 — Đơn hàng

**US-ORD-01 — Sales nhập đơn ở POS giả lập** · Là *sales*, tôi nhập đơn, kiểm tra và nộp cho CFO. · FR-ORD-01, BR-ORD-02/03
- AC1. *Given* form POS, *When* chọn dạng ngày `exact` 2026-11-18, *Then* `date_from = date_to`; `range` yêu cầu `date_from < date_to`; `latest` chỉ có `date_to`.
- AC2. *Given* khung giờ từ–đến, *Then* `window_start < window_end`; để trống nếu khách không yêu cầu.
- AC3. *When* `validate` thiếu địa chỉ/toạ độ hoặc không có dòng hàng, *Then* trả lỗi, không cho `submit`.
- AC4. *When* `submit` sau `validate` thành công, *Then* đơn `SUBMITTED_FOR_PLANNING` và được CFO kéo qua sync-now của Sales hoặc polling định kỳ.
- AC5. *Then* địa chỉ chọn từ danh sách seed có toạ độ (không geocoding thật).

**US-ORD-02 — Danh sách đơn theo phạm vi** · Là *dispatcher/kho/cửa hàng/CS*, tôi thấy đúng các đơn mình được xem. · FR-ORD-03
- AC1. *Given* quản lý kho Malmö, *Then* chỉ thấy đơn có kế hoạch/giao từ kho Malmö; *Given* store manager Göteborg Väst, chỉ thấy đơn `origin_store_id` của mình (chỉ xem).
- AC2. *Given* ID đơn ngoài phạm vi, *Then* `404`.
- AC3. *When* lọc `risk_color=orange&status=PREPARING`, *Then* kết quả đúng và mặc định sắp xếp theo `submitted_at ASC, id ASC`, có thể chủ động chọn sort `promise_end`.

**US-ORD-03 — Chi tiết đơn và dòng thời gian** · Là *dispatcher*, tôi xem toàn bộ lịch sử một đơn. · FR-ORD-04
- AC1. *Then* timeline gộp: đơn nộp, các run lập kế hoạch, quyết định, sự kiện kho/tài xế, thông báo, phiên bản ETA, theo thứ tự thời gian.
- AC2. *Given* vai trò `customer_service`, *Then* thấy trạng thái, ETA, thông báo; **không** thấy GPS, điểm số, quyết định nội bộ.

**US-ORD-04 — Hủy và lập lại đơn** · Là *dispatcher*, tôi hủy hoặc lập lại có lý do. · BR-GEN-04
- AC1. *When* `cancel` không `reason_text`, *Then* `422 REASON_REQUIRED`.
- AC2. *Given* đơn `DISPATCHED`, *When* cancel, *Then* `409 ILLEGAL_TRANSITION`.
- AC3. *Given* đơn `APPROVED`, *When* `replan` có lý do, *Then* giữ chỗ `committed` → `released`, đơn `SUBMITTED`, ghi `ORDER_REPLAN`.

**US-ORD-05 — Đơn lớn hơn một xe** · Là *dispatcher*, tôi muốn hệ thống tự gợi ý số xe, loại xe và xếp lịch nhiều xe. · FR-ORD-05, BR-DEL-05
- AC1. *Given* đơn 20.000 kg, kho có xe 18 t (18.000 kg), 12 t (6.000 kg), 26 t (26.000 kg) đều rảnh, *Then* phương án đầu dùng **1 xe 26 t** (ít xe nhất); *Given* xe 26 t bận, *Then* dùng **2 xe** (18 t + 6 t) thay vì 3 xe 12 t.
- AC2. *Then* mỗi phương án có `vehicle_count`, danh sách `vehicles` (xe, loại, tài xế, `load_kg`, `load_m3`, phần hàng) và tổng phần hàng bằng đúng đơn; một dòng được tách qua nhiều xe khi cần.
- AC3. *Then* mọi xe cùng một kho, cùng ngày, ETA trong cửa sổ và chênh nhau ≤ `multi_vehicle.max_arrival_spread_min` (30'); ETA của phương án = xe tới cuối.
- AC4. *Then* không giới hạn số xe; *Given* kho không đủ xe/tài xế rảnh cho cả đơn, *Then* kho đó bị loại `NO_TRUCK_FIT` (`detail.reason = combined_capacity`) hoặc `TRUCK_BUSY`/`NO_DRIVER`.
- AC5. *Given* đơn cần năng lực `crane` mà không xe nào có, *Then* mọi kho bị loại ở check `truck`, đơn `NO_FEASIBLE_DATE` (không có trạng thái `MANUAL_PLANNING`).
- AC6. *Then* không xe nào chở hai đơn trong cùng chuyến (không ghép đơn).

---

**US-ORD-06 — Thứ tự đặt và lịch giao** · BR-ORD-05
- AC1. Danh sách theo `submitted_at ASC, id ASC`, nhưng có thể lập lịch đơn đặt sau giao sớm trước đơn cũ.
- AC2. Không lấn nguồn lực đã `committed` của đơn cũ; nếu có đơn cũ chưa duyệt tranh công suất mà chưa chứng minh đủ năng lực, Sales không được tự duyệt đơn sau.

## Epic 4 — Tồn kho, ATP, chuyển kho

**US-ATP-01 — Time-phased ATP** · Là *hệ thống*, tôi kiểm tra đủ hàng theo ngày. · BR-ATP-01..04
- AC1. *Given* kho A: on_hand 100, wms_reserved 20, giữ chỗ đơn khác 30, cần 60, *Then* usable 50 → không đủ.
- AC2. *Given* hàng nhập confirmed 40 về trước ngày cần (đã cộng 1 ngày làm việc nhận kho), *Then* usable 90 ≥ 60 → đủ, phân loại *đủ sau hàng nhập*, `complexity_points += 1`.
- AC3. *Given* hàng nhập chưa xác nhận, *Then* không tính.
- AC4. *Given* không kho nào đủ trong 14 ngày, *Then* mọi kho `STOCK_SHORT`.
- AC5. *Given* hai phương án cùng đơn cùng kho, *Then* hàng chỉ bị giữ một lần.

**US-ATP-02 — Gợi ý chuyển kho** · **Hoãn (DEC-R3-15)**: không có trong pilot; các AC dưới đây là lịch sử. · BR-ATP-05
- AC1. *Given* kho đích thiếu 40 bao, kho nguồn B còn 100 sẵn có, A còn 20, *Then* chỉ B được gợi ý, kèm `lead_days` và khoảng cách.
- AC2. *Given* hai kho nguồn đủ, *Then* xếp theo `lead_days` tăng, rồi khoảng cách tăng; tối đa 3 gợi ý.
- AC3. *When* dispatcher duyệt gợi ý, *Then* `stock_transfer(approved)`, ghi `TRANSFER_APPROVED`.

**LATEST OWNER OVERRIDE — DEC-INT-TRANSFER-BOUNDARY/Q3 (2026-11-09)** [decision](decisions/DEC_INTEGRATION_UNBLOCK_Q2_Q10_20261109.md): CFO **gợi ý/yêu cầu/hủy** chuyển kho, WMS **duy nhất** thực hiện và ghi nhận xuất/nhập vật lý. `confirm-source` và `receive` trên CFO là route legacy trả `409 ILLEGAL_TRANSITION` sau RBAC, không tạo inbound; #127 đã merge với guard này. AC-WMS-02/03 bên dưới là **lịch sử đề xuất bị thay thế** nếu đòi CFO reviewer nhận/chấp thuận chứng cứ vật lý. CFO chỉ đọc tồn WMS mới/đầy đủ và không tính trùng physical inbound hoặc reservation.

**Stock Admin bootstrap & WMS transfer reconciliation — acceptance supplement (09/11/2026):**
- AC-BOOT-01 (đã mở rộng bởi DEC-STOCK-GRANT-CONTROL-20261109). **Chỉ System Admin có ủy quyền tường minh từ Owner** được cấp **và thu hồi** mọi Stock Admin grant theo market, ban đầu và tiếp theo; không self-grant/seed implicit grant, audit scope, actor, grantor/grantee, reason, hiệu lực và before/after. Stock Admin có grant nhưng không có ủy quyền Owner **không** được cấp quyền tiếp.
- AC-WMS-01. Giả định WMS cũ ghi nhận **xuất và nhập chuyển kho**; adapter phải chứng minh dữ liệu đó thật sự đọc được, không tự giả mã giao dịch/ACK. CFO không ghi ngược WMS.
- AC-WMS-02 (**superseded as CFO workflow; historical only**). WMS chịu trách nhiệm đối soát transfer/physical stock trong chính WMS. CFO không được yêu cầu Warehouse Manager nộp evidence chuyển kho để CFO reviewer xác nhận nhập/xuất; không tạo queue phê duyệt chứng từ vật lý. Chỉ dựa vào snapshot WMS có provenance và coverage được xác minh; thiếu bằng chứng → không hứa tồn.
- AC-WMS-03 (current safety invariant). Không tự cộng inbound chuyển kho hoặc trừ lại hàng vật lý WMS đã phản ánh; thiếu batch/SKU/WMS provenance ⇒ `unknown`, không tính stock available nhờ CFO request; không tạo giả WMS `ACK`, replay/idempotency và 503 phải fail-closed.

**US-ATP-03 — Legacy acceptance superseded by Q3 (WMS physical transfer authority)** · CFO kho chỉ xem request, **không xác nhận xuất/nhập vật lý**. WMS là source-of-truth; hành động CFO cũ giữ endpoint fail-closed có kiểm scope.
- AC1. *Given* quản lý kho nguồn có quyền, *When* gọi CFO `confirm-source`, *Then* nhận `409 ILLEGAL_TRANSITION`, **không** sinh `inbound_shipment`, không thay đổi tồn WMS, không chuyển trạng thái request.
- AC2. *Given* người quản lý khác không có scope, *When* gọi route legacy `confirm-source/receive`, *Then* từ chối theo RBAC (không lộ transfer ngoài phạm vi), không tạo thay đổi trạng thái hoặc tồn.
- AC3. *When* kho đích gọi CFO `receive`, *Then* trả `409 ILLEGAL_TRANSITION` sau kiểm quyền; **chỉ WMS** ghi nhận receipt/physical inbound, CFO chỉ đọc snapshot sau đó.

---

## Epic 5 — Kho: công suất theo ngày/ca (R3)

**US-WH-01 — Xác nhận công suất ngày/ca** · Là *Warehouse Manager*, tôi nhập số người và số giờ làm của từng ca để engine tính công suất đúng. · FR-PRP-05, BR-PRP-06, DEC-R3-06
- AC1. *When* tôi `PUT /warehouses/{id}/day-capacity` cho ngày 2026-11-12 với ca AM 8 người × 7 giờ và ca PM 5 người × 7 giờ, *Then* lưu hai dòng `warehouse_day_capacity` kèm `confirmed_by`, `confirmed_at`, audit `CAPACITY_CONFIRMED`.
- AC2. *When* tôi sửa ngày đã có dữ liệu hoặc ngày đã qua mà không có `change_reason`, *Then* `422 REASON_REQUIRED`; có lý do → dòng cũ `superseded`, dòng mới hiệu lực, audit `CAPACITY_CHANGED` có before/after.
- AC3. *Given* tôi là quản lý kho A, *When* gọi cho kho B, *Then* `404`; thiếu `can_approve` → `403`.
- AC4. *Then* không có lịch ca từng nhân viên, không có điểm danh; `attendance_gen` không chạy.

**US-WH-02 — Công suất ngày** · Là *dispatcher/kho*, tôi xem công suất. · BR-PRP-02
- AC1. *Given* ca AM 8 người × 7 giờ đã xác nhận, `delivery_share = 0,9`, *Then* `labour_cap = 8 × 7 × 0,9 = 50,4` giờ.
- AC2. *Given* đã đặt 30 giờ (committed + held đơn khác), *Then* `free = 20,4`.
- AC3. *Given* ngày lễ, *Then* công suất 0 và không xếp việc vào ngày đó.
- AC4. *Given* ngày chưa có dòng công suất đã xác nhận, *Then* công suất 0, `schedule_verified = false`, gate công suất fail (không dựng số người giả định).

**US-WH-03 — Thiết bị** · **Đã bỏ ở v1.1** (thiết bị kho ngoài MVP theo slide). Giữ mã để không đánh số lại.
- AC1. *Then* không có endpoint, bảng hay check nào về thiết bị kho; engine không trả `PREP_NO_EQUIPMENT`.

**US-WH-04 — Ghi mốc chuẩn bị** · Là *quản lý/trưởng ca*, tôi ghi `START_PREP`, `GOODS_READY`, `LOADED` thay cho công nhân. · FR-EXE-01
- AC1. *Given* đơn `APPROVED`, *When* tôi ghi `START_PREP`, *Then* đơn `PREPARING`, `occurred_at` lưu giờ tôi nhập.
- AC5. *When* `START_PREP` thiếu `crew_size`, *Then* `422`.
- AC6. *(R3)* *Given* START_PREP 07:00, GOODS_READY 09:30, *Then* `prep_actual_min = 150` (= GOODS_READY − START_PREP); không có tạm dừng/tiếp tục.
- AC7. *(R3)* *When* gửi `PREP_PAUSED` hoặc `PREP_RESUMED`, *Then* `422 VALIDATION_ERROR`.
- AC8. Đã bỏ (R3).
- AC2. *When* ghi `LOADED` trước `GOODS_READY`, *Then* `409 ILLEGAL_TRANSITION`.
- AC3. *When* gửi lại cùng `Idempotency-Key`, *Then* không tạo sự kiện thứ hai.
- AC4. *Then* sau mỗi mốc, ETA được tính lại (một dòng `eta_forecast` mới).

**US-WH-05 — Báo ngoại lệ kho** · Là *quản lý kho*, tôi báo thiếu hàng, hỏng, sự cố xe, đổi ca. · FR-EXE-01
- AC1. *When* ghi `SHORTAGE {sku, qty_missing}`, *Then* alert `EXCEPTION` cho dispatcher, ETA tính lại; hệ thống **không** tự sửa tồn kho.
- AC2. *(R3)* *When* ghi `VEHICLE_ISSUE {vehicle_id}`, *Then* chỉ tạo alert `EXCEPTION` kèm danh sách đơn đã duyệt dùng xe đó; **không** tự chạy planner hay tạo gợi ý lập lại (DEC-R3-09).
- AC3. *(R3)* Đổi số người/giờ của ca dùng US-WH-01 (sửa công suất ngày có lý do); sự kiện `SHIFT_CHANGE` không còn dùng để tính công suất.

---

**US-WH-06 — Lịch làm chính thức từng người** · Đã bỏ (R3, DEC-R3-06): thay bằng US-WH-01.

**US-EMP-05 — Ghi lịch sử thay đổi nhân sự (ASM-006)**
- AC1. Khi quản lý kho/cửa hàng chuyển công tác hoặc nghỉ, hệ thống kiểm có quản lý thay thế trước khi cho thay đổi.
- AC2. Người nghỉ việc bị khóa account, không xóa lịch sử; owner do admin gán riêng không tự đổi theo quản lý.
- AC3. Thay đổi phân công, quản lý, owner, nghỉ việc ghi decision_log với actor và before/after trong transaction; chỉnh hồi tố cần lý do, và không tạo hai phân công chồng ngày.


## Epic 6 — Lập kế hoạch và quyết định của dispatcher

**US-PLN-01 — Tính khối lượng việc** · Là *hệ thống*, tôi tính giờ công chuẩn. · BR-PRP-01
- AC1. *Given* 20 pallet xi măng (N3: 0,25 + 20×0,15), 15 pallet gạch (N2: 0,25 + 15×0,40), 3 dòng keo N1 (0,05 mỗi dòng), *Then* `labour_hours = 3,25 + 6,25 + 0,15 + 0,5 = 10,15`; không có giờ thiết bị trong kết quả.
- AC2. *Given* một dòng có cờ FRAGILE (×1,25) và HAZARDOUS (×1,30), *Then* hệ số = 1,625 (tối đa theo `flag_multiplier_cap = 2,0`).
- AC3. *Then* kết quả giống nhau với mọi kho (hệ số hiệu suất mặc định 1,0).
- AC4. *Given* 20 bao xi măng (N3, pallet 40 bao), *Then* `prep_qty = 0,5` và giờ dòng = 0,25 + 0,5×0,15 = 0,325 (tính theo đơn vị cơ sở, không làm tròn lên pallet).
- AC5. *Given* hàng không chia nhỏ được (không có `base_units_per_prep_unit`) với số lượng 2,4, *Then* `prep_qty = 3` (làm tròn lên).

**US-PLN-02 — Lịch chuẩn bị và giờ cắt** · Là *hệ thống*, tôi xếp việc theo công suất và giờ cắt. · BR-PRP-04
- AC1. *Given* công suất ngày D còn 4 giờ, việc 10,15 giờ, *Then* xếp 4 giờ ngày D, phần còn lại sang ngày làm việc kế, `goods_ready_at` ở ngày cuối.
- AC2. *Given* `goods_ready_at` 14:20 và cutoff 14:00, *Then* `loading_start_at` ca đầu ngày làm việc kế, `PREP_AFTER_CUTOFF`, `complexity_points += 1`.
- AC3. **Đã bỏ ở v1.1** (không còn ràng buộc thiết bị).

**US-PLN-03 — Kiểm tra xe và tài xế** · Là *hệ thống*, tôi chỉ chọn xe và tài xế hợp lệ. · BR-DEL-01/02
- AC1. *Given* đơn 4.200 kg, 14 m³, xe 12t (6.000 kg, 40 m³) và xe 3,5t (1.200 kg), *Then* chỉ xe 12t là ứng viên.
- AC2. *Given* xe `allowed_group_ids` không chứa N4, *Then* không là ứng viên cho đơn có N4.
- AC3. *Given* tài xế bằng `C` nhưng xe yêu cầu `CE`, *Then* không đủ điều kiện; bằng hết hạn trước ngày chuyến → `LICENCE_EXPIRED`.
- AC4. *Given* tài xế đã có 6 giờ chuyến ngày D và chuyến này 4 giờ, *Then* vượt 9 giờ → `DRIVER_HOURS_EXCEEDED`.
- AC5. *Given* xe/tài xế đã được giữ cho **đơn khác** trong khoảng thời gian trùng, *Then* `TRUCK_BUSY`/`NO_DRIVER`.

**US-PLN-04 — Giao đúng cửa sổ nhận hàng và dạng ngày** · Là *hệ thống*, tôi tôn trọng khách. · BR-ORD-02/03, BR-DEL-03
- AC1. *Given* `exact` 2026-11-13 cửa sổ 07:00–09:00, hàng có thể tới sớm nhất 2026-11-12, *Then* kế hoạch giao ngày 13 (không sớm hơn), ETA ≥ 07:00.
- AC2. *Given* `latest` 2026-11-18, *Then* ngày giao là ngày làm việc khả thi sớm nhất ≤ 18.
- AC3. *Given* `range` 13–15 và khả thi sớm nhất là 12, *Then* ngày giao 13.
- AC4. *Given* ETA tính được 16:40 và cửa sổ đóng 16:00, *Then* chuyển sang ngày làm việc kế tiếp thuộc tập ngày cho phép, nếu không còn ngày nào → `DATE_AFTER_DEADLINE`.
- AC5. *Given* chỉ có ngày, không có khung giờ, *Then* dùng `default_receiving_hours`.

**US-PLN-05 — Dự trữ và phân loại** · Là *dispatcher*, tôi thấy độ an toàn của lịch. · BR-DEL-04
- AC1. *Given* hạn cuối 18/11 16:00, ETA khả thi sớm nhất 12/11 08:00, *Then* `planning_reserve ≈ 6 ngày 8 giờ`, `reserve_class = safe`.
- AC2. *Given* ETA khả thi sớm nhất 17/11 10:00, *Then* ≈ 1 ngày 6 giờ, `tight`, UI cảnh báo vàng và dispatcher phải xác nhận khi duyệt.
- AC3. *Given* ETA khả thi sớm nhất sau hạn, *Then* `infeasible`.
- AC4. *Then* không cộng buffer vào thời gian chuyến, nên không có phương án giao được mà bị loại vì buffer.

**US-PLN-06 — Xếp hạng và đề xuất 3 phương án** · Là *dispatcher*, tôi nhận phương án tốt nhất + 2 thay thế. · BR-RNK-01..03
- AC1. *Given* ba ứng viên (km 10/40/12; mức đầy 85%/40%/60%), *Then* score 0,50/0,50/0,26 → rank 1 là phương án thứ ba (Malmö).
- AC2. *Given* chênh km chỉ 1 km (nhỏ hơn 2 km), *Then* `n_km` đều 0 (vùng bỏ qua).
- AC3. *Given* chỉ một ứng viên, *Then* score 0 và vẫn trả 1 phương án.
- AC4. *Given* hòa điểm, *Then* ưu tiên `planning_reserve` lớn hơn, rồi `complexity_points` thấp hơn, ETA sớm hơn, **tổng tải xe nhỏ hơn** (xe nhỏ hơn mà vẫn đủ chứa), rồi mã xe nhỏ hơn.
- AC7. *Given* phương án 1 xe và phương án 2 xe, *Then* phương án 1 xe xếp trước bất kể điểm.
- AC5. *Then* mỗi phương án có `checks` 5 mục, `reason_codes`, `explanation` sinh từ mẫu câu; không phương án nào quá 2 cái cùng một kho; phương án hạng 1 có mã `LOWEST_SCORE_OF_3` (không có mã/chữ "cheapest"/"cost").
- AC6. *Then* giờ công đơn không được dùng làm tiêu chí so sánh giữa các kho.

**US-PLN-07 — Không có phương án khả thi** · Là *dispatcher*, tôi biết vì sao và ngày nào khả thi. · BR-RNK-04/05
- AC1. *Given* mọi kho thiếu hàng, *Then* `failed_check = stock`, đơn `NO_FEASIBLE_DATE`, `earliest_feasible_date` (tối đa 14 ngày tới) và gợi ý chuyển kho.
- AC2. *Given* ngày yêu cầu tự đổi mà khách chưa đồng ý, *Then* hệ thống **không** đổi `date_to`.
- AC3. *When* Dispatcher ghi `date_negotiation(agreed)`, *Then* lưu contact record/`DATE_NEGOTIATION_RECORDED` nhưng **chưa** đổi ngày hoặc version của đơn và không tự replan. Chỉ hành động **Apply agreed date** riêng của Dispatcher sau kiểm agreement/version/audit mới yêu cầu cập nhật ngày và chạy planning lại (Q4); không tự approve.
- AC4. *When* ghi `unreachable`, *Then* `remind_at = now + 24 giờ` và xuất hiện nhắc.
- AC5. *When* ghi `declined`, *Then* dispatcher có thể hủy với lý do.

**US-PLN-08 — Đổi tiêu chí và chạy lại** · Là *dispatcher*, tôi loại kho/xe hoặc đổi trọng số. · FR-APR-01
- AC1. *When* chạy lại với `exclude_warehouse_ids=[3]`, *Then* không phương án nào dùng kho 3.
- AC2. *When* đặt `w_km=0,8, w_fill=0,2`, *Then* điểm tính lại theo trọng số mới.
- AC3. *When* chạy lại không có `reason_text`, *Then* `422 REASON_REQUIRED`.
- AC4. *Then* giữ chỗ của run cũ → `released`, run mới `run_no + 1`, ghi `CRITERIA_CHANGED_RERUN` kèm snapshot.

---

## Epic 7 — Giữ chỗ và duyệt

**US-RES-01 — Giữ chỗ cả 3 phương án** · Là *hệ thống*, tôi khóa tạm tài nguyên. · BR-RES-01..03
- AC1. *When* engine trả 3 phương án, *Then* tạo `planning_run.hold_expires_at = now + 15'`; `stock_reservation` và `prep_reservation` một lần cho mỗi (đơn, kho); `vehicle_reservation` cho từng xe của từng phương án.
- AC2. *Given* hai phương án cùng đơn dùng cùng xe, *Then* ghi được (cùng `order_id`); *Given* đơn khác cố giữ cùng xe trùng giờ, *Then* ràng buộc EXCLUDE từ chối.
- AC3. *When* gia hạn 2 lần thành công, *Then* lần thứ ba `409 HOLD_EXTENSION_LIMIT`.
- AC4. *When* quá `hold_expires_at`, *Then* job `hold_expiry` chuyển `held → expired`, plan `proposed → expired`.
- AC5. *Then* tồn kho khả dụng của đơn khác trừ cả `held` còn hạn lẫn `committed`.
- AC6. *Given* kho A còn 100 bao SKU X khả dụng, đơn 1 cần 80 và đơn 2 cần 70, *When* hai dispatcher **lập kế hoạch** đồng thời, *Then* cả hai đều được giữ chỗ `held` tại A (cho phép vượt); *When* hai dispatcher **duyệt** đồng thời, *Then* tổng `committed` của X tại A không vượt 100, đúng một đơn thành công, đơn kia nhận `409 RESOURCE_CONFLICT`.
- AC7. *Given* kho A ngày D còn 6 giờ công trống, hai đơn mỗi đơn cần 5 giờ trong ngày D, *When* duyệt đồng thời, *Then* tổng giờ `committed` ngày D không vượt công suất; đúng một đơn thành công.

**US-APR-01 — Duyệt kế hoạch** · Là *dispatcher* (hoặc *Sales* cho đơn cửa hàng mình, US-APR-05), tôi duyệt để thành cam kết. · BR-APR-01, FR-APR-03
- AC1. *When* `POST /plans/{id}/approve` hợp lệ, *Then* plan `approved`, giữ chỗ → `committed`, phương án khác `superseded`/`released`, tạo `delivery_trip` + `trip_stop`, mọi chuyến của đơn gán cùng một Dispatcher theo luân phiên (DEC-R3-01), đơn `APPROVED`, đặt `committed_date`, `promise_start/end`, tạo thông báo `CONFIRMED`, ghi `PLAN_APPROVED`.
- AC2. *Given* hold đã hết hạn nhưng tài nguyên còn trống, *Then* duyệt vẫn thành công nhờ kiểm tra lại.
- AC3. *Given* trong lúc đó đơn khác đã chiếm xe, *Then* `409 RESOURCE_CONFLICT` (kèm `details.conflict`) và không có thay đổi nào được ghi (rollback).
- AC4. *Given* hai dispatcher duyệt đồng thời hai đơn tranh một xe, *Then* đúng một thành công.
- AC5. *Given* gửi lại cùng `Idempotency-Key`, *Then* trả kết quả cũ, không duyệt hai lần.
- AC6. *Given* duyệt phương án rank > 1 mà không có `reason_code`, *Then* `422 REASON_REQUIRED`; ghi `ALT_SELECTED`.
- AC7. *(R3)* *Given* `reserve_class = tight` và phương án qua đủ 5 gate, *Then* Dispatcher hoặc Sales duyệt bình thường; không có tick xác nhận lịch sát.
- AC8. *Given* ngày cam kết khác ngày khách đã đồng ý, *Then* cần `date_negotiation_id` (`agreed`), thiếu → `409 DATE_AGREEMENT_REQUIRED`.

**US-APR-02 — Kế hoạch tay** · Là *dispatcher*, tôi tự lập khi hệ thống không phù hợp. · BR-APR-02
- AC1. *Given* thiếu `manual_reason_code`, *Then* `422`.
- AC4. *Given* đơn `PLANNED` hoặc `NO_FEASIBLE_DATE`, *When* kế hoạch tay với 2 xe chia đủ hàng, *Then* hợp lệ; tổng phần hàng các xe khác đơn → `422`.
- AC2. *Given* tôi chọn xe thiếu tải, *Then* engine kiểm gate và từ chối `422 NO_TRUCK_FIT`.
- AC3. *When* hợp lệ, *Then* plan `manual` được duyệt, lưu snapshot gồm phương án hệ thống đã đề xuất, tính vào `manual_plan_count`.

**US-APR-03 — Lập lại sau duyệt** · Là *dispatcher*, tôi lập lại khi có thay đổi lớn. 
- AC1. *When* `replan` có lý do, *Then* các giữ chỗ `committed` → `released`, trip → `cancelled`, đơn `SUBMITTED`, chạy lại engine.
- AC2. *Then* kế hoạch cũ `approved`/`manual` → `superseded`, `trip_stop` `pending` → `cancelled`, `approved_plan_id`/`committed_date`/`promise_*` = `NULL`, `decision_log ORDER_REPLAN` có `before` chứa ngày cam kết cũ; tất cả trong **một transaction**.
- AC3. *When* dispatcher duyệt kế hoạch mới, *Then* không bị chỉ mục `ux_one_approved_plan` chặn, và một thông báo `CONFIRMED` **mới** được tạo (dedupe theo `plan_id`) với ngày mới.
- AC4. *Given* đơn `APPROVED`, *When* `cancel` có lý do, *Then* kế hoạch, giữ chỗ, chuyến được đóng như AC2 và đơn `CANCELLED`.

**US-APR-04 — Gợi ý lập lại tự động** · Là *dispatcher*, tôi muốn hệ thống tự đưa phương án mới khi **nguồn sửa đơn** đã duyệt. · FR-APR-05, BR-APR-04
- AC1. *(R3)* *Given* đơn `APPROVED` và một trong hai tín hiệu (nguồn sửa đơn sau duyệt, `PLAN_INVALIDATED`), *Then* có `planning_run(kind='replan_suggestion')` và alert `REPLAN_SUGGESTED` kèm `run_id`; đơn giữ nguyên trạng thái. `VEHICLE_ISSUE` và giao `FAILED` **không** tạo gợi ý (DEC-R3-09).
- AC2. *Given* kho A còn 0 bao trống nhưng đơn này đang giữ `committed` 80 bao tại A, *When* tạo gợi ý, *Then* engine coi 80 bao đó là khả dụng cho chính đơn này; tương tự cho giờ công, xe, tài xế.
- AC3. *Then* lần chạy gợi ý **không** tạo dòng giữ chỗ nào.
- AC4. *When* dispatcher duyệt phương án gợi ý, *Then* trong một transaction: kế hoạch cũ `superseded`, giữ chỗ cũ `released`, chuyến cũ `cancelled`, kế hoạch mới `approved`, giữ chỗ mới `committed`, đơn `APPROVED`, thông báo `CONFIRMED` mới; tài nguyên đã bị chiếm → `409 RESOURCE_CONFLICT`, không thay đổi gì.
- AC5. *When* dispatcher chọn giữ kế hoạch cũ mà không có lý do, *Then* `422 REASON_REQUIRED`; có lý do → alert đóng, ghi `REPLAN_KEPT`.
- AC6. *Then* không có job hay đường code nào tự duyệt phương án gợi ý.
- AC7. *Given* đơn đã `DISPATCHED`, *Then* chỉ tạo alert, không tạo gợi ý.

---

**US-APR-05 — Sales duyệt trong phạm vi đơn cửa hàng mình (R3)** · FR-APR-06, BR-GEN-03, DEC-R3-10
- AC1. *Given* Sales thuộc cửa hàng nguồn, đơn `PLANNED`, hold còn hạn, dữ liệu mới, phương án qua đủ 5 gate, *When* Sales duyệt rank 1, 2 hoặc 3 (kho bất kỳ), *Then* cùng ApprovalService kiểm lại, khóa và commit → `APPROVED`, audit `actor_role = sales`, gửi `CONFIRMED`. Phương án nhiều xe được phép.
- AC2. *When* Sales duyệt rank 2 hoặc 3 không có `reason_code`, *Then* `422 REASON_REQUIRED`.
- AC3. *Given* phương án `reserve_class = tight` qua đủ 5 gate, *Then* duyệt bình thường; không có tick xác nhận lịch sát (mọi vai trò).
- AC4. *When* Sales chạy lại planner với tiêu chí khác hoặc ghi thỏa thuận ngày với khách cho đơn cửa hàng mình (trước duyệt), *Then* được phép, có audit.
- AC5. *When* Sales gọi kế hoạch tay, override, `replan` sau thực thi, `cancel` sau duyệt, gửi/bỏ `DELAY`, *Then* `403`; đơn cửa hàng khác → `404`.
- AC6. *Given* đơn đặt trước chưa duyệt đang tranh nguồn lực mà chưa chứng minh đủ cho cả hai, *Then* `409 PLAN_NOT_APPROVABLE`, chuyển Dispatcher.
- AC7. Hai Sales (hoặc Sales và Dispatcher) tranh xe/SKU/giờ công: đúng một thành công, bên kia `409 RESOURCE_CONFLICT`; không thông báo khách trước commit.
- AC8. *Then* Dispatcher thấy mọi đơn do Sales duyệt và can thiệp được.

## Epic 8 — Thực thi và tài xế

**US-EXE-01 — Tài xế xem chuyến** · Là *tài xế*, tôi xem chuyến hôm nay trên điện thoại. · 
- AC1. *Then* `GET /driver/trips` chỉ trả chuyến của tôi, gồm xe, điểm dừng, địa chỉ, người liên hệ, yêu cầu đặc biệt, cửa sổ nhận hàng.
- AC2. *Then* không có giá đơn hay thông tin điểm số.

**US-EXE-02 — Xuất phát, giao, thất bại** · Là *tài xế*, tôi ghi sự kiện. · BR-EXE-01/02
- AC1. *Given* đơn `LOADED`, *When* tôi ghi `DISPATCHED`, *Then* chuyến `on_road`, đơn `DISPATCHED`, thông báo `DISPATCHED` được tạo.
- AC5. *Given* đơn 2 xe, *When* xe 1 `DISPATCHED`, *Then* đơn `DISPATCHED` và một thông báo `DISPATCHED`; xe 2 `DISPATCHED` không tạo thông báo thứ hai.
- AC6. *Given* đơn 2 xe, *When* xe 1 `DELIVERED`, *Then* đơn vẫn `DISPATCHED`; *When* xe 2 `DELIVERED`, *Then* đơn `DELIVERED`, hai POD, một thông báo `DELIVERED`.
- AC7. *(R3)* *Given* đơn 2 xe, xe 1 `DELIVERED`, xe 2 `FAILED`, *Then* đơn chuyển `FAILED` chỉ khi cả hai chuyến kết thúc; alert `DELIVERY_FAILED` cho Dispatcher kèm kết quả từng chuyến; **không** có gợi ý lập lại tự động.
- AC2. *When* `DELIVERED {recipient_name, position}`, *Then* đơn `DELIVERED`, `proof_of_delivery` (kèm `site_distance_m`), `delivered_at`, thông báo `DELIVERED`, trip `completed`.
- AC8. *(R3)* *When* `DELIVERED` hoặc `FAILED` thiếu `position`, *Then* `422 VALIDATION_ERROR` (`position_required`); không có đường xác nhận khi không có vị trí.
- AC3. *When* `FAILED` thiếu `failure_reason`, *Then* `422`; hợp lệ → POD `failed` cho chuyến; khi mọi chuyến kết thúc → đơn `FAILED`, thông báo `FAILED` cho khách, alert `DELIVERY_FAILED`.
- AC4. *Given* tài xế khác cố ghi cho chuyến này, *Then* `403`.

**US-EXE-03 — Gửi lại khi lỗi mạng (R3)** · FR-EXE-02, DEC-R3-01
- AC1. *Then* trang tài xế chạy online; không có hàng đợi IndexedDB.
- AC2. *Given* gửi sự kiện lỗi mạng, *When* tài xế bấm "Thử lại", *Then* dùng lại đúng `Idempotency-Key` cũ; server không tạo sự kiện thứ hai.

**US-EXE-04 — Dispatcher xử lý giao thất bại (R3)** · BR-EXE-02, DEC-R3-09
- AC1. *Given* đơn `FAILED`, *When* Dispatcher `replan` `scope=full` có lý do, *Then* đơn `SUBMITTED` và chạy lại.
- AC2. *Given* đơn `FAILED` có ít nhất một chuyến `delivered`, *When* `replan` `scope=remaining`, *Then* `planning_run(kind='remaining_replan')` chỉ chứa số lượng chưa giao theo dòng; POD đã giao giữ nguyên.
- AC3. *Given* khách vắng, *When* Dispatcher ghi thỏa thuận ngày rồi Apply, *Then* lập kế hoạch mới cho ngày đã thỏa thuận; hoặc `cancel` có lý do.
- AC4. *Given* đơn FAILED lần 1 rồi giao thành công lần 2, *Then* có hai bản ghi `proof_of_delivery`, POD lần 1 không bị ghi đè, đơn `DELIVERED`; kế hoạch lần 1 `superseded`.
- AC5. *Then* đơn FAILED không nằm trong mẫu số `on_time_rate`.
- AC6. *When* Sales gọi `replan`/`cancel` cho đơn đã thực thi, *Then* `403`.

**US-EXE-05 — Tài xế báo sự cố (R3)** · DEC-R3-01
- AC1. *When* tài xế gửi `DRIVER_INCIDENT {reason}` với `reason ∈ {vehicle_breakdown, traffic_or_accident, site_inaccessible, other}`, *Then* alert `DRIVER_INCIDENT` cho Dispatcher (`critical` nếu hỏng xe); `other` thiếu `note` → `422`.
- AC2. *Given* sự cố kèm vị trí, *Then* ETA tính lại từ vị trí; *Given* `vehicle_breakdown`, *Then* không có ETA mới, alert ghi "ETA không xác định".
- AC3. *Then* không tự chạy planner hay tạo gợi ý lập lại.

---

## Epic 9 — Vị trí tài xế (R3, DEC-R3-01)

**US-GPS-01 — Tài xế chủ động gửi vị trí** · FR-GPS-01
- AC1. *Given* chuyến của tôi `on_road`, *When* tôi bấm "Cập nhật vị trí", *Then* gửi **một điểm** (`POST /trips/{id}/positions`), lưu `vehicle_position(source='driver_tap')` kèm `remaining_km`, `remaining_min`; ETA tính lại.
- AC2. *Then* không có thu vị trí theo chu kỳ, không gửi lô, không hàng đợi offline.
- AC3. *Given* chuyến không phải của tôi → `404`; chuyến chưa `on_road` hoặc ngoài khung khả dụng → `409 NOT_ON_TRIP`.
- AC4. *Then* app hiện thông báo quyền riêng tư và xin quyền vị trí trước lần gửi đầu; bị từ chối quyền → không gửi được và nút Giao xong/Thất bại bị khóa (US-EXE-02 AC8).

**US-GPS-02 — Dispatcher xem dòng vị trí gần nhất** · BR-GPS-01
- AC1. *Then* `GET /gps/live` chỉ trả các chuyến `on_road` có `assigned_dispatcher_employee_id` = chính tôi, mỗi chuyến một dòng **Vị trí gần nhất · Giờ cập nhật · ETA** (kèm km còn lại, rủi ro, sự cố mở). Không có bản đồ.
- AC2. *Then* Dispatcher khác, Sales, CS, khách → `403`; chuyến kết thúc → không còn trong danh sách.
- AC3. *Given* đơn được duyệt, *Then* mọi chuyến gán cùng một Dispatcher theo luân phiên (người `in_rotation` lâu nhất chưa được gán); `POST /trips/{id}/handover` bàn giao có audit `TRIP_DISPATCHER_HANDOVER`; không ai trong danh sách → không ai xem, alert.
- AC4. *Then* không endpoint nào trả vị trí tổng hợp theo tài xế.

**US-GPS-03 — Xóa tọa độ** 
- AC1. *Given* đơn chuyển `DELIVERED` hoặc `CANCELLED`, *Then* mọi `vehicle_position` của đơn bị xóa; đơn `FAILED` chưa xử lý xong → xóa chậm nhất 7 ngày.
- AC2. *Then* không có API đọc lịch sử vị trí; tọa độ không xuất hiện trong milestone, audit, thông báo, log.

---

## Epic 10 — ETA, rủi ro, cảnh báo

**US-RSK-01 — Tính lại ETA đúng lúc** · FR-RSK-01
- AC1. *(R3)* *Given* không có sự kiện mới (duyệt, mốc kho, xuất phát, vị trí tài xế, sự cố có vị trí, giao/thất bại, nguồn sửa đơn), *Then* không có dòng `eta_forecast` mới.
- AC2. *(R3)* *Given* mốc `GOODS_READY` kế hoạch 11:00 và đến 11:31 chưa có sự kiện, *When* job quá hạn chạy, *Then* alert `OVERDUE` cho Dispatcher; **không** tính lại ETA.
- AC5. *(R3)* *Given* chuyến `on_road`, ETA 10:00, đến 10:31 chưa có `DELIVERED`/`FAILED`, *Then* alert `OVERDUE` cho Dispatcher (dedupe theo chuyến).
- AC3. *Given* đơn nhiều ngày, *Then* rà soát tổng thể vận hành (chỉ cảnh báo, không tính lại ETA) **07:00 và 13:00 mỗi ngày theo timezone của market** (pilot Europe/Stockholm), không thay thế xử lý sự kiện hay đồng bộ đơn; các job/tần suất D8 khác **chỉ được Owner duyệt để triển khai/kiểm thử staging**, không bật production (DEC-D8-STAGING-SCHEDULE-20261109).
- AC4. *Given* chậm chuẩn bị nhưng `depart_at` kế hoạch còn dư thời gian hấp thụ, *Then* `forecast_eta = planned_eta`, tiêu hao 0%.

**US-RSK-02 — Trạng thái rủi ro** · BR-RSK-01
- AC1. *Given* `planned_eta` 08:00, `promise_end` 10:00 (reserve 120'), `forecast_eta` 08:35, *Then* tiêu hao 29% → ON_TRACK/green.
- AC2. *Given* `forecast_eta` 09:00 → 50% → AT_RISK/yellow (chỉ đổi màu).
- AC3. *Given* `forecast_eta` 09:30 → 75% → AT_RISK/orange, tạo alert `RISK_ORANGE`.
- AC4. *Given* `forecast_eta` 10:20 (slack −20') ở **hai lần tính liên tiếp cách nhau ≥ 5 phút**, *Then* PREDICTED_LATE/red, alert critical và **bản nháp** báo trễ.
- AC5. *Given* chỉ một lần slack âm, *Then* vẫn AT_RISK/orange chưa PREDICTED_LATE.
- AC6. *Given* `now > promise_end` và chưa giao, *Then* OVERDUE.
- AC7. *Given* `reserve_total` thực tế 10 phút, *Then* dùng tối thiểu 30 phút để tránh nhảy trạng thái.

**US-RSK-03 — Danh sách cảnh báo** · Là *dispatcher*, tôi xử lý cảnh báo.
- AC1. *Then* `GET /alerts` lọc theo `type`, `level`, `resolved`; sắp xếp critical trước.
- AC2. *When* `ack`, *Then* ghi `acknowledged_by/at`; cùng `dedupe_key` không tạo alert mới khi đang mở.
- AC3. *Given* alert đã `resolved`, *When* cùng điều kiện xảy ra lại, *Then* alert mới được tạo (dedupe chỉ áp dụng cho alert đang mở).

---

## Epic 11 — Thông báo khách

**US-NOT-01 — Thông báo tự động** · FR-NOT-01
- AC1. *When* duyệt, *Then* tạo `CONFIRMED` chứa ngày và khung giờ; *When* `DISPATCHED`, *Then* `DISPATCHED`; *When* giao xong `DELIVERED`, thất bại `FAILED`.
- AC2. *Then* nội dung chỉ có trạng thái và ETA; không toạ độ, không GPS, không dữ liệu nội bộ.
- AC3. *(R3)* Chỉ email qua Mailpit/SMTP; khách chọn SMS → gửi email nếu có; không có email → `suppressed` (`SKIPPED_NO_CHANNEL`). Đơn nhiều xe chỉ một `DISPATCHED`; `FAILED` luôn gửi; `DISPATCHED` tắt được bằng cờ `NOTIFY_DISPATCHED_ENABLED`.
- AC4. *Given* `shadow_mode = true`, *Then* thông báo ở trạng thái `suppressed` (`suppressed_reason = shadow_mode`).

**US-NOT-02 — Báo trễ do dispatcher gửi** · BR-RSK-02, FR-NOT-02
- AC1. *Given* alert PREDICTED_LATE **và đã có khung ETA start/end/version được Dispatcher duyệt**, *Then* tạo `notification(status=draft, template=DELAY)` trong transaction của risk, không tự gửi; nếu chưa có khung được duyệt thì chặn draft/send (N1/N2/N4).
- AC2. *When* dispatcher sửa nội dung/khung giờ và `send`, *Then* `queued → sent`, ghi `NOTIFICATION_SENT`, lưu `eta_window` đã thông báo.
- AC3. *When* dispatcher `discard` không có lý do, *Then* `422`; có lý do → `suppressed`, ghi `NOTIFICATION_SUPPRESSED`.
- AC4. *Given* đã gửi khung 11:00–13:00 và ETA mới lệch < 30 phút, *Then* không tạo bản nháp mới; lệch ≥ 30 phút → tạo bản nháp mới.
- AC5. *Given* người dùng không phải dispatcher, *Then* không thể gửi (`403`).

**US-NOT-03 — Giờ yên lặng và gửi lại** · FR-NOT-03
- AC1. *Given* thông báo `DISPATCHED` tạo lúc 22:30, *Then* `scheduled_for` = 07:00 hôm sau.
- AC2. *Given* thông báo `DELAY` lúc 22:30, *Then* gửi ngay **theo ngoại lệ đã ghi trong AC hiện có**, nhưng vẫn chỉ đến Mailpit/test recipients. Quyết định N5 giữ retry cap và không duyệt backoff mới; nếu thay đổi ngoại lệ quiet-hours cần owner review riêng.
- AC3. *Given* SMTP lỗi, *Then* thử lại tối đa 3 lần rồi `failed` kèm `last_error`.
- AC4. *Then* `dedupe_key` ngăn gửi trùng một mẫu cho cùng đơn, cùng kế hoạch/lần giao và cùng trạng thái; sau khi lập lại kế hoạch, `CONFIRMED`/`DISPATCHED` của kế hoạch mới vẫn được tạo.

---

## Epic 12 — Nhân sự, tài khoản, phân quyền

**US-EMP-01 — Nhân viên và phân công** · FR-EMP-01/02, BR-EMP-01/02
- AC1. *Given* nhân viên đã có phân công hiệu lực, *When* gán thêm phân công thứ hai mà không đóng cái cũ, *Then* DB từ chối (`ux_one_active_assignment`).
- AC2. *When* `POST /employees/{id}/assignments` chuyển sang kho khác, *Then* phân công cũ có `end_date`, phân công mới hiệu lực.
- AC3. *When* gán quản lý chính thứ hai cho cùng kho, *Then* DB từ chối.
- AC4. *Then* `owner_employee_id` mặc định là quản lý chính; `admin` gán lại được.
- AC5. *Given* quản lý kho Malmö chưa có phân công tại kho Malmö, *Then* không thể đặt làm quản lý của kho đó.

**US-EMP-02 — Năm bảng con** · 
- AC1. *Then* `warehouse_staff`, `sales_staff`, `dispatcher_staff`, `driver_staff`, `cs_staff` đều có và chỉ chứa thuộc tính đặc thù; không có bảng con cho admin, Business owner, Project lead.
- AC2. *Then* công nhân kho (`WAREHOUSE_OPERATOR`) không có `app_user`.

**US-EMP-03 — Đăng nhập và quyền** · FR-EMP-03
- AC1. *When* đăng nhập đúng, *Then* nhận JWT 8 giờ kèm `roles`, `location_ids`.
- AC2. *Given* quản lý kho A gọi API kho B, *Then* `404`.
- AC3. *Given* mỗi hàng trong ma trận quyền ở `06` mục 3, *Then* có test cho cả đường được phép và bị cấm.
- AC4. *When* nhân viên `terminated`, *Then* `app_user.is_active = false` và token hiện tại bị từ chối ở lần gọi kế.

**US-EMP-04 — Xe và tài xế** · *(R3, DEC-R3-15: dữ liệu xe/tài xế từ seed và nguồn fleet, không có màn quản lý.)*
- AC1. *Then* tài xế có hạng bằng và ngày hết hạn; hết hạn trong 30 ngày hiện cảnh báo cho quản lý kho.
- AC2. *Then* xe có tải, thể tích, năng lực, nhóm hàng chở được, kho gốc.

---

## Epic 13 — Chăm sóc khách hàng (bộ phận riêng)

**US-CS-01 — Tra cứu trạng thái** · Là *CSKH*, tôi trả lời khách nhanh.
- AC1. *Then* tìm đơn theo `order_no`, tên khách, điện thoại; xem trạng thái, khung giờ cam kết, ETA hiện tại, lịch sử thông báo.
- AC2. *Then* không thấy GPS, điểm số, quyết định nội bộ, giá vốn; mọi endpoint GPS trả `403`.
- **Owner-approved CS-01 (09/11/2026):** sử dụng `GET /orders?q=` hiện có, tìm cả `external_ref` và số `contact_phone` sau chuẩn hóa ở backend; giới hạn tra cứu ngắn, scope market/role, không lộ phone qua danh sách/log, không thêm param mới.
- **Owner-approved CS-02:** CS nhận phone/email **masked từ backend**, không có raw phone/email hoặc `delivery.lat/lon`, `receiving_restrictions`/gate code hay score/decision nội bộ trong response; UI không reveal. Chi tiết tên/kiểu DTO riêng cho CS qua contract review. [Biên bản](decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md).

**US-CS-02 — Nhật ký liên hệ** · Đã bỏ (R3, DEC-R3-05): endpoint `contact-logs` không mount (`404`).
- AC2. *Then* CS không sửa kế hoạch, không gửi báo trễ (`403`).

---

## Epic 14 — KPI và nhật ký

**US-KPI-01 — Dashboard KPI** · FR-KPI-01
- AC1. *(R3)* *Then* dashboard hiện **5 KPI**: thời gian lập kế hoạch/đơn (so baseline, tách theo đường Sales/Dispatcher), giao đúng hạn, tỷ lệ chấp nhận phương án (rank-1 duyệt không sửa, tách theo đường), can thiệp thủ công/đơn (so baseline), sai số ETA (median và P90, có mục tiêu, **không baseline**); biểu đồ theo ngày market-local, mặc định 30 ngày, tối đa 366.
- AC5. *(R3)* *Then* chỉ số phụ: thời gian từ đơn vào CFO đến `CONFIRMED` (tách theo đường) và % đơn cam kết ngay tại quầy.
- AC6. *(R3)* *Then* sai số ETA = |ETA dự báo tại `DISPATCHED` − giờ POD| theo chuyến; `PUT /kpi/baseline/eta_error_min` → `422`.
- AC2. *Given* đơn FAILED, *Then* không nằm trong mẫu số `on_time_rate`.
- AC3. Đã bỏ (R3): giờ công và km mỗi lần giao không còn là KPI.
- AC4. *Then* `/kpi/*` chỉ cho `admin` hoặc người có `ops`; Business owner (`revenue_all`) nhận `403`.

**US-REV-01 — Doanh thu** · Là *Business owner / owner kho, cửa hàng*, tôi xem doanh thu chỉ đọc. · FR-KPI-02, BR-KPI-01 (mỗi AC thành một test)
- AC1. *Given* Business owner, *Then* thấy doanh thu mọi cửa hàng và kho; `/kpi/summary`, `/audit/decisions`, `/orders/{id}` trả `403`.
- AC2. *Given* store manager là owner của ST-021, *Then* chỉ thấy ST-021; yêu cầu ST-022 trả `404`.
- AC3. *Given* quản lý kho Göteborg là owner của GBG, *Then* chỉ thấy kho GBG ở góc nhìn warehouse; `view=store` với GBG → `422`.
- AC4. *Given* dispatcher, CS, sales không phải owner, tài xế, Project lead, *Then* `403`; admin thấy tất cả.
- AC5. *Then* doanh thu ghi nhận chỉ gồm đơn DELIVERED, theo ngày giao ở múi giờ market; FAILED và CANCELLED không tính; đơn APPROVED đến DISPATCHED hiện ở "Booked".
- AC6. *Then* doanh thu bằng tổng `line_total`; không có phí giao hay đóng gói.
- AC7. *Then* tổng theo cửa hàng bằng tổng theo kho trong cùng kỳ (đơn không có cửa hàng nhóm vào "Unassigned store"); UI không có tổng gộp hai góc nhìn.
- AC8. *Then* xuất CSV chỉ cho owner, Business owner, admin; mỗi lần ghi `REVENUE_EXPORTED`; người khác `403`.
- AC9. *Then* danh sách đơn của Business owner không chứa tên, điện thoại, địa chỉ khách.
- AC10. *Given* đơn giao 23:50 giờ Stockholm, *Then* tính vào ngày đó, không lệch sang UTC.
- AC11. *Given* đơn giao thất bại rồi giao lại thành công, *Then* chỉ tính một lần, vào ngày giao thành công.

**US-REV-02 — Đơn hàng theo nhóm trạng thái (R3, DEC-R3-15)** · FR-KPI-03, BR-KPI-01
- AC1. *Given* owner ST-021 chọn 01–30/11, *Then* `GET /revenue/order-status` trả tổng số đơn và 5 nhóm (Đã duyệt, Đang vận chuyển, Đã hoàn thành, Thất bại, Đã hủy) với số đơn và giá trị; tổng các nhóm = tổng số đơn.
- AC2. *Given* đơn `APPROVED` có `committed_date` 05/12, *Then* không nằm trong kỳ 01–30/11; *Given* đơn `PLANNED` chưa duyệt, *Then* không nằm trong báo cáo.
- AC7. *Given* đơn `PLANNED` bị hủy ngày 15/11 (trước duyệt), *Then* nằm trong nhóm Đã hủy của kỳ 01–30/11 (theo ngày hủy); đơn đã duyệt bị hủy cũng tính theo ngày hủy.
- AC3. *Given* đơn chuyển từ `DISPATCHED` sang `DELIVERED`, *Then* chuyển từ nhóm Đang vận chuyển sang Đã hoàn thành (theo trạng thái hiện tại).
- AC4. *Then* quyền như US-REV-01: owner nơi khác → `404`; dispatcher, CS, sales không phải owner, tài xế, Project lead → `403`; không có dữ liệu cá nhân khách.
- AC5. *Then* `amount` là giá trị đơn, khác doanh thu ghi nhận (US-REV-01 AC5 vẫn theo ngày giao thực tế).
- AC6. *When* chọn một nhóm, *Then* `/revenue/orders?status_group=` liệt kê đúng các đơn của nhóm đó.

**US-KPI-02 — Baseline** · Là *admin*, tôi nhập baseline thủ công.
- AC1. *When* `PUT /kpi/baseline/planning_time_min {value:15}`, *Then* dashboard so sánh với 15 phút.

**US-LOG-01 — Nhật ký quyết định** · FR-LOG-01, BR-GEN-04
- AC1. *Given* mỗi hành động trong danh sách ở `04` mục 10, *Then* có đúng một dòng `decision_log` cùng transaction, kèm `correlation_id`.
- AC2. *Then* `UPDATE/DELETE` lên `decision_log` và `milestone_event` bị trigger từ chối.
- AC3. *Then* log kỹ thuật JSONL không chứa tên, điện thoại, email, địa chỉ khách (kiểm bằng test quét mẫu).
- AC4. *Then* mọi dòng `decision_log` của một request có cùng `correlation_id` với log kỹ thuật của request đó.

---

## Epic 15 — Quản trị

**US-ADM-01 — Đồng bộ và dữ liệu** · FR-ADM-01
- AC1. *Then* admin xem `sync-runs`, số dòng nạp/lỗi, `data_as_of`; mở được danh sách dòng bị loại kèm lý do.
- AC2. *When* chạy tay `/sync/orders/run` khi đang chạy, *Then* `409 SYNC_IN_PROGRESS`.

**US-ADM-02 — Cấu hình market** · **Hoãn màn (DEC-R3-15)**: cấu hình qua file/seed; các AC dưới đây chỉ áp dụng cho giá trị cấu hình. 
- AC1. *When* `PUT /markets/SE/config` với giá trị sai kiểu (ví dụ `delivery_share = 1,5`), *Then* `422` theo `MarketConfig`.
- AC2. *Then* thay đổi cấu hình ghi `decision_log`; kế hoạch đang giữ chỗ không đổi.

**US-ADM-03 — GPS và tuân thủ** · BR-GPS-01
- *(R3)* `gps_enabled` chỉ cho phép tài xế **chủ động gửi** vị trí (DEC-R3-01); không có thu theo chu kỳ.
- AC1. *When* admin bật `gps_enabled` mà chưa có DPIA `approved`, *Then* được phép (bản demo) nhưng phản hồi có `warnings: ["DPIA_MISSING"]`, UI hiện biểu ngữ.
- AC2. *Then* ghi `GPS_SETTING_CHANGED`.

---

## Epic 16 — Hệ thống nguồn giả lập (POS)

**US-SRC-01 — Dữ liệu seed hợp lệ** · 
- AC1. *When* chạy seed, *Then* có 3 kho, 25 cửa hàng, ~100 SKU phủ N1–N6, 8–10 xe, ~40 khách (DN và cá nhân), địa chỉ kèm toạ độ, tồn kho và hàng nhập, lịch xe, ~150 nhân viên, ngày lễ Thụy Điển; seed lặp lại cho kết quả giống nhau.
- AC2. *Then* seed có các tình huống cho kịch bản kiểm thử 1–18 (xem `08`).

**US-SRC-02 — Hợp đồng nguồn dùng chung** · BR-GEN-02
- AC1. *Then* mọi nước dùng cùng `openapi.yaml`; contract test chạy với instance SE và một instance giả khác.

**US-SRC-03 — Sales Validation** · 
- AC1. *When* `validate`, *Then* kiểm khách, địa chỉ/toạ độ, dòng hàng, dạng ngày, yêu cầu đặc biệt; `submit` chỉ cho phép sau khi `validate` thành công.

---

## Phụ lục — Ma trận truy vết story ↔ yêu cầu

| Epic | Story | FR / BR chính |
|---|---|---|
| 1 | US-INT-01..05 | FR-INT-01..07, BR-GEN-01/02/05, BR-ORD-01 |
| 2 | US-PRD-01..05 | FR-PRD-01..05, BR-PRD-01..05 |
| 3 | US-ORD-01..05 | FR-ORD-01..05, BR-ORD-01..04, BR-DEL-05 |
| 4 | US-ATP-01..03 | FR-ATP-01..03, BR-ATP-01..05 |
| 5 | US-WH-01..06 (US-WH-03 đã bỏ, US-WH-06 mới: lịch phân ca từng người) | FR-PRP-02, FR-PRP-04, FR-PRP-05, FR-EXE-01, BR-PRP-02, BR-PRP-04, BR-PRP-05, BR-EMP-03 |
| 6 | US-PLN-01..08 | FR-PRP-01, FR-DEL-01..04, FR-RNK-01..03, BR-PRP-01, BR-DEL-01..05, BR-GATE-01, BR-RNK-01..05 |
| 7 | US-RES-01, US-APR-01..04 | FR-APR-01..05, BR-RES-01..04, BR-APR-01..04 |
| 8 | US-EXE-01..04, US-WH-04 | FR-EXE-01..04, BR-EXE-01..03, BR-DEL-05 |
| 9 | US-GPS-01..03 | FR-GPS-01, BR-GPS-01 |
| 10 | US-RSK-01..03 | FR-RSK-01/02, BR-RSK-01/02 |
| 11 | US-NOT-01..03 | FR-NOT-01..04, BR-NOT-01..03 |
| 12 | US-EMP-01..04 | FR-EMP-01..03, BR-EMP-01..04 |
| 13 | US-CS-01/02 | FR-ORD-04, BR-GPS-01 |
| 14 | US-KPI-01/02, US-REV-01, US-LOG-01 | FR-KPI-01/02, FR-LOG-01, BR-KPI-01, BR-GEN-04 |
| 15 | US-ADM-01..03 | FR-ADM-01, BR-GPS-01 |
| 16 | US-SRC-01..03 | FR-INT-01, BR-GEN-02 |

### Owner-approved acceptance addendum — 2026-11-09

Các AC trên được làm rõ bởi [27 owner decisions](decisions/OWNER_CROSS_WORKSTREAM_APPROVED_20261109.md). Bổ sung bắt buộc cho việc nghiệm thu: T07 scope/evidence 30 ngày & snapshot coverage đầy đủ; T18 chứng cứ WMS thể hiện inbound (không chỉ timestamp); D7 history 56 ngày từng ngày có verifier, nghỉ 11h; M6 POD delivered theo mỗi `trip_stop`; GPS notice/ack riêng từng driver, upload ≤100 điểm/batch và xoá ngay khi hết trip/ca; D4 outbox cùng transaction và DELAY start/end được duyệt; API sử dụng `passed`/flat rejected candidates; M8 có 10 KPI keys, diagnostics thiếu nguồn = `null`, cohort theo market-local approval/delivery/work_date. Nếu thiếu chứng cứ thì test phải chứng minh fail-closed. Chưa có migration/API/E2E thật không được đánh dấu Done.

### Conditional acceptance — reverse product mapping for future WMS reservation (DEC-WMS-REVERSE-SKU-20261109)

- AC-WMS-SKU-01. Given one confirmed SKU mapped to a global product, a future authorized WMS reserve/release uses original WMS-recognized SKU for that market/warehouse and quantity in its fixed WMS inventory unit, not CFO global code.
- AC-WMS-SKU-02. Given two source SKUs mapping to one global product, preserve original order-line and verified warehouse allocation; do **not** choose an arbitrary inverse or combine stock aliases.
- AC-WMS-SKU-03. Given POS SKU differs from WMS SKU, missing or changed mapping, missing warehouse/market, invalid conversion or stale context, **block** outbound request until identity and quantities are verified.
- AC-WMS-SKU-04. Match authoritative WMS ACK with requested SKU/warehouse/qty and idempotency; avoid double deduction. **This acceptance does not grant WMS write permission.**

[Decision](decisions/DEC_WMS_REVERSE_SKU_FOR_RESERVATIONS_20261109.md).


### WMS stock confirmation — owner-approved business acceptance (DEC-WMS-RESERVE-SYNC-20261109)

- AC-WMS-RES-01. Given CFO has an eligible 100%-mapped order and fresh complete WMS stock, when planning, then CFO checks WMS availability (including reservations from all WMS channels) and counts only temporary CFO holds not already reflected in WMS. Missing/stale data fails closed.
- AC-WMS-RES-02. Given authorized Sales/Dispatcher approves a valid plan, then CFO must construct an idempotent WMS reserve for correctly reverse-mapped native SKU, warehouse and stock unit. Only after WMS confirms the exact lines/qty may CFO guarantee stock and finalize approval; failed, partial or unknown reserve may not be presented as approved.
- AC-WMS-RES-03. Given WMS confirms reserve 60 from on_hand 100, then WMS available becomes 40 while on_hand stays 100 until actual issue; CFO **immediately** refreshes its WMS-derived stock/order state and does **not** deduct 60 a second time. Scheduled polling verifies later changes.
- AC-WMS-RES-04. Given successful WMS ACK but delayed published snapshot, concurrent second order, timeout or failed local commit, CFO must never promise duplicate stock; use reviewed version-linked pending protection/fail-closed state, idempotent status lookup and compensation. Actual WMS API and rollout require explicit technical/security review.

[Decision](decisions/DEC_WMS_RESERVE_SYNC_20261109.md).
