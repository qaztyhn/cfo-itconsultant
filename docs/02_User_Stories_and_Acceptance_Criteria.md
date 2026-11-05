# 02 — User Stories & Acceptance Criteria (CFO MVP)

> Mỗi story có mã `US-…`, vai trò, giá trị, tham chiếu yêu cầu (`FR-…`, `BR-…` ở `01_PRD.md`) và tiêu chí chấp nhận theo dạng **Given / When / Then**. Mỗi AC phải kiểm thử được (unit/integration/E2E) và dùng làm tên test (`test_US_PLN_03_AC2_…`). Mọi story đều **M** (bắt buộc MVP) trừ khi ghi khác. Các endpoint nêu theo `06_API_Specification.md`.
> Quy ước: "hôm nay" trong ví dụ là 2026-11-04 (Thứ Tư) 10:05, giờ địa phương Europe/Stockholm, trùng đồng hồ demo `APP_NOW` ở `08`.
> **Phiên bản 1.1 (06/11/2026):** bỏ US-WH-03 và US-PLN-02 AC3 (thiết bị kho ngoài MVP); thêm US-APR-04 (xử lý ngoài CFO); bổ sung AC cho lập lại sau duyệt, giao lại sau thất bại, giữ chỗ đồng thời, dedupe thông báo/cảnh báo, doanh thu.

---

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

## Epic 2 — Sản phẩm và ánh xạ (IT)

**US-PRD-01 — Hàng đợi ánh xạ SKU** · Là *IT*, tôi muốn thấy các SKU chưa ánh xạ và các đơn đang bị chặn. · FR-PRD-02/03
- AC1. *Given* đơn chứa SKU `SE-NEW-77` chưa ánh xạ, *When* đơn vào CFO, *Then* đơn `BLOCKED_UNMAPPED_SKU` với `block_reason` nêu SKU, `mapping_task` được tạo với `blocked_order_count = 1`.
- AC2. *Given* hai đơn cùng chứa SKU đó, *Then* chỉ một `mapping_task`, `blocked_order_count = 2`.
- AC3. *Given* SKU có `gtin` trùng sản phẩm global G-000123, *Then* `candidates` có G-000123 với `reason = gtin`.
- AC4. *Given* tên SKU giống 0,6 theo `pg_trgm` và cùng category, *Then* xuất hiện ứng viên `name_sim` kèm điểm.

**US-PRD-02 — Xác nhận ánh xạ** · Là *IT*, tôi chọn hoặc tạo sản phẩm global để mở khóa đơn. · BR-PRD-02
- AC1. *Given* tôi là `admin`, *When* `POST /mapping/tasks/{id}/confirm` với `global_product_id`, *Then* `product_se.mapping_status = confirmed`, `mapped_by` là tôi, các đơn bị chặn tự chuyển `SUBMITTED` rồi vào lập kế hoạch.
- AC2. *Given* tôi là `dispatcher`, `warehouse` hoặc `sales`, *When* gọi endpoint, *Then* `403 FORBIDDEN`.
- AC3. *Given* tạo global mới, *Then* bắt buộc: nhóm xử lý, `base_unit`, cân nặng, thể tích, `base_units_per_prep_unit` (trừ nhóm đơn vị `line`), `units_to_base` > 0; thiếu → `422`.
- AC4. *Then* ghi `decision_log MAPPING_CONFIRMED` kèm trước/sau.

**US-PRD-03 — Từ chối ánh xạ** · Là *IT*, tôi từ chối với lý do. · BR-GEN-04
- AC1. *When* `reject` không có `reason_text`, *Then* `422 REASON_REQUIRED`.
- AC2. *When* reject hợp lệ, *Then* SKU `rejected`, đơn liên quan vẫn bị chặn và dispatcher thấy lý do.

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
- AC4. *When* `submit` sau `validate` thành công, *Then* đơn `SUBMITTED_FOR_PLANNING` và được CFO kéo ở lượt kế tiếp.
- AC5. *Then* địa chỉ chọn từ danh sách seed có toạ độ (không geocoding thật).

**US-ORD-02 — Danh sách đơn theo phạm vi** · Là *dispatcher/kho/cửa hàng/CS*, tôi thấy đúng các đơn mình được xem. · FR-ORD-03
- AC1. *Given* quản lý kho Malmö, *Then* chỉ thấy đơn có kế hoạch/giao từ kho Malmö; *Given* store manager Göteborg Väst, chỉ thấy đơn `origin_store_id` của mình (chỉ xem).
- AC2. *Given* ID đơn ngoài phạm vi, *Then* `404`.
- AC3. *When* lọc `risk_color=orange&status=PREPARING`, *Then* kết quả đúng và sắp xếp theo `promise_end` tăng dần.

**US-ORD-03 — Chi tiết đơn và dòng thời gian** · Là *dispatcher*, tôi xem toàn bộ lịch sử một đơn. · FR-ORD-04
- AC1. *Then* timeline gộp: đơn nộp, các run lập kế hoạch, quyết định, sự kiện kho/tài xế, thông báo, phiên bản ETA, theo thứ tự thời gian.
- AC2. *Given* vai trò `customer_service`, *Then* thấy trạng thái, ETA, thông báo; **không** thấy GPS, điểm số, quyết định nội bộ.

**US-ORD-04 — Hủy và lập lại đơn** · Là *dispatcher*, tôi hủy hoặc lập lại có lý do. · BR-GEN-04
- AC1. *When* `cancel` không `reason_text`, *Then* `422 REASON_REQUIRED`.
- AC2. *Given* đơn `DISPATCHED`, *When* cancel, *Then* `409 ILLEGAL_TRANSITION`.
- AC3. *Given* đơn `APPROVED`, *When* `replan` có lý do, *Then* giữ chỗ `committed` → `released`, đơn `SUBMITTED`, ghi `ORDER_REPLAN`.

**US-ORD-05 — Đơn cần nhiều xe/nguồn** · Là *dispatcher*, tôi muốn đơn quá lớn được đánh dấu để tự lập. · FR-ORD-05
- AC1. *Given* tổng khối lượng 28.000 kg > xe lớn nhất (9.000 kg), *Then* `needs_manual = true`, đơn `MANUAL_PLANNING`, `manual_reason = NEEDS_MULTI_VEHICLE`.
- AC2. *Given* đơn đó, *When* dispatcher gọi `manual-plan` với một xe 9.000 kg, *Then* `422 NO_TRUCK_FIT` kèm `details.hint = "EXTERNAL_HANDOFF"`.
- AC3. *When* dispatcher gọi `external-handoff` có lý do, *Then* đơn `HANDLED_EXTERNALLY` (xem US-APR-04).

---

## Epic 4 — Tồn kho, ATP, chuyển kho

**US-ATP-01 — Time-phased ATP** · Là *hệ thống*, tôi kiểm tra đủ hàng theo ngày. · BR-ATP-01..04
- AC1. *Given* kho A: on_hand 100, wms_reserved 20, giữ chỗ đơn khác 30, cần 60, *Then* usable 50 → không đủ.
- AC2. *Given* hàng nhập confirmed 40 về trước ngày cần (đã cộng 1 ngày làm việc nhận kho), *Then* usable 90 ≥ 60 → đủ, phân loại *đủ sau hàng nhập*, `complexity_points += 1`.
- AC3. *Given* hàng nhập chưa xác nhận, *Then* không tính.
- AC4. *Given* không kho nào đủ trong 14 ngày, *Then* mọi kho `STOCK_SHORT`.
- AC5. *Given* hai phương án cùng đơn cùng kho, *Then* hàng chỉ bị giữ một lần.

**US-ATP-02 — Gợi ý chuyển kho** · Là *dispatcher*, tôi nhận gợi ý kho nguồn khi mọi kho thiếu. · BR-ATP-05
- AC1. *Given* kho đích thiếu 40 bao, kho nguồn B còn 100 sẵn có, A còn 20, *Then* chỉ B được gợi ý, kèm `lead_days` và khoảng cách.
- AC2. *Given* hai kho nguồn đủ, *Then* xếp theo `lead_days` tăng, rồi khoảng cách tăng; tối đa 3 gợi ý.
- AC3. *When* dispatcher duyệt gợi ý, *Then* `stock_transfer(approved)`, ghi `TRANSFER_APPROVED`.

**US-ATP-03 — Quản lý kho nguồn xác nhận chuyển kho** · Là *quản lý kho nguồn*, tôi xác nhận có thể xuất. · BR-EMP-03
- AC1. *Given* tôi là quản lý có `can_approve` của kho nguồn, *When* `confirm-source`, *Then* tạo `inbound_shipment(source=transfer, confirmed=true, eta_date=…)` và đơn có thể chạy lại kế hoạch.
- AC2. *Given* tôi là quản lý kho khác, *Then* `403`.
- AC3. *When* kho đích `receive`, *Then* `received = true`.

---

## Epic 5 — Kho: năng lực, điểm danh

**US-WH-01 — Điểm danh** · Là *quản lý/trưởng ca kho*, tôi điểm danh nhanh để công suất đúng. · FR-PRP-05, BR-PRP-05
- AC1. *Given* 12 nhân viên kho của ngày 2026-11-12 ở trạng thái `planned`, *When* tôi bấm "tất cả có mặt", *Then* tất cả `present` trong một lần ghi.
- AC2. *When* tôi đặt 2 người `absent`, *Then* công suất ngày đó giảm tương ứng và `ATTENDANCE_CHANGED` được ghi.
- AC3. *Given* nhân viên được phân công cửa hàng, *Then* không xuất hiện ở điểm danh kho (một nơi tại một thời điểm).
- AC4. *Then* manager/supervisor (`counts_in_capacity = false`) không tính vào công suất nhặt hàng.

**US-WH-02 — Công suất ngày** · Là *dispatcher/kho*, tôi xem công suất. · BR-PRP-02
- AC1. *Given* 8 người present, `useful_hours = 7`, `delivery_share = 0,9`, *Then* `labour_cap = 8 × 7 × 0,9 = 50,4` giờ.
- AC2. *Given* đã đặt 30 giờ (committed + held đơn khác), *Then* `free = 20,4`.
- AC3. *Given* ngày lễ, *Then* công suất 0 và không xếp việc vào ngày đó.

**US-WH-03 — Thiết bị** · **Đã bỏ ở v1.1** (thiết bị kho ngoài MVP theo slide). Giữ mã để không đánh số lại.
- AC1. *Then* không có endpoint, bảng hay check nào về thiết bị kho; engine không trả `PREP_NO_EQUIPMENT`.

**US-WH-04 — Ghi mốc chuẩn bị** · Là *quản lý/trưởng ca*, tôi ghi `START_PREP`, `GOODS_READY`, `LOADED` thay cho công nhân. · FR-EXE-01
- AC1. *Given* đơn `APPROVED`, *When* tôi ghi `START_PREP`, *Then* đơn `PREPARING`, `occurred_at` lưu giờ tôi nhập.
- AC5. *When* `START_PREP` có `crew_size = 3`, *Then* giá trị được lưu trong payload và chép vào `improvement_log.crew_size` khi đơn đóng (dữ liệu để học định mức sau này); thiếu `crew_size` vẫn hợp lệ.
- AC2. *When* ghi `LOADED` trước `GOODS_READY`, *Then* `409 ILLEGAL_TRANSITION`.
- AC3. *When* gửi lại cùng `Idempotency-Key`, *Then* không tạo sự kiện thứ hai.
- AC4. *Then* sau mỗi mốc, ETA được tính lại (một dòng `eta_forecast` mới).

**US-WH-05 — Báo ngoại lệ kho** · Là *quản lý kho*, tôi báo thiếu hàng, hỏng, sự cố xe, đổi ca. · FR-EXE-01
- AC1. *When* ghi `SHORTAGE {sku, qty_missing}`, *Then* alert `EXCEPTION` cho dispatcher, ETA tính lại; hệ thống **không** tự sửa tồn kho.
- AC2. *When* ghi `VEHICLE_ISSUE {vehicle_id}`, *Then* xe đó được cờ khả năng không khả dụng cho dispatcher cân nhắc lập lại; đơn bị ảnh hưởng tính lại ETA.
- AC3. *When* ghi `SHIFT_CHANGE`, *Then* công suất ngày được tính lại và các đơn có giữ chỗ ngày đó được tính lại ETA.

---

## Epic 6 — Lập kế hoạch và quyết định của dispatcher

**US-PLN-01 — Tính khối lượng việc** · Là *hệ thống*, tôi tính giờ công chuẩn. · BR-PRP-01
- AC1. *Given* 20 pallet xi măng (N3: 0,25 + 20×0,15), 15 pallet gạch (N2: 0,25 + 15×0,40), 3 dòng keo N1 (0,05 mỗi dòng), *Then* `labour_hours = 3,25 + 6,25 + 0,15 + 0,5 = 10,15`; không có giờ thiết bị trong kết quả.
- AC2. *Given* một dòng có cờ FRAGILE (×1,25) và HAZARDOUS (×1,30), *Then* hệ số = 1,625 (tối đa theo `flag_multiplier_cap = 2,0`).
- AC3. *Then* kết quả giống nhau với mọi kho (hệ số hiệu suất mặc định 1,0).

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
- AC4. *Given* hòa điểm, *Then* ưu tiên `planning_reserve` lớn hơn, rồi `complexity_points` thấp hơn, ETA sớm hơn, mã xe nhỏ hơn.
- AC5. *Then* mỗi phương án có `checks` 5 mục, `reason_codes`, `explanation` sinh từ mẫu câu; không phương án nào quá 2 cái cùng một kho; phương án hạng 1 có mã `LOWEST_SCORE_OF_3` (không có mã/chữ "cheapest"/"cost").
- AC6. *Then* giờ công đơn không được dùng làm tiêu chí so sánh giữa các kho.

**US-PLN-07 — Không có phương án khả thi** · Là *dispatcher*, tôi biết vì sao và ngày nào khả thi. · BR-RNK-04/05
- AC1. *Given* mọi kho thiếu hàng, *Then* `failed_check = stock`, đơn `NO_FEASIBLE_DATE`, `earliest_feasible_date` (tối đa 14 ngày tới) và gợi ý chuyển kho.
- AC2. *Given* ngày yêu cầu tự đổi mà khách chưa đồng ý, *Then* hệ thống **không** đổi `date_to`.
- AC3. *When* dispatcher ghi `date_negotiation(agreed)`, *Then* đơn có thể chạy lại với ngày mới (`version + 1`, ghi `DATE_NEGOTIATION_RECORDED`).
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
- AC1. *When* engine trả 3 phương án, *Then* tạo `planning_run.hold_expires_at = now + 15'`; `stock_reservation` và `prep_reservation` một lần cho mỗi (đơn, kho); `vehicle_reservation` cho từng phương án.
- AC2. *Given* hai phương án cùng đơn dùng cùng xe, *Then* ghi được (cùng `order_id`); *Given* đơn khác cố giữ cùng xe trùng giờ, *Then* ràng buộc EXCLUDE từ chối.
- AC3. *When* gia hạn 2 lần thành công, *Then* lần thứ ba `409 HOLD_EXTENSION_LIMIT`.
- AC4. *When* quá `hold_expires_at`, *Then* job `hold_expiry` chuyển `held → expired`, plan `proposed → expired`.
- AC5. *Then* tồn kho khả dụng của đơn khác trừ cả `held` còn hạn lẫn `committed`.
- AC6. *Given* kho A còn 100 bao SKU X khả dụng, đơn 1 cần 80 và đơn 2 cần 70, *When* hai dispatcher lập kế hoạch hoặc duyệt **đồng thời**, *Then* tổng `held + committed` của X tại A không vượt 100; đúng một đơn có giữ chỗ/duyệt tại A, đơn kia bị loại kho A (`STOCK_SHORT`) hoặc nhận `409 RESOURCE_CONFLICT`.
- AC7. *Given* kho A ngày D còn 6 giờ công trống, hai đơn mỗi đơn cần 5 giờ trong ngày D, *When* duyệt đồng thời, *Then* tổng giờ đã đặt ngày D không vượt công suất; đúng một đơn thành công.

**US-APR-01 — Duyệt kế hoạch** · Là *dispatcher*, tôi duyệt để thành cam kết. · BR-APR-01, FR-APR-03
- AC1. *When* `POST /plans/{id}/approve` hợp lệ, *Then* plan `approved`, giữ chỗ → `committed`, phương án khác `superseded`/`released`, tạo `delivery_trip` + `trip_stop`, đơn `APPROVED`, đặt `committed_date`, `promise_start/end`, tạo thông báo `CONFIRMED`, ghi `PLAN_APPROVED`.
- AC2. *Given* hold đã hết hạn nhưng tài nguyên còn trống, *Then* duyệt vẫn thành công nhờ kiểm tra lại.
- AC3. *Given* trong lúc đó đơn khác đã chiếm xe, *Then* `409 RESOURCE_CONFLICT` (kèm `details.conflict`) và không có thay đổi nào được ghi (rollback).
- AC4. *Given* hai dispatcher duyệt đồng thời hai đơn tranh một xe, *Then* đúng một thành công.
- AC5. *Given* gửi lại cùng `Idempotency-Key`, *Then* trả kết quả cũ, không duyệt hai lần.
- AC6. *Given* duyệt phương án rank > 1 mà không có `reason_code`, *Then* `422 REASON_REQUIRED`; ghi `ALT_SELECTED`.
- AC7. *Given* `reserve_class = tight`, *Then* UI buộc dispatcher tick xác nhận rủi ro trước khi duyệt.
- AC8. *Given* ngày cam kết khác ngày khách đã đồng ý, *Then* cần `date_negotiation_id` (`agreed`), thiếu → `409 DATE_AGREEMENT_REQUIRED`.

**US-APR-02 — Kế hoạch tay** · Là *dispatcher*, tôi tự lập khi hệ thống không phù hợp. · BR-APR-02
- AC1. *Given* thiếu `manual_reason_code`, *Then* `422`.
- AC2. *Given* tôi chọn xe thiếu tải, *Then* engine kiểm gate và từ chối `422 NO_TRUCK_FIT`.
- AC3. *When* hợp lệ, *Then* plan `manual` được duyệt, lưu snapshot gồm phương án hệ thống đã đề xuất, tính vào `manual_plan_count`.

**US-APR-03 — Lập lại sau duyệt** · Là *dispatcher*, tôi lập lại khi có thay đổi lớn. 
- AC1. *When* `replan` có lý do, *Then* các giữ chỗ `committed` → `released`, trip → `cancelled`, đơn `SUBMITTED`, chạy lại engine.
- AC2. *Then* kế hoạch cũ `approved`/`manual` → `superseded`, `trip_stop` `pending` → `cancelled`, `approved_plan_id`/`committed_date`/`promise_*` = `NULL`, `decision_log ORDER_REPLAN` có `before` chứa ngày cam kết cũ; tất cả trong **một transaction**.
- AC3. *When* dispatcher duyệt kế hoạch mới, *Then* không bị chỉ mục `ux_one_approved_plan` chặn, và một thông báo `CONFIRMED` **mới** được tạo (dedupe theo `plan_id`) với ngày mới.
- AC4. *Given* đơn `APPROVED`, *When* `cancel` có lý do, *Then* kế hoạch, giữ chỗ, chuyến được đóng như AC2 và đơn `CANCELLED`.

**US-APR-04 — Ghi nhận xử lý ngoài CFO** · Là *dispatcher*, tôi đóng đơn cần nhiều xe hoặc xe ngoài đội mà CFO không lập được. · FR-ORD-05, BR-DEL-05
- AC1. *Given* đơn `MANUAL_PLANNING`, *When* `POST /orders/{id}/external-handoff` có `reason_code`, `reason_text`, *Then* đơn `HANDLED_EXTERNALLY`, lưu `external_handoff` (đối tác, ngày dự kiến, ghi chú), ghi `EXTERNAL_HANDOFF_RECORDED`.
- AC2. *When* thiếu `reason_code` hoặc `reason_text`, *Then* `422 REASON_REQUIRED`; *Given* đơn không ở `MANUAL_PLANNING`, *Then* `409 ILLEGAL_TRANSITION`.
- AC3. *Then* không tạo giữ chỗ, chuyến, GPS hay thông báo tự động cho khách.
- AC4. *Then* đơn không nằm trong mẫu số `on_time_rate`, được đếm ở `external_handoff_count`.
- AC5. *Given* vai trò khác `dispatcher`, *Then* `403`.

---

## Epic 8 — Thực thi và tài xế

**US-EXE-01 — Tài xế xem chuyến** · Là *tài xế*, tôi xem chuyến hôm nay trên điện thoại. · 
- AC1. *Then* `GET /driver/trips` chỉ trả chuyến của tôi, gồm xe, điểm dừng, địa chỉ, người liên hệ, yêu cầu đặc biệt, cửa sổ nhận hàng.
- AC2. *Then* không có giá đơn hay thông tin điểm số.

**US-EXE-02 — Xuất phát, giao, thất bại** · Là *tài xế*, tôi ghi sự kiện. · BR-EXE-01/02
- AC1. *Given* đơn `LOADED`, *When* tôi ghi `DISPATCHED`, *Then* chuyến `on_road`, đơn `DISPATCHED`, thông báo `DISPATCHED` được tạo.
- AC2. *When* `DELIVERED {recipient_name}`, *Then* đơn `DELIVERED`, `proof_of_delivery`, `delivered_at`, thông báo `DELIVERED`, trip `completed`.
- AC3. *When* `FAILED` thiếu `failure_reason`, *Then* `422`; hợp lệ → đơn `FAILED`, thông báo `FAILED` cho khách, alert dispatcher.
- AC4. *Given* tài xế khác cố ghi cho chuyến này, *Then* `403`.

**US-EXE-03 — Hàng đợi offline** · Là *tài xế*, tôi vẫn ghi được khi mất mạng. · FR-EXE-02
- AC1. *Given* điện thoại offline, *When* tôi bấm "Đã giao", *Then* sự kiện vào IndexedDB với `idempotency_key` và `occurred_at` = giờ chạm, UI báo "đang chờ đồng bộ".
- AC2. *When* có mạng, *Then* gửi tự động theo thứ tự; trùng key không tạo bản sao; `occurred_at` giữ giờ chạm.

**US-EXE-04 — Giao thất bại xếp lại** · Là *dispatcher*, tôi xếp lại đơn giao thất bại. · BR-EXE-02
- AC1. *Given* đơn `FAILED`, *When* `replan` có lý do, *Then* đơn `SUBMITTED` và chạy lại.
- AC2. *Then* đơn FAILED không nằm trong mẫu số `on_time_rate`, được tính ở `failed_delivery_rate`.
- AC3. *Given* đơn FAILED lần 1 (POD `failed`, `customer_absent`), *When* xếp lại, duyệt và giao thành công lần 2, *Then* có **hai** bản ghi `proof_of_delivery` (mỗi `trip_stop` một bản ghi), POD lần 1 không bị ghi đè, đơn `DELIVERED`.
- AC4. *Then* kế hoạch của lần giao thất bại chuyển `superseded` khi xếp lại (không chặn duyệt kế hoạch mới).

---

## Epic 9 — GPS

**US-GPS-01 — Gửi vị trí** · Là *tài xế*, tôi gửi vị trí khi đang chạy. · FR-GPS-01
- AC1. *Given* `gps_enabled = true` và chuyến `on_road`, *When* app gửi vị trí mỗi 30 phút, *Then* lưu `vehicle_position` (`source=device`).
- AC2. *Given* `gps_enabled = false`, *Then* `403 GPS_DISABLED`; chuyến chưa `on_road` → `409 NOT_ON_TRIP`.
- AC3. *Then* app hiện thông báo quyền riêng tư (mục đích, ai xem, chỉ gửi khi chuyến đang chạy, thời gian lưu) và xin quyền vị trí trước khi gửi.
- AC5. *Given* chuyến đã `completed` hoặc chưa `on_road` (ngoài giờ chạy chuyến), *Then* app không gửi vị trí và API trả `409 NOT_ON_TRIP`.
- AC4. *Given* bộ giả lập `gps_simulator.py`, *Then* gửi vị trí dọc tuyến mỗi 1–2 phút (`source=simulator`).

**US-GPS-02 — Dispatcher xem GPS** · Là *dispatcher*, tôi xem vị trí xe và ETA. · BR-GPS-01
- AC1. *Then* `GET /gps/live` và `/trips/{id}/positions` chỉ trả cho `dispatcher`; `customer_service`, `sales`, `warehouse`, `viewer`, khách nhận `403`.
- AC2. *Then* không endpoint nào trả GPS dưới dạng tổng hợp theo tài xế (không báo cáo năng suất cá nhân).
- AC3. *Given* bản demo chưa có DPIA, *Then* UI hiện biểu ngữ "chưa có DPIA, chỉ demo".

**US-GPS-03 — Mất tín hiệu và xóa dữ liệu** · 
- AC1. *Given* chuyến `on_road` không có vị trí quá 60 phút, *Then* alert `GPS_LOST` cho dispatcher.
- AC2. *Given* chuyến kết thúc > 30 ngày, *When* `retention_job` chạy, *Then* điểm GPS bị xóa.

---

## Epic 10 — ETA, rủi ro, cảnh báo

**US-RSK-01 — Tính lại ETA đúng lúc** · FR-RSK-01
- AC1. *Given* không có sự kiện/GPS/thay đổi nguồn, *Then* không có dòng `eta_forecast` mới (không tính vô ích).
- AC2. *Given* mốc `GOODS_READY` kế hoạch 11:00 và đến 11:31 chưa có sự kiện, *When* `milestone_overdue_check` chạy, *Then* ETA được tính lại với trigger `overdue_milestone`.
- AC3. *Given* đơn nhiều ngày, *Then* 07:00 mỗi sáng chạy kiểm tra `morning_check`.
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
- AC3. *Given* khách ưa kênh `sms_sim`, *Then* tin được lưu và hiện trong hộp thư mô phỏng; `email` đi qua Mailpit/SMTP.
- AC4. *Given* `shadow_mode = true`, *Then* thông báo ở trạng thái `suppressed` (`suppressed_reason = shadow_mode`).

**US-NOT-02 — Báo trễ do dispatcher gửi** · BR-RSK-02, FR-NOT-02
- AC1. *Given* alert PREDICTED_LATE, *Then* có `notification(status=draft, template=DELAY)` với khung ETA mới đề xuất.
- AC2. *When* dispatcher sửa nội dung/khung giờ và `send`, *Then* `queued → sent`, ghi `NOTIFICATION_SENT`, lưu `eta_window` đã thông báo.
- AC3. *When* dispatcher `discard` không có lý do, *Then* `422`; có lý do → `suppressed`, ghi `NOTIFICATION_SUPPRESSED`.
- AC4. *Given* đã gửi khung 11:00–13:00 và ETA mới lệch < 30 phút, *Then* không tạo bản nháp mới; lệch ≥ 30 phút → tạo bản nháp mới.
- AC5. *Given* người dùng không phải dispatcher, *Then* không thể gửi (`403`).

**US-NOT-03 — Giờ yên lặng và gửi lại** · FR-NOT-03
- AC1. *Given* thông báo `DISPATCHED` tạo lúc 22:30, *Then* `scheduled_for` = 07:00 hôm sau.
- AC2. *Given* thông báo `DELAY` lúc 22:30, *Then* gửi ngay.
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

**US-EMP-04 — Xe và tài xế** · Là *IT*, tôi quản lý hồ sơ xe, bằng lái.
- AC1. *Then* tài xế có hạng bằng và ngày hết hạn; hết hạn trong 30 ngày hiện cảnh báo cho quản lý kho.
- AC2. *Then* xe có tải, thể tích, năng lực, nhóm hàng chở được, kho gốc.

---

## Epic 13 — Chăm sóc khách hàng (bộ phận riêng)

**US-CS-01 — Tra cứu trạng thái** · Là *CSKH*, tôi trả lời khách nhanh.
- AC1. *Then* tìm đơn theo `order_no`, tên khách, điện thoại; xem trạng thái, khung giờ cam kết, ETA hiện tại, lịch sử thông báo.
- AC2. *Then* không thấy GPS, điểm số, quyết định nội bộ, giá vốn; mọi endpoint GPS trả `403`.

**US-CS-02 — Nhật ký liên hệ** · 
- AC1. *When* `POST /orders/{id}/contact-logs` với `channel`, `reason_code`, *Then* lưu kèm nhân viên và giờ; dispatcher xem được.
- AC2. *Then* CS không sửa kế hoạch, không gửi báo trễ (`403`).

---

## Epic 14 — KPI và nhật ký

**US-KPI-01 — Dashboard KPI** · FR-KPI-01
- AC1. *Then* hiện 8 chỉ số kèm baseline và thay đổi so với baseline; có biểu đồ chuỗi theo ngày (ngày tính theo múi giờ market).
- AC2. *Given* đơn FAILED, *Then* không nằm trong mẫu số `on_time_rate`.
- AC3. *Then* "cost per delivery" hiển thị là giờ công và km trung bình mỗi lần giao, không quy ra tiền.
- AC4. *Given* một owner cửa hàng, *Then* thấy doanh thu và số đơn của cửa hàng mình, không thấy của cửa hàng khác.
- AC5. *Given* hai đơn DELIVERED trong kỳ (tổng `line_total` 10.000 và 5.500 SEK), một đơn CANCELLED và một đơn `HANDLED_EXTERNALLY`, *Then* `revenue = "15500.00"`, `delivered_orders = 2`, `currency = SEK`.
- AC6. *Given* Business owner (`viewer`, `can_view_revenue = true`), *Then* `GET /kpi/revenue` trả `200`; *Given* Project Lead (`viewer`, `can_view_revenue = false`), *Then* `403`.

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

**US-ADM-02 — Cấu hình market** · 
- AC1. *When* `PUT /markets/SE/config` với giá trị sai kiểu (ví dụ `delivery_share = 1,5`), *Then* `422` theo `MarketConfig`.
- AC2. *Then* thay đổi cấu hình ghi `decision_log`; kế hoạch đang giữ chỗ không đổi.

**US-ADM-03 — GPS và tuân thủ** · BR-GPS-01
- AC1. *When* admin bật `gps_enabled` mà chưa có DPIA `approved`, *Then* được phép (bản demo) nhưng phản hồi có `warnings: ["DPIA_MISSING"]`, UI hiện biểu ngữ.
- AC2. *Then* ghi `GPS_SETTING_CHANGED`.

---

## Epic 16 — Hệ thống nguồn giả lập (POS)

**US-SRC-01 — Dữ liệu seed hợp lệ** · 
- AC1. *When* chạy seed, *Then* có 3 kho, 25 cửa hàng, ~100 SKU phủ N1–N6, 8–10 xe, ~40 khách (DN và cá nhân), địa chỉ kèm toạ độ, tồn kho và hàng nhập, lịch xe, ~150 nhân viên, ngày lễ Thụy Điển; seed lặp lại cho kết quả giống nhau.
- AC2. *Then* seed có các tình huống cho kịch bản kiểm thử 1–16 (xem `08`).

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
| 3 | US-ORD-01..05 | FR-ORD-01..05, BR-ORD-01..04 |
| 4 | US-ATP-01..03 | FR-ATP-01..03, BR-ATP-01..05 |
| 5 | US-WH-01..05 (US-WH-03 đã bỏ) | FR-PRP-02, FR-PRP-04, FR-PRP-05, FR-EXE-01, BR-PRP-02, BR-PRP-04, BR-PRP-05, BR-EMP-03 |
| 6 | US-PLN-01..08 | FR-PRP-01, FR-DEL-01..04, FR-RNK-01..03, BR-PRP-01, BR-DEL-01..05, BR-GATE-01, BR-RNK-01..05 |
| 7 | US-RES-01, US-APR-01..04 | FR-APR-01..04, FR-ORD-05, BR-RES-01..04, BR-APR-01..03, BR-DEL-05 |
| 8 | US-EXE-01..04 | FR-EXE-01..03, BR-EXE-01..03 |
| 9 | US-GPS-01..03 | FR-GPS-01, BR-GPS-01 |
| 10 | US-RSK-01..03 | FR-RSK-01/02, BR-RSK-01/02 |
| 11 | US-NOT-01..03 | FR-NOT-01..04, BR-NOT-01..03 |
| 12 | US-EMP-01..04 | FR-EMP-01..03, BR-EMP-01..04 |
| 13 | US-CS-01/02 | FR-ORD-04, BR-GPS-01 |
| 14 | US-KPI-01/02, US-LOG-01 | FR-KPI-01/02, FR-LOG-01, BR-KPI-01, BR-GEN-04 |
| 15 | US-ADM-01..03 | FR-ADM-01, BR-GPS-01 |
| 16 | US-SRC-01..03 | FR-INT-01, BR-GEN-02 |
