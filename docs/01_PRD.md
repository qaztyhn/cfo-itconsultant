# 01 — PRD: Central Fulfillment Orchestration (CFO) — MVP

> Product Requirements Document cho agent code và nhóm dev. Phiên bản 1.2, 06/11/2026 (1.0: 04/11/2026; 1.1 và 1.2: 06/11/2026; thay đổi ở mục 0). Tài liệu liên quan: `02` user stories, `03` UI/UX, `04` kiến trúc, `05` database, `06` API, `07` user flow, `08` kế hoạch phát triển, `09` quy tắc cho AI coding.
> Nhãn nguồn: **[S]** slide · **[T]** bản thiết kế hoàn chỉnh · **[C]** chốt trong trao đổi · **[A]** giả định mặc định (chỉnh được trong cấu hình, chưa phải số liệu thật của Company A).

---

## 0. Thay đổi phiên bản

### v1.2 (06/11/2026)
1. **Giờ công theo đơn vị nhỏ nhất:** định mức quy về đơn vị cơ sở (bao, tấm…) để dễ scale; hàng không chia nhỏ được thì làm tròn lên (FR-PRP-01, BR-PRP-01).
2. **Một đơn nhiều xe:** hệ thống tự gợi ý cơ cấu xe (ít xe nhất), xếp lịch nhiều xe cùng kho, tới gần như cùng lúc; bỏ `MANUAL_PLANNING` tự động và lối "xử lý ngoài CFO" (FR-ORD-05, BR-DEL-05, BR-RNK-02).
3. **Gợi ý lập lại tự động** khi đơn đã duyệt có thay đổi; dispatcher vẫn duyệt (FR-APR-05, BR-APR-04).
4. **Giữ chỗ lúc lập kế hoạch được phép vượt**, chỉ chặn khi duyệt (BR-RES-04).
5. **Hòa điểm:** xe nhỏ hơn mà vẫn đủ chứa thắng (FR-RNK-01, BR-RNK-02).
6. **Doanh thu** theo đặc tả riêng: hai góc nhìn store/warehouse, `kpi_scopes` (FR-KPI-02, BR-KPI-01).
7. **Dữ liệu giờ nhân công thực tế** qua bắt đầu/tạm dừng/tiếp tục/xong chuẩn bị (FR-EXE-04).
8. **GPS:** cơ sở pháp lý chốt là lợi ích hợp pháp kèm thông báo minh bạch và DPIA.

### v1.1 (06/11/2026)
1. **Thiết bị kho bỏ khỏi MVP** (theo slide: equipment-level scheduling ngoài MVP). Giả định mọi kho đủ thiết bị cho N1–N6; định mức giờ công đã gồm thời gian dùng thiết bị. Năng lực đặc biệt khi giao (cẩu, ben) vẫn là thuộc tính **xe**. FR-PRP-03, BR-PRP-03 đánh dấu "đã bỏ".
2. ~~Đơn cần nhiều xe: lối "xử lý ngoài CFO"~~ (thay ở v1.2 bằng xếp lịch nhiều xe).
3. **Vòng đời kế hoạch**: lập lại/hủy/xếp lại sau thất bại phải đóng kế hoạch cũ trong một transaction (BR-APR-03); POD theo **từng lần giao** (BR-EXE-03); khóa chống giữ chỗ vượt tồn kho và công suất (BR-RES-04).
4. **KPI và doanh thu**: định nghĩa doanh thu và quyền xem (BR-KPI-01, FR-KPI-02).
5. **GPS**: ghi rõ giả định cơ sở pháp lý (FR-GPS-01, mục 12).
6. Đối chiếu với slide proposal ở mục 13 (dùng cho báo cáo).

---

## 1. Tóm tắt sản phẩm

> Decision 2026-11-07: Sales confirms eligible standard plans in a separate CFO UI without changing POS. `docs/DECISION_SALES_CONFIRMATION.md`.

**CFO** là một lớp điều phối dùng chung, đặt trên các hệ thống POS/WMS/ERP sẵn có của từng nước. Nó kết hợp tồn kho, công suất kho và đội xe để **đưa ra cam kết giao hàng khả thi**, để Dispatcher hoặc Sales đủ điều kiện duyệt, rồi **theo dõi thực thi và ngoại lệ đến khi khách nhận hàng**, kèm thông báo cho khách và cải tiến dự báo từ dữ liệu thực tế [S].

**MVP** là một **ứng dụng web chạy thật** (không phải bản trình bày), pilot ở Thụy Điển với dữ liệu giả lập: ~100 SKU, 3 kho, 25 cửa hàng [S][C]. Kiến trúc coi mọi nước bình đẳng để mở rộng Bắc Âu mà không sửa lõi.

### 1.1 Vấn đề
Company A là nhà bán lẻ vật liệu xây dựng Đan Mạch với hàng trăm cửa hàng khắp Bắc Âu, phục vụ cả doanh nghiệp và người tiêu dùng. Mỗi nước tối ưu riêng nên có bốn thách thức liên kết: quy trình thủ công, hệ thống phân mảnh, vận hành không nhất quán, và giao hàng & fulfilment, nơi ba cái kia hội tụ (suy luận của nhóm). Khách thấy: ngày giao không đáng tin, hàng sai hoặc thiếu, đơn "mất tích", giao trễ không giải thích [S].

### 1.2 Mục tiêu sản phẩm
1. Mỗi đơn có **kế hoạch giao hàng khả thi** (kho, xe, tài xế, giờ) trong vài phút thay vì kiểm tra tay trên nhiều hệ thống.
2. **Cam kết đáng tin**: ngày/khung giờ chỉ được cam kết sau khi người có quyền duyệt, nguồn lực được kiểm tra lại và commit thành công.
3. **Phát hiện trễ sớm** bằng ETA tính lại theo sự kiện và GPS; dispatcher quyết định báo khách.
4. **Một lõi chung, cấu hình riêng theo nước**: thêm nước = thêm adapter, cấu hình và bảng sản phẩm.
5. **Chứng minh giá trị đo được** bằng 6 KPI pilot của slide cộng 2 chỉ số bổ sung.

### 1.3 Không phải mục tiêu của MVP
Thay thế POS/WMS/ERP; tối ưu toàn cục nhiều đơn/nhiều chuyến (MVP chỉ xếp nhiều xe cho **một** đơn, cùng kho); quản lý và xếp lịch thiết bị kho; ghép đơn; cửa hàng làm nguồn hàng; AI dự đoán hoặc học định mức; trang trạng thái đơn cho khách; app tài xế native; SMS thật; hệ thống thanh toán/ hóa đơn. Xem mục 10 (phần mở rộng).

---

## 2. Cơ hội và lý do ưu tiên [S]

**Cơ hội:** Order-to-Delivery Orchestration, một lớp điều phối phối hợp tồn kho, công suất kho và vận tải để lập cam kết giao hàng, rồi giám sát đến khi nhận hàng, xây trên hệ thống sẵn có.

**Vì sao Delivery & Fulfilment đi trước:** tác động kinh doanh cao (mỗi đơn trễ/thiếu là thất bại thấy được), phù hợp mọi thị trường (cùng sự kiện bàn giao), đo được từng đơn; khả thi mức trung bình (phụ thuộc dữ liệu và tích hợp). Ba hướng còn lại được **xếp thứ tự, không bỏ**: bàn giao thủ công được tự động hóa trong hành trình; chuẩn đơn chung lớn lên từ luồng chung; hệ thống được nối tại điểm bàn giao.

**Giả định then chốt [S]:** A1 khách doanh nghiệp là nhóm nhạy giao hàng nhất (kiểm chứng bằng phỏng vấn); A2 mỗi nước có hệ thống riêng nên **tích hợp, không thay thế**.

---

## 3. Người dùng và vai trò

| Vai trò | Là ai | Mục tiêu chính | Công cụ |
|---|---|---|---|
| **Dispatcher** | Điều phối viên theo nước | Duyệt kế hoạch giao hàng, xử lý ngoại lệ, quyết định báo trễ cho khách, theo dõi GPS | Web (dashboard) |
| **Warehouse manager / deputy / supervisor** | Quản lý và trưởng ca kho | Khai báo năng lực (điểm danh, ca), ghi mốc chuẩn bị, báo ngoại lệ, xác nhận chuyển kho | Web |
| **Driver** | Tài xế | Nhận chuyến, ghi xuất phát/giao/thất bại, gửi vị trí | PWA |
| **Sales** | Nhân viên bán tại cửa hàng | Tạo đơn ở POS, yêu cầu CFO đồng bộ ngay và xác nhận kế hoạch tiêu chuẩn đủ điều kiện | POS + CFO Web |
| **Store manager** | Quản lý cửa hàng (owner mặc định) | Theo dõi đơn và KPI cửa hàng mình | Web |
| **Customer service (CSKH)** | Bộ phận chăm sóc khách hàng, **tách khỏi sales** [C] | Trả lời khách về trạng thái và ETA, ghi nhật ký liên hệ | Web |
| **IT / Admin** | Nhân viên IT trung tâm (quyền admin) | Ánh xạ SKU, quản lý sản phẩm global/nhóm xử lý, nhân sự, cấu hình, đồng bộ | Web |
| **Business owner, Project lead** | Quản lý kinh doanh/dự án | Theo dõi KPI và tiến độ pilot | Web (chỉ xem) |
| Warehouse operator (công nhân kho) | Nhặt, gom hàng | **Không có tài khoản**; quản lý/trưởng ca ghi mốc và điểm danh thay [C] | — |
| Khách hàng | Doanh nghiệp (contractor, trade) và cá nhân | Biết ngày/khung giờ giao và nhận cập nhật | Email/SMS (mô phỏng) |

---

## 4. Phạm vi MVP

**Trong MVP:** tích hợp qua hệ thống nguồn giả lập từng nước; sản phẩm riêng từng nước + ánh xạ sang sản phẩm global do IT làm; nhóm xử lý N1–N6 và cờ đặc biệt; time-phased ATP; giữ chỗ cả 3 phương án; gợi ý chuyển kho bằng quy tắc; công suất kho từ điểm danh; xe, tài xế, bằng lái, lịch xe; lộ trình OpenRouteService; gate 5 check; xếp hạng; duyệt/chọn khác/chạy lại/lập tay; thực thi (kho + tài xế PWA offline queue); **GPS**; ETA và rủi ro; 4 loại thông báo; nhân sự và phân quyền; nhật ký quyết định; KPI.

**Ngoài MVP (mở rộng):** mục 10.

**Loại trừ theo thiết kế (mọi giai đoạn) [S]:** khách không xem GPS; không tự duyệt thay dispatcher; không tự đổi ngày giao khi khách chưa đồng ý.

**Pilot [S][C]:** Thụy Điển (minh họa); ~100 SKU; 3 kho (Göteborg, Stockholm, Malmö); 25 cửa hàng làm nơi nhận đơn; ~150 nhân viên; 8–10 xe. Mọi nước khác chỉ có bản ghi cấu hình.

---

## 5. Yêu cầu chức năng (FR)

Ưu tiên: **M** = bắt buộc cho MVP.

### 5.1 Tích hợp và hệ thống nguồn
- **FR-INT-01 (M)** Mỗi nước có một hệ thống nguồn giả lập (cùng mã nguồn, DB riêng) với POS form, sản phẩm, tồn kho, hàng nhập, lịch xe, REST API. Chỉ dựng Thụy Điển. [C]
- **FR-INT-02 (M)** CFO kéo dữ liệu mỗi 5 phút qua `MarketAdapter` (HTTP), theo `updated_since` với mốc trùng 2 phút; upsert theo khóa tự nhiên; chạy lại không nhân đôi. [C][T]
- **FR-INT-03 (M)** Dòng lỗi vào bảng reject, không làm hỏng cả lượt; thất bại cả lượt → alert cho IT.
- **FR-INT-04 (M)** Chỉ kéo đơn đã qua **Sales Validation** và ở trạng thái `SUBMITTED_FOR_PLANNING`. [S]
- **FR-INT-05 (M)** Đơn đã duyệt mà nguồn sửa/hủy → không ghi đè, tạo alert và gợi ý phương án mới (FR-APR-05) để dispatcher quyết định.
- **FR-INT-06 (M)** Tồn kho là ảnh chụp ghi đè kèm `as_of`; quá 15 phút chưa đồng bộ → cờ vàng + alert.
- **FR-INT-07 (M)** CFO **chỉ đọc** từ hệ thống nguồn, không ghi ngược; đơn đã duyệt hiện bước "xác nhận thủ công trong WMS".
- **FR-INT-08 (M)** Sales trong CFO yêu cầu đồng bộ ngay đơn đã submit tại POS bằng API đọc qua adapter, không cần chờ lượt polling 5 phút; polling là dự phòng. Không sửa POS hay gộp database.

### 5.2 Sản phẩm và ánh xạ

> **ASM-005 (quyết định 07/11/2026):** Pilot khởi đầu khoảng 100 SKU được IT mapping. CFO là lớp điều phối **chỉ cho đơn đủ 100% SKU mapped**; đơn không đủ điều kiện ở lại quy trình cũ, không bị giữ chờ IT trong CFO. Đây là thay đổi **mục tiêu**, chưa phải code đang chạy; xem `docs/ASSUMPTIONS.md` §ASM-005.

- **FR-PRD-01 (M)** Mỗi nước một bảng sản phẩm riêng (mã nội bộ) ánh xạ sang `product_global`. [C]
- **FR-PRD-02 (M)** Chỉ đơn có **tất cả SKU `mapping_status=confirmed`** được đưa vào luồng điều phối CFO. Nếu có một SKU chưa được xác nhận, **toàn bộ đơn đi theo quy trình cũ**, không chờ IT hoặc lập kế hoạch/giữ chỗ tại CFO. IT vẫn có hàng đợi mapping SKU để mở rộng danh mục cho **các đơn tương lai**.
- **FR-PRD-03 (M)** Gợi ý ứng viên bằng quy tắc (GTIN trùng, tên gần giống `pg_trgm`, nhóm xử lý theo bảng quy tắc). **Chỉ IT** xác nhận hoặc từ chối (từ chối bắt buộc có lý do). [C]
- **FR-PRD-04 (M)** IT mapping xong chỉ mở rộng tập SKU đủ điều kiện cho **những đơn được tiếp nhận CFO về sau**; không tự động mở khóa, chạy planning, gửi xác nhận hoặc chuyển những đơn đã đi theo quy trình cũ sang CFO. Không tái sử dụng `HANDLED_EXTERNALLY` đã bị loại khỏi schema v1.2.
- **FR-PRD-05 (M)** IT quản lý sản phẩm global, quy đổi đơn vị chuẩn bị (pallet, bó, m³, kiện), nhóm N1–N6, định mức giờ công dùng chung mọi kho, hệ số cờ.

### 5.3 Đơn hàng
- **FR-ORD-01 (M)** Đơn gồm vật liệu, số lượng, ngày giao yêu cầu (3 dạng), khung giờ nhận hàng tùy chọn (từ–đến), khách, địa chỉ chụp lại kèm toạ độ, ngày đặt, sales phụ trách, cửa hàng nhận đơn, đơn giá. [C]
- **FR-ORD-02 (M)** Ngày yêu cầu khác ngày cam kết; ngày cam kết chỉ có sau khi Dispatcher hoặc Sales đủ điều kiện duyệt thành công. [T][C]
- **FR-ORD-03 (M)** Danh sách đơn theo vai trò và phạm vi (dispatcher cả nước, kho theo kho, cửa hàng theo cửa hàng), lọc theo trạng thái, rủi ro, ngày, kho; mặc định sắp theo `submitted_at ASC, id ASC` (đơn đặt trước hiển thị trước).
- **FR-ORD-04 (M)** Dòng thời gian của đơn (sự kiện, quyết định, thông báo, ETA).
- **FR-ORD-05 (M)** Đơn lớn hơn một xe: hệ thống **gợi ý cơ cấu xe** (số xe, loại xe, phần hàng mỗi xe), ưu tiên **ít xe nhất**, và **xếp lịch nhiều xe** cùng kho, cùng ngày, tới gần như cùng lúc; không giới hạn số xe (chỉ bị giới hạn bởi xe và tài xế rảnh của kho). Không ghép đơn. Thiếu loại xe cần (cẩu, ben) hoặc kín xe → `NO_FEASIBLE_DATE` (check `truck`): dispatcher thương lượng ngày, lập tay, hoặc hủy có lý do. [C]

### 5.4 Tồn kho, ATP, chuyển kho
- **FR-ATP-01 (M)** Time-phased ATP theo công thức mục 6; một kho xử lý trọn đơn. [S][C]
- **FR-ATP-02 (M)** Hàng nhập chưa xác nhận không được tính; hàng đã về không tính hai lần.
- **FR-ATP-03 (M)** Khi mọi kho thiếu hàng: gợi ý chuyển kho bằng quy tắc; dispatcher duyệt, **kho nguồn xác nhận**, rồi tính như hàng nhập đã xác nhận. [C]

### 5.5 Chuẩn bị hàng và công suất
- **FR-PRP-01 (M)** Khối lượng việc = Σ (giờ cố định mỗi dòng + số đơn vị chuẩn bị × giờ/đơn vị) × hệ số cờ + 0,5 giờ kiểm cuối; **giống nhau ở mọi kho**. Số đơn vị tính theo **đơn vị cơ sở nhỏ nhất** (ví dụ 20 bao = 0,5 pallet 40 bao); hàng không chia nhỏ được thì làm tròn lên. [S][C]
- **FR-PRP-02 (M)** Công suất ngày = số người có mặt (điểm danh) × giờ hữu ích × **90%** tỷ lệ dành cho đơn giao − việc đã đặt. [S][C]
- **FR-PRP-03 (đã bỏ ở v1.1)** ~~Thiết bị kho được ép buộc~~. Ngoài MVP theo slide; giả định mọi kho có đủ thiết bị [C][A].
- **FR-PRP-04 (M)** Nếu chuẩn bị xong sau giờ cắt lên hàng, lên hàng ở ca đầu của ngày làm việc kế tiếp. [S]
- **FR-PRP-05 (M)** Quản lý/trưởng ca điểm danh từng người (nút "tất cả có mặt"), sửa ca; công nhân không có tài khoản.

### 5.6 Xe, giao hàng, gate
- **FR-DEL-01 (M)** Xe thuộc kho; chọn xe đủ tải/thể tích, được chở nhóm hàng, đủ khả năng, rảnh; tài xế đủ bằng và còn hạn, trong giờ làm. [S][C]
- **FR-DEL-02 (M)** Thời gian chuyến = lên hàng + lái (OpenRouteService, fallback) + dỡ hàng; tôn trọng cửa sổ nhận hàng của khách. [S]
- **FR-DEL-03 (M)** Gate 5 check: tồn kho, chuẩn bị, xe, địa điểm/ngày, an toàn; chỉ ứng viên qua cả 5 mới được xếp hạng. [S]
- **FR-DEL-04 (M)** Dự trữ lập kế hoạch phân loại: an toàn (≥ 2 ngày), sát (0 đến dưới 2 ngày), không khả thi (< 0). [C]

### 5.7 Xếp hạng, đề xuất, duyệt
- **FR-RNK-01 (M)** Điểm = 0,5 × km + 0,5 × mức đầy công suất kho (min–max trong các phương án của cùng đơn, có vùng bỏ qua); thấp hơn là tốt hơn; ưu tiên **ít xe hơn** trước rồi mới tới điểm; hòa → dự trữ lớn hơn, điểm phức tạp thấp hơn, ETA sớm hơn, **xe nhỏ hơn mà vẫn đủ chứa** (tổng tải nhỏ hơn). [C]
- **FR-RNK-02 (M)** Trả phương án tốt nhất + 2 phương án thay thế, kèm giải thích từ mã lý do. [S]
- **FR-RNK-03 (M)** Không có phương án khả thi: báo check hỏng và ngày khả thi sớm nhất; dispatcher thương lượng với khách; chỉ đổi ngày khi có bản ghi khách đồng ý. [S][C]
- **FR-APR-01 (M)** Dispatcher có 4 quyền: duyệt, chọn phương án khác (bắt buộc lý do), đổi tiêu chí và chạy lại (bắt buộc lý do), lập kế hoạch tay với một hoặc nhiều xe (bắt buộc mã lý do; dùng được cho đơn `PLANNED` hoặc `NO_FEASIBLE_DATE`). [S][C]
- **FR-APR-02 (M)** Giữ chỗ cả 3 phương án theo (đơn, địa điểm), hết hạn 15 phút, gia hạn tối đa 2 lần; hàng và giờ công chỉ tính một lần cho mỗi (đơn, kho). [C]
- **FR-APR-03 (M)** Khi duyệt: kiểm tra lại, khóa tài nguyên trong một transaction, hai đơn không tranh cùng xe/tài xế. Kế hoạch trở thành cam kết về tồn kho, công việc kho và xe. [S]
- **FR-APR-06 (M)** Sales duyệt rank-1 của đơn tại cửa hàng mình nếu 5 gate pass, reserve safe, một xe, nguồn tươi, giữ chỗ hợp lệ và không tranh chấp gây chậm đơn cũ. Dùng cùng ApprovalService, các trường hợp khác do Dispatcher xử lý.
- **FR-APR-05 (M)** **Gợi ý lập lại tự động:** khi đơn đã duyệt gặp một trong bốn tín hiệu (nguồn sửa đơn sau duyệt, tồn kho đổi làm kế hoạch không còn hợp lệ, sự cố xe, giao thất bại), hệ thống báo dispatcher và tạo phương án mới để duyệt. Khi tính, coi như kế hoạch hiện tại của chính đơn không tồn tại (không tính sai nhân công, công suất, tồn kho). Dispatcher duyệt, giữ kế hoạch cũ (lý do) hoặc lập lại tay. [C]
- **FR-APR-04 (M)** Kế hoạch tay lưu mã lý do, ghi chú, ảnh chụp bối cảnh; gắn cờ trong KPI (dữ liệu để AI học sau này). [C]

### 5.8 Thực thi và theo dõi
- **FR-EXE-01 (M)** Nhân viên chỉ nhập sự kiện thực tế, không có bước duyệt: kho (bắt đầu chuẩn bị, hàng sẵn sàng, đã lên xe), tài xế (đã xuất phát, đã giao, thất bại kèm bằng chứng), quản lý (thay đổi ca, ngoại lệ: thiếu hàng, hỏng, sự cố xe). Đơn nhiều xe: lên hàng, xuất phát, giao/thất bại ghi theo từng xe. [S]
- **FR-EXE-04 (M)** Chuẩn bị hàng có **bắt đầu / tạm dừng / tiếp tục / xong**; mỗi lần bắt đầu hoặc tiếp tục nhập số người làm. Hệ thống tính giờ nhân công thực tế = Σ (số người × thời gian từng đoạn), chia cho từng nhóm hàng theo tỷ lệ giờ kế hoạch rồi chia số đơn vị cơ sở → **giờ nhân công/đơn vị** cho từng nhóm (dữ liệu để AI hiệu chỉnh định mức sau này, không phụ thuộc số người). [C]
- **FR-EXE-02 (M)** Driver PWA có hàng đợi sự kiện khi mất mạng, dấu thời gian là giờ chạm.
- **FR-EXE-03 (M)** Giao thất bại có lý do chọn sẵn, đếm riêng; dispatcher xếp lại.
- **FR-RSK-01 (M)** Tính lại ETA khi có sự kiện, GPS mới, dữ liệu nguồn đổi, mốc quá hạn 30 phút, và 07:00 hằng ngày với đơn nhiều ngày; không tính vô ích. [C]
- **FR-RSK-02 (M)** Trạng thái rủi ro theo % tiêu hao dự trữ (xanh < 33%, vàng 33–66%, cam > 66%; trễ khi slack âm 2 lần liên tiếp; quá hạn). Cam và trễ báo dispatcher. [C][T]
- **FR-GPS-01 (M)** GPS có trong MVP: driver PWA gửi vị trí mỗi 30 phút (chỉnh được), có bộ giả lập; **chỉ dispatcher xem**; khách và CS không bao giờ thấy; mất tín hiệu > 60 phút → alert; xóa sau 30 ngày; cờ `gps_enabled` theo nước và ghi nhận DPIA. Chỉ gửi vị trí khi chuyến đang chạy (`on_road`), không theo dõi ngoài giờ làm. **Giả định pháp lý:** tài xế được thông báo khi ký hợp đồng lao động và trong app (mục đích, ai xem, khi nào gửi, thời gian lưu); vì đồng ý trong quan hệ lao động thường không được coi là tự nguyện theo GDPR, cơ sở pháp lý dự kiến là lợi ích hợp pháp/thực hiện hợp đồng, kèm DPIA và tham vấn nhân viên trước khi dùng thật. [C][S][A]

### 5.9 Thông báo
- **FR-NOT-01 (M)** 4 loại: xác nhận ngày và khung giờ (khi duyệt), đã xuất kho, đã giao (hoặc giao thất bại), báo trễ. Email thật (Mailpit/Brevo), SMS mô phỏng. [C]
- **FR-NOT-02 (M)** **Báo trễ do dispatcher bấm gửi**; hệ thống chỉ tạo bản nháp khi cam/trễ. [C]
- **FR-NOT-03 (M)** Không gửi 21:00–07:00 (trừ báo trễ); chống trùng; thử lại 3 lần.
- **FR-NOT-04 (M)** Khách chỉ thấy trạng thái và ETA, không toạ độ, không GPS.

### 5.10 Nhân sự và phân quyền
- **FR-EMP-01 (M)** Một bảng nhân viên + 5 bảng con (warehouse, sales, dispatcher, driver, customer_service). Admin là quyền do IT giữ; Business owner, Project lead chỉ xem. [C]
- **FR-EMP-02 (M)** Một nhân viên chỉ có một phân công đang hiệu lực (kho **hoặc** cửa hàng **hoặc** trung tâm); mỗi kho/cửa hàng đúng một quản lý chính; owner mặc định là quản lý, gán lại được. [C]
- **FR-EMP-03 (M)** RBAC theo vai trò và phạm vi địa điểm, kiểm ở máy chủ.

### 5.11 KPI, log, quản trị
- **FR-KPI-01 (M)** Dashboard 6 KPI của slide (thời gian lập kế hoạch, giao đúng hạn, giờ công và km mỗi lần giao thay cho "cost per delivery", sai số chuẩn bị, sai số ETA, tỷ lệ chấp nhận kế hoạch) + tỷ lệ giao thất bại + mức dùng công suất; so với baseline nhập tay. [S][C]
- **FR-KPI-02 (M)** Màn **Doanh thu** chỉ đọc (ngoài 8 KPI vận hành): doanh thu ghi nhận (đơn DELIVERED, theo ngày giao), đã duyệt chưa giao, số đơn đã giao, giá trị đơn trung bình, tỷ trọng; hai góc nhìn theo cửa hàng và theo kho, **không cộng với nhau**; xuất CSV có ghi nhật ký. Chỉ tiền hàng, không phí giao/đóng gói/nhân công/giá vốn/lợi nhuận. [C][A]
- **FR-LOG-01 (M)** Nhật ký quyết định trong DB (chỉ thêm) và log kỹ thuật JSONL; không PII trong log.
- **FR-ADM-01 (M)** IT xem lịch sử đồng bộ, dòng bị loại, cấu hình market, bật/tắt GPS, ghi nhận DPIA.

---

## 6. Quy tắc nghiệp vụ (BR)

Mỗi quy tắc là một yêu cầu kiểm thử được. Mã dùng làm tên test.

### 6.1 Nguyên tắc chung
- **BR-GEN-01** CFO chạy trên hệ thống sẵn có và chỉ đọc từ chúng. [S]
- **BR-GEN-02** Lõi quyết định dùng chung; quy tắc từng nước là dữ liệu cấu hình, không có mã riêng nước trong lõi. [S][C]
- **BR-GEN-03** Hệ thống đề xuất, Dispatcher quyết định các ca đầy đủ/ngoại lệ và Sales được duyệt có điều kiện; không tự duyệt, không tự đổi ngày giao khi khách chưa đồng ý. [S]
- **BR-GEN-04** Mọi quyết định được ghi `decision_log`; chọn phương án khác, đổi tiêu chí, kế hoạch tay, từ chối ánh xạ, hủy/lập lại đơn bắt buộc có lý do. [S][C]
- **BR-GEN-05** Mọi dữ kiện có nguồn và độ tươi; dữ liệu cũ hiển thị cờ cảnh báo. [T]

### 6.2 Đơn hàng và sản phẩm
- **BR-ORD-01** Đơn vào CFO chỉ khi `SUBMITTED_FOR_PLANNING` ở nguồn sau Sales Validation. [S]
- **BR-ORD-02** Ba dạng yêu cầu ngày: `exact` (đúng một ngày), `range` (nhận được trong khoảng), `latest` (muộn nhất ngày X). Không bao giờ giao sớm hơn ngày khách chọn (`exact`) hoặc đầu khoảng (`range`); `latest` được giao sớm hơn. [C]
- **BR-ORD-03** Giờ nhận hàng là khung từ–đến tùy chọn; nếu chỉ có ngày thì dùng giờ nhận hàng mặc định của market. [S][C]
- **BR-ORD-04** Địa chỉ giao được chụp lại trên đơn kèm toạ độ; khách ở bảng riêng. [C]
- **BR-PRD-01** Mã nội bộ từng nước ánh xạ về sản phẩm global theo thứ tự: ánh xạ đã xác nhận → GTIN/EAN → thuộc tính → (AI gợi ý, sau) → người duyệt. [S]
- **BR-PRD-02** Chỉ IT xác nhận ánh xạ SKU, vì mỗi nước có admin/quản lý kho/dispatcher riêng nên để họ tự ánh xạ sẽ làm dữ liệu không đồng nhất. [C]
- **BR-PRD-03** SKU chưa ánh xạ/chưa được IT duyệt → **đơn không thuộc luồng CFO, tiếp tục xử lý theo quy trình cũ**. Đơn có đủ mọi SKU đã xác nhận mới được CFO điều phối; không điều phối trùng, không hồi tố chuyển đơn cũ sau mapping. [C]
- **BR-PRD-04** Nhóm xử lý N1–N6 gán bằng bảng quy tắc cứng; **IT** nhập định mức (giờ cố định/dòng, giờ công/đơn vị chuẩn bị) và xác nhận nhóm, vì MVP chưa có số liệu từ quản lý kho; AI tinh chỉnh khi có đủ dữ liệu thực tế (phần mở rộng, dựa trên giờ nhân công thực tế trên một đơn vị cơ sở của từng nhóm, FR-EXE-04). Nhóm N6 không gắn cờ FRAGILE (tránh nhân hệ số hai lần). [C]
- **BR-PRD-05** Định mức giờ công dùng chung mọi kho; kho có hệ số hiệu suất mặc định 1,0 (chưa có UI). [C]

- **BR-ORD-05** Ưu tiên hiển thị đơn đặt trước; đơn đặt sau có thể chuẩn bị/giao trước nếu không làm trễ cam kết trước. Với đơn cũ chưa duyệt có tranh chấp công suất, Sales phải chuyển Dispatcher khi chưa chứng minh đủ năng lực; `held` không bảo đảm tuyệt đối.

### 6.3 Tồn kho và chuyển kho
- **BR-ATP-01** `usable = tồn hiện có − wms_reserved − giữ chỗ của đơn khác (held còn hạn + committed) + hàng nhập đã xác nhận về trước ngày cần (cộng thời gian nhận kho)`. [S][T]
- **BR-ATP-02** Hàng nhập chưa xác nhận không được tính. [S]
- **BR-ATP-03** Một kho xử lý trọn đơn; không tách đơn. [S][C]
- **BR-ATP-04** Kho không đủ hàng trong 14 ngày bị loại (`STOCK_SHORT`). [A]
- **BR-ATP-05** Thiếu hàng mọi kho → gợi ý chuyển kho bằng quy tắc (kho nguồn còn đủ hàng sẵn có, lead time ngắn nhất, gần nhất); dispatcher duyệt; kho nguồn xác nhận; mới tính là hàng nhập đã xác nhận. [C]

### 6.4 Chuẩn bị hàng
- **BR-PRP-01** Khối lượng việc theo công thức FR-PRP-01; giờ công của một đơn như nhau ở mọi kho. [S][C]
- **BR-PRP-02** Công suất ngày = Σ ca (người có mặt × giờ hữu ích) × 90% − việc đã đặt; bỏ ngày nghỉ và ngày lễ. [S][C]
- **BR-PRP-03 (đã bỏ ở v1.1)** ~~Ép buộc giờ thiết bị~~. Không có mã `PREP_NO_EQUIPMENT` trong MVP. [C]
- **BR-PRP-04** Quá giờ cắt lên hàng thì lên hàng ca đầu ngày làm việc kế. [S]
- **BR-PRP-05** Một nhân viên tại một thời điểm chỉ ở một nơi; manager/supervisor mặc định không tính vào công suất nhặt hàng. [C]

### 6.5 Giao hàng và gate
- **BR-DEL-01** Xe phải đủ tải trọng và thể tích, được chở nhóm hàng, đủ khả năng (crane, dump…) và rảnh. [S]
- **BR-DEL-02** Tài xế cùng kho, có mặt, bằng đủ hạng và còn hạn, tổng giờ trong ngày ≤ 9 giờ [A], không trùng chuyến.
- **BR-DEL-03** Thời gian chuyến = lên hàng + lái + dỡ; ETA phải nằm trong cửa sổ nhận hàng của ngày giao. [S]
- **BR-DEL-04** Phân loại dự trữ lập kế hoạch: `planning_reserve = đóng cửa sổ nhận hàng của ngày cuối được chấp nhận − ETA khả thi sớm nhất`; an toàn ≥ 2 ngày, sát 0 đến < 2 ngày, không khả thi < 0. Hạn khả thi không bị trừ buffer nên không loại oan phương án giao được. [C]
- **BR-DEL-05** Một xe chỉ chở **một đơn** trong một chuyến (không ghép đơn). Một đơn được dùng **nhiều xe** cùng kho; hàng chia theo tải và thể tích (một dòng có thể tách qua nhiều xe); các xe tới trong cùng cửa sổ, chênh nhau không quá 30 phút [A]; đơn `DELIVERED` khi mọi xe giao xong. [C]
- **BR-GATE-01** Chỉ ứng viên qua cả 5 check (stock, preparation, truck, site_date, safety) mới được xếp hạng. [S]

### 6.6 Xếp hạng và ngoại lệ
- **BR-RNK-01** Điểm = 0,5 × `n_km` + 0,5 × `n_fill` (min–max trong các phương án khả thi của cùng đơn); vùng bỏ qua: km chênh < max(2 km, 5%) hoặc mức đầy chênh < 5 điểm phần trăm thì coi là bằng nhau. [C]
- **BR-RNK-02** Xếp hạng: số xe ít hơn trước; hòa điểm: dự trữ lớn hơn → điểm phức tạp thấp hơn → ETA sớm hơn → xe nhỏ hơn mà vẫn đủ chứa (tổng tải nhỏ hơn) → mã xe nhỏ hơn. Đơn đã chiếm gần hết tải xe thì không cần ghép đơn (ghép đơn ngoài MVP). Điểm phức tạp = +1 mỗi: dùng hàng nhập chưa về, lên hàng dời ca, cần chuyển kho. [S][C]
- **BR-RNK-03** Trả 1 phương án tốt nhất + 2 thay thế (tối đa 2 phương án mỗi kho), kèm lý do. [S]
- **BR-RNK-04** Không có phương án: báo check hỏng xa nhất và ngày khả thi sớm nhất (tìm tối đa 14 ngày). [S][A]
- **BR-RNK-05** Đổi ngày chỉ khi có `date_negotiation.agreed` (người, kênh, giờ); `declined` → hủy được; `unreachable` → nhắc sau 24 giờ. [C]

### 6.7 Giữ chỗ và duyệt
- **BR-RES-01** Ba trạng thái giữ chỗ cho tồn kho, giờ công, xe, tài xế: `held` (đang được chọn, có hạn), `committed` (đã chọn), chưa ai chọn (không có dòng). [C]
- **BR-RES-02** Giữ chỗ cả 3 phương án; hàng và giờ công chỉ tính một lần cho (đơn, kho); xe và tài xế của các phương án cùng đơn được phép trùng, khác đơn thì không. [C]
- **BR-RES-03** Hạn giữ 15 phút, gia hạn tối đa 2 lần; hết hạn → `expired`. [C]
- **BR-RES-04** Lúc lập kế hoạch, giữ chỗ `held` **được phép vượt** tồn kho/công suất (không khóa). **Khi duyệt**, hệ thống tuần tự hóa theo (kho, sản phẩm) và (kho, ngày) rồi kiểm tra lại: tổng `committed` không bao giờ vượt khả dụng; hai dispatcher tranh cùng lượng hàng/giờ công thì đơn duyệt trước thắng, đơn sau nhận `409 RESOURCE_CONFLICT`. [C]
- **BR-APR-01** Duyệt kiểm lại mọi điều kiện trong một transaction; thất bại → `409 RESOURCE_CONFLICT`. [S]
- **BR-APR-02** Kế hoạch tay phải qua gate, có lý do và cờ KPI. [C]
- **BR-APR-03** Lập lại sau duyệt, xếp lại sau giao thất bại, hủy đơn: trong một transaction, kế hoạch cũ → `superseded`, giữ chỗ → `released`, chuyến/điểm dừng chưa xong → `cancelled`, ngày cam kết bị xóa (giá trị cũ ghi nhật ký). Lần duyệt mới gửi `CONFIRMED` mới cho khách. [C]
- **BR-APR-04** Gợi ý lập lại tự động không tạo giữ chỗ và không bao giờ tự duyệt; khi dispatcher duyệt, kế hoạch cũ được đóng và kế hoạch mới được kiểm tra lại, commit trong cùng một transaction. [C]

- **BR-APR-05** Sales chỉ duyệt đơn tiêu chuẩn rank-1 cùng cửa hàng, 5 gate pass, reserve safe, một xe, không thay ngày/ngoại lệ, dùng cùng transaction/locking/audit như Dispatcher.

### 6.8 Thực thi, rủi ro, thông báo
- **BR-EXE-01** Sự kiện chỉ thêm, đúng thứ tự trạng thái, có idempotency key; không có bước duyệt. [S]
- **BR-EXE-02** Giao thất bại không tính vào tỷ lệ đúng hạn; có lý do chuẩn. [C]
- **BR-EXE-03** Một đơn có thể giao nhiều lần (thất bại rồi giao lại); mỗi lần giao có bằng chứng (POD) riêng, giữ nguyên lịch sử. [C]
- **BR-RSK-01** `reserve_total = max(30 phút, promise_end − planned_eta)`; `consumption% = (forecast_eta − planned_eta) / reserve_total`; xanh < 33, vàng 33–66, cam > 66; `PREDICTED_LATE` khi `slack < 0` ở 2 lần tính liên tiếp; `OVERDUE` khi quá `promise_end` chưa giao. [C][T]
- **BR-RSK-02** Cam và trễ báo dispatcher; hệ thống chỉ tạo **bản nháp** báo trễ; dispatcher quyết định gửi. [C]
- **BR-NOT-01** Khách nhận: ngày và khung giờ đã xác nhận, đã xuất kho, đã giao/giao thất bại, báo trễ. [S]
- **BR-NOT-02** Chỉ báo trễ khi thay đổi có ý nghĩa: lệch ≥ 30 phút so với khung đã thông báo. [S][A]
- **BR-NOT-03** Không gửi 21:00–07:00 giờ địa phương, trừ báo trễ. [A]
- **BR-GPS-01** Chỉ dispatcher xem GPS; khách/CS không bao giờ; GPS chỉ bật khi `gps_enabled`; xóa 30 ngày sau chuyến; mất tín hiệu > 60 phút → alert; bản demo hiện "chưa có DPIA". [C][S]

### 6.9 Nhân sự và quyền
- **BR-EMP-01** Mỗi nhân viên `active` có đúng một phân công đang hiệu lực. [C]
- **BR-EMP-02** Mỗi kho/cửa hàng có đúng một quản lý chính; owner mặc định là quản lý. [C]
- **BR-EMP-03** Duyệt chuyển kho (nguồn), sửa ca, đóng ngoại lệ chỉ do quản lý có `can_approve` của kho đó. [C]
- **BR-EMP-04** Nhân viên thôi việc: khóa tài khoản, giữ lịch sử, ẩn danh sau hạn lưu giữ. [A]
- **BR-KPI-01** Không thêm vai trò; Business owner và Project lead đều là `viewer`, phân biệt bằng `kpi_scopes` (`revenue_all` / `ops`). **Doanh thu:** Business owner (mọi nơi, hai góc nhìn), owner cửa hàng (chỉ cửa hàng đó, góc nhìn store), owner kho (chỉ kho đó, góc nhìn warehouse), admin; người khác không xem; Business owner không xem KPI vận hành, nhật ký quyết định hay thông tin khách. **KPI vận hành:** admin, dispatcher, quản lý kho, Project lead (`ops`). Doanh thu ghi nhận = Σ `total_amount` của đơn `DELIVERED` theo ngày giao ở múi giờ market; đơn thất bại rồi giao lại chỉ tính một lần; mỗi nước tiền tệ riêng. **Giả định [A]:** chi phí giao hàng, lương nhân viên, ưu đãi giữa các nước khác nhau và nhóm thiếu số liệu, nên doanh thu chỉ là tổng giá trị đơn, không phải lợi nhuận. "Cost per delivery" của slide được thay bằng giờ công và km mỗi lần giao (KPI vận hành); so sánh "chi phí" giữa các phương án của một đơn do điểm xếp hạng đảm nhận (FR-RNK-01). [C]

---

## 7. Dữ liệu và tích hợp
Mô hình dữ liệu chi tiết ở `05_Database_Design.md`; hợp đồng API ở `06_API_Specification.md`. Thực thể chính: market, location (warehouse/store/…), handling_group, product_global + product_<cc>, customer, employee (+ 5 bảng con), attendance, vehicle, customer_order/order_line, planning_run/fulfilment_plan, các bảng giữ chỗ, delivery_trip/trip_stop, milestone_event, eta_forecast, alert, notification, vehicle_position, decision_log.

---

## 8. Yêu cầu phi chức năng
Hiệu năng (lập kế hoạch 1 đơn < 2 s; bảng đơn < 1 s với 1.000 đơn); tính đúng (không double-book; nạp lại idempotent); truy vết (tái lập mọi quyết định); mở rộng (thêm nước không sửa lõi); khả dụng khi ORS/nguồn lỗi (fallback + cờ dữ liệu cũ); truy cập WCAG AA cơ bản; bảo mật (RBAC phía máy chủ, không PII trong log, GPS chỉ dispatcher); ngôn ngữ giao diện tiếng Anh có i18n. Chi tiết ở `04`.

---

## 9. KPI thành công của pilot

| KPI | Định nghĩa ngắn | Mục tiêu |
|---|---|---|
| Thời gian lập kế hoạch mỗi đơn | Từ nộp đơn tới duyệt | Giảm so với baseline thủ công |
| Giao đúng hạn | Giao trong khung cam kết / đơn đã giao (thất bại tính riêng) | Tăng |
| Giờ công và km mỗi lần giao | Trung bình của kế hoạch đã duyệt | Theo dõi, không quy tiền |
| Sai số chuẩn bị | |thực tế − kế hoạch| | Giảm |
| Sai số ETA | |giao thực − ETA đầu| | Giảm |
| Tỷ lệ chấp nhận kế hoạch | Duyệt đúng phương án 1, không đổi / số duyệt | Tăng |
| Tỷ lệ giao thất bại | FAILED / (DELIVERED + FAILED) | Theo dõi |
| Mức dùng công suất | Giờ đã giữ `committed` / giờ khả dụng | Theo dõi |

Không công bố con số lợi ích trước khi đo baseline. Điều kiện **go/no-go để mở rộng** [S]: cải thiện đo được so với baseline đã thống nhất; tổng chi phí và tính khả thi vận hành chấp nhận được; dữ liệu đáng tin, trách nhiệm rõ, ngoại lệ kiểm soát được. Bước tiếp theo trước khi cam kết pilot: xác nhận dữ liệu baseline, ước tính chi phí, chủ sở hữu và tiêu chí thành công.

---

## 10. Phần mở rộng (ngoài MVP)

1. **Ghép đơn** (làm nếu còn thời gian): tối đa 3 điểm dừng, cùng kho và ngày, cửa sổ nhận hàng có phần chung, độ vòng ≤ 25% so với đi thẳng, không quá tải xe; đơn lớn (≥ 60% xe lớn nhất) đi riêng; đơn nhỏ giữ chờ ghép nhưng không quá "giờ xuất phát muộn nhất" của chính nó; cộng thêm thời gian dỡ cho mỗi điểm dừng; dùng `delivery_trip`/`trip_stop` đã có sẵn.
2. **Cửa hàng làm nguồn hàng** kèm xe riêng cửa hàng và công suất cửa hàng.
3. **AI:** gợi ý ánh xạ sản phẩm, tinh chỉnh nhóm xử lý/định mức/hệ số hiệu suất kho, dự báo ETA và rủi ro trễ, gợi ý chuyển kho học từ lựa chọn thực tế, giải thích kế hoạch bằng ngôn ngữ tự nhiên, dispatcher copilot.
4. **Trang trạng thái đơn** cho khách (chỉ trạng thái và ETA).
5. **Nhiều kho/nhiều chuyến**, OR-Tools, Drools/Camunda.
6. **SMS thật** (nhà cung cấp EU), kênh thông báo theo nước.
7. **App tài xế native**, ảnh POD (lưu trữ blob), GPS nền.
8. **Ghi ngược vào WMS/TMS**, CDC thay polling, adapter thật cho POS/WMS/ERP.
9. **Geocoding thật**, địa chỉ tự do.
10. **Thêm nước** (Đan Mạch, Na Uy, Phần Lan): onboarding 6 bước, cấu hình, bảng sản phẩm, adapter.
11. **VIP rule**, ưu tiên khách, tự phục vụ đổi lịch.
12. **UI hệ số hiệu suất kho**; vai trò Goods-in clerk, Fleet coordinator, Master data steward.

---

## 11. Triển khai nhiều nước và quản trị [S]

- **Một gốc nguyên nhân, nhiều điểm vào.** Thị trường fulfilment-critical (điểm vào: ATP + công suất + ETA → ngày đáng tin); process-heavy (một luồng kế hoạch + duyệt → ít làm lại); store-operations-heavy (góc nhìn mốc cửa hàng → nhất quán). Rủi ro tương ứng: quyền truy cập dữ liệu; mã nguồn/sản phẩm khác nhau; luật lao động, tham vấn nhân viên.
- **Nước mới = adapter mới + cấu hình mới.** Quy tắc là dữ liệu cấu hình (ngày làm việc, giờ cắt, giờ nhận hàng, luật lao động, lịch lễ, ngôn ngữ, sender SMS, buffer, thời gian lưu giữ, VIP).
- **Playbook onboarding 6 bước:** (1) đánh giá sẵn sàng: chấm nỗi đau, quyền truy cập dữ liệu, chủ sở hữu, giới hạn pháp lý; chọn điểm vào; (2) nối dữ liệu: adapter cho POS/WMS/ERP địa phương, ánh xạ mã sản phẩm sang `canonical_id`; (3) cấu hình địa phương; (4) **chạy bóng**: chạy song song, dispatcher vẫn quyết định, đo baseline và KPI (cờ `shadow_mode` chặn gửi thông báo khách); (5) go live: huấn luyện, chế độ hỗ trợ, dispatcher giữ quyền duyệt cuối; (6) xét duyệt: chỉ sang nước tiếp theo khi KPI đạt và quyền truy cập dữ liệu được xác nhận.
- **Quản trị:** chủ sở hữu địa phương mỗi nước; cùng một bộ KPI mọi nơi; tham vấn nhân viên khi luật yêu cầu; DPIA trước khi dùng GPS thật. Vai trò: Business/Operations sở hữu KPI, Warehouse Manager xác nhận tồn kho và công suất, IT đảm bảo chất lượng tích hợp, Dispatcher duyệt kế hoạch và xử lý ngoại lệ, Project Lead theo dõi phạm vi, tiến độ, rủi ro.
- **Chi phí (danh mục chỉ định) [S]:** một lần (phát triển tích hợp, cấu hình, ánh xạ dữ liệu, kiểm thử, triển khai); định kỳ (hosting, DB, giám sát, API bản đồ, SMS/email); vận hành và thay đổi (thời gian nhân viên, huấn luyện, cập nhật quy trình, hỗ trợ, bảo trì). Chi phí thật cần khảo sát và báo giá nhà cung cấp.

---

## 12. Giả định, ràng buộc, rủi ro

| # | Mục | Xử lý |
|---|---|---|
| 1 | POS/WMS/ERP và dữ liệu đội xe truy cập được [T] | MVP dùng hệ thống nguồn giả lập; kiểm chứng với dữ liệu thật ở pilot |
| 2 | Kho cung cấp được chuẩn lao động và ca ban đầu [T] | Dùng định mức mẫu [A]; IT thay bằng số thật |
| 3 | Company A kiểm soát kho, cửa hàng, lịch xe [T] | Hãng vận tải ngoài là phần mở rộng |
| 4 | Dữ liệu tồn kho/hàng nhập đủ tươi (5 phút) | Cờ dữ liệu cũ sau 15 phút; adapter có thể đổi sang CDC |
| 5 | Chất lượng ánh xạ sản phẩm | Hàng đợi IT, quy tắc gợi ý, chặn đơn rõ ràng |
| 6 | **GPS tài xế là dữ liệu cá nhân người lao động** | Cờ theo nước, DPIA, tham vấn nhân viên, chỉ dispatcher, chỉ khi chuyến `on_road`, xóa 30 ngày; cơ sở pháp lý dự kiến là lợi ích hợp pháp/thực hiện hợp đồng (không dựa vào "đồng ý"), cần pháp lý xác nhận khi pilot; PWA chỉ định vị khi mở app (iOS hạn chế) nên dùng bộ giả lập demo; app native là phần mở rộng |
| 7 | Giới hạn free-tier (Render ngủ, Supabase tạm dừng, ORS quota) | Ping 5 phút; ma trận lộ trình tính trước và cache; kiểm tra lại giới hạn trước khi deploy |
| 8 | Khách DN thật sự nhạy giao hàng nhất (A1) | Phỏng vấn khách trong pilot |
| 9 | Các hằng số [A] (giờ hữu ích, định mức, tốc độ, hệ số cờ…) chưa đo thực tế | Cấu hình được; hiệu chỉnh bằng `improvement_log` sau pilot |
| 10 | Slide cần đồng bộ: GPS đưa lên MVP; nhóm xử lý bằng quy tắc cứng, AI giai đoạn sau | Xem mục 13 |

---

## 13. Đối chiếu với slide proposal (dùng cho báo cáo)

### 13.1 Các quyết định chốt khi khác slide

| # | Chủ đề | Slide proposal | MVP (chốt) | Lý do |
|---|---|---|---|---|
| 1 | Nhóm xử lý N1–N6, cờ | AI gợi ý từ thuộc tính ERP, **quản lý kho** duyệt | Bảng quy tắc cứng; **IT** nhập định mức và xác nhận; AI ở giai đoạn 2 | Chưa có số liệu kho thật; dữ liệu `improvement_log` làm nền cho AI sau này; một bộ định mức chung tránh lệch giữa các nước |
| 2 | Xếp hạng | Cheapest feasible plan / lowest cost | `0,5 × n_km + 0,5 × n_fill` (min–max), thấp hơn tốt hơn | "Rẻ" = gần kho (chi phí vận chuyển) và kho không quá tải; không quy tiền vì thiếu số liệu chi phí |
| 3 | Hòa điểm | Delivery buffer lớn hơn, thao tác đơn giản hơn | Ít xe hơn → dự trữ lập kế hoạch → điểm phức tạp → ETA sớm → xe nhỏ hơn mà đủ chứa | Buffer không cộng vào thời gian chuyến (BR-DEL-04); xe nhỏ hơn gần nghĩa "rẻ" hơn |
| 4 | GPS tài xế | Ngoài MVP, sau đánh giá GDPR | Trong MVP; chỉ dispatcher; chỉ khi `on_road`; xóa 30 ngày; DPIA trước khi dùng thật | Giá trị phát hiện trễ sớm; giả định cơ sở pháp lý ở FR-GPS-01 |
| 5 | Tech stack | Azure (EU), Azure Maps, SMS/email EU | Supabase/Render/Vercel, OpenRouteService, Mailpit/Brevo, SMS mô phỏng; lõi giống (PostgreSQL, Python, React, PWA) | MVP mô phỏng nên dùng công cụ miễn phí; provider nằm sau interface |
| 6 | Thời gian | 6 tuần | Không cố định, làm xong càng nhanh càng tốt (lịch 7 ngày ở `08` chỉ tham khảo) | — |
| 7 | Thiết bị kho | Equipment-level scheduling ngoài MVP | **Bỏ** (khớp slide); năng lực cẩu/ben là thuộc tính xe | Chưa biết thiết bị cụ thể và cách dùng |
| 8 | KPI chi phí | Cost per delivery | Giờ công và km mỗi lần giao; doanh thu là màn riêng (chỉ tiền hàng), quyền theo `kpi_scopes` và owner | Thiếu số liệu chi phí theo nước |
| 9 | Đơn nhiều xe | Multi-truck optimisation ngoài MVP; manual fallback | **Có trong MVP ở mức một đơn:** gợi ý cơ cấu xe ít nhất, xếp lịch nhiều xe cùng kho, tới gần như cùng lúc; không ghép đơn | Đơn vật liệu xây dựng lớn hay vượt một xe; không muốn đơn bị kẹt |
| 10 | Giữ chỗ đồng thời | — | Lập kế hoạch cho vượt, chỉ chặn khi duyệt | Lập kế hoạch nhanh, cam kết vẫn đúng |
| 11 | Lập lại sau duyệt | Dispatcher xử lý | Hệ thống tự gợi ý phương án mới, dispatcher duyệt | Giảm thao tác, vẫn giữ quyền quyết định |

### 13.2 Các khác biệt khác

| Chủ đề | Slide proposal | MVP |
|---|---|---|
| Thời gian chuyến | Lên hàng + lái + dỡ + buffer | Không cộng buffer; dự trữ chỉ dùng phân loại an toàn/sát |
| Tích hợp | API polling ~5 phút, dự phòng CSV qua SFTP | API hệ thống nguồn giả lập; dự phòng tải CSV lên |
| Công suất kho | Người × giờ năng suất − việc đã đặt | Thêm tỷ lệ 90% dành cho đơn giao |
| Báo trễ | Gửi khi thay đổi có ý nghĩa | Hệ thống tạo nháp, **dispatcher bấm gửi**; ngưỡng lệch ≥ 30 phút |
| KPI | Planning time, on-time, cost per delivery, prep error, ETA error, plan acceptance; trang 10 thêm manual interventions/order, rollout effort, shared component reuse | 8 KPI (6 của slide + giao thất bại + mức dùng công suất); manual interventions ≈ `manual_plan_count`; rollout effort và component reuse đo ở giai đoạn mở rộng (MVP chỉ một nước) |
| Chuyển kho | Không nhắc | Gợi ý chuyển kho bằng quy tắc (vẫn một kho xử lý trọn đơn) |
| Giờ công | Theo đơn vị chuẩn bị | Quy về đơn vị cơ sở nhỏ nhất; hàng không chia nhỏ được thì làm tròn lên |
| Dữ liệu cho AI | Học từ thực tế | Giờ nhân công/đơn vị cơ sở theo nhóm, thu qua bắt đầu/tạm dừng/tiếp tục/xong |
| Vai trò | Không tách CSKH | Thêm Customer service tách khỏi sales |
| Ngày yêu cầu | Một ngày | Ba dạng: exact / range / latest |
| Phạm vi pilot | 2–3 kho, 20–30 cửa hàng, ~100 SKU | 3 kho, 25 cửa hàng, ~100 SKU (khớp) |

**Giữ nguyên như slide:** khách không thấy GPS; không tự duyệt thay dispatcher; không tự đổi ngày khi khách chưa đồng ý; một kho xử lý trọn đơn; gate 5 check; best + 2 alternatives kèm lý do; nhật ký mọi quyết định; chạy bóng (shadow mode); nước mới = adapter mới + cấu hình.

### 13.3 Việc cần đồng bộ trên slide
- Slide MVP & Implementation, mục 03: bỏ "live GPS integration" khỏi danh sách ngoài MVP; thay bằng "native driver app".
- Slide Execute and feed back: "Later: dispatcher-only live GPS (GDPR review)" → GPS trong MVP, DPIA trước khi dùng thật.
- Slide MVP và W3: "AI-suggested handling groups" → nhóm xử lý bằng quy tắc cứng do IT xác nhận; AI giai đoạn 2.
- Slide "3 checks…" và W4: "Cheapest feasible plan / cost ranking" → "Lowest score (distance + warehouse load)"; KPI "cost per delivery" → "labour hours & km per delivery".

## 14. Thuật ngữ

**ATP** (available-to-promise): lượng hàng có thể hứa theo thời gian. **Dispatcher**: người duyệt kế hoạch giao hàng. **Gate**: chuỗi 5 check bắt buộc. **Giữ chỗ (hold)**: khóa tạm tài nguyên cho một phương án. **Cam kết (commit)**: giữ chỗ chính thức sau khi duyệt. **Dự trữ lập kế hoạch**: khoảng cách giữa ETA khả thi sớm nhất và hạn của khách. **Dự trữ cam kết**: khoảng giữa ETA kế hoạch và hết khung hứa với khách, dùng để theo dõi rủi ro. **Nhóm xử lý (handling group)**: N1–N6 theo kiểu bốc xếp. **Đơn vị chuẩn bị**: line/pallet/m³/bó/kiện. **POD**: bằng chứng giao hàng. **Shadow mode**: chạy song song, không gửi thông báo khách.
