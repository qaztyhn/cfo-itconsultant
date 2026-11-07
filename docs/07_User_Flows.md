# 07 — User Flows (CFO MVP)

> **Phiên bản 1.2 (06/11/2026):** bỏ `MANUAL_PLANNING`/`HANDLED_EXTERNALLY`; luồng 12a thành **đơn nhiều xe**; thêm luồng 12b **gợi ý lập lại tự động**; tạm dừng/tiếp tục chuẩn bị; giữ chỗ chỉ khóa khi duyệt.
>
> Lịch sử **v1.1:** bỏ thiết bị kho; thêm luồng xử lý ngoài CFO (12a); làm rõ đóng kế hoạch khi lập lại/hủy/xếp lại; khóa đồng thời khi giữ chỗ và duyệt; POD theo từng lần giao.
>
> Luồng người dùng và luồng hệ thống, mô tả bằng bước đánh số và sơ đồ Mermaid. Mỗi luồng có tác nhân, điều kiện đầu, các bước chính, nhánh ngoại lệ, kết quả và màn hình liên quan (`03_UI_UX_Specification.md`), endpoint (`06`), quy tắc (`BR-…` ở `01`). Trạng thái đơn theo `05`. Agent code dùng tài liệu này để dựng điều hướng, kiểm tra thứ tự thao tác và viết test E2E.

## 0. Quy ước

- **Tác nhân:** SALES (POS giả lập), SYS (hệ thống/job), IT, DISP (dispatcher), WH (quản lý/trưởng ca kho), DRV (tài xế), CS (chăm sóc khách hàng), CUS (khách, nhận email/SMS).
- Trạng thái đơn: `SUBMITTED`, `BLOCKED_UNMAPPED_SKU`, `PLANNED`, `NO_FEASIBLE_DATE`, `APPROVED`, `PREPARING`, `GOODS_READY`, `LOADED`, `DISPATCHED`, `DELIVERED`, `FAILED`, `CANCELLED`.
- Mọi nút ghi có `Idempotency-Key`; mọi quyết định ghi `decision_log`.

## 1. Bản đồ tổng thể: từ nhập đơn đến nhận hàng

```mermaid
flowchart LR
  A["SALES nhập đơn tại POS"] --> B["Sales Validation"]
  B --> C["Submit for planning"]
  C --> D["SYS kéo đơn mỗi 5 phút"]
  D --> E{"SKU đã ánh xạ?"}
  E -- "Chưa" --> F["Đơn xử lý theo quy trình cũ; CFO không tạo plan hoặc hold"]
  F --> G["IT ánh xạ SKU cho các đơn tương lai; không tự đưa đơn cũ về CFO"]
  E -- "Rồi" --> H["Engine lập kế hoạch"]
  H --> I{"Có phương án khả thi?"}
  I -- "Có (một hoặc nhiều xe)" --> J["PLANNED: 3 phương án, giữ chỗ 15 phút"]
  I -- "Không" --> K["NO_FEASIBLE_DATE"]
  J --> M["DISP duyệt"]
  K --> N["DISP thương lượng ngày với khách"] --> H
  K --> O["DISP lập kế hoạch tay (một hoặc nhiều xe)"] --> M
  M --> P["APPROVED: cam kết và thông báo CONFIRMED"]
  P --> Q["WH chuẩn bị, ghi mốc"]
  Q --> R["DRV xuất phát và giao"]
  R --> S{"Kết quả"}
  S -- "Giao được" --> T["DELIVERED"]
  S -- "Thất bại" --> U["FAILED: SYS gợi ý phương án mới, DISP duyệt"] --> M
```

## 2. Luồng nhập đơn và kéo về CFO

**Tác nhân:** SALES, SYS · **Màn:** POS giả lập (5.5), Order queue (5.1) · **Quy tắc:** BR-ORD-01..04, FR-INT-02/04

1. SALES mở POS, chọn khách và địa chỉ giao (danh sách seed có toạ độ), chọn **dạng ngày** (Exact/Range/Latest), nhập khung giờ nhận (tùy chọn), yêu cầu đặc biệt, thêm dòng hàng (SKU, số lượng).
2. Bấm **Submit for CFO planning**: POS gọi `validate` (khách, địa chỉ/toạ độ, dòng hàng > 0, dạng ngày hợp lệ, ngày làm việc, khung giờ nằm trong giờ của điểm giao). Lỗi → hiện lỗi từng trường, không nộp. Thành công → `submit` → `SUBMITTED_FOR_PLANNING`.
3. SYS (`ingest_orders`, 5 phút) kéo đơn theo `updated_since`, upsert theo `(market_id, external_ref)`; dòng lỗi vào reject.
4. SYS đánh giá **100% SKU đã mapping confirmed** trước khi đưa đơn vào luồng CFO. Nếu đủ: nạp `customer_order` `SUBMITTED`, chụp địa chỉ/toạ độ, lập kế hoạch (luồng 4). Nếu thiếu: đơn đi theo quy trình cũ; CFO không chạy planning/hold/approve. Không tạo cam kết CFO khi nguồn sở hữu luồng chưa xác minh được.
5. Nếu nguồn sửa đơn **trước khi duyệt**: đơn được cập nhật, `version + 1`, lập kế hoạch lại tự động; **sau khi duyệt**: chỉ tạo alert (luồng 13).

**Nhánh:** Nếu thiếu SKU đã xác nhận, Sales tiếp tục quy trình cũ (không chặn thao tác trên POS), CFO chỉ báo không đủ điều kiện điều phối và **không lập plan/hold**. IT vẫn mapping dần danh mục; đơn đã đi theo quy trình cũ không tự chuyển sang CFO sau mapping.

## 2a. Sales xác nhận tại quầy bằng CFO riêng

1. Sales tạo/submit đơn trong POS cũ, không thay POS. 2. Sales mở CFO, nhập mã đơn nguồn và bấm `Sync now`; CFO GET nguồn qua adapter và upsert đơn. 3. Sales bấm `Check feasibility`; CFO lập phương án mặc định + hold 15 phút. 4. Nếu đủ điều kiện Sales (rank 1, 5 gate pass, safe, một xe, đúng cửa hàng, nguồn mới, không gây chậm đơn cũ), Sales bấm `Confirm`. 5. ApprovalService kiểm tra/khóa/commit nguồn lực, ghi actor và chuyển APPROVED. Chỉ lúc này mới thông báo cam kết cho khách. Nếu không đạt → Retry/Dispatcher. Polling 5 phút vẫn dự phòng; không ghi ngược POS.

```mermaid
flowchart TD
  A[Sales submit đơn tại POS] --> B[Sales mở CFO và Sync now]
  B --> C{Nguồn có đơn, đúng cửa hàng?}
  C -- Không --> X[Retry hoặc chờ polling]
  C -- Có --> C2{100% SKU confirmed và chưa thuộc quy trình cũ?}
  C2 -- Không --> L[Tiếp tục quy trình cũ; CFO không lập plan/hold]
  C2 -- Có --> D[CFO import và lập plan + hold]
  D --> E{Sales đủ điều kiện xác nhận?}
  E -- Không --> F[Chuyển Dispatcher]
  E -- Có --> G[Sales bấm Confirm]
  G --> H{Recheck và commit thành công?}
  H -- Không --> F
  H -- Có --> I[APPROVED và xác nhận khách]
```

## 3. Luồng ánh xạ SKU (IT)

**Tác nhân:** SYS, IT · **Màn:** Product mapping (5.A7) · **Quy tắc:** BR-PRD-01..03

```mermaid
flowchart TD
  A["SKU sản phẩm nguồn chưa được xác nhận"] --> B["Đơn chứa SKU này đi quy trình cũ; không chờ mapping trong CFO"]
  B --> C["Tạo hoặc cập nhật mapping_task"]
  C --> D["Tính ứng viên: GTIN, tên gần giống, nhóm theo quy tắc"]
  D --> E["IT mở task"]
  E --> F{"Có ứng viên đúng?"}
  F -- "Có" --> G["Approve ứng viên"]
  F -- "Không" --> H["Choose other hoặc Create global product"]
  F -- "SKU không dùng" --> R["Reject, bắt buộc lý do"]
  H --> I["Nhập nhóm N1-N6, đơn vị chuẩn bị, quy đổi, cờ"]
  G --> J["Xác nhận ánh xạ"]
  I --> J
  J --> K["Các đơn mới đủ mapping sẽ được CFO tiếp nhận"]
  K --> L["Đơn đã đi theo quy trình cũ không tự chuyển vào CFO"]
```

**Chi tiết:** (1) IT xem SKU chưa mapping và ứng viên; (2) tạo global mới với nhóm xử lý, `base_unit`, cân nặng/thể tích, đơn vị quy đổi và cờ; (3) xác nhận → `MAPPING_CONFIRMED` và SKU đủ điều kiện cho **các đơn mới**; (4) từ chối → lưu lý do tại task/audit. **Đơn đã chuyển sang quy trình cũ không được tự mở khóa, tự tạo plan/hold hay chuyển về CFO.**

## 4. Luồng lập kế hoạch (hệ thống)

**Tác nhân:** SYS · **Quy tắc:** BR-ATP, BR-PRP, BR-DEL, BR-GATE, BR-RNK, BR-RES

```mermaid
flowchart TD
  A["Đơn SUBMITTED"] --> B["Tiền kiểm: đủ ánh xạ"]
  B --> C["Tính khối lượng việc giống nhau mọi kho"]
  C --> D["Với mỗi kho: ATP theo ngày"]
  D -- "Không đủ 14 ngày" --> X1["Loại: STOCK_SHORT"]
  D --> E["Xếp việc theo công suất giờ công"]
  E -- "Thiếu công suất" --> X2["Loại: PREP_NO_CAPACITY"]
  E --> F["Giờ cắt: dời lên hàng ca sau nếu quá"]
  F --> G["Chọn bộ xe ít nhất và tài xế hợp lệ"]
  G -- "Không có" --> X3["Loại: NO_TRUCK_FIT, TRUCK_BUSY, NO_DRIVER"]
  G --> H["Ngày giao theo dạng ngày, cửa sổ nhận hàng"]
  H -- "Ngoài cửa sổ hoặc ngày" --> X4["Loại: OUTSIDE_RECEIVING_HOURS, DATE_AFTER_DEADLINE"]
  H --> I["Gate an toàn: tải, giờ lái, bằng lái"]
  I -- "Vi phạm" --> X5["Loại: OVER_LOAD, DRIVER_HOURS_EXCEEDED, LICENCE_EXPIRED"]
  I --> J["Ứng viên khả thi"]
  J --> K["Xếp hạng min-max 0.5 km + 0.5 mức đầy"]
  K --> L["Top 3 (ít xe trước), giải thích, giữ chỗ 15 phút (không khóa, cho phép vượt)"]
  L --> P["Đơn PLANNED"]
  X1 --> Z{"Còn ứng viên?"}
  X2 --> Z
  X3 --> Z
  X4 --> Z
  X5 --> Z
  Z -- "Không" --> N["Tìm ngày sớm nhất tối đa 14 ngày, gợi ý chuyển kho"]
  N --> Q["Đơn NO_FEASIBLE_DATE"]
```

## 5. Luồng duyệt kế hoạch (Dispatcher đầy đủ; Sales nhánh tiêu chuẩn mục 2a)

**Tác nhân:** DISP · **Màn:** Plan review (5.2) · **Quy tắc:** BR-APR, BR-RES

```mermaid
sequenceDiagram
  participant D as Dispatcher
  participant UI as Web
  participant API as CFO API
  participant DB as PostgreSQL
  D->>UI: Mở đơn PLANNED
  UI->>API: GET planning-run
  API-->>UI: 3 phương án, hold_expires_at
  D->>UI: Xem checks, lý do loại, bản đồ
  alt Duyệt phương án 1
    D->>UI: Approve
  else Chọn phương án khác
    D->>UI: Select plan 2 hoặc 3 và nhập lý do
  else Đổi tiêu chí
    D->>UI: Rerun với loại kho hoặc đổi trọng số và lý do
    UI->>API: POST plan
    API-->>UI: Run mới, giữ chỗ cũ released
  else Lập tay
    D->>UI: Plan manually và mã lý do
  end
  UI->>API: POST approve với Idempotency-Key
  API->>DB: BEGIN, advisory lock kho → sản phẩm → ngày, rồi khóa mọi xe → mọi tài xế (chỉ khóa khi duyệt)
  API->>API: Kiểm tra lại bằng engine
  alt Còn hợp lệ
    API->>DB: Giữ chỗ thành committed, tạo trip, đơn APPROVED
    API->>DB: decision_log, eta v1, thông báo CONFIRMED
    API-->>UI: 200 đã duyệt
  else Đã bị chiếm
    API->>DB: ROLLBACK
    API-->>UI: 409 RESOURCE_CONFLICT
    UI-->>D: Toast và nút Re-run plan
  end
```

**Chi tiết bổ sung**
1. Nếu `reserve_class = tight`: bắt buộc tick "I accept the tight schedule" trước khi Approve.
2. Hold hết hạn: chip đỏ nhạt; Approve vẫn thử (kiểm tra lại); nút **Extend** tối đa 2 lần mỗi lần 15 phút.
3. Duyệt phương án rank > 1: modal lý do bắt buộc (`ALT_SELECTED`).
4. Ngày cam kết khác ngày khách đã đồng ý: cần chọn bản ghi `date_negotiation.agreed`.
5. **Kết quả:** đơn `APPROVED`, `committed_date`, `promise_start/end`, `delivery_trip` + `trip_stop`, email/SMS `CONFIRMED`, các hold khác `released`.

## 6. Luồng không có ngày khả thi và thương lượng ngày

**Tác nhân:** DISP, CS (liên hệ nếu được giao), CUS · **Màn:** No feasible date (5.3) · **Quy tắc:** BR-RNK-04/05

```mermaid
flowchart TD
  A["Đơn NO_FEASIBLE_DATE"] --> B["Xem check hỏng theo kho và ngày sớm nhất"]
  B --> C{"Do thiếu hàng?"}
  C -- "Có" --> D["Xem gợi ý chuyển kho"]
  D --> E["DISP duyệt chuyển kho"]
  E --> F["Kho nguồn xác nhận"]
  F --> G["Hàng nhập xác nhận ETA"] --> H
  C -- "Không" --> H["DISP liên hệ khách đề xuất ngày mới"]
  H --> I{"Kết quả"}
  I -- "Khách đồng ý" --> J["Ghi date_negotiation agreed"]
  J --> K["Cập nhật ngày yêu cầu, version +1, chạy lại kế hoạch"]
  I -- "Từ chối" --> L["Ghi declined, hủy đơn có lý do hoặc thử ngày khác"]
  I -- "Không liên lạc được" --> M["Ghi unreachable, nhắc sau 24 giờ"]
  M --> H
  K --> N["Về luồng 4 và 5"]
```

**Quy tắc cứng:** hệ thống **không bao giờ** tự đổi ngày yêu cầu; chỉ khi có bản ghi `agreed` (người, kênh, giờ) mới đổi. **Chuyển kho:** `suggested → approved (DISP) → source_confirmed (quản lý kho nguồn) → received (kho đích)`; sau `source_confirmed` hàng được tính như hàng nhập đã xác nhận; kho đích vẫn xử lý trọn đơn.

## 7. Luồng khai báo năng lực kho hằng ngày

**Tác nhân:** WH, SYS · **Màn:** Attendance & shifts (5.A5), Prep queue (5.6) · **Quy tắc:** BR-PRP-02/03/05, BR-EMP

1. SYS sinh điểm danh `planned` cho 14 ngày tới từ ca mẫu của kho.
2. Đầu ca, WH mở **Attendance & shifts** cho hôm nay → bấm **All present**, rồi đánh dấu người vắng/nghỉ → công suất ngày tự tính lại (số có mặt × giờ hữu ích × 90%).
3. Khi ca thực tế khác kế hoạch: WH ghi `SHIFT_CHANGE` (số người, ghi chú). SYS tính lại ETA các đơn có giữ chỗ ngày đó và báo DISP nếu có rủi ro.
4. Thay đổi nhân sự dài hạn do IT xử lý (chuyển công tác, thôi việc); công nhân kho **không có tài khoản**.

## 8. Luồng chuẩn bị hàng và bốc xếp (kho)

**Tác nhân:** WH, SYS · **Màn:** Prep queue (5.6) · **Quy tắc:** BR-EXE-01, FR-EXE-01

```mermaid
flowchart TD
  A["Đơn APPROVED trong hàng đợi"] --> B["WH bấm Start prep"]
  B --> C["Sự kiện START_PREP (crew_size), đơn PREPARING"]
  C --> P1["WH bấm Pause khi dừng giữa chừng"] --> P2["WH bấm Resume (crew_size)"] --> C
  C --> D["WH bấm Goods ready"]
  D --> E["Sự kiện GOODS_READY"]
  E --> F["WH bấm Mark loaded cho từng xe"]
  F --> G["Mọi xe đã LOADED → đơn LOADED"]
  C -.-> X["Ngoại lệ: Shortage, Breakage, Vehicle issue, Shift change"]
  D -.-> X
  X --> Y["Alert cho DISP, tính lại ETA"]
  B --> H["Mỗi mốc: tính lại ETA ngay, ghi eta_forecast"]
  D --> H
  F --> H
```

**Quy tắc:** không có bước duyệt; `START_PREP` và `PREP_RESUMED` bắt buộc nhập số người làm (`crew_size`); `PREP_PAUSED` khi dừng giữa chừng (đơn vẫn `PREPARING`); khi `GOODS_READY`, hệ thống cộng các đoạn làm việc thành giờ nhân công thực tế, chia theo nhóm hàng và đơn vị cơ sở để làm dữ liệu cho AI; mỗi sự kiện nhận `occurred_at` (mặc định giờ bấm, sửa được bằng popover "Happened at"); sai thứ tự → lỗi `ILLEGAL_TRANSITION`; `SHORTAGE` không tự sửa tồn kho (chỉ cảnh báo); `VEHICLE_ISSUE` gắn cờ xe để DISP cân nhắc lập lại.

## 9. Luồng giao hàng của tài xế (PWA) và GPS

**Tác nhân:** DRV, SYS, DISP · **Màn:** Driver (5.10), Tracking (5.4) · **Quy tắc:** BR-EXE, BR-GPS-01

```mermaid
sequenceDiagram
  participant T as Tài xế (PWA)
  participant Q as Hàng đợi offline
  participant API as CFO API
  participant D as Dispatcher
  T->>API: Mở app, tải chuyến hôm nay
  API-->>T: Chuyến, điểm dừng, cửa sổ nhận hàng
  T->>T: Hộp xin quyền vị trí và thông báo riêng tư
  T->>API: DISPATCHED (Idempotency-Key)
  API-->>T: Chuyến on_road, thông báo DISPATCHED cho khách
  loop Mỗi 30 phút khi on_road
    T->>API: POST positions
    API-->>D: Vị trí mới, ETA tính lại
  end
  Note over T,Q: Mất mạng: sự kiện vào IndexedDB với occurred_at là giờ chạm
  T->>Q: DELIVERED hoặc FAILED
  Q->>API: Gửi lại khi có mạng, trùng key không tạo bản sao
  API-->>T: Đơn DELIVERED hoặc FAILED
```

**Chi tiết**
1. Trước khi gửi GPS lần đầu: thông báo "gửi vị trí cho dispatcher mỗi 30 phút, khách không thấy, xóa sau 30 ngày" và xin quyền vị trí. Từ chối → app vẫn dùng được cho các mốc (không có GPS), dispatcher thấy "Location off".
2. `DELIVERED`: bắt buộc **Received by**; ghi chú tùy chọn. Mỗi lần giao (mỗi `trip_stop`) có một bản ghi POD riêng. `FAILED`: bắt buộc **Failure reason** (customer absent, site inaccessible, refused, wrong address, vehicle breakdown, goods damaged, other).
3. Khi `gps_enabled = false` hoặc chưa `on_road`, API từ chối vị trí; app im lặng thôi gửi.
4. Mất tín hiệu > 60 phút: SYS tạo alert `GPS_LOST` cho DISP.
5. Khi demo, `tools/gps_simulator.py` gửi vị trí dọc tuyến mỗi 1–2 phút với `source=simulator`.

## 10. Luồng theo dõi rủi ro và báo trễ cho khách

**Tác nhân:** SYS, DISP, CUS · **Màn:** Order queue, Tracking (5.1, 5.4), Notification inbox (5.8) · **Quy tắc:** BR-RSK-01/02, BR-NOT-02

```mermaid
flowchart TD
  A["Có tín hiệu: sự kiện, GPS, thay đổi nguồn, mốc quá hạn 30 phút, 07:00 sáng"] --> B["Tính forecast_eta"]
  B --> C["Ghi eta_forecast phiên bản mới"]
  C --> D{"Tiêu hao dự trữ"}
  D -- "dưới 33 phần trăm" --> G["ON_TRACK xanh"]
  D -- "33 đến 66" --> Y["AT_RISK vàng, chỉ đổi màu"]
  D -- "trên 66 hoặc slack âm lần đầu" --> O["AT_RISK cam, alert cho DISP"]
  D -- "slack âm hai lần liên tiếp" --> R["PREDICTED_LATE đỏ, alert critical"]
  R --> N["Tạo bản nháp thông báo DELAY"]
  N --> P["DISP xem nháp"]
  P --> Q{"Quyết định"}
  Q -- "Gửi, có thể sửa khung ETA" --> S["NOTIFICATION_SENT, khách nhận email hoặc SMS"]
  Q -- "Bỏ, nhập lý do" --> T["NOTIFICATION_SUPPRESSED"]
  Q -- "Lập lại kế hoạch" --> U["Luồng 12"]
  A --> V{"now sau promise_end và chưa giao"}
  V -- "Có" --> W["OVERDUE đỏ đậm"]
```

**Quy tắc:** chỉ DISP gửi báo trễ; sau khi gửi, bản nháp mới chỉ xuất hiện khi `forecast_eta` lệch ≥ 30 phút so với khung đã thông báo; không tính lại khi không có tín hiệu; khách chỉ nhận trạng thái và ETA.

## 11. Vòng đời thông báo

```mermaid
flowchart LR
  A["Sự kiện nghiệp vụ"] --> B{"Mẫu"}
  B -- "CONFIRMED, DISPATCHED, DELIVERED, FAILED" --> C["Tạo notification queued"]
  B -- "DELAY" --> D["Tạo notification draft"] --> E["DISP gửi hoặc bỏ"] --> C
  C --> F{"shadow_mode?"}
  F -- "Bật" --> S["suppressed: shadow_mode"]
  F -- "Tắt" --> G{"Giờ yên lặng 21-07 và không phải DELAY?"}
  G -- "Có" --> H["scheduled_for = 07:00"] --> I
  G -- "Không" --> I["Worker gửi: email qua SMTP hoặc sms_sim"]
  I --> J{"Thành công?"}
  J -- "Có" --> K["sent"]
  J -- "Không" --> L["Thử lại tối đa 3 lần rồi failed"]
```

Mỗi thông báo có `dedupe_key` theo (đơn, mẫu, trạng thái). Nội dung dựng từ mẫu ở `03` mục 6; người nhận hiển thị đã che.

## 12. Luồng giao thất bại và lập lại

**Tác nhân:** DRV, SYS, DISP · **Quy tắc:** BR-EXE-02

1. DRV ghi `FAILED` + lý do chuẩn; chuyến `completed`; đơn `FAILED` khi mọi chuyến của đơn đã kết thúc và có xe thất bại; thông báo `FAILED` cho khách; alert cho DISP; **SYS gợi ý phương án mới** (luồng 12b).
2. DISP liên hệ khách (CS có thể hỗ trợ và ghi nhật ký), rồi duyệt phương án gợi ý, hoặc bấm **Replan this order** (lý do bắt buộc). Trong **một transaction**: kế hoạch cũ → `superseded`, giữ chỗ còn lại → `released`, ngày cam kết xóa (ghi vào nhật ký) → đơn `SUBMITTED` → luồng 4. POD của lần giao thất bại được giữ nguyên; lần giao sau có POD riêng.
3. Đơn FAILED không nằm trong mẫu số "đúng hạn", được đếm ở "tỷ lệ giao thất bại".
4. Lập lại một đơn **đã duyệt** vì thay đổi lớn (xe hỏng, khách đổi): cùng thao tác; kế hoạch cũ → `superseded`, giữ chỗ `committed` → `released`, `trip_stop`/`delivery_trip` → `cancelled` trước khi chạy lại. Khi duyệt kế hoạch mới, khách nhận `CONFIRMED` mới với ngày mới.
5. Hủy đơn (trước `DISPATCHED`) đóng kế hoạch, giữ chỗ, chuyến giống bước 4; đơn → `CANCELLED`.

## 12a. Luồng đơn lớn hơn một xe (nhiều xe, một kho)

**Tác nhân:** SYS, DISP, WH, DRV · **Màn:** Plan review (5.2), Prep queue (5.6), Driver (5.10) · **Quy tắc:** FR-ORD-05, BR-DEL-05, BR-RNK-02

```mermaid
flowchart TD
  A["Đơn vượt tải một xe"] --> B["Mỗi kho: tìm bộ xe rảnh cùng ngày, đủ kg và m³, đủ năng lực"]
  B --> C["Ít xe nhất trước; cùng số xe thì tổng tải nhỏ hơn"]
  C --> D["Chia hàng theo tải và thể tích (một dòng có thể tách)"]
  D --> E["Mỗi xe một tài xế; xếp giờ để mọi xe tới trong cửa sổ, chênh ≤ 30 phút"]
  E --> F["Phương án hiện số xe, loại xe, phần hàng từng xe"]
  F --> G["DISP duyệt: giữ mọi xe trong một transaction"]
  G --> H["Mỗi xe một chuyến: WH Mark loaded từng xe; DRV giao từng xe"]
  H --> I{"Mọi xe giao xong?"}
  I -- "Có" --> J["DELIVERED, một thông báo"]
  I -- "Có xe thất bại" --> K["FAILED, ghi phần đã giao, gợi ý lập lại"]
  B -- "Thiếu loại xe hoặc kín xe ở mọi kho" --> L["NO_FEASIBLE_DATE, check truck"]
```

Không ghép đơn: một xe chỉ chở một đơn trong một chuyến. Không giới hạn số xe (chỉ bị giới hạn bởi xe và tài xế rảnh). Thông báo: một `CONFIRMED`, `DISPATCHED` khi xe đầu tiên xuất phát, `DELIVERED` khi xe cuối giao xong.

## 12b. Luồng gợi ý lập lại tự động

**Tác nhân:** SYS, DISP · **Màn:** Order queue (alert), Plan review (5.2) · **Quy tắc:** FR-APR-05, BR-APR-04

```mermaid
flowchart TD
  A["Đơn đã duyệt + tín hiệu: nguồn sửa đơn, PLAN_INVALIDATED, VEHICLE_ISSUE, giao FAILED"] --> B["SYS chạy replan_suggestion"]
  B --> C["Coi kế hoạch hiện tại của chính đơn như không tồn tại: cộng lại hàng, giờ công, xe, tài xế"]
  C --> D["Không tạo giữ chỗ; alert REPLAN_SUGGESTED cho DISP"]
  D --> E{"DISP quyết định"}
  E -- "Duyệt phương án gợi ý" --> F["Một transaction: đóng kế hoạch cũ, khóa, kiểm tra lại, commit kế hoạch mới, APPROVED, CONFIRMED mới"]
  F -- "Tài nguyên đã bị chiếm" --> G["409 RESOURCE_CONFLICT, không đổi gì"]
  E -- "Giữ kế hoạch cũ (lý do)" --> H["REPLAN_KEPT, đóng alert"]
  E -- "Lập lại tay" --> I["Replan this order hoặc Plan manually"]
```

Không bao giờ tự duyệt. Đơn đã `DISPATCHED` chỉ nhận alert.

## 13. Luồng đơn thay đổi sau khi duyệt

1. SYS nhận phiên bản mới của đơn đã `APPROVED` từ nguồn (sửa số lượng, ngày, địa chỉ, hủy).
2. SYS **không ghi đè**; tạo alert `ORDER_CHANGED_AFTER_APPROVAL` kèm khác biệt và **tự gợi ý phương án mới** theo bản mới (luồng 12b).
3. DISP xem khác biệt và chọn: **duyệt phương án gợi ý**, **Keep current plan** (ghi lý do, đóng alert) hoặc **Cancel** (nếu nguồn hủy).
4. Đơn đã `DISPATCHED`: chỉ alert, không đổi trạng thái; DISP xử lý ngoài hệ thống.

## 14. Luồng đồng bộ dữ liệu và dữ liệu cũ

**Tác nhân:** SYS, IT · **Màn:** Data integration (5.9)

```mermaid
flowchart TD
  A["Tick 5 phút"] --> B["Mỗi entity: đọc checkpoint trừ 2 phút"]
  B --> C["Gọi API nguồn theo trang"]
  C --> D{"Lỗi từng dòng?"}
  D -- "Có" --> E["sync_reject, tiếp tục"]
  D -- "Không" --> F["Upsert theo khóa tự nhiên"]
  E --> F
  F --> G{"Cả lượt thành công?"}
  G -- "Có" --> H["Ghi checkpoint, sync_run ok hoặc partial"]
  G -- "Không" --> I["sync_run failed, giữ checkpoint, alert SYNC_FAILED cho IT"]
  H --> J["Đơn đã duyệt bị ảnh hưởng? tính lại ETA"]
  H --> K{"as_of tồn kho quá 15 phút?"}
  K -- "Có" --> L["Cờ vàng ở màn lập kế hoạch, alert STALE_DATA"]
```

IT xem lượt chạy, dòng bị loại và có thể chạy tay (`/sync/{entity}/run`); **Upload CSV (fallback)** đi qua `CsvMarketAdapter` với kiểm tra hash để tránh nạp trùng.

## 15. Luồng CSKH tra cứu và ghi liên hệ

**Tác nhân:** CS · **Màn:** Order lookup (5.A14)

1. Khách gọi; CS tìm theo mã đơn, tên khách hoặc điện thoại.
2. CS xem trạng thái, khung giờ cam kết, ETA hiện tại, lịch sử thông báo (không GPS, không điểm số).
3. CS trả lời khách; ghi **Log a contact** (kênh, lý do, ghi chú).
4. Nếu khách yêu cầu đổi ngày hoặc có khiếu nại cần quyết định: CS chuyển cho DISP (ghi chú trong nhật ký liên hệ); CS **không** sửa kế hoạch, không gửi báo trễ.

## 16. Luồng thêm nước mới (IT)

1. IT chạy `tools/add_market.py <CC>` → dòng `ref.market`, bảng `ref.product_<cc>`, cập nhật view `ref.v_product_local`.
2. Cấu hình `MarketConfig` (ngày làm việc, giờ nhận hàng, giờ cắt, ngày lễ, ngôn ngữ, múi giờ, tiền tệ) trong màn Market config; `shadow_mode = true`.
3. Cấu hình `source_base_url` và khóa; nếu hệ thống nguồn không theo hợp đồng chuẩn thì viết lớp con của `RestMarketAdapter`.
4. Chạy đồng bộ sản phẩm → hàng đợi mapping → IT ánh xạ.
5. Chạy bóng (`shadow_mode`): dispatcher vẫn quyết định; không gửi thông báo cho khách; đo baseline và KPI.
6. Go-live: tắt `shadow_mode`, huấn luyện, dispatcher giữ quyền duyệt cuối; chỉ sang nước tiếp theo khi KPI đạt và quyền truy cập dữ liệu được xác nhận. Không sửa lõi ở bất kỳ bước nào.

## 17. Sơ đồ trạng thái đơn hàng

```mermaid
stateDiagram-v2
  [*] --> SUBMITTED
  %% ASM-005: phân luồng SKU phải diễn ra trước khi CFO tiếp nhận/lập plan.
  %% BLOCKED_UNMAPPED_SKU còn trong enum legacy, không dùng để giữ đơn mới chờ mapping.
  SUBMITTED --> BLOCKED_UNMAPPED_SKU: legacy only (chờ migration/chốt thiết kế)
  BLOCKED_UNMAPPED_SKU --> SUBMITTED: legacy only (không tự thực thi cho đơn xử lý cũ)
  SUBMITTED --> PLANNED: có phương án khả thi
  SUBMITTED --> NO_FEASIBLE_DATE: không khả thi
  PLANNED --> APPROVED: dispatcher duyệt
  PLANNED --> SUBMITTED: đổi tiêu chí và chạy lại
  NO_FEASIBLE_DATE --> SUBMITTED: khách đồng ý ngày mới
  NO_FEASIBLE_DATE --> APPROVED: kế hoạch tay
  APPROVED --> PREPARING: START_PREP
  PREPARING --> GOODS_READY: GOODS_READY
  GOODS_READY --> LOADED: LOADED
  LOADED --> DISPATCHED: DISPATCHED
  DISPATCHED --> DELIVERED: DELIVERED
  DISPATCHED --> FAILED: FAILED
  FAILED --> SUBMITTED: xếp lại
  FAILED --> APPROVED: duyệt gợi ý lập lại
  PREPARING --> APPROVED: duyệt gợi ý lập lại
  GOODS_READY --> APPROVED: duyệt gợi ý lập lại
  LOADED --> APPROVED: duyệt gợi ý lập lại
  APPROVED --> SUBMITTED: lập lại
  PLANNED --> CANCELLED
  NO_FEASIBLE_DATE --> CANCELLED
  APPROVED --> CANCELLED
  PREPARING --> CANCELLED
  GOODS_READY --> CANCELLED
  LOADED --> CANCELLED
  DELIVERED --> [*]
  CANCELLED --> [*]
```

## 18. Ma trận điều hướng theo vai trò (điểm vào mặc định và bước tiếp)

| Vai trò | Sau đăng nhập | Việc thường gặp nhất | Bước tiếp thường dẫn đến |
|---|---|---|---|
| Dispatcher | Order queue | Mở đơn `PLANNED` → Plan review → Approve | Tracking & risk khi có cảnh báo; Exceptions khi có đơn không khả thi |
| Warehouse | Prep queue | Điểm danh → bấm mốc chuẩn bị → báo ngoại lệ | Attendance & shifts, Transfers |
| Driver | Today's trips | Mark dispatched → Delivered/Failed | — |
| Sales | My store orders / Sync & confirm trong CFO | Submit ở POS cũ, sync-now, check feasibility, confirm nếu đủ điều kiện | Thành công → APPROVED; ngoại lệ → Dispatcher |
| Store manager | My store orders | Theo dõi đơn; xem doanh thu cửa hàng mình nếu là owner | Revenue · my location |
| Customer service | Order lookup | Tra cứu, ghi liên hệ | — |
| IT/Admin | Data integration | Xử lý hàng đợi mapping, đồng bộ lỗi, nhân sự | Product mapping, Market config & GPS |
| Business owner (`revenue_all`) | Revenue | Xem doanh thu mọi cửa hàng và kho, xuất CSV | — |
| Project lead (`ops`) | KPIs & decision log | Xem KPI vận hành và nhật ký | — |

## 19. Tình huống ngoại lệ thường gặp và cách hệ thống phản ứng

| Tình huống | Phản ứng |
|---|---|
| Hai dispatcher duyệt cùng lúc hai đơn tranh một xe | Một thành công; người còn lại nhận `409 RESOURCE_CONFLICT` và nút Re-run plan |
| Hai đơn cùng tranh một lượng hàng (cùng kho, cùng SKU) hoặc cùng giờ công một ngày | Lúc lập kế hoạch cả hai được giữ chỗ (cho phép vượt); khi duyệt khóa theo (kho, sản phẩm) / (kho, ngày): đơn duyệt trước thắng, đơn sau nhận `409 RESOURCE_CONFLICT` |
| Đơn lớn hơn một xe | Tự xếp nhiều xe cùng kho, ít xe nhất (luồng 12a) |
| Thiếu loại xe cần (cẩu, ben) hoặc kín xe | `NO_FEASIBLE_DATE` (check `truck`); DISP thương lượng ngày, lập tay hoặc hủy |
| Hold hết hạn trong lúc dispatcher đang xem | Chip đỏ; Approve vẫn kiểm tra lại và thành công nếu tài nguyên còn trống |
| Tồn kho nguồn đổi sau khi duyệt | Kiểm tra lại các đơn đã duyệt bị ảnh hưởng; nếu kế hoạch không còn hợp lệ → alert `PLAN_INVALIDATED` + gợi ý phương án mới (luồng 12b) |
| Xe hỏng sau khi duyệt | `VEHICLE_ISSUE` → alert + gợi ý phương án mới (luồng 12b) |
| Tài xế mất mạng | Sự kiện xếp hàng, gửi lại một lần |
| ORS lỗi hoặc hết quota | Dùng ước lượng fallback có nhãn "Estimated route" (hoặc loại cặp nếu `routing.allow_fallback = false`) |
| Nguồn lỗi | `sync_run failed`, giữ checkpoint, alert IT; dispatcher thấy cờ dữ liệu cũ sau 15 phút |
| SMTP lỗi | Thử lại 3 lần rồi `failed`; DISP thấy trạng thái trong Notification inbox |
| Khách không liên lạc được khi thương lượng ngày | `unreachable`, nhắc sau 24 giờ |
