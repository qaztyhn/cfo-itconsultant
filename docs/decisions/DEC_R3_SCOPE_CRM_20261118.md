# DEC-R3 — Round 3: phạm vi pilot, vị trí tài xế, KPI, quyền Sales trong phạm vi (2026-11-18)

> **Người duyệt:** Chủ dự án, phiên làm việc 2026-11-18 (trả lời từng câu hỏi Q1–Q9 và các quyết định cắt giảm).
> **Hiệu lực:** ràng buộc nghiệp vụ cho Round 3, **thay thế** các quyết định cũ được liệt kê ở §3.
> **Không có nghĩa** code, migration hay kiểm thử đã hoàn thành. Hợp đồng `05`/`06` được đồng bộ ở PR riêng (task T01);
> mọi task triển khai phải theo hợp đồng đó.
>
> **Sửa 19/11/2026:** Owner hủy DEC-R3-11 → DEC-R3-14 (xem §2a). Hiệu lực còn lại: DEC-R3-01 → DEC-R3-10 và DEC-R3-15 (thêm 19/11).
>
> Nguồn: các câu hỏi Q1–Q9 và quyết định cắt giảm trong phiên làm việc 18/11/2026. Bản đề xuất ban đầu đã bị xóa vì lỗi thời.

## 1. Bối cảnh

Đề Round 3: thay Microsoft Dynamics 365 bằng CRM mới, đồng thời ngân sách giảm 30%, giữ nguyên khung 6 tuần. MVP trong
repo là bản mô phỏng để trình bày; phần bị cắt được **ẩn/tắt bằng cờ**, không xóa code hay bảng. Ngân sách và track CRM
**không** được ghi thành quyết định trong repo này (xem §2a).

## 2. Quyết định

| ID | Quyết định | Quy tắc chính xác |
|---|---|---|
| **DEC-R3-01** Vị trí & ETA *(sửa 18/11 lần 3)* | Hoãn GPS thu liên tục, hàng đợi offline và **bản đồ**; vị trí do tài xế chủ động gửi | Tài xế bấm **Cập nhật vị trí** khi đang chạy; gửi kèm vị trí khi **báo sự cố**; **bắt buộc** gửi vị trí khi báo `DELIVERED`/`FAILED` (tối thiểu 1 lần/chuyến) — không lấy được vị trí thì **không** xác nhận được. Không thu theo chu kỳ. ETA tính lại từ vị trí mới (thời gian tuyến còn lại tới điểm giao + dỡ hàng). Báo sự cố: lý do `vehicle_breakdown` \| `traffic_or_accident` \| `site_inaccessible` \| `other` (ghi chú); luôn cảnh báo Dispatcher; có vị trí thì tính lại ETA; hỏng xe → ETA không xác định, Dispatcher quyết định (không tự lập lại). Quá ETA 30 phút (hoặc mốc kho quá 30 phút) mà không có sự kiện → cảnh báo `OVERDUE` cho Dispatcher, không tự tính lại ETA. **Hiển thị:** không có bản đồ; Dispatcher được gán chuyến thấy một dòng **Vị trí gần nhất · Giờ cập nhật · ETA** (tọa độ, cách điểm giao bao nhiêu km, giờ gửi, ETA) khi chuyến đang `on_road`; khách, CS, Sales không bao giờ thấy. **Gán Dispatcher:** luân phiên khi duyệt kế hoạch — mọi chuyến của một đơn gán cho cùng một Dispatcher, chọn người trong danh sách luân phiên của market đã lâu nhất chưa được gán; Dispatcher có thể bàn giao cho người khác (có audit); không có ai trong danh sách thì không ai xem (fail-closed). **Lưu trữ:** tọa độ xóa khi đơn kết thúc (`DELIVERED` hoặc `CANCELLED`); đơn `FAILED` chưa xử lý xong thì xóa chậm nhất sau 7 ngày; không có truy cập lịch sử sau khi xóa. Chuyến kết thúc thì Dispatcher mất quyền xem tọa độ chuyến đó. Dùng với tài xế thật cần DPIA và tham vấn nhân viên trước. Driver PWA chạy online, retry bằng cùng `Idempotency-Key`. |
| **DEC-R3-02** Thông báo | Bỏ SMS; chỉ email | Email `CONFIRMED`, `DISPATCHED` (khi xe đầu tiên rời kho, một lần/đơn), `DELIVERED`, `FAILED`, `DELAY`. `DELAY` chỉ phát sau khi Dispatcher gửi. **`FAILED` luôn giữ.** `DISPATCHED` có thể tắt bằng cờ `NOTIFY_DISPATCHED_ENABLED`. Khách không có email → `SKIPPED_NO_CHANNEL`, không log PII. |
| **DEC-R3-03** KPI | 10 KPI → 5 KPI | (1) **Thời gian lập kế hoạch/đơn**: thời gian người xử lý thao tác, so baseline thủ công từ shadow pilot, ↓, báo cáo tách theo đường duyệt `sales`/`dispatcher`; chỉ số phụ `order_to_commit_min` = từ lúc đơn vào CFO đến `CONFIRMED`, tách theo đường. (2) **Giao đúng hạn**: % đơn giao trong cửa sổ đã hứa, ↑. (3) **Tỷ lệ chấp nhận phương án**: % rank-1 được duyệt không sửa, bởi Dispatcher hoặc Sales, ↑, tính cả hai đường nhưng **báo cáo tách theo đường**; chỉ số phụ `counter_commit_rate` = % đơn cam kết ngay tại quầy. (4) **Can thiệp thủ công/đơn**: % đơn phải lập tay hoặc override (gồm số kế hoạch lập tay), ↓. (5) **Sai số ETA**: phút chênh giữa ETA dự báo và giờ POD thực tế, median và P90, ↓; **chỉ số tuyệt đối có mục tiêu, không baseline**. |
| **DEC-R3-04** Quy mô pilot | 3 kho → 2 kho; 20–30 cửa hàng → 10 | ~100 SKU giữ nguyên. |
| **DEC-R3-05** CS | Bỏ contact log của CS | CS Order Lookup chỉ đọc, che dữ liệu, giữ nguyên. Không còn endpoint ghi liên hệ; bảng giữ, không drop. |
| **DEC-R3-06** Công suất kho | Chỉ ghi công suất theo ngày/ca | Warehouse Manager nhập và xác nhận cho mỗi (kho, ngày, ca): số người làm, số giờ làm hữu ích. Công suất ngày = Σ ca (số người × số giờ × hệ số sử dụng hiện hành của market, mặc định 90%) − việc đã cam kết. **Không có dòng đã xác nhận = 0 công suất (fail-closed).** Bỏ lịch ca từng nhân viên, điểm danh, sinh điểm danh. |
| **DEC-R3-07** Tài xế | Đội quản lý tài xế cung cấp dữ liệu đã xác minh | Đội quản lý tài xế cung cấp lịch khả dụng theo ngày và danh sách xe/loại xe mỗi tài xế được phép lái, **sau khi đã xác minh bằng lái và giờ lái/nghỉ**. CFO chỉ dùng dữ liệu đã xác nhận (có người/nguồn xác nhận, còn hạn) để lập kế hoạch; thiếu hoặc hết hạn → tài xế không đủ điều kiện (fail-closed). CFO **không** tự tính lịch sử lái/nghỉ 56 ngày. |
| **DEC-R3-08** Thời gian chuẩn bị | `prep_time = GOODS_READY − START_PREP` | Bỏ `PREP_PAUSED`/`PREP_RESUMED` và tính theo đoạn. Thứ tự mốc bắt buộc START_PREP → GOODS_READY → LOADED. |
| **DEC-R3-09** Thất bại & sự cố | CFO dừng ở cảnh báo | Bỏ tự chạy planner/tạo gợi ý khi đơn `FAILED` **và** khi báo sự cố xe. Tài xế báo `FAILED` cho chuyến của mình kèm lý do; CFO lưu kết quả chuyến. Đơn nhiều xe chuyển `FAILED` khi **mọi chuyến đã kết thúc và có ít nhất một chuyến thất bại**. CFO gửi cảnh báo nội bộ cho Dispatcher kèm lý do và kết quả từng chuyến. Dispatcher chọn: hẹn giao lại, yêu cầu CFO chạy planner lại (đơn giao một phần → **chỉ lập cho phần hàng chưa giao**), hoặc hủy có lý do. |
| **DEC-R3-10** Quyền Sales (phương án 2) | Sales ngang Dispatcher **trong phạm vi đơn cửa hàng mình**, trước khi duyệt | Sales được: chọn rank 1, 2 hoặc 3 ở **bất kỳ kho nào** (rank 2–3 bắt buộc mã lý do); chạy lại planner/đổi tiêu chí; ghi thỏa thuận ngày với khách. Server vẫn kiểm đủ 5 gate, hold còn hạn, dữ liệu mới, cùng `ApprovalService`, khóa và audit. Người duyệt (Sales và Dispatcher) chỉ cần biết phương án **khả thi hay không**: mọi phương án qua đủ 5 gate đều duyệt được; **bỏ tick chấp nhận lịch sát cho mọi vai trò** (bổ sung 18/11). Dispatcher tồn tại để điều phối các trường hợp khác ngoài đơn tạo tại quầy. Dispatcher giữ riêng: kế hoạch tay/override ngoài 3 phương án, xử lý FAILED/sự cố xe/lập lại sau thực thi, gửi `DELAY`, đơn cửa hàng khác. Dispatcher thấy và can thiệp được mọi đơn Sales đã duyệt. Quy tắc cũ "đơn đặt trước chưa duyệt đang tranh nguồn lực → chuyển Dispatcher" **giữ nguyên**. |
| **DEC-R3-15** Màn hình & báo cáo đơn hàng *(19/11)* | Bỏ màn Transfers, Users, Vehicles, Employees, Market config; giữ báo cáo đơn hàng | **Bỏ** các màn Transfers (Dispatcher và kho), Users, Vehicles & drivers, Employees & locations, Market config. Chuyển kho (gợi ý, yêu cầu, hủy) **không có** trong pilot: `NO_FEASIBLE_DATE` chỉ trả ngày khả thi sớm nhất và các check bị loại. Người dùng, nhân viên, xe, tài xế, cấu hình market lấy từ seed/file cấu hình; không có màn hay API ghi cho các dữ liệu này (API đọc phục vụ lập kế hoạch giữ nguyên). **Giữ** báo cáo liên quan đến đơn hàng: màn **Đơn hàng & doanh thu** (mở rộng màn Revenue) gồm doanh thu, tổng số đơn, và số đơn + giá trị theo 6 nhóm trạng thái: Chờ duyệt (`SUBMITTED`, `PLANNED`, `NO_FEASIBLE_DATE`) · Đã duyệt (`APPROVED`, `PREPARING`, `GOODS_READY`, `LOADED`) · Đang vận chuyển (`DISPATCHED`) · Đã hoàn thành (`DELIVERED`) · Thất bại (`FAILED`) · Đã hủy (`CANCELLED`). Bộ lọc thời gian theo **ngày cam kết giao** (`committed_date`); đơn chưa có ngày cam kết (nhóm Chờ duyệt, đơn hủy trước duyệt) dùng ngày giao khách yêu cầu (`date_to`). Doanh thu ghi nhận vẫn theo ngày giao thực tế (BR-KPI-01). Quyền xem giữ như Revenue: Business owner mọi nơi, owner cửa hàng/kho nơi mình, admin tất cả, người khác 403. |

## 2a. Quyết định đã hủy (19/11/2026)

Owner hủy các quyết định sau; nội dung không còn hiệu lực và **không** được dùng làm căn cứ triển khai. Các quy tắc cũ mà
chúng từng thay thế được áp dụng lại.

| ID | Chủ đề | Hệ quả |
|---|---|---|
| DEC-R3-11 | Ngoài phạm vi R3 (chuyển kho, Revenue, UI quản trị, ACK WMS mô phỏng, multi-truck) | Revenue giữ theo đặc tả cũ; chuyển kho và UI quản trị sau đó bị bỏ lại bởi **DEC-R3-15** (19/11). ACK WMS mô phỏng và multi-truck tiếp tục theo quyết định cũ (DEC-WMS-RESERVE-SYNC-20261109, multi-vehicle trong MVP) |
| DEC-R3-12 | Track CRM (`CustomerContactPort`, mock D365/Salesforce) | Không có hợp đồng CRM trong repo |
| DEC-R3-13 | Ngân sách 46/20/4 và thang cắt | Không ghi trong repo |
| DEC-R3-14 | Thị trường Đan Mạch giả lập, AI gợi ý theo lô | Không có trong phạm vi R3 |

## 3. Quyết định cũ bị thay thế (giữ lại để truy vết)

| Cũ | Bị thay bởi | Phần bị thay |
|---|---|---|
| D3 GPS trong DEV2_D2_D3_D4_D5; DEC-GPS-RET-20261109; DEC-INT-GPS-HISTORY-20261109 | DEC-R3-01 | Chu kỳ 30 phút, hàng đợi offline, bản đồ, lưu 7 ngày và truy cập lịch sử theo case (thay bằng xóa khi đơn kết thúc). Quyền xem chỉ Dispatcher được gán chuyến, dừng khi chuyến kết thúc **giữ nguyên** |
| D4 kênh SMS, DEC-NOTIFY-001 phần kênh | DEC-R3-02 | Kênh SMS |
| Danh sách 10 KPI (`01`, `08` §10) | DEC-R3-03 | Danh mục KPI |
| `08` §5 quy mô 3 kho, 20–30 cửa hàng | DEC-R3-04 | Quy mô seed/pilot |
| DEC-INT-CS-GET-PRIVACY-20261109 phần contact log | DEC-R3-05 | Ghi liên hệ CS |
| ASM-007, DEC-SHIFTS-001 (phần kho), lịch người–ca trong DEC-M6-PREP-QUEUE-20261109 (`schedule_verified` theo roster) | DEC-R3-06 | Lịch từng người, điểm danh |
| DEC-DEV2-D7-001, DEC-DRIVER-001 (phần CFO tự kiểm lịch sử lái/nghỉ) | DEC-R3-07 | Bằng chứng lịch sử 56 ngày |
| `PREP_PAUSED`/`PREP_RESUMED` | DEC-R3-08 | Tạm dừng/tiếp tục chuẩn bị |
| Tick "I accept the tight schedule" (`02` US-APR AC7, `03`, `07`) | DEC-R3-10 | Điều kiện tick khi duyệt lịch sát |
| DEC-INT-TRANSFER-BOUNDARY-20261109; FR-ATP-03, BR-ATP-05; màn quản trị IT (A4, A9, A10, A12, Users) | DEC-R3-15 | Chuyển kho và màn quản trị trong pilot |
| `suggest_replan` tín hiệu `delivery_failed`, `vehicle_issue` | DEC-R3-09 | Gợi ý lập lại tự động sau thực thi |
| DEC-SALES-001, `docs/DECISION_SALES_CONFIRMATION.md` §3, `09` bất biến 26 | DEC-R3-10 | Giới hạn rank-1, một xe, không đổi tiêu chí/ngày |
| ASM-010…ASM-015 (proposed) | DEC-R3-01…10 | Đề xuất CRM gửi thông báo/CS trên CRM không được chọn |

## 4. Còn mở

- Hệ số sử dụng 90% trong DEC-R3-06 dùng giá trị hiện hành; xác nhận lại khi có dữ liệu kho.
- Cách trình bày 15 phút (slide/demo/prototype) chốt sau.

## 5. Tình trạng triển khai

Chưa triển khai. Thứ tự: hợp đồng `05`/`06` (đã cập nhật) → các task triển khai.
