# CR-2026-11-18 — Cắt giảm 30% ngân sách và tích hợp CRM mới (thay Microsoft Dynamics 365)

> **ĐÃ LỖI THỜI (2026-11-18).** Chủ dự án chốt khác đề xuất này: CFO tự gửi email (không qua CRM), CS lookup giữ trong CFO, Salesforce Sales Cloud cơ bản, giữ multi-truck, Sales có quyền trong phạm vi. Quyết định có hiệu lực: [DEC-R3](../decisions/DEC_R3_SCOPE_CRM_20261118.md). File giữ lại để truy vết lập luận.

> **Trạng thái:** `proposed` — đề xuất của nhóm Dev, **chưa phải quyết định của chủ dự án**. Không có mục nào ở đây được
> triển khai trước khi chủ dự án duyệt và ghi `DEC-…` vào `docs/ASSUMPTIONS.md`. Các mã đề xuất ASM-010…ASM-015 bên dưới
> đã được ghi ở trạng thái *proposed* trong sổ.
>
> **Đầu vào:** proposal Round 1 (Team Peanutt), System Context Diagram Round 2, User Journey Round 2, trạng thái repo `main`
> tại `b990399` (2026-11-18), `docs/08`, `docs/10`, `docs/AGENT_TASK_BOARD_20261109.md`.
>
> **Giả định của đề bài (cần xác nhận):** (1) Dynamics 365 hiện là nơi giữ khách hàng / tài khoản B2B / liên hệ và là công cụ
> của bộ phận chăm sóc khách hàng; (2) CRM mới chưa chọn nhà cung cấp, nên thiết kế trung lập nhà cung cấp; (3) "budget giảm
> 30%" áp dụng cho phần build MVP + pilot (6 tuần × 3 dev ≈ 18 dev-week trong proposal), không cắt chi phí vận hành CRM vì
> CRM là hệ thống của doanh nghiệp, không phải của CFO.

---

## 1. Tóm tắt điều hành

- **Ngân sách mới ≈ 12,6 dev-week** (70% × 18). Tích hợp CRM tốn thêm **≈ 2,5 dev-week**. Vậy phải giải phóng **≥ 8 dev-week**
  khỏi phạm vi cũ. Đề xuất bên dưới giải phóng **≈ 10 dev-week**, giữ ~2 dev-week dự phòng cho rủi ro nhà cung cấp CRM.
- **Core value giữ nguyên**: *mỗi đơn trở thành một lời hứa giao hàng đáng tin và nhìn thấy được* — tức là chuỗi
  **Sync đơn → 5 cổng kiểm tra (tồn kho theo thời gian, công suất kho, xe, khung giao, an toàn tài xế) → 3 phương án có lý do →
  con người duyệt (Dispatcher / Sales rank-1) → mốc kho & giao → cảnh báo rủi ro → khách nhận trạng thái + ETA → KPI pilot**.
- **Nguyên tắc cắt**: cắt những gì *không nằm trên đường đi của lời hứa* (GPS live, chuyển kho, doanh thu, màn quản trị CRUD),
  và **đẩy sang CRM** những gì CRM làm tốt hơn và doanh nghiệp đã trả tiền (gửi email/SMS cho khách, sổ liên hệ CS, tra cứu CS).
  Như vậy CRM vừa là yêu cầu mới **vừa là nguồn tiết kiệm**.
- **Tích hợp CRM theo đúng triết lý "integrate, don't replace"**: CRM là *nguồn chuẩn dữ liệu khách hàng* (đọc vào CFO qua
  một adapter mới) và là *kênh liên lạc với khách* (CFO đẩy sự kiện trạng thái đơn qua outbox). CFO vẫn là nguồn chuẩn của
  *lời hứa giao hàng*. Không đổi engine, không đổi luồng duyệt.

---

## 2. Hiện trạng repo (đối chiếu nhanh, không phải nghiệm thu)

| Khu vực | Hiện trạng quan sát được | Ghi chú |
|---|---|---|
| Engine thuần (`backend/app/engine/`) | Có planner, delivery (≈630 dòng), types | Đường găng, giữ |
| Ingestion / adapter (`adapters/`, `ingest_*`) | REST + CSV adapter, stock batch, sync | Nền để cắm CRM adapter |
| Reservation / approval | `reservation_service`, `approval_service` (≈770 dòng) | Giữ |
| `order_service` | 6 hàm còn `NotImplementedError` (list, get, timeline, counts, replan, cancel) | **Phải làm** — trên đường găng |
| Jobs | `risk_check`, `retention`, `nightly_metrics` còn stub | `risk_check` phải làm; 2 job còn lại có thể đơn giản hóa |
| API stub | `admin` (3), `mapping` (4), `hr` (7), `internal` (1) còn `NotImplementedError` | Phần lớn thuộc nhóm có thể cắt/đơn giản hóa |
| WMS reserve | adapter tắt, disposable WMS service, readiness validator (~1.400 dòng) | Đã đủ làm "nền"; ngừng đầu tư |
| GPS | `gps_service` (≈400 dòng), `driver_history`, PR #137 mở | Ứng viên cắt lớn nhất |
| Notifications | `notify_service` (≈670 dòng), SMTP, SMS simulator | Chuyển vai trò gửi sang CRM |
| Frontend | Nhiều màn đã có; `Tracking`, `Transfers`, `Users`, `Vehicles`, `Employees`, `MarketConfig`, `Attendance`, `NotificationInbox`, `TripDetail`, `PlanReviewList` vẫn là khung ~9 dòng | Phần khung chưa làm chủ yếu là màn có thể cắt |

> Bảng trên dựa trên đọc mã, chưa chạy `tools/harness.py verify` — **NOT VERIFIED** về hành vi.

---

## 3. Những gì KHÔNG cắt (bảo toàn core value)

| # | Năng lực | Bước journey | Lý do bắt buộc |
|---|---|---|---|
| K1 | Sales *Sync now* theo mã đơn POS, đọc nguồn chỉ-GET, kiểm tra 100% SKU đã ánh xạ | 1–2 | Bỏ re-key; cửa vào của mọi giá trị |
| K2 | Engine thuần: ATP theo thời gian (14 ngày), công suất kho theo nhóm xử lý, xe & tài xế, khung giao, 5 cổng, xếp hạng top 3 + reason codes, ngày khả thi sớm nhất | 2 | Đây chính là "reliable promise" |
| K3 | Hold 15 phút, chỉ khóa khi duyệt, 409 `RESOURCE_CONFLICT`, `transition()` + `audit.decision_log` cùng transaction | 3 | An toàn cam kết, truy vết |
| K4 | Dispatcher duyệt / override có lý do; Sales confirm rank-1 cửa hàng mình (DEC Sales) | 3 | "System proposes, human decides" |
| K5 | Mốc kho START_PREP → GOODS_READY → LOADED; tài xế DISPATCHED / DELIVERED / FAILED + POD | 4–5 | "Visible promise" + dữ liệu KPI |
| K6 | Rủi ro theo luật (plan vs forecast vs actual, ON_TRACK → AT_RISK → PREDICTED_LATE → OVERDUE), DELAY do hệ thống *soạn*, Dispatcher *gửi* | 6 | Báo trễ trước khi khách gọi |
| K7 | Khách nhận CONFIRMED / DISPATCHED / DELIVERED / FAILED / DELAY (nay **qua CRM**) | 3, 5, 6 | Khách thấy lời hứa |
| K8 | 4 KPI pilot: thời gian lập kế hoạch/đơn, giao đúng hạn, tỉ lệ chấp nhận phương án, can thiệp thủ công/đơn (+ ETA error nếu kịp) | 6 | Điều kiện go/no-go |
| K9 | Ranh giới an toàn: không tự duyệt, không ghi POS/ERP, không đổi on_hand WMS, không GPS cho khách/CS/Sales | toàn bộ | Bất biến `09` §4 |

**Multi-vehicle**: giữ như owner đã duyệt (engine đã có "bộ xe ít nhất"). Chỉ đề xuất *không* làm thêm trình chỉnh sửa
kế hoạch tay nhiều xe phức tạp ngoài phạm vi đã có (xem C7).

---

## 4. Đề xuất cắt / hoãn (để đạt −30% và trả tiền cho CRM)

Ước lượng tính trên 18 dev-week gốc; là **ước lượng thô của nhóm**, cần chủ dự án/PM hiệu chỉnh.

| ID | Cắt / hoãn | Thay bằng | Tiết kiệm (dev-week) | Ảnh hưởng core value | Cần quyết định |
|---|---|---|---|---|---|
| **C1** | **GPS live** cho Dispatcher: thu GPS 30 phút, bản đồ trip, lưu 7 ngày, reviewer quyền riêng tư, lịch sử lái xe theo GPS, DPIA, job retention GPS; PR #137 park | ETA từ mốc + ma trận tuyến đã tính trước (ORS/Haversine); "đã xuất phát lúc…, dự kiến tới…" | **2,5** | Thấp — proposal R1 đã xếp GPS vào "Later (GDPR review)"; khách vốn không thấy GPS | Đổi DEC-GPS-RET-20261109 → *deferred* |
| **C2** | **WMS reserve/release**: dừng phát triển thêm disposable WMS, ACK mô phỏng, readiness, re-read sau ACK | Giữ adapter ở trạng thái *disabled* (đã merge); ATP trừ lượng CFO đã cam kết; đọc stock WMS chỉ-đọc như cũ | **1,5** | Thấp — real write vốn đã tắt; cam kết vẫn đúng trong CFO | DEC-WMS-RESERVE-SYNC → *deferred*, giữ ranh giới read-only |
| **C3** | **Ngăn xếp gửi thông báo trong CFO**: template engine, quiet hours, retry 3 lần tới SMTP/SMS, Brevo, SMS simulator, Notification inbox UI | CFO chỉ phát **sự kiện đơn** vào outbox → CRM gửi email/SMS bằng template & consent của CRM (xem §5) | **1,2** (một phần dùng lại cho CRM sink) | Không — khách vẫn nhận thông báo; DELAY vẫn chỉ phát ra sau khi Dispatcher bấm gửi | DEC-NOTIFY-001 cập nhật kênh |
| **C4** | **Module CS trong CFO**: tra cứu đa tiêu chí, chuẩn hóa SĐT, contact log, timeline CS riêng | CS làm việc trong CRM (case + contact log); CRM gọi **một API trạng thái chỉ-đọc** của CFO hoặc nhúng thẻ trạng thái | **1,2** | Không — CS vẫn thấy trạng thái + ETA, ít màn hơn | DEC-INT-CS-GET-PRIVACY cập nhật |
| **C5** | **Gợi ý chuyển kho** (`transfer_service`, màn Transfers; PR #127 park) | Đơn thiếu hàng → NO_FEASIBLE_DATE + ngày khả thi sớm nhất; Dispatcher xử lý tay | **0,8** | Thấp — "một kho/đơn" vẫn giữ | DEC-INT-TRANSFER-BOUNDARY → *deferred* |
| **C6** | **Revenue dashboard** và KPI nhiều phạm vi | Chỉ 4–5 KPI pilot (K8) trên một màn; doanh thu lấy từ ERP/BI sẵn có | **0,8** | Không — doanh thu không phải KPI pilot | Freeze màn đã merge |
| **C7** | **Màn quản trị CRUD**: Users, Vehicles, Employees, MarketConfig, Attendance từng người, HR write API còn stub; manual plan editor mở rộng | Seed + import CSV có kiểm tra; Warehouse Manager **xác nhận công suất theo ngày/nhóm** thay vì lập lịch từng người (vẫn fail-closed khi chưa xác nhận) | **1,5** | Thấp — vẫn có công suất đã xác nhận cho cổng 2 | Cần sửa DEC-SHIFTS-001 / ASM-007 (mức chi tiết lịch) |
| **C8** | **Offline queue IndexedDB** của Driver PWA | PWA online, retry idempotent (Idempotency-Key), Dispatcher nhập hộ khi mất sóng | **0,5** | Thấp | Ghi ASM |
| **C9** | **Quy mô pilot**: 3 kho → 2, 20–30 cửa hàng → ~10, shadow pilot 1 tuần | — | **0,5** + giảm chi phí vận hành/đào tạo | Thấp — vẫn chứng minh được KPI | Owner |
| **C10** | Công cụ đa thị trường (`add_market`, bảo trì CSV adapter) | Giữ interface `MarketAdapter`; thị trường thứ 2 để sau go/no-go | **0,3** | Không (giữ kiến trúc) | — |
| | **Tổng giải phóng** | | **≈ 10,8** | | |

**Chi phí định kỳ cũng giảm**: không lưu/serve GPS, không trả SMS gateway/Brevo (dùng kênh CRM đã có license), giữ hosting
free-tier + ORS free key + Haversine fallback, không thêm dịch vụ trả phí.

**Không đề xuất cắt**: kiểm thử PostgreSQL thật cho khóa/overcommit, audit log, RBAC theo phạm vi — cắt các phần này làm hỏng
"Everything is traceable" và rủi ro hơn số tiền tiết kiệm.

### Cân đối ngân sách

| Hạng mục | Dev-week |
|---|---|
| Phạm vi gốc | 18,0 |
| − Cắt/hoãn C1–C10 | −10,8 |
| + Tích hợp CRM (§5, §7) | +2,5 |
| + Dự phòng rủi ro CRM / nhà cung cấp chưa chốt | +2,0 |
| **Tổng mới** | **≈ 11,7** (≤ 12,6 = 70%) |

---

## 5. Thiết kế tích hợp CRM mới

### 5.1 Phân định nguồn chuẩn (system of record)

| Dữ liệu | Nguồn chuẩn | CFO làm gì |
|---|---|---|
| Đơn hàng, dòng hàng, mã cửa hàng, Sales | POS/ERP (không đổi) | Đọc (GET) như hiện tại |
| Tồn kho, inbound | WMS/ERP | Đọc như hiện tại |
| **Khách hàng / tài khoản B2B, người liên hệ, địa điểm công trình, giờ nhận hàng, kênh ưu tiên, consent liên lạc, phân khúc/VIP, trạng thái ẩn danh GDPR** | **CRM mới** (trước là D365) | **Đọc** qua `CrmAdapter`, lưu bản sao tối thiểu trong `ref.customer` / địa chỉ |
| Lời hứa giao hàng: kế hoạch, ngày cam kết, ETA, mốc, rủi ro | **CFO** | Ghi; **phát sự kiện** sang CRM |
| Gửi email/SMS cho khách, case CS, contact log | **CRM** | Không còn tự gửi (C3), không còn contact log (C4) |

Quy tắc ưu tiên khi trùng: liên hệ/consent/giờ nhận hàng **lấy từ CRM**; thông tin liên hệ *ghi trên một đơn POS cụ thể*
chỉ ghi đè cho đơn đó (giữ hành vi hiện tại của `OrderDTO.contact`).

### 5.2 Kiến trúc

```
              POS/ERP/WMS (per market)                     CRM mới (toàn Nordic hoặc per market)
                    │ GET, 5' + Sync now                    │ GET accounts/contacts/sites (updated_since)
                    ▼                                        ▼                      ▲ POST order-events (idempotent)
 ┌──────────────── CFO boundary ─────────────────────────────────────────────────────┼─────────────┐
 │ adapters/  MarketAdapter (REST/CSV)          CrmAdapter (REST | CSV | D365-legacy)  │             │
 │               └──────────► services/ingest_* ◄──────┘  (checkpoint, reject log,   │             │
 │                               │                       freshness flag > 15')       │             │
 │                               ▼                                                    │             │
 │   ref.customer (+ crm_ref, consent, preferred_channel)  ref.customer_xref          │             │
 │                               │                                                    │             │
 │   engine/ (PURE — không đổi) ◄┘ receiving hours từ CRM đi vào OrderCtx            │             │
 │                                                                                    │             │
 │   approval / execution / risk ──transition()──► ops.notification (outbox)          │             │
 │                                                    │ job outbox (3 retry)           │             │
 │                                                    └──► providers/CrmEventSink ────┘             │
 │   api/v1/crm/orders/{ref}/status  ◄── service account `crm_integration` (chỉ-đọc, status+ETA)    │
 └─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Điểm then chốt:

1. **Engine không đổi.** Giờ nhận hàng/site restrictions từ CRM đi vào `OrderCtx` qua `planning_inputs` như hiện nay
   lấy từ `AddressDTO.receiving_hours`. Không `if crm == ...` trong lõi (bất biến 15).
2. **`CrmAdapter` tách khỏi `MarketAdapter`**: CRM có thể là một hệ chung cho cả Nordic trong khi POS/WMS là per-market.
   Tái dùng `CustomerDTO`/`AddressDTO`, thêm `ContactDTO`, `ConsentDTO`, `CustomerAnonymisedDTO`. Ba hiện thực:
   `RestCrmAdapter` (CRM mới), `CsvCrmAdapter` (fallback/khởi tạo), `D365LegacyAdapter` (chỉ trong giai đoạn chuyển đổi).
   Chọn bằng cấu hình thị trường `crm.provider` — đổi nhà cung cấp = đổi adapter + config.
3. **Khớp khách**: `ref.customer_xref(system, external_ref → customer_id)` để nối `customer_ref` trên đơn POS với account CRM
   (và với ID D365 cũ khi chuyển đổi). Không khớp được → đơn vẫn lập kế hoạch bằng dữ liệu liên hệ trên đơn, gắn cờ
   `CUSTOMER_UNMATCHED` ở màn Data integration; thông báo khách giữ lại trong outbox chờ khớp (không gửi nhầm người).
4. **Sự kiện ra CRM (outbound) qua outbox giao dịch đã có**: CONFIRMED, DISPATCHED, DELIVERED, FAILED, DELAY_SENT (chỉ sau
   khi Dispatcher bấm gửi), DATE_CHANGED (chỉ sau khi khách đã đồng ý và Dispatcher áp dụng). Payload tối thiểu: mã đơn,
   trạng thái, ngày & khung cam kết, ETA, lý do hiển thị cho khách, event_id (idempotency). **Không** GPS, không điểm rủi ro
   nội bộ, không phương án/chi phí. CRM dùng template + consent của mình để gửi email/SMS.
5. **CRM đọc trạng thái**: endpoint chỉ-đọc cho service account `crm_integration` (masked, status + ETA + lịch sử mốc
   công khai) để CS xem trong CRM thay cho màn CS của CFO.
6. **Đồng bộ**: polling 5 phút + "Sync now" như POS — không thêm webhook/queue (giữ quy tắc không Redis/Celery/WebSocket).
   Webhook CRM → CFO để sau MVP.
7. **Khi CRM sập**: CFO dùng bản sao khách gần nhất (cờ dữ liệu cũ > 15'), lập kế hoạch vẫn chạy; sự kiện ra nằm trong outbox
   và retry; quá ngưỡng → cảnh báo Dispatcher + fallback email SMTP test (Mailpit) chỉ trong staging.
8. **GDPR**: CRM là nơi quản lý consent và yêu cầu xóa; sự kiện `anonymised` từ CRM → CFO đặt `is_anonymised` và xóa PII bản
   sao (gắn vào job `retention` hiện còn stub). Không log PII (bất biến 16).

### 5.3 Chuyển đổi từ Dynamics 365

1. **Khảo sát (W1)**: danh sách thực thể D365 đang dùng (Account, Contact, Address, Case, Activity), trường nào CFO cần.
2. **Ánh xạ ID**: CRM mới giữ trường `legacy_d365_id`; CFO nạp `customer_xref(D365 → CRM)` từ file đối soát.
3. **Chạy song song ngắn**: `crm.provider = d365_legacy` → chuyển `rest_crm` theo từng thị trường; báo cáo đối soát số
   lượng, không khớp, khác biệt giờ nhận hàng/consent.
4. **Cắt chuyển**: tắt `D365LegacyAdapter`; giữ bản đối soát trong `stg` để kiểm toán.

Trong MVP (dữ liệu synthetic): **mô phỏng CRM ngay trong `source_system`** (router `/crm/*`, bảng `src_crm_*` riêng) — không
thêm container, không dịch vụ trả phí, giống cách đang mô phỏng POS/WMS.

### 5.4 Thay đổi hợp đồng cần duyệt (theo `09` §13–14)

| Thay đổi | Tài liệu | Ghi chú |
|---|---|---|
| `CrmAdapter` + DTO mới | `04` §5, `06` §16 (hợp đồng nguồn CRM) | Dev 2 |
| `ref.customer_xref`, cột `crm_ref`/consent ở `ref.customer` | `05` + migration Alembic | Dev 1 |
| Kênh outbox `crm_event` (enum mới), mã lỗi/cảnh báo `CUSTOMER_UNMATCHED`, `CRM_STALE` | `05`, `06` §11 | Dev 1 + Dev 2 |
| Endpoint `GET /api/v1/crm/orders/{external_ref}/status`, vai trò `crm_integration` | `06` (ma trận quyền) | Dev 1 |
| **Ghi ra hệ thống ngoài (CRM)** | `09` §4 / AGENTS | Ngoại lệ có kiểm soát, giống WMS reserve: chỉ sự kiện trạng thái, idempotent, không ghi POS/ERP — **cần DEC riêng** |

---

## 6. User journey sau thay đổi

| Bước | Trước (R2) | Sau CR |
|---|---|---|
| 1 Order intake | Sync POS | Sync POS + **khớp khách CRM** (giờ nhận hàng, kênh, consent) |
| 2 Plan | 5 cổng, top 3 | Không đổi (giờ nhận hàng lấy từ CRM) |
| 3 Confirm | Approve → CFO gửi CONFIRMED | Approve → sự kiện CONFIRMED → **CRM gửi** |
| 4 Prepare & load | Mốc kho | Không đổi |
| 5 Dispatch & deliver | PWA + GPS 30', bản đồ | PWA online + POD; **ETA từ mốc + tuyến**, không GPS |
| 6 Monitor & close | DELAY do Dispatcher gửi; CS dùng Order lookup CFO | DELAY do Dispatcher phát hành → **CRM gửi**; **CS tra trong CRM** qua API trạng thái |

Ngoại lệ A–D giữ nguyên logic; chỉ kênh liên lạc khách đổi sang CRM.

---

## 7. Kế hoạch thực hiện (≈ 4 tuần, 3 dev, khớp 70% ngân sách)

### Tuần 0 (2 ngày) — Quyết định & đóng băng
- Chủ dự án duyệt/từ chối C1–C10 và CRM DEC; ghi `DEC-…` vào `docs/ASSUMPTIONS.md`.
- Park/đóng PR thuộc phạm vi cắt (kiểm tra lại trạng thái: #137 GPS, #127 Transfers, phần Revenue/KPI nhiều phạm vi).
- Chốt hợp đồng CRM (§5.4) bằng một PR đồng bộ `04/05/06` + `CHANGELOG`.
- **Gate G0**: danh sách cắt được duyệt; hợp đồng CRM merged.

### Tuần 1 — Lõi đường găng + CRM inbound
| Dev | Việc | Kết quả kiểm chứng |
|---|---|---|
| Dev 1 | Hoàn thành 6 hàm `order_service` (list/get/timeline/counts/replan/cancel); migration `customer_xref` + cột CRM | Test PG thật; `test_US_ORD_*` xanh |
| Dev 2 | CRM mô phỏng trong `source_system` (`/crm/accounts`, `/contacts`, `/sites`, `updated_since`); `RestCrmAdapter` + `CsvCrmAdapter`; ingest + reject + freshness | Contract test; ingest idempotent |
| Dev 3 | Gỡ menu/route các màn bị cắt; Data integration hiển thị `CUSTOMER_UNMATCHED`; Plan review/Approval nối API thật | Lint/test/build xanh |

### Tuần 2 — Thực thi + CRM outbound
| Dev | Việc | Kết quả kiểm chứng |
|---|---|---|
| Dev 1 | Execution mốc kho + POD nối `transition()`; endpoint trạng thái cho `crm_integration` (allowed/forbidden tests) | Test quyền 2 chiều |
| Dev 2 | `CrmEventSink` qua outbox (idempotent, retry 3, không PII trong log); thay gửi SMTP/SMS bằng sự kiện; `D365LegacyAdapter` dạng CSV cho demo chuyển đổi | Sự kiện xuất hiện đúng 1 lần trong CRM giả lập |
| Dev 3 | Driver PWA online (DISPATCHED/DELIVERED/FAILED + POD, retry idempotent); Prep Queue nối API | E2E driver cơ bản |

### Tuần 3 — Rủi ro, KPI, E2E
| Dev | Việc | Kết quả kiểm chứng |
|---|---|---|
| Dev 1 | `risk_check` job theo luật; DELAY draft → Dispatcher gửi → sự kiện CRM; 4–5 KPI pilot | Test ngưỡng 33/66%, PREDICTED_LATE |
| Dev 2 | Seed kịch bản journey (20 pallet xi măng…); fallback khi CRM down; đối soát D365 → CRM | Báo cáo đối soát |
| Dev 3 | Màn KPI pilot gọn; banner rủi ro + DELAY; Playwright cho kịch bản happy path + A–D | Ảnh chụp/trace E2E thật |

### Tuần 4 — UAT, shadow pilot, go/no-go
- UAT với Dispatcher/Warehouse/Sales/CS (CS trên CRM); shadow pilot 1 tuần trên 2 kho, ~10 cửa hàng.
- Đo baseline vs pilot cho K8; `python tools/harness.py verify` + smoke.
- **Gate G-final**: KPI đạt ngưỡng đã thống nhất, sự kiện CRM không trùng/không mất, không rò PII, không vi phạm bất biến.

### Rủi ro chính

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Nhà cung cấp CRM chưa chốt / API khác giả định | Cao | Adapter trung lập + CSV fallback; 2 dev-week dự phòng |
| Dữ liệu khách D365 bẩn, khớp ID thấp | Trung bình | `customer_xref` + hàng đợi không khớp; không chặn lập kế hoạch |
| Thông báo khách phụ thuộc CRM | Trung bình | Outbox + retry + cảnh báo; lời hứa vẫn đúng trong CFO |
| Bỏ GPS làm ETA kém chính xác | Thấp–TB | ETA theo mốc + tuyến; đo ETA error trong pilot, GPS là ứng viên phase 2 sau DPIA |
| Giảm lịch từng người → công suất thô hơn | Thấp–TB | Vẫn fail-closed; theo dõi preparation error KPI |

### Quyết định cần chủ dự án (để chốt trước Tuần 1)
1. Duyệt danh sách cắt C1–C10 (từng mục) — đặc biệt C1 (GPS), C2 (WMS reserve), C7 (mức chi tiết lịch kho).
2. Duyệt **ngoại lệ ghi ra CRM** (chỉ sự kiện trạng thái đơn) và CRM là nguồn chuẩn khách hàng/consent.
3. CRM chung Nordic hay per-market? (ảnh hưởng cấu hình adapter, không ảnh hưởng engine.)
4. Ai sở hữu template thông báo khách — CRM team hay CFO (CFO chỉ gửi dữ liệu)?
5. Ngưỡng KPI go/no-go và quy mô pilot (C9).

Assumptions: reviewed; new/changed decision IDs: ASM-010…ASM-015 (proposed).
