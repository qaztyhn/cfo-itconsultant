# DEC-R3 — Round 3: cắt giảm 30% ngân sách, track CRM, quyền Sales trong phạm vi (2026-11-18)

> **Người duyệt:** Chủ dự án, phiên làm việc 2026-11-18 (trả lời từng câu hỏi Q1–Q9 và các quyết định cắt giảm).
> **Hiệu lực:** ràng buộc nghiệp vụ cho Round 3, **thay thế** các quyết định cũ được liệt kê ở §3.
> **Không có nghĩa** code, migration hay kiểm thử đã hoàn thành. Hợp đồng `05`/`06` được đồng bộ ở PR riêng (task T01);
> mọi task triển khai phải theo hợp đồng đó.
>
> Nguồn: các câu hỏi Q1–Q9 và quyết định cắt giảm trong phiên làm việc 18/11/2026. Bản đề xuất ban đầu đã bị xóa vì lỗi thời.

## 1. Bối cảnh

Đề Round 3: thay Microsoft Dynamics 365 bằng CRM mới, đồng thời ngân sách giảm 30%, giữ nguyên khung 6 tuần. Đây là
**ngân sách dự án thật của client** (giả định của bài thi); MVP trong repo là bản mô phỏng để trình bày, phần bị cắt
được **ẩn/tắt bằng cờ**, không xóa code hay bảng.

## 2. Quyết định

| ID | Quyết định | Quy tắc chính xác |
|---|---|---|
| **DEC-R3-01** Vị trí & ETA *(sửa 18/11 lần 2)* | Hoãn GPS thu liên tục và hàng đợi offline IndexedDB; **vị trí do tài xế chủ động gửi**, có bản đồ cho Dispatcher | Tài xế bấm **Cập nhật vị trí** khi đang chạy; gửi kèm vị trí khi **báo sự cố**; **bắt buộc** gửi vị trí khi báo `DELIVERED`/`FAILED` (tối thiểu 1 lần/chuyến) — không lấy được vị trí thì **không** xác nhận được. Không thu theo chu kỳ. ETA tính lại từ vị trí mới (thời gian tuyến còn lại tới điểm giao + dỡ hàng). Báo sự cố: lý do `vehicle_breakdown` \| `traffic_or_accident` \| `site_inaccessible` \| `other` (ghi chú); luôn cảnh báo Dispatcher; có vị trí thì tính lại ETA; hỏng xe → ETA không xác định, đơn có rủi ro, Dispatcher quyết định (không tự lập lại). Quá ETA 30 phút (hoặc mốc kho quá 30 phút) mà không có sự kiện → cảnh báo `OVERDUE` cho Dispatcher, không tự tính lại ETA. **Quyền xem:** chỉ Dispatcher **được gán chuyến** xem tọa độ trên **bản đồ** (Leaflet + OSM) khi chuyến đang `on_road`; khách, CS, Sales không bao giờ. **Lưu trữ:** tọa độ lưu trong `ops.vehicle_position`, xóa sau tối đa 7 ngày; chuyến kết thúc thì Dispatcher mất quyền xem; lịch sử chỉ reviewer quyền riêng tư theo case (quy tắc D3/DEC-GPS-RET giữ nguyên). Cách gán Dispatcher cho chuyến: **chờ chốt**; chưa gán = không ai xem. Dùng với tài xế thật cần DPIA và tham vấn nhân viên trước. Driver PWA chạy online, retry bằng cùng `Idempotency-Key`. |
| **DEC-R3-02** Thông báo | Bỏ SMS; chỉ email | Email `CONFIRMED`, `DISPATCHED` (khi xe đầu tiên rời kho, một lần/đơn), `DELIVERED`, `FAILED`, `DELAY`. `DELAY` chỉ phát sau khi Dispatcher gửi. **`FAILED` luôn giữ.** `DISPATCHED` là mục đầu tiên của thang cắt (cờ `NOTIFY_DISPATCHED_ENABLED`). Khách không có email → `SKIPPED_NO_CHANNEL`, không log PII. |
| **DEC-R3-03** KPI | 10 KPI → 5 KPI | (1) **Thời gian lập kế hoạch/đơn**: thời gian người xử lý thao tác, so baseline thủ công từ shadow pilot, ↓, báo cáo tách theo đường duyệt `sales`/`dispatcher`; chỉ số phụ `order_to_commit_min` = từ lúc đơn vào CFO đến `CONFIRMED`, tách theo đường. (2) **Giao đúng hạn**: % đơn giao trong cửa sổ đã hứa, ↑. (3) **Tỷ lệ chấp nhận phương án**: % rank-1 được duyệt không sửa, bởi Dispatcher hoặc Sales, ↑, tính cả hai đường nhưng **báo cáo tách theo đường**; chỉ số phụ `counter_commit_rate` = % đơn cam kết ngay tại quầy. (4) **Can thiệp thủ công/đơn**: % đơn phải lập tay hoặc override (gồm số kế hoạch lập tay), ↓. (5) **Sai số ETA**: phút chênh giữa ETA dự báo và giờ POD thực tế, median và P90, ↓; **chỉ số tuyệt đối có mục tiêu, không baseline**. |
| **DEC-R3-04** Quy mô pilot | 3 kho → 2 kho; 20–30 cửa hàng → 10 | ~100 SKU giữ nguyên. |
| **DEC-R3-05** CS | Bỏ contact log của CS | CS Order Lookup chỉ đọc, che dữ liệu, giữ nguyên. Không còn endpoint ghi liên hệ; bảng giữ, không drop. |
| **DEC-R3-06** Công suất kho | Chỉ ghi công suất theo ngày/ca | Warehouse Manager nhập và xác nhận cho mỗi (kho, ngày, ca): số người làm, số giờ làm hữu ích. Công suất ngày = Σ ca (số người × số giờ × hệ số sử dụng hiện hành của market, mặc định 90%) − việc đã cam kết. **Không có dòng đã xác nhận = 0 công suất (fail-closed).** Bỏ lịch ca từng nhân viên, điểm danh, sinh điểm danh. |
| **DEC-R3-07** Tài xế | Đội quản lý tài xế cung cấp dữ liệu đã xác minh | Đội quản lý tài xế cung cấp lịch khả dụng theo ngày và danh sách xe/loại xe mỗi tài xế được phép lái, **sau khi đã xác minh bằng lái và giờ lái/nghỉ**. CFO chỉ dùng dữ liệu đã xác nhận (có người/nguồn xác nhận, còn hạn) để lập kế hoạch; thiếu hoặc hết hạn → tài xế không đủ điều kiện (fail-closed). CFO **không** tự tính lịch sử lái/nghỉ 56 ngày. |
| **DEC-R3-08** Thời gian chuẩn bị | `prep_time = GOODS_READY − START_PREP` | Bỏ `PREP_PAUSED`/`PREP_RESUMED` và tính theo đoạn. Thứ tự mốc bắt buộc START_PREP → GOODS_READY → LOADED. |
| **DEC-R3-09** Thất bại & sự cố | CFO dừng ở cảnh báo | Bỏ tự chạy planner/tạo gợi ý khi đơn `FAILED` **và** khi báo sự cố xe. Tài xế báo `FAILED` cho chuyến của mình kèm lý do; CFO lưu kết quả chuyến. Đơn nhiều xe chuyển `FAILED` khi **mọi chuyến đã kết thúc và có ít nhất một chuyến thất bại**. CFO gửi cảnh báo nội bộ cho Dispatcher kèm lý do và kết quả từng chuyến. Dispatcher chọn: hẹn giao lại, yêu cầu CFO chạy planner lại (đơn giao một phần → **chỉ lập cho phần hàng chưa giao**), hoặc hủy có lý do. |
| **DEC-R3-10** Quyền Sales (phương án 2) | Sales ngang Dispatcher **trong phạm vi đơn cửa hàng mình**, trước khi duyệt | Sales được: chọn rank 1, 2 hoặc 3 ở **bất kỳ kho nào** (rank 2–3 bắt buộc mã lý do); chạy lại planner/đổi tiêu chí; ghi thỏa thuận ngày với khách. Server vẫn kiểm đủ 5 gate, hold còn hạn, dữ liệu mới, cùng `ApprovalService`, khóa và audit. Người duyệt (Sales và Dispatcher) chỉ cần biết phương án **khả thi hay không**: mọi phương án qua đủ 5 gate đều duyệt được; **bỏ tick chấp nhận lịch sát cho mọi vai trò** (bổ sung 18/11). Dispatcher tồn tại để điều phối các trường hợp khác ngoài đơn tạo tại quầy. Dispatcher giữ riêng: kế hoạch tay/override ngoài 3 phương án, xử lý FAILED/sự cố xe/lập lại sau thực thi, gửi `DELAY`, đơn cửa hàng khác. Dispatcher thấy và can thiệp được mọi đơn Sales đã duyệt. Quy tắc cũ "đơn đặt trước chưa duyệt đang tranh nguồn lực → chuyển Dispatcher" **giữ nguyên**. |
| **DEC-R3-11** Ngoài phạm vi R3 | Hoãn/chuyển sang cấu hình | Hoãn: gợi ý chuyển kho, màn Revenue, 5 KPI còn lại của PRD. UI quản trị (Users, Vehicles, Employees, MarketConfig, Attendance) → seed/file cấu hình. WMS reserve/release: giữ adapter tắt, chỉ ACK mô phỏng ở staging có nhãn *simulated*. **Giữ multi-truck** (đơn nhiều xe cùng một kho). |
| **DEC-R3-12** Track CRM | Thay Dynamics 365 | Chức năng Dynamics giả định cơ bản (Account, Contact, Opportunity/Quote, Activity), độ phức tạp dữ liệu/tích hợp trung bình; mục tiêu Salesforce Sales Cloud, Service Cloud chỉ là tùy chọn sau khảo sát tuần 1. CFO **không bao giờ gọi trực tiếp CRM**: đọc liên hệ và đồng ý liên lạc qua `CustomerContactPort`; MVP có hai provider giả lập `d365_mock` và `salesforce_mock`, chọn bằng cấu hình, để chứng minh CFO không phải sửa khi đổi CRM. Sau cutover, Salesforce là nguồn đúng duy nhất cho liên hệ/đồng ý liên lạc. Chỉ migrate dữ liệu đang hoạt động, upsert theo External ID. Hạn tắt Dynamics giả định tuần 8, cutover tuần 5 có tiêu chí go/no-go, đường lùi Dynamics chỉ đọc. Giấy phép: phần dùng trong dự án tính vào dự án, phí định kỳ thuộc ngân sách vận hành của client. |
| **DEC-R3-13** Ngân sách & thang cắt | Chỉ số 100 → 70 | CFO 46 / CRM 20 / dự phòng 4 (bản cuối sau 4 lần sửa). Thang cắt khi CRM vượt 20: dùng dự phòng → bỏ email `DISPATCHED` → bỏ nháp DELAY → hoãn CS lookup → thu nhỏ adapter Đan Mạch (cấu hình + test "engine không đổi") → AI về rule-based. AI chỉ được bảo vệ mềm. CRM vượt ngưỡng thang → quay lại client, không âm thầm cắt ETA. Không bao giờ cắt: 5 gate, duyệt + khóa + nhật ký, ETA, `FAILED`. |
| **DEC-R3-14** Đa thị trường & AI | Adapter Đan Mạch giả lập; AI theo lô | Đan Mạch chỉ bằng cấu hình (múi giờ, ngày lễ, giờ chốt, ngôn ngữ), cùng engine; không `if market ==` trong lõi. AI gợi ý nhóm xử lý hàng chạy theo lô lúc seed, không gọi live; gợi ý ở trạng thái chờ cho tới khi người xác nhận; rule-based là nền chạy trước. |

## 3. Quyết định cũ bị thay thế (giữ lại để truy vết)

| Cũ | Bị thay bởi | Phần bị thay |
|---|---|---|
| D3 GPS trong DEV2_D2_D3_D4_D5 | DEC-R3-01 | Chu kỳ thu 30 phút và hàng đợi offline (thay bằng vị trí tài xế chủ động gửi). Quyền xem theo Dispatcher được gán chuyến, dừng khi chuyến kết thúc, lưu tối đa 7 ngày (DEC-GPS-RET-20261109, DEC-INT-GPS-HISTORY-20261109) **giữ nguyên** |
| D4 kênh SMS, DEC-NOTIFY-001 phần kênh | DEC-R3-02 | Kênh SMS |
| Danh sách 10 KPI (`01`, `08` §10) | DEC-R3-03 | Danh mục KPI |
| `08` §5 quy mô 3 kho, 20–30 cửa hàng | DEC-R3-04 | Quy mô seed/pilot |
| DEC-INT-CS-GET-PRIVACY-20261109 phần contact log | DEC-R3-05 | Ghi liên hệ CS |
| ASM-007, DEC-SHIFTS-001 (phần kho), lịch người–ca trong DEC-M6-PREP-QUEUE-20261109 (`schedule_verified` theo roster) | DEC-R3-06 | Lịch từng người, điểm danh |
| DEC-DEV2-D7-001, DEC-DRIVER-001 (phần CFO tự kiểm lịch sử lái/nghỉ) | DEC-R3-07 | Bằng chứng lịch sử 56 ngày |
| `PREP_PAUSED`/`PREP_RESUMED` | DEC-R3-08 | Tạm dừng/tiếp tục chuẩn bị |
| Tick "I accept the tight schedule" (`02` US-APR AC7, `03`, `07`) | DEC-R3-10 | Điều kiện tick khi duyệt lịch sát |
| `suggest_replan` tín hiệu `delivery_failed`, `vehicle_issue` | DEC-R3-09 | Gợi ý lập lại tự động sau thực thi |
| DEC-SALES-001, `docs/DECISION_SALES_CONFIRMATION.md` §3, `09` bất biến 26 | DEC-R3-10 | Giới hạn rank-1, một xe, không đổi tiêu chí/ngày |
| DEC-INT-TRANSFER-BOUNDARY-20261109 | DEC-R3-11 | Gợi ý chuyển kho trong pilot |
| ASM-010…ASM-015 (proposed) | DEC-R3-01…14 | Đề xuất CRM gửi thông báo/CS trên CRM không được chọn |

## 4. Còn mở

- Gói bù ngân sách cho multi-truck trên ngân sách thật (đề xuất P2 + P4 + P6 + R2 ≈ 5,5 đơn vị) chưa chốt.
- Hệ số sử dụng 90% trong DEC-R3-06 dùng giá trị hiện hành; xác nhận lại khi có dữ liệu kho.
- Cách trình bày 15 phút (slide/demo/prototype) chốt sau.

## 5. Tình trạng triển khai

Chưa triển khai. Thứ tự: T01 (hợp đồng `05`/`06`) → các task T02–T24.
