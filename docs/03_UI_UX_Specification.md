# 03 — UI/UX Specification (CFO MVP)

> **Phiên bản 1.1 (06/11/2026):** đã đối chiếu lại toàn bộ 23 trang `CFO_Web_Platform_UI.pdf`. Bổ sung các điều chỉnh #25–#36 ở mục 7 (chỗ thiết kế khác quy tắc mà bản 1.0 chưa ghi); bỏ màn và thành phần thiết bị kho; thêm form "Handled outside CFO" và panel doanh thu.
>
> Đặc tả giao diện cho agent code, dựa trên bộ thiết kế `CFO_Web_Platform_UI.pdf` của nhóm design (23 trang, 12 màn hình + ngôn ngữ hình ảnh). **Bố cục, hệ thống hình ảnh, thành phần và nội dung chữ theo bản thiết kế.** Chỗ bản thiết kế khác với quy tắc nghiệp vụ đã chốt thì **làm theo quy tắc nghiệp vụ** (`01_PRD.md`), mọi điều chỉnh liệt kê ở mục 7. Hợp đồng dữ liệu ở `06_API_Specification.md` (kèm Phụ lục A). Bản thiết kế dùng dữ liệu minh họa; số, mã, tên trong ảnh là ví dụ.

## 1. Nguyên tắc thiết kế

1. **Một kế hoạch bạn duyệt**: mọi đơn đi từ nhận đến giao qua một kế hoạch dispatcher quyết định; giao diện luôn trả lời "đơn đang ở đâu, vì sao, tôi cần làm gì".
2. **Giải thích được**: mỗi phương án có 5 check, lý do bị loại, mã lý do; mỗi cảnh báo nói rõ vì sao.
3. **Dữ liệu có nguồn và độ tươi**: luôn hiện "Data as of …" và nguồn đồng bộ.
4. **Không bao giờ lộ GPS cho khách/CS**; GPS chỉ hiện ở màn của dispatcher.
5. **Màu không là tín hiệu duy nhất**: trạng thái rủi ro khác nhau về độ sáng, kèm nhãn chữ, đọc được ở thang xám.
6. **Một hành động lớn mỗi bước** trên điện thoại (tài xế).
7. **Bản demo luôn có banner "DEMO · SYNTHETIC DATA"** (bật theo `APP_ENV != production`).

## 2. Ngôn ngữ hình ảnh (design tokens)

### 2.1 Màu

| Token | Hex | Dùng cho |
|---|---|---|
| `deep-pine` | `#0B2E2B` | Thanh điều hướng, thanh quyết định, nền panel đăng nhập |
| `pine` | `#0F4D47` | Hành động chính, trạng thái hoàn thành |
| `apricot` | `#E07B39` | Chú ý, hành động quan trọng (Approve, Mark dispatched, Replan), số huy hiệu |
| `stone` | `#F4F2ED` | Nền trang |
| `ink` | `#14201F` | Chữ |
| `surface` | `#FFFFFF` | Card, bảng |
| `border` | `#E3DFD6` | Viền card, đường kẻ bảng |
| `ink-muted` | `#56625F` | Chữ phụ |
| `demo-bar` | `#14201F` (nền) + chữ `#F4F2ED`, chấm `#E07B39` | Banner demo |

**Trạng thái rủi ro** (khác nhau về độ sáng, không chỉ sắc độ):

| Trạng thái | Nền | Chữ | Màu API |
|---|---|---|---|
| On track | `#E0EEEA` | `#0E4A44` | `green` |
| At risk (vàng) | `#FCE8CC` | `#7A4106` | `yellow` |
| At risk (cam) | `#FCE8CC` + viền trái `#E07B39` 3px | `#7A4106` | `orange` |
| Predicted late | `#F9DBD2` | `#8F2710` | `red` (PREDICTED_LATE) |
| Overdue | `#7A1F10` | `#FFFFFF` | `red` (OVERDUE) |

Mức xanh/vàng/cam/đỏ lấy từ `eta_forecast.risk_color`; nhãn chữ lấy từ `risk_status`. Hàng của đơn `Predicted late` trong bảng có nền `#FFF4EE`. Chip trạng thái đơn (PREPARING, LOADED…) dùng nền `#ECE9E1`, chữ `ink`, phông mono; chip `NO_FEASIBLE_DATE` dùng bộ màu Predicted late; chip `MANUAL`/cảnh báo ánh sáng dùng bộ At risk; chip `DELIVERED`/`APPROVED` dùng bộ On track.

### 2.2 Chữ
- **Schibsted Grotesk** (Google Fonts) cho tiêu đề, nhãn, thân chữ. Dự phòng: `Arial, sans-serif`.
- **JetBrains Mono** cho số đơn, giờ, số đo, mã lý do, nhãn nhỏ viết hoa. Dự phòng: `Courier New, monospace`.
- Thang chữ: H1 36/40 bold (tiêu đề trang) · H2 22/28 bold (tiêu đề card) · H3 16/22 semibold · body 14/20 · caption 12/16 · overline mono 11/14 uppercase, tracking +0,08em, màu `ink-muted` hoặc `apricot` cho nhãn nhấn.
- Số liệu lớn (giờ ETA, KPI): mono 32–48 bold. Đơn vị đi kèm (`min`, `%`, `SEK`) nhỏ hơn và màu `ink-muted`.

### 2.3 Hình khối
- Bo góc: card 16px, nút/chip/input 10px, chip trạng thái bo tròn hoàn toàn (pill).
- Viền 1px `border`; không đổ bóng đậm (tối đa `0 1px 2px rgba(20,32,31,.06)`).
- Khoảng cách: lưới 8px; padding card 20–24px; khoảng giữa card 16–24px; chiều rộng nội dung tối đa 1440px.
- Logo: vòng tròn rỗng màu `apricot` nối dấu chấm (biểu tượng đơn–giao), cạnh chữ "CFO" và dòng phụ "Central Fulfilment Orchestration".
- Biểu tượng: bộ đường nét 1,5px đơn giản (lucide-react) — thoát (log-out), tìm kiếm, mũi tên →, dấu ✓ ✕.

## 3. Khung ứng dụng và điều hướng

### 3.1 Bố cục
- **Sidebar** rộng 262px nền `deep-pine`, chữ sáng. Trên cùng: logo; bộ chọn **Market** (thẻ "Sweden · SE / Europe/Stockholm · SEK", có mũi tên xổ) — với vai trò kho thay bằng bộ chọn **Warehouse** ("Göteborg DC / Sweden · cut-off 15:00"). Dưới: nhóm menu theo vai trò, rồi khối người dùng (avatar tròn `apricot` với chữ cái đầu, tên, email mono, nút thoát).
- **Banner demo** cao 38px phía trên nội dung: chấm `apricot` + "DEMO · SYNTHETIC DATA" (mono) + câu ngữ cảnh riêng từng màn.
- **Thanh trên** (chỉ màn danh sách): ô tìm kiếm "Search order no., customer or SKU" bên trái; bên phải "Data as of **10:05** · next sync 10:10" (lấy từ `sync_run.data_as_of` mới nhất; cờ vàng khi quá 15 phút).
- **Tiêu đề trang**: overline mono (ví dụ `DISPATCHER · SWEDEN`) → H1 → mô tả một dòng.
- **Breadcrumb** ở màn chi tiết: `Order queue / SE-2026-000123` (liên kết + mono).

### 3.2 Menu theo vai trò (huy hiệu là số đếm từ `GET /orders/counts`)

| Nhóm | Mục | Hiện cho |
|---|---|---|
| **DISPATCHER** | Order queue (huy hiệu: đơn cần xử lý) · Plan review (đơn chờ duyệt) · Exceptions (NO_FEASIBLE_DATE, MANUAL_PLANNING, BLOCKED_UNMAPPED_SKU) · Tracking & risk (đơn cam/đỏ) · Transfers · KPIs & decision log | dispatcher; `viewer` thấy KPIs & decision log |
| **SALES** | New order (mở ứng dụng POS giả lập) · My store orders (chỉ xem) | sales, store manager |
| **WAREHOUSE** | Prep queue · Attendance & shifts · Transfers (kho nguồn/đích) | quản lý/phó/trưởng ca kho (thiết kế gộp "Prep queue & mapping"; phần mapping chuyển sang ADMIN, xem #15) |
| **CUSTOMER SERVICE** | Order lookup · Contact log | customer_service |
| **ADMIN (IT)** | Data integration · Product mapping · Handling groups & norms · Employees & locations · Vehicles & drivers · Users · Market config & GPS · Notification inbox | admin; dispatcher và CS đọc Notification inbox |
| **Driver** | Không dùng sidebar: ứng dụng PWA riêng (mục 5.11) | driver |

Mục đang chọn: nền `#E8F1EF`, chữ `deep-pine`, bo 10px; mục chưa chọn chữ sáng 80%. Huy hiệu tròn `apricot`, chữ mono nhỏ.

## 4. Thành phần dùng chung

| Thành phần | Mô tả và hành vi |
|---|---|
| **Status chip** | Pill mono 11px; mã trạng thái đơn viết hoa đúng enum (thiết kế viết tắt `MANUAL`, `IN PREP` → hiển thị `MANUAL_PLANNING`, `PREPARING`; `HANDLED_EXTERNALLY` dùng bộ màu trung tính `#ECE9E1`) |
| **Risk chip** | Theo bảng 2.1, có chấm tròn trước chữ; `aria-label` đọc đủ nhãn |
| **Filter chips** | Hàng chip có đếm (mono) ví dụ `All 34 · Needs plan 6 · Awaiting approval 4 · No feasible date 1 · In execution 12 · Manual 2 · Delivered today 9`; chip chọn nền `ink` chữ trắng |
| **Journey bar** | 6 đoạn ngang: Approved · Prep · Goods ready · Loaded · Dispatched · Delivered. Đoạn xong `pine`, chưa tới `#E3DFD6`, **đoạn quá mốc kế hoạch `apricot`** (chú thích "Milestone overdue") |
| **Check chip** | `✓ Stock` nền On track, `✕ Truck` nền Predicted late; dưới chip lỗi hiện mã mono (ví dụ `NO_TRUCK_FIT`) |
| **Plan card** | Mục 5.3 |
| **Timeline mốc** | Chuỗi nút tròn nối đường: xong (đặc `pine`), chưa (rỗng), quá hạn (viền `apricot`); mỗi nút ba dòng: tên, `plan hh:mm`, `actual/fcst` |
| **Decision bar** | Thanh nền `deep-pine` bo 16px dưới cùng trang, có tiêu đề, mô tả hệ quả, nút `apricot` bên phải |
| **Bảng** | Tiêu đề cột mono uppercase 11px; hàng cao 72–90px; hover nền `#FAF8F4`; cột đầu mã đơn mono đậm |
| **Overline label** | Mono uppercase 11px |
| **Modal xác nhận có lý do** | Dùng cho: chọn phương án khác, đổi tiêu chí/chạy lại, kế hoạch tay, hủy/lập lại đơn, bỏ bản nháp báo trễ, từ chối ánh xạ, ghi nhận xử lý ngoài CFO. Gồm danh sách mã lý do (select) + ô ghi chú, nút xác nhận chỉ bật khi đủ |
| **Form xử lý ngoài CFO** | Khối trong màn nhập tay (5.2), chỉ khi đơn `MANUAL_PLANNING` và gate báo không xe nào vừa; mã lý do + ghi chú bắt buộc; nút xác nhận chỉ bật khi đủ |
| **Toast** | Góc phải trên, tự tắt 5 giây; lỗi `409 RESOURCE_CONFLICT` thì giữ lại và có nút "Re-run plan" |
| **Trạng thái rỗng/tải/lỗi** | Rỗng: biểu tượng + một câu ("No orders match these filters") + hành động; tải: skeleton cùng kích thước thật; lỗi: khung `Predicted late` nhạt, nút "Retry" và `correlation_id` (mono, chép được) |
| **Mask dữ liệu cá nhân** | Email hiện `u•••@takservice.demo`; điện thoại `+46 •• ••• 12 34`; chỉ vai trò được phép mới thấy đầy đủ |

## 5. Màn hình

Mỗi màn: mục đích · vai trò · dữ liệu · bố cục · hành động · trạng thái đặc biệt. Số thứ tự `00–11` theo bản thiết kế; `A1…` là màn **bổ sung** cần dựng vì chưa có trong thiết kế (cùng ngôn ngữ hình ảnh).

### 5.0 — 00 Sign in
- **Bố cục:** hai nửa. Trái nền `deep-pine`: logo; overline `ORDER-TO-DELIVERY ORCHESTRATION`; tiêu đề "Make every order a reliable, visible promise."; đoạn mô tả; ba mục đánh số 01 Time-phased inventory / 02 Warehouse readiness / 03 Fleet & delivery; chân trang mono "Sweden pilot · synthetic data · v0.1-demo". Phải nền `stone`: "Sign in", "Use your work account. Access follows your role.", ô Email (`name@company.se`), Password, nút `pine` "Sign in".
- **Demo accounts:** lưới thẻ nhỏ có mũi tên → bấm là điền sẵn tài khoản: Dispatcher ("Plans & approvals"), Sales ("Order intake"), Warehouse ("Prep & milestones"), Driver ("PWA on phone"), Admin ("Data & inbox"), **thêm Customer service ("Status & contact log")** và **Business owner ("KPIs, read-only")**. Chỉ hiện ở môi trường demo.
- **Chân:** "Customers have no login. They receive order status and ETA by email or SMS — never driver location."
- API: `POST /auth/login`; sai → thông báo dưới form, `429` hiện "Too many attempts, try again in a minute".

### 5.1 — 01 Order queue (dispatcher)
- **Dữ liệu:** `GET /orders` + `GET /orders/counts` + `GET /alerts?resolved=false` + trạng thái nguồn (`GET /integration/overview`).
- **Bố cục:** cột trái rộng (bảng đơn), cột phải 330px (Risk alerts, Source data).
- **Mô tả dưới H1:** "Wednesday 4 November 2026 · Every order moves from intake to goods received through one plan you approve." (ngày lấy từ `clock.now()` theo múi giờ market).
- **Bảng "Orders — Sorted by requested date"**, cột theo thiết kế: ORDER (mã mono xuống dòng + kho nguồn bên dưới; đơn chưa có nguồn hiện "No source yet"; PLANNED hiện "3 feasible plans"; SUBMITTED hiện "Submitted 09:41") · **CUSTOMER · SITE** (một cột: tên khách đậm, dòng dưới địa điểm) · REQUESTED (ngày: `Today`/`Thu 5 Nov` + khung giờ mono hoặc "Site hours" nếu chỉ có ngày) · STATUS (chip) · JOURNEY (journey bar; NO_FEASIBLE_DATE hiện "Earliest **Thu 12 Nov**"). **Bổ sung** (không có trong thiết kế): cột cuối hẹp hiện chip rủi ro (cho người không phân biệt màu nền hàng). Đơn Predicted late có nền hàng `#FFF4EE`. Chân bảng có chú giải Journey.
- **Panel Risk alerts (n open):** thẻ cảnh báo màu theo mức: `Predicted late` (giờ, tiêu đề `SE-… · ETA 13:15 vs close 12:30`, mô tả nguyên nhân), `At risk`, và thẻ trung tính cho sự kiện hệ thống (ví dụ `PLAN_INVALIDATED`: "Malmö DC stock update — 2 approved plans re-checked; SE-… still passes. No action needed."). Bấm thẻ → màn 04.
- **Panel Source data:** POS orders, WMS stock & inbound, Fleet calendar, ERP products kèm giờ đồng bộ cuối (lấy `data_as_of` thật; ảnh thiết kế có Fleet 09:00 và ERP 06:00 vì chạy theo giờ/ngày, MVP chạy mọi nguồn theo `sync.interval_min`, xem #31); liên kết "View integration runs".
- **Tương tác:** bấm hàng → màn 02 (PLANNED), 03 (NO_FEASIBLE_DATE), 04 (APPROVED trở đi). Chip lọc đổi `status`. Tìm kiếm theo mã đơn, khách, SKU.

### 5.2 — 02 Plan review & approval (dispatcher)
- **Dữ liệu:** `GET /orders/{id}`, `GET /planning-runs/{id}` (gồm `plans`, `rejected_candidates`).
- **Banner demo:** "Route times from a pre-computed OpenRouteService matrix. Ranking uses distance and warehouse load, not money." (bỏ "Costs are illustrative (SEK)").
- **Đầu trang:** breadcrumb; chip `PLANNED`, `ORDER v1`, `RUN 412 ms`; H1 **"3 feasible plans for Tue 10 Nov"**; dòng khách · địa điểm · giờ nhận · số dòng, kg, m³.
- **Thứ tự phương án có thể khác ảnh:** thiết kế xếp Göteborg 12 t → Malmö 18 t (262 km) → Göteborg 18 t theo tiền. Với điểm `0,5·n_km + 0,5·n_fill`, hai phương án cùng kho Göteborg có cùng km và cùng mức đầy nên thường đứng #1, #2 (phân định bằng tie-break), Malmö xa nhất xuống #3. UI hiển thị đúng thứ tự `rank` từ API, không cố khớp ảnh.
- **Dải 3 bước:** (1) Feasibility "9 candidates checked · 3 pass all 5 hard checks" (2) Ranking "Lowest score first. Tie-break: larger planning reserve, then simpler operation" (3) **Your decision** (nền `#FFF4EE`) "Approve, pick an alternative, change criteria or plan manually".
- **Ba plan card** (rộng bằng nhau; card #1 viền `pine` 2px):
  - Nhãn: `Recommended · #1` (pill `pine`) / `Alternative · #2`, `#3`; nhãn phụ mono bên phải (`Lowest score`, `Shortest drive`, `Same source` — sinh từ khác biệt nổi bật).
  - Tên kho (H2); dòng "Truck 12 t · GBG-12-03 · 48 km".
  - **Số lớn chính: điểm xếp hạng** (`score`) hoặc, theo thiết kế, một con số nổi bật. *Thay con số tiền bằng* **`0.26` + nhãn "rank score"** và hai số phụ: `48 km` và `Fill 60%`.
  - Hàng 5 check chip (✓ Stock, ✓ Prep, ✓ Truck, ✓ Site/date, ✓ Safety).
  - Lưới 2×2: Goods ready · Depart · ETA · Site closes (mono). Dưới: **"Slack before site closes 85 min"** (cửa sổ đóng − ETA) và **"Planning reserve 3.6 d · Safe"** (chip theo `reserve_class`: Safe nền On track, Tight nền At risk).
  - Thanh tiến độ mảnh thể hiện mức đầy công suất kho (60%).
  - Đoạn giải thích (từ `explanation`); khối mono chi tiết: `Prep 10.15 h · fill 60% · 12.0 km · drive 1 h 50 · reserve 5 220 min`.
  - Nút: card #1 "Approve plan" (`pine`), card #2/#3 "Select this plan" (viền).
  - Nếu `route_provenance = fallback`: chip vàng "Estimated route" kèm tooltip.
- **Bảng "Why other candidates were not ranked"** (`rejected_candidates`, "6 rejected · 4 shown", nút "Show all 6"): CANDIDATE (kho + xe) · FAILED CHECK (chip ✕ + mã mono) · DETAIL (câu giải thích có số: "Order weighs 4 120 kg; van carries 3 500 kg.").
- **Panel Route options:** sơ đồ minh họa kho–điểm giao với thời gian đường (nguồn `route_matrix`, ghi "ORS matrix · <ngày tính>"). Ghi chú "Schematic. Live map tiles (OpenStreetMap) are a later phase" **được thay bằng bản đồ Leaflet/OSM** ở màn tracking (5.4); ở màn này giữ sơ đồ.
- **Panel "Change criteria and rerun":** "Creates a new planning run; current plans become superseded. Logged as CRITERIA_CHANGED_RERUN." Điều khiển: **"Optimise for"** (xem mục 7: thay "Lowest cost / Largest buffer" bằng preset trọng số **Balanced 50/50 · Shortest distance 80/20 · Lowest warehouse load 20/80** và ô tùy chỉnh trọng số), **Exclude warehouse** (checkbox từng kho), **Try date** (chỉ cho dạng `range`/`latest`, trong tập ngày khách chấp nhận), nút "Rerun plan" → modal lý do.
- **Panel "Manual fallback":** "Choose warehouse, truck and times yourself. A reason is required; checks still run and warnings stay visible. Flagged in KPIs." Nút "Plan manually" → màn nhập tay (chọn kho/xe/tài xế/giờ + mã lý do).
- **Màn nhập tay, khi đơn `MANUAL_PLANNING` (v1.1):** nếu gate trả `422` kèm `details.hint = "EXTERNAL_HANDOFF"` (không xe nào trong đội vừa), hiện khối **"Handled outside CFO"**: "This order needs more than one truck or a vehicle outside the fleet. CFO does not plan multi-truck deliveries in the MVP. Record how it is handled; no confirmation is sent automatically." Trường: mã lý do (`multi_vehicle`, `special_vehicle`, `partner_haulier`, `other`), ghi chú lý do (bắt buộc), đối tác/hãng vận tải, ngày dự kiến, ghi chú bàn giao. Nút `apricot` "Record external handoff" → `POST /orders/{id}/external-handoff`; đơn chuyển `HANDLED_EXTERNALLY`.
- **Decision bar:** "**Approve the recommended plan** — Reserves 4 stock lines, 148 prep minutes at Göteborg on Tue 10 Nov and GBG-12-03 from 10:48 to 13:40 in one transaction. The customer gets a confirmation; every decision is logged." Nút `apricot` **"Approve #1"** (bỏ số tiền). Khi chọn phương án khác trong card #2/#3: thanh đổi thành "Approve plan #2…" và mở modal lý do bắt buộc.
- **Bộ đếm hold:** chip "Hold expires in 11:42" (mono), nút "Extend (+15 min, 2 left)". Hết hạn: chip đỏ nhạt, vẫn cho duyệt (hệ thống kiểm tra lại), kèm cảnh báo.
- **Khi `reserve_class = tight`:** hộp tick "I accept the tight schedule" bắt buộc trước khi Approve.
- **Khi duyệt `409 RESOURCE_CONFLICT`:** toast giữ lại + nút "Re-run plan".

### 5.3 — 03 No feasible date (dispatcher)
- **Đầu trang:** chip `NO_FEASIBLE_DATE`, `ORDER v1`; H1 **"No plan meets Mon 9 Nov"**; dòng khách · địa điểm · giờ nhận · số dòng/kg/m³.
- **Thẻ "EARLIEST FEASIBLE DATE"** (nền `#FFF4EE`): ngày lớn "Thu 12 Nov"; dòng "Malmö DC · Truck 12 t MLM-12-02 · ETA 09:40 · 18 km" (**bỏ giá tiền**); giải thích phụ thuộc ("Relies on confirmed inbound IN-SE-88213…"); lời dặn "Discuss the new date with the customer. CFO proposes dates; it never changes a promised date on its own." Nút: **"Record agreed date and replan"** (`pine`; mở form thương lượng: ngày, kênh, giờ liên hệ, kết quả), "Try another date", "Plan manually".
- **Form ghi thương lượng:** `outcome` (agreed/declined/unreachable), `channel`, `contacted_at`, `note`. `agreed` → đơn chạy lại với ngày mới; `declined` → gợi ý hủy; `unreachable` → hiện "Reminder in 24 h".
- **"Dates searched"** (dải ô ngày, ghi "Working days only · 14-day horizon · Swedish holidays excluded"): ô ngày yêu cầu nền Predicted late nhạt "REQUESTED"; ô lỗi "✕ stock", "✕ prep"; ô khả thi sớm nhất nền On track, viền `pine`, "✓ first"; ô sau dùng "—".
- **Bảng "Which check failed, per warehouse · <ngày>"** ("Checks stop at the first failure"): cột WAREHOUSE · STOCK · PREP · TRUCK · SITE/DATE · SAFETY · REASON. Ô lỗi là chip ✕ + mã; ô sau điểm lỗi là "—". Ví dụ mã: `INBOUND_LATE` (hiển thị khi `detail.inbound_available_on` có giá trị: "Enough adhesive only after inbound on 11 Nov."), `STOCK_SHORT`, `PREP_NO_CAPACITY` ("Needs 198 min; 102 min free before loading cut-off 15:00.").
- **Bảng "Usable stock on <ngày>"** (công thức mono ở góc: `usable = on hand − WMS reserved + confirmed inbound by date − active commitments`): cột LINE (tên + SKU · đơn vị) · NEEDED · từng kho. Số thiếu màu `#8F2710`; hàng nhập hiện dưới số ("+200 on 11 Nov"). Chân: "One warehouse fulfils the whole order — the MVP never splits lines across warehouses."
- **Panel bổ sung "Transfer suggestions"** (khi mọi kho thiếu): danh sách gợi ý (kho nguồn, lead time, khoảng cách, số lượng) + nút "Approve transfer"; trạng thái luồng (`approved → source_confirmed → received`).

### 5.4 — 04 Order tracking & risk (dispatcher)
- **Banner:** "Risk is rule-based: slack against the committed window, recalculated when a milestone, GPS fix or source data changes." (đổi so với "mỗi 5 phút", xem mục 7).
- **Đầu trang:** breadcrumb; Risk chip + chip trạng thái; H1 tên khách; dòng "SE-… · Stockholm DC → Uppsala · Truck 12 t STO-12-04 · today 10:00–12:30". Nút: "Acknowledge alert" (viền), "Replan this order" (`apricot`, mở modal lý do).
- **3 ô lớn:** COMMITTED WINDOW ("10:00–12:30 · Confirmed to customer 3 Nov") · PLANNED ETA ("11:15 · 75 min slack at approval") · FORECAST ETA (nền Predicted late khi trễ: "13:15 · 45 min after window closes"). **Thêm ô thứ tư nhỏ:** "Reserve used 120%" (mono, thanh tiêu hao với vạch 33/66%).
- **Milestones · planned vs actual vs forecast** ("Now 11:00"): 6 mốc (Approved, Start prep, Goods ready, Loaded, Dispatched, Delivered); mỗi mốc `plan hh:mm`, `✓ hh:mm` (thực tế, mono `pine`) hoặc `not recorded · fcst hh:mm` (đỏ). Hộp "**Why it is late:**" sinh từ `forecast` theo đúng công thức ở `04` mục 6.3, ví dụ: "Goods ready is 90 min past plan and not recorded. CFO assumes goods are ready no earlier than now (11:00), then loading 25 min, drive 65 min. Forecast 13:15 is 45 min after the site closes." Bỏ câu "assumes 40 min of preparation remains (proportional to recorded work)" của thiết kế vì MVP không ghi tiến độ bên trong bước chuẩn bị (#29).
- **Event log** (TIME · EVENT chip · BY · EFFECT): `RISK · PREDICTED_LATE`, `RISK · AT_RISK`, `START_PREP`, `PLAN_APPROVED`, `SUBMITTED`…; hiệu ứng ví dụ "Alert to dispatcher; **delay notice draft created**".
- **Cột phải — "Customer notifications":** danh sách (giờ, loại · kênh, nội dung ngắn, trạng thái). **Bản nháp DELAY** hiện thẻ nền `#FFF4EE`: "Draft · Delay notice — new window 13:00–13:30" với **Edit**, **Send**, **Discard** (lý do bắt buộc). Chân: "A new draft appears only if the ETA moves ≥ 30 min from the last notified window. Customers see status and ETA only — never driver location." Liên kết "Open inbox".
- **Thẻ "Approved plan":** Warehouse · Truck · Prep (giờ/phút) · **Distance** (thay "Cost") · Score.
- **Event log:** hiệu ứng của `RISK · AT_RISK` lấy theo mức thật (ví dụ "Goods ready 30 min overdue" khớp `milestone_grace_min = 30`); hiệu ứng của `RISK · PREDICTED_LATE` là "Alert to dispatcher; delay notice draft created" (không "delay email queued").
- **Panel bổ sung "Live position" (chỉ dispatcher, khi `gps_enabled` và chuyến `on_road`):** bản đồ Leaflet/OSM với kho, điểm giao, đường đi, xe; dòng "Last fix 10:52 · accuracy 12 m · source device/simulator"; trạng thái "GPS lost since 10:20" (nền Predicted late); biểu ngữ "No DPIA on file — demo only". Không hiển thị cho vai trò khác.
- Hộp thoại khẩn cấp cho `VEHICLE_ISSUE`: hiển thị cảnh báo kèm nút "Replan this order".

### 5.5 — 05 New order (POS giả lập, sales)
- **Vị trí:** ứng dụng **POS giả lập** của hệ thống nguồn (`source_system/pos_ui`), dùng **cùng ngôn ngữ hình ảnh**, banner "Customers, sites and products are seeded test data." CFO chỉ đọc đơn sau khi nộp (mục 7). Mục menu SALES · New order mở ứng dụng này.
- **Bố cục:** cột trái ba khối đánh số (overline `01/02/03` màu `apricot`): **01 Customer and delivery site** (Customer, Delivery site — địa chỉ chọn từ danh sách seed có toạ độ; ghi chú "Contractor · prefers email", "Site receives Mon–Fri 07:00–16:00") · **02 Delivery request** (Requested delivery date, Receiving from/until tùy chọn, ghi chú "If the customer gives only a date, CFO uses the site's receiving hours.", Receiving restrictions, Special requirements) · **03 Materials** (bảng SKU · PRODUCT · QTY · UNIT · WEIGHT, ô QTY nhập, "Add product by SKU, GTIN or name", "Quantities in sales units; converted to base units on submit"). Cột phải 330px **Order summary**: Total weight, Total volume, Lines; **READY TO SUBMIT** (checklist ✓): "Products found in the catalogue" (thiết kế ghi "All products mapped to a canonical SKU", nhưng POS không biết ánh xạ của CFO, xem #30), "Quantities positive, units known", "<ngày> is a Swedish working day", "Window fits site hours"; nút `pine` **"Submit for CFO planning"** (chạy `validate` rồi `submit`), nút "Save as draft"; ghi chú "CFO then checks stock, warehouse capacity and trucks. The date is confirmed to the customer only after a dispatcher approves a plan."
- **Ô ngày:** hiển thị theo `03` mục 8 (`Tue 10 Nov 2026` hoặc ISO `2026-11-10`), không dùng dạng Mỹ `11/10/2026` như ảnh (dễ nhầm ngày/tháng ở Bắc Âu).
- **Bổ sung:** điều khiển phân đoạn **Date type: Exact · Range · Latest** (Range hiện hai ô ngày "from/to"; Latest ghi "No later than"); ghi chú ngắn giải thích từng dạng.
- **Bỏ khỏi POS:** cột "Handling group" và số "Handling groups" (khái niệm của CFO; xem đơn đầy đủ ở CFO). SKU chưa ánh xạ **không chặn** nộp: hiện cảnh báo vàng "This product has not been mapped by IT yet; CFO will hold the order until it is".

### 5.6 — 06 Preparation queue (kho)
- **Dữ liệu:** `GET /warehouses/{id}/prep-queue`, `GET /warehouses/{id}/capacity`.
- **Banner demo:** "Labour standards are shared rule-based assumptions set by IT; shifts are entered by the warehouse team."
- **Đầu trang:** overline `GÖTEBORG DC · WEDNESDAY 4 NOVEMBER`; H1 "Preparation queue"; "Record what really happens. Each milestone updates the ETA immediately — no approval step."; nút "Edit shifts & staff" → màn 5.A5.
- **Thẻ "Capacity today"** ("<booked> of <total> min booked · <free> free"): thanh xếp chồng theo ca (Shift 1, Shift 2) + vạch Loading cut-off. Chú thích mỗi ca dạng **"8 present × 7.0 h useful × 90% = 3 024 min · fully booked"** (thay "8 staff × 85% productive = 3 264 min"). Vì công thức đổi, tổng ngày với seed (8 + 6 người) là 3 024 + 2 268 = **5 292 phút**, không phải 5 712 như ảnh; UI hiển thị số từ API. **Không có hàng thiết bị** (thiết bị kho ngoài MVP, #25).
- **Bảng "Orders to prepare" ("Approved plans only · in planned order")**, cột: ORDER (mã + "6 lines · 3 340 kg") · HANDLING MIX (chip nhóm dạng `N2 · Boards, sheets & tiles`, tên lấy từ `handling_group.name`, xem #27) · WORK (phút) · PREP WINDOW (`06:00 → 08:10`) · LOADING (`08:30 · GBG-12-03`, hoặc "Thu 06:00 **after cut-off**" màu `#7A4106`) · STATUS (chip) · hành động theo trạng thái: `APPROVED` → **Start prep** (viền), `PREPARING` → **Goods ready** (`pine`), `GOODS_READY` → **Mark loaded** (`pine`). Mỗi bấm gửi sự kiện, hiện toast, hàng cập nhật; cần chọn giờ thực tế nếu khác "bây giờ" (popover "Happened at").
- **"Report an exception":** 4 thẻ **Shortage / Breakage / Vehicle issue / Shift change** ("Alerts the dispatcher and recalculates affected orders"), mỗi thẻ mở form nhỏ theo payload ở `06` mục 8.1.
- **Bỏ khỏi màn kho:** panel "Products waiting for a handling group … Approve" — chuyển sang màn IT (5.A7).

### 5.7 — 07 KPIs & decision log
- **Đầu trang:** overline `PILOT VALUE METRICS · SWEDEN`; H1 "KPIs & decision log"; "Demo week 3–9 Nov · 48 orders closed · baselines entered as assumptions"; bộ chọn kỳ + "Export CSV".
- **Lưới thẻ KPI 3×2** (mỗi thẻ: nhãn mono, chip `↓ lower is better`/`↑ higher is better`, số lớn mono, thanh so sánh với baseline, ghi chú phương pháp):
  1. PLANNING TIME / ORDER — "3.2 min" vs baseline 15 min; ghi chú "Submit → approval, people time. Engine run alone: 0.4 s median."
  2. ON-TIME DELIVERY — "92%"; "44 of 48 delivered before the committed window closed. No real baseline yet." (giao thất bại không tính, xem 7)
  3. **LABOUR & DISTANCE PER DELIVERY** (thay "Cost per delivery"): hai số "9.8 h" và "31.4 km"; so với baseline "Nearest-warehouse rule"; ghi chú "Same seeded orders. Not converted to money."
  4. PREPARATION ERROR — "11 min"; "Mean |actual − planned| from Start prep to Goods ready. Calibrate labour standards only with ≥ 30 orders per group."
  5. ETA ERROR — "14 min"; "Rule-based forecast, not AI prediction."
  6. PLAN ACCEPTANCE — "81%"; "39 of 48 recommended plans approved unchanged · 7 alternatives chosen · 2 manual."
- **Thêm hai thẻ phụ:** FAILED DELIVERY RATE và CAPACITY UTILISATION.
- **Thanh nền tối (chẩn đoán):** "HARD-CONSTRAINT VIOLATIONS — 0 in approved plans (target 0)" · "EVENT → ALERT LATENCY — 4 s median, milestone to dispatcher alert".
- **Bảng "Decision log — Append-only · every approval, override and rule change"** cột TIME · WHO · ACTION (chip) · SUBJECT · DETAIL / REASON; có lọc theo hành động, đơn, khoảng ngày; mã hành động theo `04` mục 10 (`ALT_SELECTED`, `CRITERIA_CHANGED_RERUN`, `MANUAL_PLAN_CREATED`, `MAPPING_CONFIRMED`…). Chip `MANUAL_PLAN_CREATED` dùng bộ At risk để nổi bật.
- **Panel "Revenue & orders" (v1.1, chỉ hiện khi có quyền):** owner của kho/cửa hàng, admin, `viewer` có `can_view_revenue` (Business owner). Bộ chọn địa điểm; hai số lớn: doanh thu (mono, kèm `SEK`) và số đơn đã giao; ghi chú "Sum of quantity × unit price of delivered orders. Not profit; delivery costs and wages differ by country." Không cộng giữa các nước. Dữ liệu: `GET /kpi/revenue`.
- **Quyền xem:** doanh thu/số đơn kho hoặc cửa hàng theo `06` mục 3.1; viewer chỉ đọc; Project Lead (`viewer` không có `can_view_revenue`) không thấy panel doanh thu.
- **Đơn vị định mức trong nhật ký:** thiết kế ghi "0.8 → 0.9 min per unit"; MVP lưu giờ (`labour_hours_per_unit`). UI hiển thị cả hai: "0.15 h (9 min) per pallet".

### 5.8 — 08 Notification inbox
- **Banner:** "Nothing here reaches a real customer. Email goes to Mailpit locally; SMS is simulated."
- **Đầu trang:** overline `CUSTOMER COMMUNICATION · OUTBOX`; H1; "Four message types: date confirmed, dispatched, delivered or failed, and delay — delay notices are sent by a dispatcher."
- **Chip lọc:** `All · 6`, `Email · 4`, `SMS · 2`, `Draft · 1`, `Suppressed · 1`.
- **Danh sách trái:** mỗi mục: chip mẫu (`DELAY`, `DISPATCHED`, `DELIVERED`, `CONFIRMED`) + kênh + giờ, dòng `SE-… · Khách`, dòng trạng thái ("Sent · new ETA 13:00–13:30", "Suppressed · ETA moved < 30 min", "Draft · waiting for dispatcher").
- **Chi tiết phải:** khung email (From/To/Subject; To đã che `u•••@…`), thân thư theo mẫu mục 8.1 (dải màu `apricot` phía trên, tiêu đề, đoạn, khối "New arrival / Status", chân thư). Dưới: **SMS preview · simulated** và thẻ **"What a customer can see"** ("Order number, status, delivery window and ETA. **Never driver location or GPS.**").
- **Bản nháp DELAY:** thanh hành động Edit / Send (dispatcher) / Discard (có lý do). CS và admin chỉ đọc.

### 5.9 — 09 Data integration (admin/IT)
- **Banner:** "Each country plugs in its own systems; source systems here are mock APIs standing in for POS, WMS, ERP and the fleet calendar."
- **Tiêu đề:** overline `ADMIN · MARKET ADAPTERS · SWEDEN`; nút "Upload CSV (fallback)" và `pine` "Run all sources now".
- **5 thẻ nguồn:** POS orders · WMS stock · WMS inbound · ERP products · Fleet calendar; mỗi thẻ: chip OK/PARTIAL/FAILED, số lớn (rows/slots), "rows · 2 rejected" hoặc (chỉ ERP products) "3 unmapped" kèm liên kết tới Product mapping, "last run 10:05 · every <interval_min> min" (mọi nguồn theo `MarketConfig.sync.interval_min`, mặc định 5; thiết kế ghi ERP "daily", Fleet "hourly", xem #31), **`data_as_of`**. SKU chưa ánh xạ **không** làm thẻ thành PARTIAL (#32).
- **Dải 5 bước:** `01 FETCH` "New records since the last checkpoint" · `02 STAGE` "Raw payloads kept as received" · `03 NORMALISE` "Canonical SKU, base units" · `04 VALIDATE` "Bad rows set aside, run continues" · `05 UPSERT` "Natural key; same data twice changes nothing".
- **"Recent runs"** (TIME · SOURCE · FILE/CHECKPOINT · STATUS · IN · OK · REJECTED); chạy CSV hiện tên file; lượt trùng hash hiện `SKIPPED · SAME HASH`.
- **"Rejected rows — A bad row never stops the run"** (RUN · ROW · REASON chip · DETAIL); mã lý do theo `04` mục 5.2 (`BAD_QTY`, `UNKNOWN_WAREHOUSE`, `BAD_DATE`, `MISSING_COORDS`, `UNKNOWN_SKU`). Sản phẩm ERP chưa ánh xạ **không phải dòng bị loại**: chúng được nạp với `mapping_status = pending` và nằm ở hàng đợi mapping, nên không hiện dòng "UNMAPPED_SKU … waits for a handling group" như ảnh (#32). `UNKNOWN_SKU` (dòng tồn kho/đơn trỏ tới SKU không có trong danh mục) có liên kết "review".
- **Cột phải:** thẻ **Route matrix** ("195 warehouse → site pairs · OpenRouteService truck profile · fetched <giờ>. Planning reads this table, not the live API."; thêm "Estimated (fallback) pairs: 3") · thẻ **Scheduler** (Tick interval 5 min · Last tick · Jobs per tick · Stale source alert **> 15 min** theo `stale_stock_min`, thiết kế ghi "> 24 h", xem #31).

### 5.10 — 10–11 Driver app (PWA điện thoại, 390×844)
- **Khung:** nền `stone`, đầu trang `deep-pine` bo dưới; "CFO Driver" + mã xe mono bên phải.
- **Màn danh sách "Today's trips":** ngày · số chuyến; chip "Saved for offline · synced 10:52". Thẻ chuyến: `NOW · TRIP 1` + chip trạng thái (LOADED); tên điểm ("Mölndal · Kvarnbyn"), khách; ba ô Window / Drive / Load; mã đơn · số dòng; **một nút lớn `apricot` cho bước kế**: `LOADED` → "Mark dispatched". Thẻ `LATER · TRIP 2` mờ hơn, chip trạng thái theo enum (`PREPARING`, thiết kế ghi "IN PREP"), ghi "Loading at DC from 14:40", "Window 15:30–17:00".
- **Quyền riêng tư (thay câu "Your location is not tracked or shared"):** thẻ chân trang "While a trip is on the road this app sends your position to your dispatcher every 30 minutes. Customers never see it. Deleted after 30 days." kèm nút "Privacy details"; lần đầu hiện hộp xin quyền vị trí; chip trạng thái "Sharing location" / "Location off".
- **Màn chi tiết chuyến:** quay lại "Today's trips"; mã đơn + chip `DISPATCHED 08:45`; tên điểm giao; thẻ thông tin (Receiving window, Goods, ghi chú "Report to the site office. Forklift on site."); **Outcome** (phân đoạn Delivered/Failed); **Received by** (tên người ký — bắt buộc khi Delivered); **Note** (tùy chọn); khi chọn **Failed** hiện **Failure reason** (select bắt buộc: customer absent, site inaccessible, refused, wrong address, vehicle breakdown, goods damaged, other); nút lớn `apricot` **"Confirm delivered"** / "Confirm failed". Chân: "No signal? Your update is saved and sent once you are back online — never twice."
- **Offline:** sự kiện vào hàng đợi IndexedDB (`idempotency_key`, `occurred_at` = giờ chạm); chip "1 update waiting to send" khi chưa đồng bộ.
- **Cảm ứng:** vùng chạm ≥ 48px, một hành động chính mỗi màn, chữ ≥ 16px.

### 5.A — Màn bổ sung (chưa có trong thiết kế; dựng theo cùng ngôn ngữ)

**A1. Plan review (danh sách):** bảng đơn `PLANNED` (cột như Order queue + "Hold expires in", "Reserve class") dẫn tới màn 5.2. **A2. Exceptions:** ba tab `No feasible date` · `Manual planning` · `Blocked (unmapped SKU)`; hàng dẫn tới 5.3, màn kế hoạch tay (có khối "Handled outside CFO" khi không xe nào vừa), hoặc liên kết tới hàng đợi mapping. Tab `Manual planning` hiện `manual_reason` (`NEEDS_MULTI_VEHICLE`, `NO_CAPABLE_VEHICLE`); đơn đã `HANDLED_EXTERNALLY` rời tab và xem được ở Order queue với bộ lọc trạng thái. **A3. Tracking & risk:** bảng đơn cam/đỏ sắp theo `slack` tăng dần, kèm bản đồ tóm tắt xe đang chạy (dispatcher). **A4. Transfers:** bảng chuyển kho (trạng thái `suggested/approved/source_confirmed/received`), nút theo vai trò (dispatcher: Approve/Cancel; kho nguồn: Confirm source; kho đích: Receive).

**A5. Attendance & shifts (kho):** chọn ngày (mặc định hôm nay, tối đa 14 ngày tới); bảng nhân viên kho (tên, vai trò, ca, trạng thái `planned/present/absent/leave` dạng phân đoạn); nút **"All present"**; cột "Counts in capacity" (khóa với manager/supervisor); tóm tắt bên phải: người có mặt, giờ công khả dụng (= người × giờ hữu ích × 90%), cảnh báo khi dưới nhu cầu các đơn đã giữ chỗ; tab "Shift templates" (ca theo thứ trong tuần: giờ, giờ hữu ích/người, số người dự kiến); tab "Absences". (Không có tab Equipment, #25.)

**A7. Product mapping (IT):** danh sách task bên trái (SKU nội bộ, nước, số đơn bị chặn, tuổi task); chi tiết phải theo mẫu thẻ "Products waiting for a handling group" của thiết kế: tên/ERP code/cân nặng/đóng gói, **ứng viên theo quy tắc** (GTIN trùng, tên gần giống `pg_trgm` kèm điểm, nhóm gợi ý theo bảng quy tắc) thay cho "AI confidence"; hành động **Approve** (chọn ứng viên), **Choose other** (tìm sản phẩm global hoặc **Create global product** với nhóm N1–N6, đơn vị chuẩn bị, `base_units_per_prep_unit`, cờ, `units_to_base`), **Reject** (lý do bắt buộc). Văn bản dẫn: "Suggestions come from GTIN, name, category and size rules. Until IT approves, orders with these SKUs stay blocked (SKU_UNMAPPED)." Chân: "Every approval is written to the audit log."
**A8. Handling groups & norms (IT):** bảng N1–N6 (mã, tên, đơn vị chuẩn bị, giờ cố định/dòng, giờ/đơn vị kèm quy ra phút, số người tối thiểu, yêu cầu xe) và bảng hệ số cờ; ghi chú "N6 never carries the FRAGILE flag"; chỉnh sửa tại chỗ có xác nhận và lý do; ghi chú "One norm set for all warehouses". Tab "Group rules" (quy tắc gán nhóm theo category).
**A9. Employees & locations (IT):** danh bạ nhân viên (lọc vị trí, kho/cửa hàng, trạng thái); trang nhân viên (hồ sơ, phân công hiện tại, chuyển công tác, thôi việc); trang địa điểm (owner, quản lý chính/phó, danh sách nhân viên).
**A10. Vehicles & drivers (IT):** xe (tải, thể tích, năng lực, nhóm chở được, hạng bằng yêu cầu), lịch bận; tài xế (hạng bằng, hạn bằng, kho gốc; cảnh báo hết hạn trong 30 ngày). **A11. Users:** tài khoản, vai trò, kích hoạt, đặt lại mật khẩu.
**A12. Market config & GPS (IT):** form `MarketConfig` nhóm theo mục (có chú thích đơn vị, giá trị mặc định, nút "Reset"); thẻ **GPS & compliance**: công tắc `gps_enabled`, chu kỳ, mất tín hiệu, thời gian lưu; bảng `compliance_record` (DPIA, tham vấn nhân viên, thông báo GPS) với trạng thái; biểu ngữ vàng "No DPIA on file — demo only".
**A14. CS · Order lookup:** ô tìm (mã đơn, tên, điện thoại); thẻ trạng thái (trạng thái, khung giờ cam kết, ETA, lịch sử thông báo); khối "Log a contact" (kênh, lý do, ghi chú). **Không** có GPS, điểm số, quyết định nội bộ.
**A15. My store orders (sales/store manager):** danh sách chỉ xem đơn của cửa hàng (trạng thái, ETA), chip rủi ro; store manager thấy thêm KPI cửa hàng mình (doanh thu, số đơn) khi là owner.

## 6. Nội dung thư và tin nhắn (mẫu)

Nguồn chung: `From: CFO deliveries (demo) · noreply@cfo.demo`; ngôn ngữ theo `market.locale` (mặc định tiếng Anh). Mọi thư có dải màu `apricot` phía trên, dòng `ORDER SE-2026-000141`, tiêu đề, đoạn, khối tóm tắt, chân thư: "For questions, contact your store and quote the order number." **Không bao giờ có toạ độ, GPS, tên tài xế.**

| Mẫu | Chủ đề | Nội dung chính |
|---|---|---|
| `CONFIRMED` | "Your delivery is confirmed — order SE-…" | "Your delivery is planned for **Wed 4 Nov, 10:00–12:30**." |
| `DISPATCHED` | "Your order is on its way" | "Your order has left <Warehouse>. Expected arrival **13:10–13:40**." |
| `DELIVERED` | "Your order was delivered" | "Delivered at 09:12, received by <name>." |
| `FAILED` | "We could not deliver your order" | "We could not deliver today (<reason in plain words>). We will contact you to arrange a new time." |
| `DELAY` | "Delivery update for order SE-…" | "**Your delivery is running later than planned.** We now expect to arrive … between **13:00 and 13:30** today. The confirmed window was 10:00–12:30." khối New arrival / Status; "We will tell you again only if this changes." |

SMS (≤ 160 ký tự): "CFO demo: order SE-2026-000129 has left Malmö DC. Expected arrival 13:10–13:40." Ghi chú dưới bản xem trước: `sms_sim · 10:12 · not sent to a network`.

## 7. Điều chỉnh bắt buộc so với bản thiết kế

Bảng dưới liệt kê chỗ bản thiết kế khác quy tắc nghiệp vụ đã chốt; **agent code làm theo cột "Làm theo"**.

| # | Màn | Thiết kế ban đầu | Làm theo | Lý do |
|---|---|---|---|---|
| 1 | 02 | Con số lớn là **tiền (SEK)** trên plan card; "Lowest-cost ranking"; phân rã Labour/truck fixed/km | Con số lớn là **`score`** (0,5 km + 0,5 mức đầy công suất kho); hiện km, Fill %, giờ công, planning reserve; không có tiền | Đã chốt: xếp hạng theo km và mức đầy công suất, không quy ra tiền |
| 2 | 02 | "Optimise for: Lowest cost / Largest buffer" | Preset trọng số (Balanced / Shortest distance / Lowest warehouse load) + tùy chỉnh `w_km`, `w_fill` | Như trên; "buffer" không là tiêu chí xếp hạng |
| 3 | 02 | Nhãn tie-break "larger delivery buffer, then simpler operation" | "larger planning reserve, then simpler operation, then earlier ETA, then smaller vehicle code" | Khớp `BR-RNK-02` |
| 4 | 02 | Hiện "Delivery buffer 85 min" | Giữ như **Slack before site closes** (chỉ thông tin) + thêm **Planning reserve (ngày) & lớp Safe/Tight** | `BR-DEL-04` |
| 5 | 02, 03 | Mã `NO_TRUCK_SLOT`, `SAFETY_LIMIT`, `PREP_OVER_CAPACITY`, `INBOUND_LATE` | Mã chuẩn: `TRUCK_BUSY`/`NO_DRIVER`, `DRIVER_HOURS_EXCEEDED`/`OVER_LOAD`, `PREP_NO_CAPACITY`, và `STOCK_SHORT` kèm `detail.inbound_available_on` (hiển thị nhãn "INBOUND_LATE") | Danh mục mã ở `04` mục 6.2 |
| 6 | 03 | Thẻ ngày sớm nhất hiện giá tiền | Hiện km và ETA, không tiền | Như #1 |
| 7 | 03 | Không có gợi ý chuyển kho | Thêm panel "Transfer suggestions" | Đã chốt |
| 8 | 04 | "recalculated … every 5 minutes" | "recalculated when a milestone, GPS fix, source data or an overdue milestone changes" | Đã chốt: không tính vô ích |
| 9 | 04, 08 | Thông báo trễ **tự gửi** ("delay email queued/sent") | Hệ thống tạo **bản nháp**, **dispatcher bấm gửi** | Đã chốt Q16 |
| 10 | 04, 08 | "Max one delay message per hour" | Bản nháp mới chỉ khi ETA lệch ≥ 30 phút so với khung đã thông báo | `BR-NOT-02` |
| 11 | 04 | "Approved plan … Cost 3 960 SEK" | Distance, prep hours, score | Như #1 |
| 12 | 04 | Không có GPS | Thêm panel "Live position" (chỉ dispatcher) | Đã chốt GPS trong MVP |
| 13 | 05 | "New order" trong ứng dụng CFO, một ô ngày | Màn thuộc **POS giả lập**; thêm **Date type Exact/Range/Latest**; bỏ "Handling group" | Đơn đến từ POS nguồn; ba dạng ngày; nhóm xử lý là khái niệm CFO |
| 14 | 06 | Công suất "85% productive" tính phút | "người có mặt × giờ hữu ích × **90%**" (v1.1: không có hàng thiết bị, #25) | Đã chốt 90% |
| 15 | 06 | Warehouse manager duyệt nhóm xử lý (AI gợi ý) | Chuyển sang **IT**; gợi ý bằng quy tắc, không AI | Đã chốt: chỉ IT ánh xạ; AI sau |
| 16 | 07 | "Cost per delivery" bằng SEK, so với "Nearest-DC rule" | "Labour & distance per delivery" (giờ công và km), vẫn so với quy tắc kho gần nhất | Đã chốt: không quy tiền |
| 17 | 07 | Log do warehouse manager đổi labour standard (`LABOUR_STANDARD_CHANGED`) | Chỉ IT đổi định mức; mã hành động chuẩn ở `04` | Đã chốt: định mức chung do IT giữ |
| 18 | 07 | Mã `PLAN_ALT_SELECTED`, `CRITERIA_CHANGED`, `MANUAL_OVERRIDE`, `MAPPING_APPROVED` | `ALT_SELECTED`, `CRITERIA_CHANGED_RERUN`, `MANUAL_PLAN_CREATED`, `MAPPING_CONFIRMED` | Đồng nhất mã ở `04` |
| 19 | 08 | Mọi thông báo gửi tự động, có `Suppressed · delay within 60 min` | `DELAY` là bản nháp; thêm lọc `Draft`; lý do bị chặn: `shadow_mode`, lệch < 30 phút, dispatcher bỏ | Đã chốt |
| 20 | 09 | Nguồn là **file CSV**, bước FETCH "files from the inbox" | Nguồn là **API giả lập** theo `updated_since`; CSV chỉ là phương án dự phòng ("Upload CSV (fallback)") | Đã chốt: gọi API qua adapter |
| 21 | 09 | "A missing pair returns ROUTE_DATA_UNAVAILABLE — never a fake pass" | Có **fallback ước lượng** gắn nhãn "Estimated route"; nếu cấu hình `routing.allow_fallback = false` thì cặp thiếu trả `ROUTE_DATA_UNAVAILABLE` | Fallback đã chốt; vẫn giữ nguyên tắc không giả vờ |
| 22 | 10–11 | "Location is not tracked or shared" | Thông báo GPS có điều kiện, xin quyền, chip trạng thái; **bắt buộc chọn lý do khi Failed** | Đã chốt GPS trong MVP; `failure_reason` |
| 23 | Menu | Mọi mục hiện chung trong mockup | Lọc mục theo vai trò (mục 3.2) | RBAC |
| 24 | Đăng nhập | 5 tài khoản demo | Thêm Customer service, Business owner | Vai trò đã chốt |
| 25 | 06, A5, A8 | Màn kho có thiết bị (thiết kế không vẽ, nhưng bản 1.0 thêm hàng "Equipment today", tab Equipment) | **Bỏ** mọi UI thiết bị kho | Chốt v1.1: thiết bị kho ngoài MVP theo slide |
| 26 | 02 | Banner "Costs are illustrative (SEK)"; thứ tự #1 GBG 12 t, #2 Malmö, #3 GBG 18 t | Banner không nói tiền; thứ tự theo `rank` của API (thường hai phương án GBG đứng trước) | Xếp hạng theo điểm, không theo tiền |
| 27 | 06, 01 | Nhóm hàng hiện bằng tên tự do: Boards & sheets, Bagged cement & mortar, Long goods, Tiles & heavy, Paint & chemicals, Small tools & accessories | Chip `N1…N6 · <name>` theo `05` mục 11; Tiles & heavy → N2; Paint & chemicals → N1 kèm cờ; thêm N4 Bulk, N6 Large & fragile | Nhóm xử lý là N1–N6 của `05` |
| 28 | 06 (mapping) | "AI suggests, you decide", điểm tin cậy 0.91, warehouse manager Approve | Đã ở #15; nhắc lại: gợi ý bằng quy tắc (GTIN, `pg_trgm`, bảng quy tắc), IT duyệt | Chốt |
| 29 | 04 | "Why it is late: … assumes 40 min of preparation remains (proportional to recorded work)" | Diễn giải theo công thức `04` mục 6.3 (goods ready không sớm hơn `now`) | MVP không ghi tiến độ trong bước chuẩn bị |
| 30 | 05 | Checklist "All products mapped to a canonical SKU"; ô ngày dạng `11/10/2026` | "Products found in the catalogue"; ngày theo mục 8 | POS không biết ánh xạ của CFO; tránh nhầm ngày/tháng |
| 31 | 01, 09 | ERP products "daily", Fleet calendar "hourly"; "Stale source alert > 24 h"; nguồn là file CSV `pos_orders_…csv` | Mọi nguồn theo `sync.interval_min` (5); cảnh báo dữ liệu cũ theo `stale_stock_min` (15 phút); lượt API hiện checkpoint, chỉ lượt CSV dự phòng hiện tên file | Cấu hình `04` mục 8; nguồn là API (#20) |
| 32 | 09 | ERP products PARTIAL vì "3 unmapped"; dòng bị loại `UNMAPPED_SKU` | SKU chưa ánh xạ được nạp (`pending`) và đếm riêng "unmapped", không là dòng bị loại; mã loại chuẩn là `UNKNOWN_SKU` | Khớp `04` mục 5.2 và luồng mapping |
| 33 | 07 | Decision log có `MANUAL_OVERRIDE` "Crane delivery by partner haulier; vehicle not in fleet calendar" | Trường hợp này là **`EXTERNAL_HANDOFF_RECORDED`** (đơn `HANDLED_EXTERNALLY`); kế hoạch tay trong đội vẫn là `MANUAL_PLAN_CREATED` | Lối xử lý ngoài CFO v1.1 |
| 34 | 07 | Chỉ có thẻ "Cost per delivery" (SEK) | Thẻ giờ công và km (#16) + panel "Revenue & orders" riêng, chỉ người có quyền | Doanh thu khác chi phí; quyền theo `06` mục 3.1 |
| 35 | 01, 10–11 | Chip `MANUAL`, `IN PREP` | `MANUAL_PLANNING`, `PREPARING` (enum đúng) | Status chip theo enum |
| 36 | 01 | Bảng không có cột rủi ro riêng (chỉ nền hàng) | Thêm cột chip rủi ro hẹp | Màu không là tín hiệu duy nhất (mục 1.5) |

## 8. Hành vi chung

- **Định dạng:** giờ 24h `hh:mm` theo `market.timezone`; ngày `Wed 4 Nov` (hôm nay hiện `Today`); khoảng giờ dùng gạch nối en `10:00–12:30`; số nghìn cách bằng khoảng hẹp (`4 120 kg`); thập phân dùng dấu chấm trong tiếng Anh; tiền (nếu hiện, chỉ ở đơn giá/doanh thu) có mã tiền tệ (`SEK`).
- **Cập nhật dữ liệu:** polling 15–30 giây cho Order queue, Tracking, Alerts, Prep queue; không WebSocket. Hiện chấm "live" khi vừa làm mới.
- **Phản hồi thao tác:** mọi nút gọi API có trạng thái đang xử lý; nút ghi nguy hiểm có xác nhận; lỗi API theo định dạng `06` mục 1.1, hiện `message` và `correlation_id`.
- **Quyền:** nút không có quyền thì ẩn (và API vẫn từ chối); thông tin cá nhân được che theo vai trò.
- **Banner demo:** có ở mọi màn khi `APP_ENV != production`; câu ngữ cảnh theo màn như thiết kế.

## 9. Responsive và PWA

| Khoảng | Hành vi |
|---|---|
| ≥ 1280 px | Bố cục như thiết kế (sidebar cố định 262px) |
| 1024–1279 px | Panel phải của Order queue xuống dưới bảng; ba plan card xếp 1 cột cuộn ngang |
| 768–1023 px (máy tính bảng kho) | Sidebar thu thành biểu tượng; Prep queue một cột, nút hành động lớn hơn (≥ 48px) |
| < 768 px | Chỉ ứng dụng **Driver** được tối ưu cho điện thoại; các màn khác hiện thông báo "Open on a larger screen" trừ màn tra cứu của CS và danh sách đơn (chỉ đọc) |

Driver PWA: `manifest.webmanifest` (tên "CFO Driver", biểu tượng logo, `display: standalone`, `theme_color #0B2E2B`), service worker cache danh sách chuyến của ngày, hàng đợi sự kiện offline, cảnh báo cài lên màn hình chính.

## 10. Khả năng truy cập

WCAG AA: tương phản chữ ≥ 4,5:1 (đã kiểm với các cặp màu ở mục 2.1); trạng thái có chữ và biểu tượng, không chỉ màu; điều hướng bằng bàn phím được trên toàn bộ màn dispatcher (Tab, Enter, Esc trong modal, phím tắt `a` = Approve khi đang chọn kế hoạch, có xác nhận); `aria-live="polite"` cho cảnh báo mới; nhãn cho mọi ô nhập; thứ tự focus theo luồng đọc; bảng có `scope` và tiêu đề cột; giảm chuyển động theo `prefers-reduced-motion`.

## 11. Hướng dẫn chuyển thiết kế sang mã

- **Tailwind config:** khai báo màu ở mục 2.1 (`deepPine`, `pine`, `apricot`, `stone`, `ink`, `border`, và bộ `risk.{onTrack,atRisk,predictedLate,overdue}.{bg,fg}`); `fontFamily.sans = ['Schibsted Grotesk', 'Arial', 'sans-serif']`, `fontFamily.mono = ['JetBrains Mono', 'Courier New', 'monospace']`; `borderRadius.card = 16px`, `borderRadius.control = 10px`.
- **Thành phần:** `AppShell`, `Sidebar`, `DemoBanner`, `PageHeader`, `StatusChip`, `RiskChip`, `FilterChips`, `JourneyBar`, `CheckChip`, `PlanCard`, `RejectedCandidatesTable`, `DecisionBar`, `MilestoneTimeline`, `EventLog`, `KpiCard`, `NotificationPreview`, `ReasonModal`, `ExternalHandoffForm`, `MaskedText`, `DataFreshness`, `TripCard` (driver), `OutcomeToggle`.
- **Thư mục:** `features/dispatcher/{OrderQueue,PlanReview,NoFeasibleDate,Tracking,Transfers}`, `features/warehouse/{PrepQueue,Attendance}`, `features/it/{Mapping,HandlingGroups,Employees,Vehicles,Users,MarketConfig,Integration}`, `features/kpi`, `features/cs`, `features/store`, `features/driver`, `features/notifications`.
- **Dữ liệu mẫu cho UI:** dùng seed ở `08_Development_Plan.md` để các màn có số giống thiết kế (SE-2026-000123/137/141…); mã đơn trong seed chủ đích khớp thiết kế để so sánh ảnh.

## 12. Bảng đối chiếu trang PDF ↔ màn hình

| Trang PDF | Nội dung | Mục |
|---|---|---|
| 1 | Bìa và mục lục (00–11) | — |
| 2 | Visual language | 2 |
| 3 | 00 Sign in | 5.0 |
| 4–5 | 01 Order queue (đầu và cuối bảng) | 5.1 |
| 6–8 | 02 Plan review (card, bảng loại, điều khiển và thanh duyệt) | 5.2 |
| 9–10 | 03 No feasible date | 5.3 |
| 11–12 | 04 Tracking & risk | 5.4 |
| 13–14 | 05 New order | 5.5 |
| 15–16 | 06 Prep queue & product mapping (trang 17 trống) | 5.6, 5.A7 |
| 18–19 | 07 KPIs & decision log | 5.7 |
| 20 | 08 Notification inbox | 5.8 |
| 21–22 | 09 Data integration | 5.9 |
| 23 | 10–11 Driver PWA | 5.10 |
